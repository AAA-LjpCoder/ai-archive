"""鉴权：M1 单用户模式；M2 接入微信登录"""
from fastapi import Header, HTTPException

from app.config import settings


def get_current_user(x_user_id: str | None = Header(default=None)) -> str:
    """返回当前用户 openid。

    M1 单用户模式：忽略请求头，固定 dev_user（自用）。
    M2 多用户模式：x_user_id 由微信登录换取，未带则 401。
    """
    if settings.app_env == "dev" or settings.single_user_openid:
        return settings.single_user_openid
    if not x_user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return x_user_id
