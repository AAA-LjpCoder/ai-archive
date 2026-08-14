"""检索质量评测：golden QA → Recall@K / MRR / 关键词覆盖率

用法：
  # 先开 SSH 隧道（连服务器 PG）：
  #   ssh -L 5433:localhost:5432 ubuntu@122.51.27.182
  DATABASE_URL="postgresql+psycopg2://<user>:<pw>@localhost:5433/aiarchive" \
  .venv/bin/python scripts/eval_retrieval.py --pipeline baseline
  .venv/bin/python scripts/eval_retrieval.py --pipeline v2 --rerank
"""
import argparse
import json
import os
import sys
from pathlib import Path

# 允许从 backend/ 目录直接运行
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL", ""))
from app.config import settings  # noqa: E402
from app.services.embedding import embedding_client  # noqa: E402
from app.services import retrieval as retrieval_baseline  # noqa: E402
from app.services import retrieval_v2  # noqa: E402

GOLDEN = Path(__file__).resolve().parent.parent.parent / "eval" / "golden_qa.json"


def load_golden() -> list[dict]:
    with open(GOLDEN, encoding="utf-8") as f:
        return json.load(f)


def chunk_hits(chunks, keywords: list[str]) -> tuple[bool, int]:
    """top-K 内是否出现包含全部关键词的 chunk；以及关键词覆盖数（去重、跨 chunk 累计）"""
    all_text = "\n".join(c.content for c in chunks)
    covered = {kw for kw in keywords if kw in all_text}
    full_hit = any(all(kw in c.content for kw in keywords) for c in chunks)
    return full_hit, len(covered)


def evaluate(pipeline: str, use_rerank: bool, top_k: int, expand: bool = False) -> dict:
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    golden = load_golden()

    rows = []
    n_full = n_partial = 0
    rr_sum = 0.0
    total_kw = 0
    covered_kw = 0

    for item in golden:
        q = item["question"]
        kws = item["keywords"]
        q_emb = embedding_client.embed_one(q)

        if pipeline == "baseline":
            chunks = retrieval_baseline.hybrid_search(db, "dev_user", q, q_emb, top_k=top_k)
        else:
            chunks = retrieval_v2.hybrid_search(
                db, "dev_user", q, q_emb, top_k=top_k,
                use_rerank=use_rerank, expand=expand,
            )

        full_hit, covered = chunk_hits(chunks, kws)
        # 计算首个 full-hit 的 rank（MRR）
        rank = None
        for i, c in enumerate(chunks):
            if all(kw in c.content for kw in kws):
                rank = i + 1
                break
        if rank:
            rr_sum += 1.0 / rank
        if full_hit:
            n_full += 1
        if covered == len(kws):
            n_partial += 1
        total_kw += len(kws)
        covered_kw += covered

        rows.append({
            "id": item["id"], "hit": full_hit, "rank": rank,
            "kw": f"{covered}/{len(kws)}", "q": q[:28],
            "top1": chunks[0].content[:40].replace("\n", " ") if chunks else "",
        })

    n = len(golden)
    recall = {k: None for k in (1, 3, 6, 10)}
    # 按 rank ≤ K 统计 Recall@K
    for k in recall:
        recall[k] = sum(1 for r in rows if r["rank"] and r["rank"] <= k) / n

    result = {
        "pipeline": f"{pipeline}{'+rerank' if use_rerank else ''}{'+expand' if expand else ''}",
        "top_k": top_k,
        "n_questions": n,
        "recall": {f"R@{k}": round(v * 100, 1) for k, v in recall.items()},
        "MRR": round(rr_sum / n, 4),
        "kw_coverage": round(covered_kw / total_kw * 100, 1),
        "rows": rows,
    }
    db.close()
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipeline", choices=["baseline", "v2"], default="baseline")
    ap.add_argument("--rerank", action="store_true", help="v2 管线启用 reranker 精排")
    ap.add_argument("--expand", action="store_true", help="v2 管线启用 LLM 查询改写")
    ap.add_argument("--top-k", type=int, default=10)
    args = ap.parse_args()

    result = evaluate(args.pipeline, args.rerank, args.top_k, args.expand)
    print(f"\n===== {result['pipeline']} (top_k={result['top_k']}) =====")
    print(f"问题数: {result['n_questions']}")
    print("Recall: " + "  ".join(f"{k}={v}%" for k, v in result["recall"].items()))
    print(f"MRR: {result['MRR']}   关键词覆盖率: {result['kw_coverage']}%")
    print("\n--- 明细 ---")
    for r in result["rows"]:
        mark = "✅" if r["hit"] else ("◐" if r["kw"].startswith(("1/",)) else "❌")
        rank = str(r["rank"]) if r["rank"] else "-"
        print(f"{mark} {r['id']:<10} rank={rank:<3} kw={r['kw']:<5} {r['q']}")
        if not r["hit"]:
            print(f"      top1: {r['top1']}")


if __name__ == "__main__":
    main()
