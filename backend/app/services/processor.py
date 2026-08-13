"""文档异步处理：解析 → 分块 → 向量化 → 入库"""
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Chunk, Document
from app.services.chunker import chunk_parsed
from app.services.embedding import embedding_client
from app.services.parser import parse_file

logger = logging.getLogger(__name__)


def process_document(doc_id: int) -> None:
    """后台任务：处理文档到 ready / failed（独立 session）"""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        _process(db, doc_id)
    finally:
        db.close()


def _process(db: Session, doc_id: int) -> None:
    doc = db.get(Document, doc_id)
    if doc is None:
        return
    try:
        doc.status = "processing"
        db.commit()

        file_path = Path(doc.file_url)
        parsed = parse_file(file_path, doc.type)
        pieces = chunk_parsed(parsed.pages, parsed.blocks)
        if not pieces:
            raise ValueError("文档解析后没有可用的文本内容")

        texts = [p.content for p in pieces]
        embeddings = embedding_client.embed_texts(texts)

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
        db.commit()
        logger.info("doc %s processed, %d chunks", doc_id, len(pieces))
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        doc.status = "failed"
        doc.fail_reason = str(exc)[:500]
        db.commit()
        logger.exception("doc %s failed", doc_id)
