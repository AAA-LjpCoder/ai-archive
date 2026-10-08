"""OCR 服务：智谱 GLM-4V-Flash（OpenAI 兼容），图片/扫描件转文本

用法：
    from app.services.ocr import ocr_image
    text = ocr_image(png_bytes)          # 同步
    text = await ocr_image_async(...)    # 异步

2026-10-08：从硅基流动 Qwen3-VL 迁到智谱免费视觉模型。
glm-4v-flash 输出上限 1024 token，长图/密集页会截断 → 内部**自适应切分**：
当识别结果 finish_reason=length（被截断）时，把图纵向二分（带重叠）再识别，
最后按行合并、去掉重叠处重复的行。
"""
import base64
import io
import logging
from functools import lru_cache

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OCR_MODEL = "glm-4v-flash"          # 智谱免费视觉（输出上限 1024 token）
OCR_FALLBACK_MODEL = "glm-4.6v-flash"  # 主模型连续失败时降级
OCR_RETRY = {OCR_MODEL: 2, OCR_FALLBACK_MODEL: 1}
OCR_MAX_TOKENS = 1024               # glm-4v-flash 限制 [1,1024]
MAX_SPLIT_DEPTH = 6                 # 截断时最多二分 6 层
MIN_BAND_H = 160                    # 单段最小高度（像素），再小不再切
OVERLAP_PX = 120                    # 相邻切片重叠像素

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


def _split_vertical(image_bytes: bytes, mime: str, n: int = 2) -> list[tuple[bytes, str]]:
    """把图纵向均分成 n 段（相邻重叠 OVERLAP_PX）；无法切分时原样返回"""
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = im.size
        if h < MIN_BAND_H * n:
            return [(image_bytes, mime)]
        step = h // n
        parts: list[tuple[bytes, str]] = []
        y = 0
        for i in range(n):
            y2 = h if i == n - 1 else min(h, y + step + OVERLAP_PX)
            crop = im.crop((0, y, w, y2))
            buf = io.BytesIO()
            crop.save(buf, format="PNG")
            parts.append((buf.getvalue(), "image/png"))
            y = y2 - OVERLAP_PX
        return parts
    except Exception as exc:  # noqa: BLE001
        logger.warning("切图失败，按整图 OCR: %s", exc)
        return [(image_bytes, mime)]


def _merge_texts(parts: list[str]) -> str:
    """按行合并，去掉相邻片重叠处重复的行"""
    out: list[str] = []
    for t in parts:
        lines = t.splitlines()
        k = 0
        for j in range(min(len(out), len(lines)), 0, -1):
            if out[-j:] == lines[:j]:
                k = j
                break
        out.extend(lines[k:])
    return "\n".join(out).strip()


def _ocr_once(model: str, image_bytes: bytes, mime: str, timeout: float) -> tuple[str, str | None]:
    """单次调用，返回 (识别文本, finish_reason)"""
    url = f"{settings.embedding_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _data_uri(image_bytes, mime)}},
                    {"type": "text", "text": OCR_PROMPT},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": OCR_MAX_TOKENS,
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            url, json=payload,
            headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
        )
        resp.raise_for_status()
        ch = resp.json()["choices"][0]
        return ch["message"]["content"].strip(), ch.get("finish_reason")


def _ocr_recursive(model: str, image_bytes: bytes, mime: str, timeout: float, depth: int = 0) -> str:
    """识别单张图；若被截断则二分后分别识别再合并"""
    text, fin = _ocr_once(model, image_bytes, mime, timeout)
    if fin == "length" and depth < MAX_SPLIT_DEPTH:
        parts = _split_vertical(image_bytes, mime, n=2)
        if len(parts) > 1:
            logger.info("OCR 命中截断 → 切分（深度 %d）", depth + 1)
            return _merge_texts(
                [_ocr_recursive(model, b, m, timeout, depth + 1) for b, m in parts]
            )
    return text


def ocr_image(image_bytes: bytes, timeout: float = 90.0) -> str:
    """OCR 单张图片：主模型(可自适应切分) → 备用模型降级；全失败抛异常"""
    import time

    if not settings.embedding_api_key:
        raise RuntimeError("未配置 API KEY，无法 OCR")
    mime = _mime_from_bytes(image_bytes)
    last_err: Exception | None = None
    for model, attempts in OCR_RETRY.items():
        for i in range(attempts):
            try:
                text = _ocr_recursive(model, image_bytes, mime, timeout)
                if text.strip():
                    return text
                last_err = RuntimeError(f"{model} 返回空文本")
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning("OCR %s 第 %s 次失败: %s", model, i + 1, exc)
            time.sleep(1.0)
    raise RuntimeError(f"OCR 全部失败: {last_err}") from last_err


async def _ocr_once_async(model: str, image_bytes: bytes, mime: str, timeout: float) -> tuple[str, str | None]:
    url = f"{settings.embedding_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _data_uri(image_bytes, mime)}},
                    {"type": "text", "text": OCR_PROMPT},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": OCR_MAX_TOKENS,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            url, json=payload,
            headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
        )
        resp.raise_for_status()
        ch = resp.json()["choices"][0]
        return ch["message"]["content"].strip(), ch.get("finish_reason")


async def _ocr_recursive_async(model: str, image_bytes: bytes, mime: str, timeout: float, depth: int = 0) -> str:
    text, fin = await _ocr_once_async(model, image_bytes, mime, timeout)
    if fin == "length" and depth < MAX_SPLIT_DEPTH:
        parts = _split_vertical(image_bytes, mime, n=2)
        if len(parts) > 1:
            logger.info("OCR(异步) 命中截断 → 切分（深度 %d）", depth + 1)
            merged = []
            for b, m in parts:
                merged.append(await _ocr_recursive_async(model, b, m, timeout, depth + 1))
            return _merge_texts(merged)
    return text


async def ocr_image_async(image_bytes: bytes, timeout: float = 90.0) -> str:
    """异步 OCR（后端解析任务用）：主模型(可自适应切分) → 备用模型降级"""
    import asyncio

    if not settings.embedding_api_key:
        raise RuntimeError("未配置 API KEY，无法 OCR")
    mime = _mime_from_bytes(image_bytes)
    last_err: Exception | None = None
    for model, attempts in OCR_RETRY.items():
        for i in range(attempts):
            try:
                text = await _ocr_recursive_async(model, image_bytes, mime, timeout)
                if text.strip():
                    return text
                last_err = RuntimeError(f"{model} 返回空文本")
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning("OCR(异步) %s 第 %s 次失败: %s", model, i + 1, exc)
            await asyncio.sleep(1.0)
    raise RuntimeError(f"OCR 全部失败: {last_err}") from last_err


@lru_cache(maxsize=64)
def ocr_image_cached(image_bytes: bytes) -> str:
    """带缓存（同图不重复调用）；大图建议走 async"""
    return ocr_image(image_bytes)
