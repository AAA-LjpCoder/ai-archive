"""Pydantic 请求/响应模型"""
from datetime import datetime

from pydantic import BaseModel, Field


# ---------- 文档 ----------
class DocumentOut(BaseModel):
    id: int
    name: str
    type: str
    size: int
    status: str
    chunk_count: int
    fail_reason: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChunkOut(BaseModel):
    id: int
    seq: int
    content: str
    page_no: int | None = None
    meta: dict | None = None

    model_config = {"from_attributes": True}


# ---------- 会话 ----------
class ConversationOut(BaseModel):
    id: int
    title: str
    mode: str
    doc_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationCreate(BaseModel):
    title: str | None = None
    mode: str = "global"
    doc_id: int | None = None


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    citations: list | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- 问答 ----------
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    search_only: bool = False  # True=仅检索模式，不生成


class Citation(BaseModel):
    doc_id: int
    doc_name: str
    snippet: str
    page_no: int | None = None
    chunk_id: int


# ---------- 额度 ----------
class QuotaOut(BaseModel):
    date: str
    used: int
    limit: int
    docs: int
    docs_limit: int
    storage_bytes: int
    storage_limit: int
