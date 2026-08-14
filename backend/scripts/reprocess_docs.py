"""全量重处理文档：用当前解析器/分块器重建 chunks（V2.0 检索升级前置）

用法（服务器上执行）：
  cd /home/ubuntu/ai-archive/backend
  .venv/bin/python scripts/reprocess_docs.py [doc_id...]   # 不传则全量
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Chunk, Document  # noqa: E402
from app.services.chunker import chunk_parsed  # noqa: E402
from app.services.embedding import embedding_client  # noqa: E402
from app.services.parser import parse_file  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("reprocess")


def reprocess(doc_id: int | None = None) -> None:
    db = SessionLocal()
    try:
        stmt = select(Document)
        if doc_id:
            stmt = stmt.where(Document.id == doc_id)
        docs = db.execute(stmt).scalars().all()
        log.info("待处理文档 %d 个", len(docs))

        for doc in docs:
            try:
                log.info("[%s] %s (%s) 开始…", doc.id, doc.name, doc.type)
                file_path = Path(doc.file_url)
                if not file_path.exists():
                    raise FileNotFoundError(f"文件不存在: {file_path}")

                parsed = parse_file(file_path, doc.type)
                pieces = chunk_parsed(parsed.pages, parsed.blocks)
                if not pieces:
                    raise ValueError("解析后无文本内容")

                texts = [p.content for p in pieces]
                embeddings = embedding_client.embed_texts(texts, batch_size=8)

                # 删旧建新（同一事务）
                db.execute(delete(Chunk).where(Chunk.doc_id == doc.id))
                for piece, emb in zip(pieces, embeddings):
                    meta: dict = {}
                    if piece.heading_path:
                        meta["heading"] = piece.heading_path
                    elif piece.heading:
                        meta["heading"] = piece.heading
                    meta["type"] = piece.meta.get("type", "text")
                    db.add(
                        Chunk(
                            doc_id=doc.id,
                            user_id=doc.user_id,
                            seq=piece.seq,
                            content=piece.content,
                            embedding=emb,
                            page_no=piece.page_no,
                            meta=meta if meta else None,
                        )
                    )
                doc.chunk_count = len(pieces)
                doc.status = "ready"
                doc.fail_reason = None
                db.commit()
                log.info("[%s] ✅ %d chunks", doc.id, len(pieces))
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                doc.status = "failed"
                doc.fail_reason = str(exc)[:500]
                db.commit()
                log.exception("[%s] ❌ %s", doc.id, exc)
    finally:
        db.close()


if __name__ == "__main__":
    ids = [int(x) for x in sys.argv[1:]] or [None]
    for did in ids:
        reprocess(did)
    log.info("完成")
