"""额度路由：查询与广告解锁（M3 完整化，先留接口）"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.db import get_db
from app.models import Document, User
from app.schemas import QuotaOut

router = APIRouter(prefix="/api/quota", tags=["quota"])


@router.get("", response_model=QuotaOut)
def get_quota(db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    today = date.today().isoformat()
    user = db.get(User, user_id)
    used = 0
    if user and user.quota_date == today:
        used = user.quota_used or 0
    n_docs = db.scalar(
        select(func.count()).select_from(Document).where(Document.user_id == user_id)
    ) or 0
    storage = db.scalar(
        select(func.coalesce(func.sum(Document.size), 0)).where(Document.user_id == user_id)
    ) or 0
    chunks = db.scalar(
        select(func.count())
        .select_from(__import__("app.models", fromlist=["Chunk"]).Chunk)
        .where(__import__("app.models", fromlist=["Chunk"]).Chunk.user_id == user_id)
    ) or 0
    return QuotaOut(
        date=today, used=used, limit=settings.daily_quota_asks,
        docs=n_docs, docs_limit=settings.max_docs_per_user,
        chunks=chunks,
        storage_bytes=storage, storage_limit=settings.max_storage_mb * 1024 * 1024,
    )


@router.post("/reward")
def reward(
    kind: str = "asks", amount: int = 10,
    db: Session = Depends(get_db), user_id: str = Depends(get_current_user),
):
    """广告解锁入口（M3 接入激励视频后由前端调起，服务端只做入账）。

    说明：MVP 阶段先直接入账；正式版需校验广告完成回调。
    """
    if kind not in ("asks", "doc"):
        raise HTTPException(400, "kind 只支持 asks/doc")
    user = db.get(User, user_id)
    if user is None:
        user = User(openid=user_id)
        db.add(user)
        db.commit()
        db.refresh(user)
    # 简化：asks 直接+amount；doc 额度由前端控制（M3 细化）
    return {"ok": True, "rewarded": amount if kind == "asks" else 0, "note": "M3 接入广告回调后生效"}
