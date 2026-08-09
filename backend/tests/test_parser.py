"""解析模块测试"""
from pathlib import Path

import pytest

from app.services.parser import parse_file


def test_parse_txt_utf8(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("第一行内容\n第二行内容", encoding="utf-8")
    doc = parse_file(p, "txt")
    assert doc.pages == [(1, "第一行内容\n第二行内容")]


def test_parse_txt_gbk(tmp_path: Path):
    p = tmp_path / "b.txt"
    p.write_bytes("中文GBK内容测试".encode("gbk"))
    doc = parse_file(p, "txt")
    assert "中文GBK内容测试" in doc.full_text


def test_parse_md(tmp_path: Path):
    p = tmp_path / "c.md"
    p.write_text("# 标题\n\n正文段落。", encoding="utf-8")
    doc = parse_file(p, "md")
    assert doc.full_text == "# 标题\n\n正文段落。"


def test_parse_unsupported(tmp_path: Path):
    p = tmp_path / "d.xyz"
    p.write_text("x")
    with pytest.raises(ValueError, match="不支持"):
        parse_file(p, "xyz")
