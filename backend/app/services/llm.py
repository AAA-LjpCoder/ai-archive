"""LLM 客户端：OpenAI 兼容 chat completions，SSE 流式"""
from collections.abc import AsyncGenerator

import httpx

from app.config import settings

SYSTEM_PROMPT = """你是一个严谨的私人知识库助手。你只能基于用户提供的文档内容回答。
规则：
1. 回答必须来源于文档，关键结论后标注引用 [n]，n 对应提供的片段编号
2. 文档中没有答案时，明确回答"你的文档中没有相关内容"，不要编造
3. 使用中文回答，语言简洁、条理清晰
4. 涉及多个文档时，优先综合，标注各出处
5. 回答总长度不超过约 800 字"""


def build_messages(question: str, snippets: list[dict], history: list[dict] | None = None) -> list[dict]:
    """组装 Prompt（PRD §8.5）：检索片段 + 历史 + 当前问题"""
    snippet_block = "\n\n".join(
        f"[{i + 1}] 《{s['doc_name']}》"
        + (f"第{s['page_no']}页" if s.get("page_no") else "")
        + f": {s['content']}"
        for i, s in enumerate(snippets)
    )
    user_content = f"【检索片段】\n{snippet_block}\n"
    if history:
        hist_lines = []
        for h in history[-6:]:  # 最多携带最近 6 轮
            role = "用户" if h["role"] == "user" else "助手"
            hist_lines.append(f"{role}: {h['content'][:200]}")
        user_content += "\n【历史对话】\n" + "\n".join(hist_lines) + "\n"
    user_content += f"\n【当前问题】\n{question}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


async def stream_chat(messages: list[dict]) -> AsyncGenerator[str, None]:
    """流式调用 LLM，逐段 yield 文本"""
    if not settings.llm_api_key:
        raise RuntimeError("未配置 LLM_API_KEY")
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": True,
        "temperature": 0.3,
        "max_tokens": 1200,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", url, json=payload,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                import json

                try:
                    obj = json.loads(data)
                    delta = obj["choices"][0]["delta"].get("content", "")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta
