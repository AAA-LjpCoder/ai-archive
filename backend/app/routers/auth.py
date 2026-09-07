"""微信登录路由：code → code2session → openid → 签发 token"""
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.db import get_db
from app.models import User
from app.services.token import sign_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    code: str


def code2session(code: str) -> dict:
    """调微信 jscode2session 换 openid"""
    resp = httpx.get(
        "https://api.weixin.qq.com/sns/jscode2session",
        params={
            "appid": settings.wechat_app_id,
            "secret": settings.wechat_app_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    """wx.login 换 token。返回 {token, openid, is_new}"""
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        # 开发环境未配密钥：免登录自测（auth 层 dev 模式自动回落 dev_user）
        raise HTTPException(503, "服务端未配置微信登录（WECHAT_APP_SECRET）")
    if not body.code.strip():
        raise HTTPException(400, "code 不能为空")
    try:
        data = code2session(body.code.strip())
    except httpx.HTTPError:
        raise HTTPException(502, "微信登录服务暂时不可用") from None
    if data.get("errcode"):
        raise HTTPException(401, f"微信登录失败: {data.get('errmsg', data.get('errcode'))}")
    openid = data.get("openid")
    if not openid:
        raise HTTPException(401, "微信登录失败：未获取到 openid")

    user = db.get(User, openid)
    is_new = user is None
    if user is None:
        db.add(User(openid=openid))
        db.commit()
    else:
        db.commit()  # last_active_at 由 onupdate 自动刷新

    return {"token": sign_token(openid), "openid": openid, "is_new": is_new}


@router.get("/me")
def me(user_id: str = Depends(get_current_user)):
    """返回当前登录身份（dev 模式为 dev_user）"""
    return {"openid": user_id}
