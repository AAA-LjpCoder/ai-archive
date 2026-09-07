"""鉴权：M1 单用户模式；M2 微信登录（Bearer token）

规则：
1. 带合法 Bearer token → 该 token 对应的真实 openid（生产/开发都认）
2. 无 token / token 无效：
   - dev 模式（app_env=dev 或配置了 single_user_openid）→ 回落 dev_user，方便自测
   - 生产模式 → 401
"""
from fastapi import Header, HTTPException

from app.config import settings
from app.services.token import verify_token


def get_current_user(authorization: str | None = Header(default=None)) -> str:
    """返回当前用户 openid"""
    if authorization and authorization.lower().startswith("bearer "):
        openid = verify_token(authorization[7:].strip())
        if openid:
            return openid
    if settings.app_env == "dev" or settings.single_user_openid:
        return settings.single_user_openid
    raise HTTPException(status_code=401, detail="未登录或登录已过期")
