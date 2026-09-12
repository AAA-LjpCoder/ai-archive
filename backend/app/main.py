"""AI档案室 FastAPI 入口"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text

from app.auth import auth_fallback_enabled
from app.config import settings
from app.db import Base, engine
from app.routers import auth, chat, docs, me, quota

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-archive")


@asynccontextmanager
async def lifespan(app: FastAPI):
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(docs.router)
app.include_router(chat.router)
app.include_router(quota.router)
app.include_router(me.router)


# 启动自检：把鉴权模式打出来，防止 APP_ENV 写错（如 APP_ENV=production / PROD）导致静默回落
if auth_fallback_enabled():
    logger.warning(
        "鉴权回落已启用：APP_ENV=%r → 无 token 的请求将以 %r 身份放行（仅限本地/测试）",
        settings.app_env,
        settings.single_user_openid,
    )
    if settings.wechat_app_secret:
        logger.warning(
            "⚠️ 已配置 WECHAT_APP_SECRET 却仍在回落模式——生产部署请显式设 APP_ENV=prod"
        )
else:
    logger.info("鉴权模式：强制 Bearer token（APP_ENV=%r）", settings.app_env)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}
