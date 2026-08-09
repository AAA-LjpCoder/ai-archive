"""AI档案室 后端配置"""
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 应用
    app_env: str = "dev"
    app_name: str = "AI档案室"

    # 数据库
    database_url: str = (
        "postgresql+psycopg2://aiarchive:aiarchive_dev_pw@localhost:5432/aiarchive"
    )

    # LLM（OpenAI 兼容）
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"

    # Embedding（OpenAI 兼容）
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"

    # 文件存储
    upload_dir: Path = BASE_DIR / "data" / "uploads"

    # 用户模式
    single_user_openid: str = "dev_user"

    # 业务参数
    max_file_size_mb: int = 20
    max_docs_per_user: int = 10
    max_storage_mb: int = 100
    daily_quota_asks: int = 20
    chunk_size: int = 500      # 小块目标字数
    chunk_overlap: int = 80    # 小块重叠字数
    big_block_size: int = 2000 # 大块上限字数
    retrieval_top_k: int = 20  # 向量/BM25 各自取前 K
    rerank_top_n: int = 6      # MMR 重排后保留 N 个片段
    max_answer_chars: int = 800

    @property
    def upload_dir_resolved(self) -> Path:
        p = self.upload_dir
        if not p.is_absolute():
            p = BASE_DIR / p
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
