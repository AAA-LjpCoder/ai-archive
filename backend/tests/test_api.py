"""API 集成测试：需要 docker compose 起的 pgvector 数据库

跑法：
  cd backend && docker compose up -d
  ./.venv/bin/python -m pytest tests/test_api.py -x
"""
import io
import os

os.environ.setdefault("APP_ENV", "dev")

import pytest
from fastapi.testclient import TestClient

# 关键：先确保数据库连接指向测试库
os.environ["DATABASE_URL"] = (
    os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://aiarchive:aiarchive_dev_pw@localhost:5432/aiarchive",
    )
)

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db():
    from app.db import engine
    from app.models import Chunk, Conversation, Document, Message, QuotaLog, User
    from sqlalchemy import text

    with engine.begin() as conn:
        for t in (Message, QuotaLog, Conversation, Chunk, Document, User):
            conn.execute(text(f'TRUNCATE "{t.__tablename__}" RESTART IDENTITY CASCADE'))
    yield


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_upload_txt_and_process(client, monkeypatch):
    # monkeypatch embedding，避免真实 API key
    import app.services.processor as processor_mod
    from app.services import embedding as emb_mod

    fake_emb = [[0.1] * 4096, [0.2] * 4096]
    monkeypatch.setattr(
        processor_mod.embedding_client, "embed_texts", lambda texts, batch_size=16: fake_emb[: len(texts)]
    )

    content = "# 测试文档\n\n这是第一段内容，关于项目介绍。\n\n这是第二段内容。"
    r = client.post(
        "/api/docs/upload",
        files={"file": ("test.md", io.BytesIO(content.encode("utf-8")), "text/markdown")},
    )
    assert r.status_code == 200, r.text
    doc_id = r.json()["id"]

    # 列表
    r = client.get("/api/docs")
    assert r.status_code == 200
    assert len(r.json()) == 1

    # 手动触发处理（TestClient 下 BackgroundTasks 会执行，但等一轮确保完成）
    import time

    for _ in range(20):
        r = client.get(f"/api/docs/{doc_id}")
        if r.json()["status"] in ("ready", "failed"):
            break
        time.sleep(0.2)
    assert r.json()["status"] == "ready", r.json()
    assert r.json()["chunk_count"] > 0

    # chunks 可查
    r = client.get(f"/api/docs/{doc_id}/chunks")
    assert r.status_code == 200
    assert len(r.json()) == r.json() and len(r.json()) >= 1

    # 删除
    r = client.delete(f"/api/docs/{doc_id}")
    assert r.status_code == 200
    r = client.get("/api/docs")
    assert len(r.json()) == 0


def test_quota(client):
    r = client.get("/api/quota")
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 20
    assert body["docs_limit"] == 10


def test_conversation_and_ask_search_only(client, monkeypatch):
    """仅检索模式：不依赖 LLM key，验证链路"""
    from app.services import embedding as emb_mod
    from app.services import retrieval as retr_mod
    from app.services import processor as processor_mod

    fake_emb = [[0.15] * 4096] * 20
    monkeypatch.setattr(processor_mod.embedding_client, "embed_texts", lambda texts, batch_size=16: fake_emb[: len(texts)])
    monkeypatch.setattr(emb_mod.embedding_client, "embed_one", lambda text: [0.1] * 4096)

    # 准备一个文档
    content = "# 面试知识\n\nRAG 是检索增强生成，用于基于私有文档问答。"
    r = client.post(
        "/api/docs/upload",
        files={"file": ("kb.md", io.BytesIO(content.encode("utf-8")), "text/markdown")},
    )
    doc_id = r.json()["id"]
    import time

    for _ in range(20):
        st = client.get(f"/api/docs/{doc_id}").json()["status"]
        if st in ("ready", "failed"):
            break
        time.sleep(0.2)

    # 建会话
    r = client.post("/api/conversations", json={"mode": "global"})
    assert r.status_code == 200
    conv_id = r.json()["id"]

    # 仅检索提问（不调 LLM）
    r = client.post(
        f"/api/conversations/{conv_id}/ask",
        json={"question": "什么是RAG", "search_only": True},
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    events = r.text
    assert "citations" in events
    assert "done" in events

    # 消息已保存
    r = client.get(f"/api/conversations/{conv_id}/messages")
    msgs = r.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["citations"] is not None
