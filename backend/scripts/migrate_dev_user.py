"""一次性迁移：dev_user 数据 → 真实 openid（第 6 步多用户上线时执行）

用法:
    cd backend && .venv/bin/python scripts/migrate_dev_user.py <openid> [--dry-run]

将 dev_user 名下的文档/分块/会话/消息/反馈/额度记录全部过户到目标 openid。
目标 openid 需是空库新用户（避免覆盖）；已存在数据时要求 --force。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select, update  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Chunk,
    Conversation,
    Document,
    Message,
    MessageFeedback,
    QuotaLog,
    User,
)

SRC = "dev_user"

TABLES = [Message, MessageFeedback, Conversation, Chunk, Document, QuotaLog, User]


def main(target: str, dry_run: bool = False, force: bool = False) -> None:
    db: Session = SessionLocal()
    try:
        # 目标用户现状检查
        target_docs = db.scalar(
            select(func.count()).select_from(Document).where(Document.user_id == target)
        ) or 0
        target_convs = db.scalar(
            select(func.count()).select_from(Conversation).where(Conversation.user_id == target)
        ) or 0
        if (target_docs or target_convs) and not force:
            print(f"❌ 目标用户 {target} 已有数据（文档 {target_docs} / 会话 {target_convs}），加 --force 覆盖")
            return

        src_docs = db.scalar(
            select(func.count()).select_from(Document).where(Document.user_id == SRC)
        ) or 0
        src_convs = db.scalar(
            select(func.count()).select_from(Conversation).where(Conversation.user_id == SRC)
        ) or 0
        if src_docs == 0 and src_convs == 0:
            print("ℹ️  dev_user 名下无数据，无需迁移")
            return
        print(f"📦 dev_user → {target}: 文档 {src_docs} / 会话 {src_convs}")
        if dry_run:
            print("（dry-run 模式，未实际执行）")
            return

        # 用户行（额度状态）：目标不存在→直接改名；都存在→保留目标、删 dev_user 行
        src_user = db.get(User, SRC)
        tgt_user = db.get(User, target)
        if src_user is not None and tgt_user is None:
            db.execute(update(User).where(User.openid == SRC).values(openid=target))
        elif src_user is not None and tgt_user is not None:
            db.execute(delete(User).where(User.openid == SRC))
        elif src_user is None and tgt_user is None:
            db.add(User(openid=target))

        for model in (Message, MessageFeedback, Conversation, Chunk, Document, QuotaLog):
            db.execute(update(model).where(model.user_id == SRC).values(user_id=target))
        db.commit()
        print("✅ 迁移完成")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"❌ 迁移失败已回滚: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = set(sys.argv[1:])
    if not args:
        print(__doc__)
        sys.exit(1)
    main(args[0], dry_run="--dry-run" in flags, force="--force" in flags)
