"""OCR 服务：硅基流动 Qwen-VL（OpenAI 兼容），图片/扫描件转文本

用法：
    from app.services.ocr import ocr_image
    text = ocr_image(png_bytes)          # 同步
    text = await ocr_image_async(...)    # 异步
"""
import base64
import logging
from functools import lru_cache

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# 2026-09-07 实测：PaddleOCR-VL-1.5 在硅基流动输出乱码、DeepSeek-OCR 空响应；
# Qwen3-VL-8B 识别准确（中英文文档/截图）→ 定为主模型
OCR_MODEL = "Qwen/Qwen3-VL-8B-Instruct"
OCR_PROMPT = (
    "你是文档 OCR 引擎。请完整识别图片中的所有文字内容，"
    "保留原有段落结构、标题层级和表格结构（表格用 | 分隔单元格）。"
    "只输出识别到的文字，不要任何解释。"
)


def _data_uri(image_bytes: bytes, mime: str = "image/png") -> str:
    b64 = base64.b64encode(image_bytes).decode()
    return f"data:{mime};base64,{b64}"


def _mime_from_bytes(image_bytes: bytes) -> str:
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:4] == b"GIF8":
        return "image/gif"
    if image_bytes[:2] == b"BM":
        return "image/bmp"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def ocr_image(image_bytes: bytes, timeout: float = 60.0) -> str:
    """同步 OCR 单张图片，返回识别文本；失败抛异常由调用方兜底"""
    if not settings.embedding_api_key:
        raise RuntimeError("未配置 API KEY，无法 OCR")
    url = f"{settings.embedding_base_url.rstrip('/')}/chat/completions"  # 同硅基流动
    payload = {
        "model": OCR_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": _data_uri(image_bytes, _mime_from_bytes(image_bytes))}},
                    {"type": "text", "text": OCR_PROMPT},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            url, json=payload,
            headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


async def ocr_image_async(image_bytes: bytes, timeout: float = 60.0) -> str:
    """异步 OCR（后端解析任务用）"""
    if not settings.embedding_api_key:
        raise RuntimeError("未配置 API KEY，无法 OCR")
    url = f"{settings.embedding_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": OCR_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": _data_uri(image_bytes, _mime_from_bytes(image_bytes))}},
                    {"type": "text", "text": OCR_PROMPT},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            url, json=payload,
            headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


@lru_cache(maxsize=64)
def ocr_image_cached(image_bytes: bytes) -> str:
    """带缓存（同图不重复调用）；大图建议走 async"""
    return ocr_image(image_bytes)
