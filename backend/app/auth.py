"""鉴权：微信登录（Bearer token）

规则：
1. 带合法 Bearer token → 该 token 对应的真实 openid（生产/开发都认）
2. 无 token / token 无效：
   - 明确的非生产环境（app_env ∈ dev/local/test，且配置了回落身份）→ 回落 dev_user，方便自测
   - 其余一切取值（prod / production / PROD / staging / 拼错 / 空）→ 401（fail-closed）
"""
from fastapi import Header, HTTPException

from app.config import settings
from app.services.token import verify_token

# 只有这些明确的本地区才允许免登录回落。
# 其余任何取值一律 fail-closed——避免 APP_ENV 写成 production/PROD/拼错时静默回落，导致生产鉴权失效。
FALLBACK_ENVS = {"dev", "local", "test"}


def auth_fallback_enabled() -> bool:
    """是否启用免登录回落（供启动日志与自测判断）"""
    env = (settings.app_env or "").strip().lower()
    return env in FALLBACK_ENVS and bool((settings.single_user_openid or "").strip())


def get_current_user(authorization: str | None = Header(default=None)) -> str:
    """返回当前用户 openid；生产环境强制有效 token，仅明确的非生产环境回落 dev_user"""
    if authorization and authorization.lower().startswith("bearer "):
        openid = verify_token(authorization[7:].strip())
        if openid:
            return openid
    if auth_fallback_enabled():
        return settings.single_user_openid.strip()
    raise HTTPException(status_code=401, detail="未登录或登录已过期")
