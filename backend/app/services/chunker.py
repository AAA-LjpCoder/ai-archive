"""结构感知分块：标题层级切分 + 标题上下文前缀 + 代码/表格整体保留（PRD §8.3）"""
import re
from dataclasses import dataclass, field

from app.config import settings

SENT_END = re.compile(r"(?<=[。！？；.!?;])")


@dataclass
class ChunkPiece:
    seq: int
    content: str
    heading: str | None = None       # 最近一级标题
    heading_path: str | None = None  # 完整标题路径（如 "第一章 / 1.1 方法"）
    page_no: int | None = None
    meta: dict = field(default_factory=dict)


def chunk_parsed(pages: list[tuple[int, str]], blocks=None) -> list[ChunkPiece]:
    """结构感知分块。

    pages: [(page_no, text)] —— 兼容旧调用（无 blocks 时退回纯文本启发式）
    blocks: 可选结构化块（parser.ParsedDoc.blocks），优先使用
    """
    from app.services.parser import _plain_to_blocks

    if blocks is None:
        blocks = []
        for page_no, text in pages:
            for b in _plain_to_blocks(text):
                b.page_no = page_no
                blocks.append(b)
    return _chunk_blocks(blocks)


def _chunk_blocks(blocks) -> list[ChunkPiece]:
    size = settings.chunk_size
    pieces: list[ChunkPiece] = []
    path: list[str] = []
    seq = 0
    buf: list[str] = []
    buf_page: int | None = None

    def flush() -> None:
        nonlocal seq
        if not buf:
            return
        text = "\n".join(buf)
        prefix = " / ".join(path)
        for seg in _split_to_size(text, size):
            content = f"{prefix}\n{seg}".strip() if prefix else seg
            pieces.append(
                ChunkPiece(
                    seq=seq,
                    content=content,
                    heading=path[-1] if path else None,
                    heading_path=prefix or None,
                    page_no=buf_page,
                    meta={"type": "text"},
                )
            )
            seq += 1
        buf.clear()

    for block in blocks:
        if block.type == "heading":
            flush()
            _update_path(path, block.level, block.text)
        elif block.type in ("code", "table"):
            # 代码块 / 表格整体保留，不切碎
            flush()
            prefix = " / ".join(path)
            content = f"{prefix}\n{block.text}".strip() if prefix else block.text
            # 超长代码块按行切
            for seg in _split_code(block.text, size):
                c = f"{prefix}\n{seg}".strip() if prefix else seg
                pieces.append(
                    ChunkPiece(
                        seq=seq, content=c,
                        heading=path[-1] if path else None,
                        heading_path=prefix or None,
                        page_no=block.page_no,
                        meta={"type": block.type},
                    )
                )
                seq += 1
        else:
            if buf_page is None:
                buf_page = block.page_no
            buf.append(block.text)

    flush()
    return pieces


def _update_path(path: list[str], level: int, title: str) -> None:
    """按标题层级维护路径栈：level 变化时弹出更深层级"""
    while len(path) >= level:
        path.pop()
    path.append(title)


def _split_to_size(text: str, size: int) -> list[str]:
    """按段落聚合 + 超长段落按句子切，目标 ≤ size 字"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        # 超长段落内部按句子切
        for sent in _split_sentences(para, size):
            if len(sent) > size:
                # 句子仍超长：硬切
                chunks.append(sent[:size])
                chunks.append(sent[size:])
                current = ""
                continue
            if current and len(current) + len(sent) + 1 > size:
                chunks.append(current)
                current = sent
            else:
                current = f"{current}\n{sent}".strip() if current else sent
    if current:
        chunks.append(current)
    return chunks


def _split_sentences(para: str, size: int) -> list[str]:
    """按句末标点切分，再聚合成 ≤ size 的段"""
    sents = [s.strip() for s in SENT_END.split(para) if s.strip()]
    if not sents:
        return [para]
    out: list[str] = []
    cur = ""
    for s in sents:
        if cur and len(cur) + len(s) > size:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur}{s}" if cur else s
    if cur:
        out.append(cur)
    return out


def _split_code(text: str, size: int) -> list[str]:
    """代码块：尽量保持行完整地切分"""
    lines = text.split("\n")
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for line in lines:
        if cur and cur_len + len(line) + 1 > size:
            chunks.append("\n".join(cur))
            cur, cur_len = [], 0
        cur.append(line)
        cur_len += len(line) + 1
    if cur:
        chunks.append("\n".join(cur))
    return chunks
