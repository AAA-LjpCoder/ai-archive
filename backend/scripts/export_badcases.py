"""导出点踩 badcase 供分析：CSV（Excel 直接打开）+ JSONL（完整 citations）。

用法:
    cd backend
    ./.venv/bin/python scripts/export_badcases.py

输出:
    backend/data/badcases_YYYYMMDD.csv
    backend/data/badcases_YYYYMMDD.jsonl
"""

import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import engine  # noqa: E402
from app.models import Message, MessageFeedback  # noqa: E402


def _fmt_time(value: datetime) -> str:
    if value is None:
        return ""
    return value.isoformat(sep=" ", timespec="seconds")


def _question_for(db: Session, msg: Message) -> str:
    """同会话中，该条回答之前最近的一条用户消息。"""
    return (
        db.execute(
            select(Message.content)
            .where(
                Message.conversation_id == msg.conversation_id,
                Message.role == "user",
                Message.id < msg.id,
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
        .scalar_one_or_none()
        or ""
    )


def main() -> None:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    csv_path = data_dir / f"badcases_{stamp}.csv"
    jsonl_path = data_dir / f"badcases_{stamp}.jsonl"

    db = Session(engine)
    try:
        rows = (
            db.execute(
                select(MessageFeedback, Message)
                .join(Message, MessageFeedback.message_id == Message.id)
                .where(MessageFeedback.value == "dislike")
                .order_by(MessageFeedback.created_at, MessageFeedback.message_id)
            )
            .all()
        )

        headers = ["反馈时间", "user_id", "conversation_id", "对应提问", "回答正文", "引用", "原因"]
        counter: Counter = Counter()
        with csv_path.open("w", encoding="utf-8-sig", newline="") as cf, jsonl_path.open(
            "w", encoding="utf-8"
        ) as jf:
            writer = csv.writer(cf)
            writer.writerow(headers)
            for feedback, msg in rows:
                question = _question_for(db, msg)
                citations = msg.citations or []
                reason = feedback.reason or ""

                counter[feedback.reason or "未填写"] += 1
                writer.writerow(
                    [
                        _fmt_time(feedback.created_at),
                        feedback.user_id,
                        msg.conversation_id,
                        question,
                        msg.content,
                        json.dumps(citations, ensure_ascii=False),
                        reason,
                    ]
                )
                jf.write(
                    json.dumps(
                        {
                            "feedback_time": _fmt_time(feedback.created_at),
                            "user_id": feedback.user_id,
                            "conversation_id": msg.conversation_id,
                            "question": question,
                            "answer": msg.content,
                            "citations": citations,
                            "reason": reason,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        total = len(rows)
        print(f"环境: {settings.app_env}")
        print(f"导出完成: {csv_path}")
        print(f"导出完成: {jsonl_path}")
        print(f"总数: {total}")
        print("按原因分组:")
        for reason, count in sorted(counter.items(), key=lambda item: -item[1]):
            print(f"  {reason}: {count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
