"""文档管理路由：上传/列表/详情/删除"""
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.db import get_db
from app.models import Chunk, Document
from app.schemas import ChunkOut, DocumentOut, DocumentUpdate
from app.services.processor import process_document

router = APIRouter(prefix="/api/docs", tags=["docs"])

ALLOWED_TYPES = {
    "txt", "md", "markdown", "pdf", "docx", "doc",
    "pptx", "xlsx", "xls", "epub", "html", "htm", "csv",
}


@router.post("/upload", response_model=DocumentOut)
async def upload_doc(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    filename: str | None = Form(default=None),  # 原始文件名（微信上传时 file.filename 是临时路径名）
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    raw_name = (filename or file.filename or "").strip()
    ftype = raw_name.rsplit(".", 1)[-1].lower() if "." in raw_name else ""
    if ftype not in ALLOWED_TYPES:
        raise HTTPException(400, f"不支持的文件格式: {ftype}（支持 txt/md/pdf/docx/pptx/xlsx/epub/html/csv）")

    # 数量与容量校验
    n_docs = db.scalar(
        select(func.count()).select_from(Document).where(Document.user_id == user_id)
    )
    if n_docs >= settings.max_docs_per_user:
        raise HTTPException(400, f"文档数量已达上限（{settings.max_docs_per_user} 个），可看广告扩容")

    content = await file.read()
    if len(content) > settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(400, f"文件超过 {settings.max_file_size_mb}MB 限制")

    total_size = db.scalar(
        select(func.coalesce(func.sum(Document.size), 0)).where(Document.user_id == user_id)
    )
    if total_size + len(content) > settings.max_storage_mb * 1024 * 1024:
        raise HTTPException(400, f"总容量超过 {settings.max_storage_mb}MB 限制")

    # 落盘
    upload_dir = settings.upload_dir_resolved
    store_name = f"{user_id}_{uuid.uuid4().hex}.{ftype}"
    file_path = upload_dir / store_name
    file_path.write_bytes(content)

    doc = Document(
        user_id=user_id,
        name=raw_name or store_name,
        type="md" if ftype == "markdown" else ftype,
        size=len(content),
        status="pending",
        file_url=str(file_path),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    background.add_task(process_document, doc.id)
    return doc


@router.get("", response_model=list[DocumentOut])
def list_docs(db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    return (
        db.execute(
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
        )
        .scalars()
        .all()
    )


@router.get("/{doc_id}", response_model=DocumentOut)
def get_doc(doc_id: int, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if doc is None or doc.user_id != user_id:
        raise HTTPException(404, "文档不存在")
    return doc


@router.get("/{doc_id}/chunks", response_model=list[ChunkOut])
def get_doc_chunks(
    doc_id: int, limit: int = 50, db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    doc = db.get(Document, doc_id)
    if doc is None or doc.user_id != user_id:
        raise HTTPException(404, "文档不存在")
    return (
        db.execute(
            select(Chunk).where(Chunk.doc_id == doc_id).order_by(Chunk.seq).limit(limit)
        )
        .scalars()
        .all()
    )


@router.patch("/{doc_id}", response_model=DocumentOut)
def rename_doc(
    doc_id: int,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """重命名文档（仅改名称，不影响类型/索引）"""
    doc = db.get(Document, doc_id)
    if doc is None or doc.user_id != user_id:
        raise HTTPException(404, "文档不存在")
    doc.name = payload.name
    db.commit()
    db.refresh(doc)
    return doc


@router.delete("/{doc_id}")
def delete_doc(doc_id: int, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if doc is None or doc.user_id != user_id:
        raise HTTPException(404, "文档不存在")
    # 级联删除 chunks（ORM cascade）
    db.delete(doc)
    db.commit()
    # 物理删除原文件
    try:
        Path(doc.file_url).unlink(missing_ok=True)
    except OSError:
        pass
    return {"ok": True}
