"""BM25 单元测试。"""
import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, r'D:\awork\win-e-book')
from src.core.bm25 import (
    tokenize, scan_workspace, BM25Index, get_index,
    search_workspace, format_hits_for_prompt, invalidate_cache,
)


class TokenizeTest(unittest.TestCase):
    def test_chinese_1_gram(self):
        toks = tokenize("我喜欢写代码")
        self.assertIn("我", toks)
        self.assertIn("喜", toks)
        self.assertIn("欢", toks)
        self.assertIn("喜", toks)

    def test_chinese_2_gram(self):
        toks = tokenize("我喜欢写代码")
        self.assertIn("我喜", toks)
        self.assertIn("喜欢", toks)
        self.assertIn("欢写", toks)

    def test_english_words(self):
        toks = tokenize("hello world Python3 编程")
        self.assertIn("hello", toks)
        self.assertIn("world", toks)
        self.assertIn("python3", toks)

    def test_stopwords_filtered(self):
        toks = tokenize("我的一本书")
        # "的" 应该在停用词里
        self.assertNotIn("的", toks)
        # 但 "我" 不该被过滤
        self.assertIn("我", toks)
        self.assertIn("本", toks)
        self.assertIn("书", toks)

    def test_short_english_filtered(self):
        toks = tokenize("a I am ok")
        # 单词长度 < 2 被过滤
        self.assertNotIn("a", toks)
        self.assertNotIn("i", toks)
        # am(2 char)和 ok(2 char)都保留
        self.assertIn("am", toks)
        self.assertIn("ok", toks)


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "a.md").write_text(
            "# 测试文档\n\n这是关于墨写软件的中文内容。包含足够多的字符以通过分块最小长度。\n\n"
            "墨写是一款 AI 写作工具,支持在线补全、内联编辑、引用选区等功能。\n",
            encoding="utf-8")
        (self.root / "b.txt").write_text(
            "another file with some 中文 content. "
            "this file is long enough to pass the minimum chunk size filter "
            "and demonstrate that scanning works correctly for txt format files too. " * 2,
            encoding="utf-8")
        (self.root / "sub").mkdir()
        (self.root / "sub" / "c.md").write_text(
            "## 子目录文档\n\n"
            "这是一个子目录里的 markdown 文件,内容足够长以通过分块过滤,用于测试子目录扫描。\n",
            encoding="utf-8")
        (self.root / "skip.exe").write_bytes(b"\x00" * 100)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_scan_finds_md_txt(self):
        chunks = scan_workspace(self.root)
        paths = {c.doc_path for c in chunks}
        self.assertTrue(any("a.md" in p for p in paths), f"a.md not in {paths}")
        self.assertTrue(any("b.txt" in p for p in paths), f"b.txt not in {paths}")
        # 子目录也扫
        self.assertTrue(any("c.md" in p for p in paths), f"c.md not in {paths}")
        # .exe 跳过
        self.assertFalse(any("skip.exe" in p for p in paths))

    def test_scan_skips_short(self):
        # 写一个超短文件
        (self.root / "tiny.md").write_text("# 短\n", encoding="utf-8")
        chunks = scan_workspace(self.root)
        self.assertFalse(any("tiny.md" in c.doc_path for c in chunks))


class BM25IndexTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "doc1.md").write_text(
            "墨写是写作软件。在线补全是核心功能。补全基于 LLM,"
            "能根据上下文自动续写下一句或下一段文本。补全有短和长两种模式,"
            "短补全续写 8-80 字,长补全续写段落级 200-800 字,"
            "适合不同写作场景的续写需求。",
            encoding="utf-8")
        (self.root / "doc2.md").write_text(
            "墨读是阅读软件。支持 txt 和 epub 格式的本地电子书阅读,"
            "自动解析章节记忆阅读位置。每本书有独立的阅读历史记录,"
            "关闭重开自动回到上次章节和滚动位置。",
            encoding="utf-8")
        (self.root / "doc3.md").write_text(
            "海鲸是小说项目。主角是海军上将,讲述他被流放后在大洋上的故事。"
            "第一卷叫'北海之王',讲他流落到北海后的求生历程,"
            "以及与海鲸这种海洋生物的奇妙互动。",
            encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)
        invalidate_cache()

    def test_search_finds_relevant(self):
        idx = get_index(self.root, force=True)
        hits = idx.search("补全", k=2)
        # doc1 提到补全多次,应该命中
        self.assertGreater(len(hits), 0)
        self.assertIn("doc1.md", hits[0].doc_path)

    def test_search_returns_top_k(self):
        idx = get_index(self.root, force=True)
        hits = idx.search("软件", k=2)
        # doc1 和 doc2 都含"软件"
        self.assertGreaterEqual(len(hits), 2)
        paths = [h.doc_path for h in hits]
        self.assertTrue(any("doc1.md" in p for p in paths))
        self.assertTrue(any("doc2.md" in p for p in paths))

    def test_search_ranks_better_first(self):
        # 加一个含"墨写"多次的文档(直接加文件)
        (self.root / "doc_extra.md").write_text(
            "墨写软件介绍。墨写工具使用。墨写 AI 写作助手。"
            "墨写功能介绍。墨写使用教程。墨写 PRD 文档。墨写 Phase 2。",
            encoding="utf-8")
        invalidate_cache()
        idx = get_index(self.root, force=True)
        hits = idx.search("墨写", k=5)
        # doc_extra 排在最前(词频高)
        self.assertGreater(len(hits), 0)
        self.assertIn("doc_extra.md", hits[0].doc_path)

    def test_cache(self):
        invalidate_cache()
        idx1 = get_index(self.root)
        idx2 = get_index(self.root)  # 应该命中缓存
        self.assertIs(idx1, idx2)


def _make_chunk(path, content, prefix=""):
    from src.core.bm25 import Chunk
    return Chunk(
        doc_id=hash(path) & 0x7fffffff,
        doc_path=path,
        content=prefix + content,
        start=0,
    )


class FormatTest(unittest.TestCase):
    def test_format_with_no_hits(self):
        self.assertEqual(format_hits_for_prompt([]), "")

    def test_format_with_hits(self):
        from src.core.bm25 import SearchHit
        hits = [
            SearchHit(doc_path="a.md", content="内容1", score=3.0, chunk_start=0),
            SearchHit(doc_path="b.md", content="内容2" * 100, score=2.0, chunk_start=0),
        ]
        text = format_hits_for_prompt(hits, max_total_chars=1000)
        self.assertIn("[相关片段 1]", text)
        self.assertIn("[相关片段 2]", text)
        self.assertIn("a.md", text)
        self.assertIn("b.md", text)


if __name__ == "__main__":
    unittest.main()
