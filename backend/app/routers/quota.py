"""额度路由：查询与广告解锁（M3 完整化，先留接口）"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.db import get_db
from app.models import Chunk, Document, QuotaLog, User
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
        select(func.count()).select_from(Chunk).where(Chunk.user_id == user_id)
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

    防刷：单次上限 20、每日最多 10 次（按 quota_logs 计数）；
    正式版需校验广告完成回调（M3）。
    """
    if kind not in ("asks", "doc"):
        raise HTTPException(400, "kind 只支持 asks/doc")
    if amount < 1 or amount > 20:
        raise HTTPException(400, "amount 范围 1-20")
    today = date.today().isoformat()
    today_rewards = db.scalar(
        select(func.count()).select_from(QuotaLog).where(
            QuotaLog.user_id == user_id,
            QuotaLog.action == "ad_reward",
            func.date(QuotaLog.created_at) == today,
        )
    ) or 0
    if today_rewards >= 10:
        raise HTTPException(429, "今日广告解锁次数已达上限")

    user = db.get(User, user_id)
    if user is None:
        user = User(openid=user_id)
        db.add(user)
        db.commit()
        db.refresh(user)
    if kind == "asks":
        user.quota_used = max((user.quota_used or 0) - amount, 0)
        db.add(QuotaLog(user_id=user_id, action="ad_reward", delta=amount))
        db.commit()
        return {"ok": True, "rewarded": amount, "note": "M3 接入广告回调后生效"}
    # kind=doc（文档额度扩容）M3 细化，先不入账
    return {"ok": True, "rewarded": 0, "note": "doc 扩容 M3 实现"}
