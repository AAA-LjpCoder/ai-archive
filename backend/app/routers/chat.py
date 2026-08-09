"""会话与问答路由：SSE 流式回答 + 引用溯源"""
import json
from collections.abc import AsyncGenerator
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.db import get_db
from app.models import Conversation, Document, Message, User
from app.schemas import AskRequest, ConversationCreate, ConversationOut, MessageOut
from app.services.embedding import embedding_client
from app.services.llm import build_messages, stream_chat
from app.services.retrieval import hybrid_search

router = APIRouter(prefix="/api", tags=["chat"])


# ---------- 会话 ----------
@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    return (
        db.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        )
        .scalars()
        .all()
    )


@router.post("/conversations", response_model=ConversationOut)
def create_conversation(
    body: ConversationCreate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    if body.mode == "doc":
        doc = db.get(Document, body.doc_id or 0)
        if doc is None or doc.user_id != user_id:
            raise HTTPException(404, "文档不存在")
    conv = Conversation(user_id=user_id, title=body.title or "新会话", mode=body.mode, doc_id=body.doc_id)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageOut])
def get_messages(
    conv_id: int, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)
):
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(404, "会话不存在")
    return (
        db.execute(
            select(Message).where(Message.conversation_id == conv_id).order_by(Message.id)
        )
        .scalars()
        .all()
    )


@router.delete("/conversations/{conv_id}")
def delete_conversation(
    conv_id: int, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)
):
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(404, "会话不存在")
    db.delete(conv)
    db.commit()
    return {"ok": True}


# ---------- 问答（SSE） ----------
def _check_quota(db: Session, user_id: str) -> None:
    today = date.today().isoformat()
    user = db.get(User, user_id)
    if user is None:
        user = User(openid=user_id, quota_date=today, quota_used=0)
        db.add(user)
        db.commit()
        db.refresh(user)
    if user.quota_date != today:
        user.quota_date = today
        user.quota_used = 0
        db.commit()
    if user.quota_used >= settings.daily_quota_asks:
        raise HTTPException(429, f"今日问答额度已用完（{settings.daily_quota_asks} 轮），看广告可解锁")


@router.post("/conversations/{conv_id}/ask")
async def ask(
    conv_id: int,
    body: AskRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(404, "会话不存在")
    if not body.search_only:
        _check_quota(db, user_id)

    async def gen() -> AsyncGenerator[str, None]:
        try:
            # 1) 向量化问题
            q_emb = embedding_client.embed_one(body.question)
            # 2) 混合检索
            chunks = hybrid_search(
                db, user_id, body.question, q_emb,
                doc_id=conv.doc_id if conv.mode == "doc" else None,
            )
            citations = [
                {
                    "doc_id": c.doc_id,
                    "doc_name": _doc_name(db, c.doc_id),
                    "snippet": c.content[:200],
                    "page_no": c.page_no,
                    "chunk_id": c.id,
                }
                for c in chunks
            ]
            # 3) 先推引用
            yield f"data: {json.dumps({'type': 'citations', 'data': citations}, ensure_ascii=False)}\n\n"

            if body.search_only or not citations:
                answer = "你的文档中没有相关内容。" if not citations else "（仅检索模式）已找到以上相关片段。"
                yield f"data: {json.dumps({'type': 'delta', 'data': answer}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                _save_pair(db, conv, body.question, answer, citations)
                return

            # 4) LLM 流式生成
            history = _history(db, conv_id)
            messages = build_messages(body.question, citations, history)
            answer_parts: list[str] = []
            async for delta in stream_chat(messages):
                answer_parts.append(delta)
                yield f"data: {json.dumps({'type': 'delta', 'data': delta}, ensure_ascii=False)}\n\n"
            answer = "".join(answer_parts)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            _save_pair(db, conv, body.question, answer, citations)
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'data': str(exc)[:300]}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


def _doc_name(db: Session, doc_id: int) -> str:
    doc = db.get(Document, doc_id)
    return doc.name if doc else f"文档{doc_id}"


def _history(db: Session, conv_id: int) -> list[dict]:
    msgs = (
        db.execute(select(Message).where(Message.conversation_id == conv_id).order_by(Message.id))
        .scalars()
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in msgs]


def _save_pair(db: Session, conv: Conversation, question: str, answer: str, citations: list) -> None:
    db.add(Message(conversation_id=conv.id, user_id=conv.user_id, role="user", content=question))
    db.add(
        Message(
            conversation_id=conv.id, user_id=conv.user_id, role="assistant",
            content=answer, citations=citations or None,
        )
    )
    if conv.title == "新会话":
        conv.title = question[:20]
    # 扣额度
    user = db.get(User, conv.user_id)
    if user is not None:
        user.quota_used = (user.quota_used or 0) + 1
    db.commit()
