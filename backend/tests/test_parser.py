"""解析模块测试"""
from pathlib import Path

import pytest

from app.services.parser import parse_file


def test_parse_txt_utf8(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("第一行内容\n第二行内容", encoding="utf-8")
    doc = parse_file(p, "txt")
    assert any("第一行内容" in b.text for b in doc.blocks)
    assert any("第二行内容" in b.text for b in doc.blocks)


def test_parse_txt_gbk(tmp_path: Path):
    p = tmp_path / "b.txt"
    p.write_bytes("中文GBK内容测试".encode("gbk"))
    doc = parse_file(p, "txt")
    assert "中文GBK内容测试" in doc.full_text


def test_parse_md_structure(tmp_path: Path):
    """md 应解析出标题层级与正文结构"""
    p = tmp_path / "c.md"
    p.write_text(
        "# 第一章 概述\n\n正文段落。\n\n## 1.1 方法\n\n第二段。\n\n```python\nprint('hi')\n```\n\n| 列A | 列B |\n| --- | --- |\n| 1 | 2 |",
        encoding="utf-8",
    )
    doc = parse_file(p, "md")
    types = [(b.type, b.level) for b in doc.blocks]
    assert ("heading", 1) in types
    assert ("heading", 2) in types
    assert any(b.type == "code" for b in doc.blocks)
    assert any(b.type == "table" for b in doc.blocks)
    # 标题文本不带 # 符号
    assert any(b.type == "heading" and b.text == "第一章 概述" for b in doc.blocks)


def test_parse_md_plain_txt_heading(tmp_path: Path):
    """纯 txt 也应识别常见章节标题"""
    p = tmp_path / "d.txt"
    p.write_text("第一章 概述\n这是内容。\n\n1.2 小节\n更多内容。", encoding="utf-8")
    doc = parse_file(p, "txt")
    headings = [b.text for b in doc.blocks if b.type == "heading"]
    assert "第一章 概述" in headings
    assert "1.2 小节" in headings


def test_parse_unsupported(tmp_path: Path):
    p = tmp_path / "e.xyz"
    p.write_text("x")
    with pytest.raises(ValueError, match="不支持"):
        parse_file(p, "xyz")
