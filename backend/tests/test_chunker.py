"""分块模块测试"""
from app.services.chunker import chunk_parsed


def _make_pages(text: str) -> list[tuple[int, str]]:
    return [(1, text)]


def test_heading_splitting():
    text = "# 第一章 概述\n这是第一章的内容，介绍背景。\n\n## 1.1 方法\n这是方法部分的内容。"
    pieces = chunk_parsed(_make_pages(text))
    assert len(pieces) >= 2
    # 标题信息保留在 meta/heading
    assert any(p.heading and "第一章" in p.heading for p in pieces)
    assert any(p.heading and "1.1" in p.heading for p in pieces)


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
