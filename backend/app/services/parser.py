"""文档解析：txt / md / pdf / docx → 结构化块（标题层级、代码块、表格、列表）"""
from dataclasses import dataclass, field
from pathlib import Path

import mistune

# ---------- 数据结构 ----------


@dataclass
class Block:
    """结构块：heading / paragraph / list / quote / code / table"""
    type: str
    text: str
    level: int = 0          # heading 层级 1-6；非标题为 0
    page_no: int | None = None


@dataclass
class ParsedDoc:
    blocks: list[Block] = field(default_factory=list)
    pages: list[tuple[int, str]] = field(default_factory=list)  # 兼容旧接口 [(page_no, text)]

    @property
    def full_text(self) -> str:
        return "\n".join(b.text for b in self.blocks)


# ---------- 入口 ----------


def parse_file(path: Path, ftype: str) -> ParsedDoc:
    ftype = ftype.lower().lstrip(".")
    if ftype in ("txt", "md", "markdown"):
        return _parse_text(path)
    if ftype == "pdf":
        return _parse_pdf(path)
    if ftype in ("docx", "doc"):
        return _parse_docx(path)
    raise ValueError(f"不支持的文件格式: {ftype}")


# ---------- txt / md ----------

_md = mistune.create_markdown(renderer=None, plugins=["table", "strikethrough", "task_lists"])


def _extract_text(node) -> str:
    """递归提取 AST 节点的纯文本"""
    if node is None:
        return ""
    if isinstance(node, list):
        return "".join(_extract_text(n) for n in node)
    if isinstance(node, dict):
        t = node.get("type", "")
        if t == "text":
            return node.get("raw", "") or node.get("text", "")
        if t == "softbreak":
            return "\n"
        if t == "hardbreak":
            return "\n"
        if t == "image":
            alt = node.get("attrs", {}).get("alt", "") or ""
            return alt
        return _extract_text(node.get("children")) + (node.get("raw", "") or "")
    return ""


def _md_to_blocks(text: str, page_no: int = 1) -> list[Block]:
    """Markdown AST → Block 列表（标题层级 + 结构类型）"""
    blocks: list[Block] = []
    tokens = _md.parse(text)[0]  # mistune v3 返回 (tokens, state)

    def walk(tokens_: list) -> None:
        for tok in tokens_:
            t = tok.get("type", "")
            raw = tok.get("raw", "")
            if t == "heading":
                level = tok.get("attrs", {}).get("level", 1)
                blocks.append(Block(type="heading", text=_extract_text(tok).strip(), level=level, page_no=page_no))
            elif t in ("paragraph", "block_text"):
                body = _extract_text(tok).strip()
                if body:
                    blocks.append(Block(type="paragraph", text=body, page_no=page_no))
            elif t in ("fence", "block_code"):
                code = raw.rstrip("\n")
                if code.strip():
                    blocks.append(Block(type="code", text=code, page_no=page_no))
            elif t == "list":
                walk(tok.get("children", []))
            elif t == "list_item":
                # 列表项转成带符号的段落（保序）
                body = _extract_text(tok).strip()
                if body:
                    blocks.append(Block(type="list", text=body, page_no=page_no))
            elif t == "table":
                table_text = _table_to_text(tok)
                if table_text:
                    blocks.append(Block(type="table", text=table_text, page_no=page_no))
            elif t == "block_quote":
                body = _extract_text(tok).strip()
                if body:
                    blocks.append(Block(type="quote", text=body, page_no=page_no))
            elif t == "thematic_break":
                continue
            else:
                # 兜底：其他块类型取纯文本
                body = _extract_text(tok).strip()
                if body and t not in ("html_block",):
                    blocks.append(Block(type="paragraph", text=body, page_no=page_no))

    walk(tokens)
    return blocks


def _table_to_text(tok: dict) -> str:
    """表格 token → 可读文本（表头 + 行，| 分隔）"""
    rows: list[list[str]] = []
    for child in tok.get("children", []):
        t = child.get("type")
        if t == "table_head":
            # mistune v3: head 的 children 直接是 cell（无 row 包裹）
            cells = [_extract_text(c).strip() for c in child.get("children", [])]
            if any(cells):
                rows.append(cells)
        elif t == "table_body":
            for row in child.get("children", []):
                if row.get("type") != "table_row":
                    continue
                cells = [_extract_text(c).strip() for c in row.get("children", [])]
                if any(cells):
                    rows.append(cells)
    if not rows:
        return ""
    return "\n".join(" | ".join(cell for cell in r) for r in rows)


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

    ftype = path.suffix.lower().lstrip(".")
    if ftype in ("md", "markdown"):
        blocks = _md_to_blocks(text)
    else:
        blocks = _plain_to_blocks(text)

    pages = [(1, text)]
    return ParsedDoc(blocks=blocks, pages=pages)


def _plain_to_blocks(text: str) -> list[Block]:
    """纯文本：启发式识别标题（# / 第X章 / 1.2.3 / 一、）"""
    import re

    blocks: list[Block] = []
    md_heading = re.compile(r"^(#{1,6})\s+(.*)$")
    cn_heading = re.compile(r"^第[一二三四五六七八九十百千\d]+[章节部分卷].*$")
    num_heading = re.compile(r"^(\d+(?:\.\d+)*)[、.．]\s*(.+)$")  # 1.2.3 小节
    cn_num_heading = re.compile(r"^([一二三四五六七八九十]+)、(.+)$")  # 一、二、
    paren_heading = re.compile(r"^（[一二三四五六七八九十\d]+）(.+)$")  # （一）

    def is_heading(line: str) -> int | None:
        m = md_heading.match(line)
        if m:
            return len(m.group(1))
        if cn_heading.match(line) and len(line) <= 30:
            return 1
        m = num_heading.match(line)
        if m and len(line) <= 40:
            return len(m.group(1).split("."))
        if cn_num_heading.match(line) and len(line) <= 30:
            return 1
        if paren_heading.match(line) and len(line) <= 30:
            return 2
        return None

    current: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        lvl = is_heading(stripped)
        if lvl is not None:
            if current:
                blocks.append(Block(type="paragraph", text="\n".join(current)))
                current = []
            blocks.append(Block(type="heading", text=stripped, level=lvl))
        else:
            current.append(stripped)
    if current:
        blocks.append(Block(type="paragraph", text="\n".join(current)))
    return blocks


# ---------- pdf ----------


def _parse_pdf(path: Path) -> ParsedDoc:
    import pdfplumber

    doc = ParsedDoc()
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            page_texts: list[str] = []
            t = page.extract_text() or ""
            if t.strip():
                page_texts.append(t.strip())
            # 表格：提取为可读文本
            try:
                for tbl in page.extract_tables():
                    rows = []
                    for r in tbl:
                        cells = [(c or "").replace("\n", " ").strip() for c in r]
                        if any(cells):
                            rows.append(" | ".join(cells))
                    if rows:
                        page_texts.append("\n".join(rows))
            except Exception:  # noqa: BLE001
                pass
            if page_texts:
                text = "\n\n".join(page_texts)
                doc.pages.append((i, text))
                # PDF 无标题结构信息，按纯文本启发式分块
                for b in _plain_to_blocks(text):
                    b.page_no = i
                    doc.blocks.append(b)
    if not doc.pages:
        raise ValueError("PDF 无可提取文本（可能是扫描件/加密，OCR 功能 v2 支持）")
    return doc


# ---------- docx ----------


def _parse_docx(path: Path) -> ParsedDoc:
    import docx

    d = docx.Document(str(path))
    doc = ParsedDoc()
    heading_levels = {
        "Heading 1": 1, "Heading 2": 2, "Heading 3": 3,
        "Heading 4": 4, "Heading 5": 5, "Heading 6": 6,
        "标题 1": 1, "标题 2": 2, "标题 3": 3,
        "标题 4": 4, "标题 5": 5, "标题 6": 6,
    }

    def add_paragraph(p) -> None:
        text = (p.text or "").strip()
        if not text:
            return
        style_name = (p.style.name if p.style else "") or ""
        lvl = heading_levels.get(style_name)
        if lvl:
            doc.blocks.append(Block(type="heading", text=text, level=lvl))
        else:
            doc.blocks.append(Block(type="paragraph", text=text))

    def add_table(tbl) -> None:
        rows = []
        for r in tbl.rows:
            cells = [(c.text or "").replace("\n", " ").strip() for c in r.cells]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            doc.blocks.append(Block(type="table", text="\n".join(rows)))

    try:
        # 按文档顺序遍历段落与表格（python-docx 1.2+）
        for item in d.iter_inner_content():
            if item.__class__.__name__ == "Paragraph":
                add_paragraph(item)
            elif item.__class__.__name__ == "Table":
                add_table(item)
    except Exception:  # noqa: BLE001 旧版本回退
        for p in d.paragraphs:
            add_paragraph(p)
        for tbl in d.tables:
            add_table(tbl)

    if not doc.blocks:
        raise ValueError("docx 无可提取文本")
    return doc
