"""层级分块：按标题切大块 → 按句群切小块（PRD §8.3）"""
import re
from dataclasses import dataclass

from app.config import settings

HEADING_RE = re.compile(r"^(#{1,6}\s+.*|第[一二三四五六七八九十百千\d]+[章节部分].*|[\d]+[.、]\s*\S.*)$")


@dataclass
class ChunkPiece:
    seq: int
    content: str
    heading: str | None = None
    page_no: int | None = None


def chunk_parsed(pages: list[tuple[int, str]]) -> list[ChunkPiece]:
    """pages: [(page_no, text)] → 层级分块结果"""
    # 1) 按页收集，识别标题
    big_blocks: list[dict] = []  # {heading, text, page}
    current: dict | None = None

    for page_no, text in pages:
        lines = text.split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if HEADING_RE.match(stripped) and len(stripped) <= 60:
                if current:
                    big_blocks.append(current)
                current = {"heading": stripped, "text": "", "page": page_no}
            else:
                if current is None:
                    current = {"heading": None, "text": "", "page": page_no}
                current["text"] += stripped + "\n"

    if current:
        big_blocks.append(current)

    # 2) 大块内按句群切小块
    pieces: list[ChunkPiece] = []
    seq = 0
    for block in big_blocks:
        text = block["text"].strip()
        if not text:
            continue
        for small in _split_small(text, settings.chunk_size, settings.chunk_overlap):
            pieces.append(
                ChunkPiece(seq=seq, content=small, heading=block["heading"], page_no=block["page"])
            )
            seq += 1
    return pieces


def _split_small(text: str, size: int, overlap: int) -> list[str]:
    """按段落/句群切分，目标 size 字，重叠 overlap 字"""
    # 先按空行分段
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        # 超长段落内部再切
        while len(para) > size:
            cut = para[:size]
            # 尽量在句号处断
            m = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"), cut.rfind("；"))
            if m > size * 0.5:
                cut, para = cut[: m + 1], para[m + 1 :]
            else:
                para = para[size:]
            chunks.append(cut.strip())
        if len(current) + len(para) <= size:
            current = (current + "\n" + para).strip() if current else para
        else:
            if current:
                chunks.append(current)
            current = para
    if current:
        chunks.append(current)

    # 重叠处理：对相邻块做尾部拼接（保持上下文连续）
    merged: list[str] = []
    for c in chunks:
        if not merged:
            merged.append(c)
            continue
        if overlap > 0 and len(merged[-1]) > overlap:
            merged.append(merged[-1][-overlap:] + c)
        else:
            merged.append(c)
    return merged
