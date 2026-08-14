"""检索管线 v2：全库 BM25 + 大候选池 + RRF + Reranker 精排 + 可选查询改写（V2.0 极致版）

相对 v1 的改进：
1. BM25 全库独立检索（v1 只在向量 top20 候选池内算，idf 失真、召回受限）
2. 候选池扩大：向量 top60 ∪ BM25 top60
3. bge-reranker-v2-m3 精排（硅基流动 rerank API），RRF top30 → rerank → top6
4. 可选 LLM 查询改写（HyDE-lite）：多路检索再 RRF 融合
5. 失败兜底：reranker/改写挂掉时回退
"""
import json
import math
import time

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Chunk
from app.services.embedding import embedding_client

RRF_K = 60.0
_CORPUS_CACHE: dict[str, tuple[int, list[tuple[int, str]]]] = {}


def _get_corpus(db: Session, user_id: str) -> list[tuple[int, str]]:
    """全库 chunk (id, content) 缓存（按 user_id + chunk 数失效）"""
    n = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.user_id == user_id))
    cached = _CORPUS_CACHE.get(user_id)
    if cached and cached[0] == n:
        return cached[1]
    rows = db.execute(
        select(Chunk.id, Chunk.content).where(Chunk.user_id == user_id)
    ).all()
    corpus = [(r[0], r[1]) for r in rows]
    _CORPUS_CACHE[user_id] = (n, corpus)
    return corpus


def _bm25_scores(query_terms: list[str], corpus: list[tuple[int, str]]) -> dict[int, float]:
    """全库 BM25：df/idf 基于整个语料统计"""
    n_docs = max(len(corpus), 1)
    avg_len = sum(len(t) for _, t in corpus) / n_docs
    df: dict[str, int] = {}
    for _, text in corpus:
        seen = set()
        for term in query_terms:
            if term in text and term not in seen:
                seen.add(term)
                df[term] = df.get(term, 0) + 1
    idf = {t: math.log(1 + (n_docs - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    scores: dict[int, float] = {}
    k1, b = 1.5, 0.75
    for cid, text in corpus:
        doc_len = len(text)
        s = 0.0
        for term in query_terms:
            tf = text.count(term)
            if tf == 0 or term not in idf:
                continue
            denom = tf + k1 * (1 - b + b * doc_len / max(avg_len, 1))
            s += idf[term] * tf * (k1 + 1) / denom
        if s > 0:
            scores[cid] = s
    return scores


def _rrf_merge(*ranked_lists: list[int]) -> dict[int, float]:
    rrf: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, cid in enumerate(ranked):
            rrf[cid] = rrf.get(cid, 0) + 1.0 / (RRF_K + rank + 1)
    return rrf


def _mmr_rerank(chunks: list[Chunk], scores: list[float], top_n: int,
                lambda_: float = 0.7) -> list[int]:
    """MMR 多样性重排，返回选中下标（仅兜底用）"""
    n = len(chunks)
    if n <= 1:
        return list(range(n))
    embs = [np.asarray(c.embedding, dtype=np.float32) for c in chunks]
    mat = np.stack(embs)
    norm = np.linalg.norm(mat, axis=1, keepdims=True)
    sims = (mat @ mat.T) / (norm @ norm.T + 1e-9)

    picked: list[int] = []
    remaining = set(range(n))
    while len(picked) < min(top_n, n):
        best, best_val = -1, -1e9
        for i in remaining:
            diversity = max(sims[i, j] for j in picked) if picked else 0.0
            val = lambda_ * scores[i] - (1 - lambda_) * diversity
            if val > best_val:
                best_val, best = val, i
        picked.append(best)
        remaining.discard(best)
    return picked


def _rerank_api(query: str, documents: list[str], top_n: int) -> list[int] | None:
    """bge-reranker-v2-m3（硅基流动），返回按相关性排序的 documents 下标"""
    import httpx

    api_key = settings.embedding_api_key  # 复用硅基流动 key
    if not api_key:
        return None
    url = f"{settings.embedding_base_url.rstrip('/')}/rerank"
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                url,
                json={"model": "BAAI/bge-reranker-v2-m3", "query": query,
                      "documents": documents, "top_n": top_n},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        ordered = sorted(results, key=lambda r: r["relevance_score"], reverse=True)
        return [r["index"] for r in ordered]
    except Exception:  # noqa: BLE001 reranker 故障兜底
        return None


def _query_terms(query: str) -> list[str]:
    """jieba 分词 + 过滤：保留长度>1 的词，以及有意义的单字（非高频虚词）"""
    import jieba

    stop1 = set("的了是和在就有被把让给于与及或而但也都很还")
    terms: list[str] = []
    for w in jieba.lcut(query):
        w = w.strip()
        if not w:
            continue
        if len(w) == 1:
            if w in stop1 or not w.isalpha():
                continue
        terms.append(w)
    return terms


def _expand_queries(question: str) -> list[str]:
    """LLM 查询改写：生成 2 条检索友好变体（HyDE-lite），失败时退回原问题"""
    import httpx

    api_key = settings.llm_api_key
    if not api_key:
        return [question]
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    prompt = (
        "你是检索专家。把下面的问题改写成 2 条更适合关键词/向量检索的查询，"
        "保留数字、专有名词、缩写；只输出 JSON 数组，不要其他文字。\n问题：" + question
    )
    try:
        with httpx.Client(timeout=25) as client:
            resp = client.post(
                url,
                json={"model": settings.llm_model, "messages": [
                    {"role": "system", "content": "只输出 JSON 数组"},
                    {"role": "user", "content": prompt},
                ], "temperature": 0.2, "max_tokens": 200},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        arr = json.loads(content.strip().strip("`").removeprefix("json"))
        variants = [str(x) for x in arr if isinstance(x, str) and x.strip()][:2]
        return [question] + variants
    except Exception:  # noqa: BLE001
        return [question]


def _retrieve_one(db: Session, user_id: str, query: str, query_embedding: list[float],
                  doc_id: int | None, candidate_pool: int) -> tuple[dict[int, float], set[int]]:
    """单路检索：向量 + 全库 BM25 → RRF"""
    corpus = _get_corpus(db, user_id)
    if doc_id is not None:
        cid2doc = dict(db.execute(
            select(Chunk.id, Chunk.doc_id).where(Chunk.user_id == user_id)
        ).all())
        corpus = [(cid, t) for cid, t in corpus if cid2doc.get(cid) == doc_id]

    vec_stmt = (
        select(Chunk, Chunk.embedding.cosine_distance(query_embedding).label("dist"))
        .where(Chunk.user_id == user_id, Chunk.embedding.isnot(None))
        .order_by("dist")
        .limit(candidate_pool)
    )
    if doc_id is not None:
        vec_stmt = vec_stmt.where(Chunk.doc_id == doc_id)
    vec_ordered = [r[0].id for r in db.execute(vec_stmt).all()]

    terms = _query_terms(query)
    bm_scores = _bm25_scores(terms, corpus) if terms else {}
    bm_ordered = sorted(bm_scores, key=bm_scores.get, reverse=True)[:candidate_pool]

    rrf = _rrf_merge(vec_ordered, bm_ordered)
    return rrf, set(vec_ordered) | set(bm_ordered)


def _query_variants(query: str) -> list[str]:
    """规则式查询变体：日期归一化（3月6号→3.6）、数字单位去空格（20 轮→20轮）"""
    import re

    variants = [query]
    m = re.search(r"(\d+)\s*月\s*(\d+)\s*[号日]", query)
    if m:
        variants.append(f"{m.group(1)}.{m.group(2)}")
    if re.search(r"\d+\s+[轮个张条页元次]", query):
        variants.append(re.sub(r"(\d)\s+([轮个张条页元次])", r"\1\2", query))
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def hybrid_search(db: Session, user_id: str, query: str, query_embedding: list[float],
                  doc_id: int | None = None, top_k: int | None = None,
                  use_rerank: bool = True, expand: bool = False) -> list[Chunk]:
    """v2 混合检索入口"""
    t0 = time.time()
    candidate_pool = settings.retrieval_candidate_pool  # 60
    rerank_input_n = settings.rerank_input_n            # 30
    rerank_n = settings.rerank_top_n                    # 6

    # ---- 查询改写（可选）：规则变体 + LLM 改写 → 多路检索 → RRF 再融合 ----
    queries = _query_variants(query)
    if expand:
        queries += _expand_queries(query)
    all_rrf: dict[int, float] = {}
    all_ids: set[int] = set()
    for i, q in enumerate(queries):
        q_emb = query_embedding if i == 0 else embedding_client.embed_one(q)
        rrf, ids = _retrieve_one(db, user_id, q, q_emb, doc_id, candidate_pool)
        for cid, score in rrf.items():
            all_rrf[cid] = all_rrf.get(cid, 0) + score
        all_ids.update(ids)

    rrf_ordered = sorted(all_rrf, key=all_rrf.get, reverse=True)[:rerank_input_n]
    chunks = list(db.execute(select(Chunk).where(Chunk.id.in_(rrf_ordered))).scalars())
    pos = {cid: rank for rank, cid in enumerate(rrf_ordered)}
    chunks.sort(key=lambda c: pos[c.id])

    # ---- 精排：reranker（默认，相关性优先） ----
    if use_rerank and len(chunks) > 1:
        docs = [c.content for c in chunks]
        dyn_n = rerank_n + (1 if len(query) > 60 else 0)  # 长问题多给 1 个片段
        idx = _rerank_api(query, docs, min(dyn_n, len(docs)))
        if idx is not None:
            chunks = [chunks[i] for i in idx]
    elif len(chunks) > 1:
        # 兜底：RRF 分数 + MMR 多样性
        scores = [all_rrf.get(c.id, 0.0) for c in chunks]
        picked = _mmr_rerank(chunks, scores, rerank_n)
        chunks = [chunks[i] for i in picked]

    return chunks[:top_k] if top_k else chunks[:rerank_n]
