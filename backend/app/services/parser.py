"""文档解析：txt / md / pdf（v2 加 docx/OCR）"""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedDoc:
    """解析结果：带页码的文本片段列表"""
    pages: list[tuple[int, str]] = field(default_factory=list)  # [(page_no, text)]

    @property
    def full_text(self) -> str:
        return "\n".join(t for _, t in self.pages)


def parse_file(path: Path, ftype: str) -> ParsedDoc:
    ftype = ftype.lower().lstrip(".")
    if ftype in ("txt", "md", "markdown"):
        return _parse_text(path)
    if ftype == "pdf":
        return _parse_pdf(path)
    if ftype in ("docx", "doc"):
        return _parse_docx(path)
    raise ValueError(f"不支持的文件格式: {ftype}")


def _parse_text(path: Path) -> ParsedDoc:
    raw = path.read_bytes()
    # 尝试常见编码
    for enc in ("utf-8", "gbk", "gb18030", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return ParsedDoc(pages=[(1, text)])


def _parse_pdf(path: Path) -> ParsedDoc:
    import pdfplumber

    doc = ParsedDoc()
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                doc.pages.append((i, text))
    if not doc.pages:
        raise ValueError("PDF 无可提取文本（可能是扫描件/加密，OCR 功能 v2 支持）")
    return doc


def _parse_docx(path: Path) -> ParsedDoc:
    import docx

    d = docx.Document(str(path))
    parts: list[str] = []
    for p in d.paragraphs:
        if p.text.strip():
            parts.append(p.text)
    text = "\n".join(parts)
    return ParsedDoc(pages=[(1, text)])
