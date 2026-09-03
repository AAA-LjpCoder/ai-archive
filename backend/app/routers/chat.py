"""会话与问答路由：SSE 流式回答 + 引用溯源"""
import json
from collections.abc import AsyncGenerator
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.db import get_db
from app.models import Conversation, Document, Message, MessageFeedback, User
from app.schemas import (
    AskRequest,
    ConversationCreate,
    ConversationOut,
    FeedbackBody,
    MessageOut,
)
from app.services.embedding import embedding_client
from app.services.llm import build_messages, stream_chat
from app.services.retrieval_v2 import hybrid_search  # V2 管线：全库BM25 + reranker 精排

router = APIRouter(prefix="/api", tags=["chat"])


# ---------- 会话 ----------
@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    q: str | None = None,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """会话列表；q 非空时按标题或用户提问内容模糊搜索"""
    stmt = select(Conversation).where(Conversation.user_id == user_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Conversation.title.ilike(like),
                exists().where(
                    Message.conversation_id == Conversation.id,
                    Message.user_id == user_id,
                    Message.role == "user",
                    Message.content.ilike(like),
                ),
            )
        )
    return (
        db.execute(stmt.order_by(Conversation.updated_at.desc()))
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
    msgs = (
        db.execute(
            select(Message).where(Message.conversation_id == conv_id).order_by(Message.id)
        )
        .scalars()
        .all()
    )
    # 附加当前用户对每条消息的反馈（瞬态属性，非表字段）
    if msgs:
        fb_rows = (
            db.execute(
                select(MessageFeedback).where(
                    MessageFeedback.user_id == user_id,
                    MessageFeedback.message_id.in_([m.id for m in msgs]),
                )
            )
            .scalars()
            .all()
        )
        fb_map = {f.message_id: f.value for f in fb_rows}
        for m in msgs:
            m.feedback = fb_map.get(m.id)
    return msgs


# ---------- 消息反馈（点赞/点踩） ----------
@router.put("/messages/{message_id}/feedback")
def set_feedback(
    message_id: int,
    body: FeedbackBody,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    msg = db.get(Message, message_id)
    if msg is None or msg.user_id != user_id:
        raise HTTPException(404, "消息不存在")
    row = db.execute(
        select(MessageFeedback).where(
            MessageFeedback.message_id == message_id,
            MessageFeedback.user_id == user_id,
        )
    ).scalar_one_or_none()
    if body.value is None:
        if row is not None:
            db.delete(row)
            db.commit()
        return {"ok": True, "value": None}
    if row is None:
        db.add(MessageFeedback(message_id=message_id, user_id=user_id, value=body.value))
    else:
        row.value = body.value
    db.commit()
    return {"ok": True, "value": body.value}


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


async def _ask_stream(
    db: Session,
    conv_id: int,
    user_id: str,
    question: str,
    search_only: bool,
    add_user_msg: bool = True,
    history_cut: int = 0,
) -> AsyncGenerator[str, None]:
    """问答 SSE 事件流（ask 与 regenerate 共用）。

    add_user_msg: 是否把当前问题落库为用户消息（regenerate 复用已有提问时传 False）
    history_cut: 从历史末尾丢弃 N 条（regenerate 剔除与当前问题重复的提问）
    """
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.user_id != user_id:
        yield f"data: {json.dumps({'type': 'error', 'data': '会话不存在'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return
    # StreamingResponse 生成器延迟执行：提前提取为局部变量，避免 detached 实例问题
    conv_id_v, conv_user_id_v, conv_title_v = conv.id, conv.user_id, conv.title
    conv_mode_v, conv_doc_id_v = conv.mode, conv.doc_id

    try:
        # 1) 向量化问题
        q_emb = embedding_client.embed_one(question)
        # 2) 混合检索
        chunks = hybrid_search(
            db, user_id, question, q_emb,
            doc_id=conv_doc_id_v if conv_mode_v == "doc" else None,
        )
        citations = [
            {
                "doc_id": c.doc_id,
                "doc_name": _doc_name(db, c.doc_id),
                "content": c.content,  # 完整内容（LLM prompt 用）
                "snippet": c.content[:200],  # 截断片段（前端展示用）
                "page_no": c.page_no,
                "heading": (c.meta or {}).get("heading"),  # 标题路径（溯源展示）
                "chunk_id": c.id,
            }
            for c in chunks
        ]
        # 3) 先推引用
        yield f"data: {json.dumps({'type': 'citations', 'data': citations}, ensure_ascii=False)}\n\n"

        if search_only or not citations:
            answer = "你的文档中没有相关内容。" if not citations else "（仅检索模式）已找到以上相关片段。"
            yield f"data: {json.dumps({'type': 'delta', 'data': answer}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            _save_pair(
                db, conv_id_v, conv_user_id_v, conv_title_v,
                question, answer, citations, add_user_msg=add_user_msg,
            )
            return

        # 4) LLM 流式生成
        history = _history(db, conv_id_v)
        if history_cut:
            history = history[:-history_cut]
        messages = build_messages(question, citations, history)
        answer_parts: list[str] = []
        async for delta in stream_chat(messages):
            answer_parts.append(delta)
            yield f"data: {json.dumps({'type': 'delta', 'data': delta}, ensure_ascii=False)}\n\n"
        answer = "".join(answer_parts)
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        _save_pair(
            db, conv_id_v, conv_user_id_v, conv_title_v,
            question, answer, citations, add_user_msg=add_user_msg,
        )
    except Exception as exc:  # noqa: BLE001
        yield f"data: {json.dumps({'type': 'error', 'data': str(exc)[:300]}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"


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
    return StreamingResponse(
        _ask_stream(db, conv.id, user_id, body.question, body.search_only),
        media_type="text/event-stream",
    )


@router.post("/conversations/{conv_id}/regenerate")
async def regenerate(
    conv_id: int,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """重新生成最后一条 AI 回答：删除旧回答 → 以同一提问重跑检索+生成（SSE）"""
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(404, "会话不存在")
    msgs = (
        db.execute(select(Message).where(Message.conversation_id == conv_id).order_by(Message.id))
        .scalars()
        .all()
    )
    if not msgs or msgs[-1].role != "assistant":
        raise HTTPException(400, "当前没有可重新生成的回答")
    # 向前找这条回答对应的提问
    qmsg = next((m for m in reversed(msgs[:-1]) if m.role == "user"), None)
    if qmsg is None:
        raise HTTPException(400, "找不到对应的提问")
    question = qmsg.content
    # 删除旧回答（其反馈随外键级联删除），提问保留
    db.delete(msgs[-1])
    db.commit()
    _check_quota(db, user_id)
    # 剔除从该提问起的历史（避免与当前问题重复）；正常情况只剔除提问本身 1 条
    remain_ids = (
        db.execute(select(Message.id).where(Message.conversation_id == conv_id))
        .scalars()
        .all()
    )
    history_cut = sum(1 for mid in remain_ids if mid >= qmsg.id)
    return StreamingResponse(
        _ask_stream(
            db, conv.id, user_id, question,
            search_only=False, add_user_msg=False, history_cut=history_cut,
        ),
        media_type="text/event-stream",
    )


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


def _save_pair(db: Session, conv_id: int, conv_user_id: str, conv_title: str, question: str, answer: str, citations: list, add_user_msg: bool = True) -> None:
    if add_user_msg:
        db.add(Message(conversation_id=conv_id, user_id=conv_user_id, role="user", content=question))
    db.add(
        Message(
            conversation_id=conv_id, user_id=conv_user_id, role="assistant",
            content=answer, citations=citations or None,
        )
    )
    if conv_title == "新会话":
        c = db.get(Conversation, conv_id)
        if c is not None:
            c.title = question[:20]
    # 扣额度
    user = db.get(User, conv_user_id)
    if user is not None:
        user.quota_used = (user.quota_used or 0) + 1
    db.commit()
