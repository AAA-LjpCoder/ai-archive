"""Embedding 客户端（OpenAI 兼容接口，硅基流动 BGE-M3 / 可切任意）"""
import httpx

from app.config import settings


class EmbeddingClient:
    def __init__(self) -> None:
        self.api_key = settings.embedding_api_key
        self.base_url = settings.embedding_base_url.rstrip("/")
        self.model = settings.embedding_model

    def embed_texts(self, texts: list[str], batch_size: int = 16) -> list[list[float]]:
        """批量向量化，自动分片"""
        if not self.api_key:
            raise RuntimeError("未配置 EMBEDDING_API_KEY")
        results: list[list[float]] = []
        with httpx.Client(timeout=60) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                resp = client.post(
                    f"{self.base_url}/embeddings",
                    json={"model": self.model, "input": batch},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()["data"]
                # 按 index 排序保证顺序
                data.sort(key=lambda x: x["index"])
                results.extend(d["embedding"] for d in data)
        return results

    def embed_one(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


embedding_client = EmbeddingClient()
