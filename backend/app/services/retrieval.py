"""混合检索：向量 + BM25 + RRF 融合 + MMR 重排（PRD §8.4）"""
import math

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Chunk


def _bm25_score(query_terms: list[str], text: str, avg_len: float, doc_len: float,
                idf: dict[str, float], k1: float = 1.5, b: float = 0.75) -> float:
    score = 0.0
    for term in query_terms:
        tf = text.count(term)
        if tf == 0 or term not in idf:
            continue
        denom = tf + k1 * (1 - b + b * doc_len / max(avg_len, 1))
        score += idf[term] * tf * (k1 + 1) / denom
    return score


def _mmr_rerank(scores: list[float], sims: np.ndarray, top_n: int,
                lambda_: float = 0.7) -> list[int]:
    """MMR: 兼顾相关性与多样性"""
    n = len(scores)
    picked: list[int] = []
    remaining = set(range(n))
    while len(picked) < min(top_n, n):
        best = -1
        best_val = -1e9
        for i in remaining:
            diversity = 0.0
            if picked:
                diversity = max(sims[i, j] for j in picked)
            val = lambda_ * scores[i] - (1 - lambda_) * diversity
            if val > best_val:
                best_val = val
                best = i
        picked.append(best)
        remaining.discard(best)
    return picked


def hybrid_search(db: Session, user_id: str, query: str, query_embedding: list[float],
                  doc_id: int | None = None, top_k: int | None = None,
                  rerank_n: int | None = None) -> list[Chunk]:
    """返回重排后的 Chunk 列表（按相关性排序）"""
    top_k = top_k or settings.retrieval_top_k
    rerank_n = rerank_n or settings.rerank_top_n

    # ---- 向量检索（pgvector cosine）----
    vec_stmt = (
        select(Chunk, Chunk.embedding.cosine_distance(query_embedding).label("dist"))
        .where(Chunk.user_id == user_id, Chunk.embedding.isnot(None))
        .order_by("dist")
        .limit(top_k)
    )
    if doc_id is not None:
        vec_stmt = vec_stmt.where(Chunk.doc_id == doc_id)
    vec_rows = db.execute(vec_stmt).all()
    vec_chunks = [r[0] for r in vec_rows]

    # ---- BM25 检索（jieba 分词，Python 实现）----
    import jieba

    doc_texts = [c.content for c in vec_chunks]
    # 候选池：向量 top_k 的并集上做 BM25（MVP 够用；大库可扩到全量）
    query_terms = [w for w in jieba.lcut(query) if w.strip() and len(w.strip()) > 1]
    avg_len = np.mean([len(t) for t in doc_texts]) if doc_texts else 1.0
    df: dict[str, int] = {}
    for t in doc_texts:
        for term in set(query_terms):
            if term in t:
                df[term] = df.get(term, 0) + 1
    n_docs = max(len(doc_texts), 1)
    idf = {term: math.log(1 + (n_docs - f + 0.5) / (f + 0.5)) for term, f in df.items()}
    bm_scores = [
        _bm25_score(query_terms, t, avg_len, len(t), idf) for t in doc_texts
    ]

    # ---- RRF 融合 ----
    rrf_k = 60.0
    rrf: dict[int, float] = {}
    for rank, chunk in enumerate(vec_chunks):
        rrf[chunk.id] = rrf.get(chunk.id, 0) + 1.0 / (rrf_k + rank + 1)
    # BM25 排名（在向量候选内）
    bm_ranked = sorted(range(len(vec_chunks)), key=lambda i: bm_scores[i], reverse=True)
    for rank, i in enumerate(bm_ranked):
        cid = vec_chunks[i].id
        rrf[cid] = rrf.get(cid, 0) + 1.0 / (rrf_k + rank + 1)

    # 排序
    ordered = sorted(vec_chunks, key=lambda c: rrf.get(c.id, 0), reverse=True)
    ordered = [c for c in ordered if rrf.get(c.id, 0) > 0][: top_k]

    # ---- MMR 重排 ----
    if len(ordered) <= 1:
        return ordered
    texts = [c.content for c in ordered]
    # 用 embedding 相似度矩阵（余弦）
    embs = []
    for c in ordered:
        embs.append(np.asarray(c.embedding, dtype=np.float32))
    mat = np.stack(embs)
    norm = np.linalg.norm(mat, axis=1, keepdims=True)
    sims = (mat @ mat.T) / (norm @ norm.T + 1e-9)
    rrf_scores = [rrf.get(c.id, 0) for c in ordered]
    picked_idx = _mmr_rerank(rrf_scores, sims, rerank_n)
    return [ordered[i] for i in picked_idx]
