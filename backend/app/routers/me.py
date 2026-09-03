"""个人数据中心：清空全部数据"""
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Chunk, Conversation, Document, Message, QuotaLog, User

router = APIRouter(prefix="/api/me", tags=["me"])


@router.delete("/data")
def clear_all_data(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """一键清空当前用户全部数据。

    删除：原始文件（磁盘物理删）+ 文档/分块/向量 + 会话/消息 + 额度记录，
    并重置当日额度。返回各表删除行数。
    """
    # 1. 先收集物理文件路径（删除前）
    paths = (
        db.execute(select(Document.file_url).where(Document.user_id == user_id))
        .scalars()
        .all()
    )

    # 2. 按依赖序显式清库（不依赖 ORM 级联，杜绝孤儿行）
    stats = {}
    for model in (Message, QuotaLog, Conversation, Chunk, Document):
        res = db.execute(delete(model).where(model.user_id == user_id))
        stats[model.__tablename__] = res.rowcount or 0
    db.commit()

    # 3. 物理删除原始文件
    files_removed = 0
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
            files_removed += 1
        except OSError:
            pass

    # 4. 重置当日额度（用户行可能不存在，不影响）
    db.execute(
        update(User).where(User.openid == user_id).values(quota_date=None, quota_used=0)
    )
    db.commit()

    return {"ok": True, "removed": stats, "files_removed": files_removed}
