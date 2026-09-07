"""无状态登录 token：HMAC-SHA256 签名（payload.base64url + sig.base64url）

不引入 JWT 依赖，够用且可控：
  token = b64url(payload) + "." + b64url(hmac_sha256(secret, payload))
payload = {"openid": ..., "exp": <epoch秒>}
"""
import base64
import hashlib
import hmac
import json
import time

from app.config import settings


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64url(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload_b64: str) -> str:
    mac = hmac.new(
        settings.token_secret.encode(), payload_b64.encode(), hashlib.sha256
    )
    return _b64url(mac.digest())


def sign_token(openid: str) -> str:
    payload = {"openid": openid, "exp": int(time.time()) + settings.token_ttl_days * 86400}
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_token(token: str) -> str | None:
    """校验并返回 openid；无效/过期返回 None"""
    try:
        payload_b64, sig = token.split(".", 1)
        if not hmac.compare_digest(_sign(payload_b64), sig):
            return None
        payload = json.loads(_unb64url(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        openid = payload.get("openid")
        return openid if isinstance(openid, str) and openid else None
    except Exception:  # noqa: BLE001 任何解析失败都视为无效
        return None
