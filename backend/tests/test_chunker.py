"""分块模块测试"""
import pytest

from app.services.chunker import chunk_parsed
from app.services.parser import parse_file
from pathlib import Path


def _make_pages(text: str) -> list[tuple[int, str]]:
    return [(1, text)]


def _chunk_md(text: str):
    """完整链路：md 文本 → parse → chunk（结构感知）"""
    import tempfile
    from app.services.parser import parse_file

    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
        f.write(text)
        name = f.name
    parsed = parse_file(Path(name), "md")
    return chunk_parsed(parsed.pages, parsed.blocks)


def test_heading_splitting():
    text = "# 第一章 概述\n这是第一章的内容，介绍背景。\n\n## 1.1 方法\n这是方法部分的内容。"
    pieces = chunk_parsed(_make_pages(text))
    assert len(pieces) >= 2
    # 标题路径保留在 content / heading_path
    assert any(p.heading_path and "第一章" in p.heading_path for p in pieces)
    assert any(p.heading_path and "1.1" in p.heading_path for p in pieces)


def test_heading_path_hierarchy():
    """标题路径应体现层级：第一章 > 1.1 > 小节"""
    text = (
        "# 第一章 概述\n概述内容。\n\n"
        "## 1.1 方法\n方法内容。\n\n"
        "### 1.1.1 细节\n细节内容。"
    )
    pieces = chunk_parsed(_make_pages(text))
    # 1.1.1 下的块应带完整路径
    detail = [p for p in pieces if "1.1.1" in (p.heading_path or "")]
    assert detail and "第一章" in detail[0].heading_path


def test_code_block_preserved():
    """代码块应整体保留，不被句子切分破坏"""
    text = "# 代码示例\n\n```python\nfor i in range(10):\n    print(i)\n```"
    pieces = _chunk_md(text)
    code = [p for p in pieces if p.meta.get("type") == "code"]
    assert code and "for i in range(10)" in code[0].content


def test_table_preserved():
    text = "# 表格\n\n| 列A | 列B |\n| --- | --- |\n| 1 | 2 |"
    pieces = _chunk_md(text)
    tbl = [p for p in pieces if p.meta.get("type") == "table"]
    assert tbl and "列A | 列B" in tbl[0].content


def test_long_paragraph_split():
    # 超过 chunk_size 的长文本应被切开
    text = "这是一个长段落。" * 200
    pieces = chunk_parsed(_make_pages(text))
    assert len(pieces) > 1
    assert all(p.content for p in pieces)


def test_empty_content():
    assert chunk_parsed([(1, "")]) == []
    assert chunk_parsed([(1, "   \n  ")]) == []


def test_seq_continuous():
    text = "段落一。\n\n段落二。\n\n段落三。"
    pieces = chunk_parsed(_make_pages(text))
    seqs = [p.seq for p in pieces]
    assert seqs == list(range(len(pieces)))


def test_chunk_size_limited():
    """每个块内容不应远超 chunk_size（允许标题前缀少量溢出）"""
    from app.config import settings

    text = "这是一段测试内容，用于验证分块大小。" * 50
    pieces = chunk_parsed(_make_pages(text))
    for p in pieces:
        assert len(p.content) <= settings.chunk_size * 1.3


def test_md_file_end_to_end(tmp_path: Path):
    """从 md 文件到分块的全链路"""
    p = tmp_path / "doc.md"
    p.write_text(
        "# 产品介绍\n这是产品介绍内容。\n\n## 功能列表\n- 支持文档上传\n- 支持 AI 问答\n\n```sql\nSELECT 1;\n```",
        encoding="utf-8",
    )
    parsed = parse_file(p, "md")
    pieces = chunk_parsed(parsed.pages, parsed.blocks)
    assert len(pieces) >= 2
    assert any("产品介绍" in (pc.heading_path or "") for pc in pieces)
    assert any(pc.meta.get("type") == "code" for pc in pieces)
