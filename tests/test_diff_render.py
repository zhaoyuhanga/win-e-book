"""Diff 渲染(Phase 4a)单元测试。

覆盖:
- 行级 diff:equal/delete/add/replace
- 词级 inline diff:中文/英文混排
- HTML 输出:结构/CSS/统计栏
- has_changes / diff_summary
- 边缘:空/单边/完全相同
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from src.core.diff_render import (
    compute_line_diff, render_diff_html, diff_summary, has_changes,
    _tokenize_for_word_diff, _word_level_inline_diff,
)


class LineDiffTest(unittest.TestCase):

    def test_identical(self):
        diff = compute_line_diff("a\nb\nc", "a\nb\nc")
        tags = [d[0] for d in diff]
        self.assertEqual(tags, ["equal", "equal", "equal"])

    def test_add_line(self):
        diff = compute_line_diff("a\nc", "a\nb\nc")
        tags = [d[0] for d in diff]
        # expected: equal a, add b, equal c
        self.assertEqual(tags, ["equal", "add", "equal"])

    def test_delete_line(self):
        diff = compute_line_diff("a\nb\nc", "a\nc")
        tags = [d[0] for d in diff]
        # expected: equal a, delete b, equal c
        self.assertEqual(tags, ["equal", "delete", "equal"])

    def test_replace_line(self):
        diff = compute_line_diff("a\nb\nc", "a\nB\nc")
        tags = [d[0] for d in diff]
        # 期望:equal a, replace b→B, equal c
        self.assertEqual(tags, ["equal", "replace", "equal"])

    def test_empty_old(self):
        diff = compute_line_diff("", "hello")
        tags = [d[0] for d in diff]
        self.assertEqual(tags, ["add"])

    def test_empty_new(self):
        diff = compute_line_diff("hello", "")
        tags = [d[0] for d in diff]
        self.assertEqual(tags, ["delete"])

    def test_both_empty(self):
        diff = compute_line_diff("", "")
        self.assertEqual(diff, [])


class WordDiffTest(unittest.TestCase):

    def test_chinese_single_char(self):
        old_html, new_html = _word_level_inline_diff("我喜欢编程", "我喜欢写作")
        # "编程" → "写作" 是 replace
        self.assertIn("word-del", old_html)
        self.assertIn("word-add", new_html)
        self.assertIn("编", old_html)
        self.assertIn("写", new_html)

    def test_english_words(self):
        old_html, new_html = _word_level_inline_diff(
            "I love Python", "I love Rust")
        self.assertIn("word-del", old_html)
        self.assertIn("Python", old_html)
        self.assertIn("Rust", new_html)

    def test_mixed(self):
        old_html, new_html = _word_level_inline_diff(
            "今天天气很好", "今天天气不错")
        # "很" → "不" 是 replace
        self.assertIn("word-add", new_html)

    def test_identical(self):
        old_html, new_html = _word_level_inline_diff("hello", "hello")
        self.assertNotIn("word-del", old_html)
        self.assertNotIn("word-add", new_html)


class TokenizeTest(unittest.TestCase):

    def test_chinese_chars(self):
        toks = _tokenize_for_word_diff("中文")
        self.assertEqual(toks, ["中", "文"])

    def test_english_words(self):
        toks = _tokenize_for_word_diff("hello world")
        self.assertIn("hello", toks)
        self.assertIn("world", toks)

    def test_numbers(self):
        toks = _tokenize_for_word_diff("abc 123 def")
        self.assertIn("123", toks)
        self.assertIn("abc", toks)

    def test_punct(self):
        toks = _tokenize_for_word_diff("hi,world")
        self.assertIn("hi", toks)
        self.assertIn(",", toks)


class RenderHtmlTest(unittest.TestCase):

    def test_html_structure(self):
        html = render_diff_html("a\nb", "a\nB", title="test")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("test", html)
        self.assertIn("<table>", html)
        self.assertIn("</table>", html)

    def test_html_includes_css(self):
        html = render_diff_html("a", "a")
        self.assertIn("word-del", html)
        self.assertIn("word-add", html)

    def test_html_includes_summary(self):
        html = render_diff_html("a\nb", "a\nB")
        self.assertIn("新增", html)
        self.assertIn("删除", html)
        self.assertIn("未变", html)

    def test_html_escapes_special_chars(self):
        html = render_diff_html("<script>", "safe")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_html_contains_lines(self):
        html = render_diff_html("第一行", "第二行")
        # ndiff + 词级 inline diff 会把"第一行"拆成单字,但"一"/"行"等片段
        # 应保留在 HTML 中(被 word-del/word-add 包裹)
        self.assertIn("一", html)
        self.assertIn("行", html)


class SummaryTest(unittest.TestCase):

    def test_identical(self):
        s = diff_summary("a\nb", "a\nb")
        self.assertEqual(s["added"], 0)
        self.assertEqual(s["deleted"], 0)
        self.assertEqual(s["unchanged"], 2)

    def test_added_one(self):
        s = diff_summary("a", "a\nb")
        self.assertEqual(s["added"], 1)
        self.assertEqual(s["unchanged"], 1)

    def test_replaced(self):
        s = diff_summary("a\nb", "a\nB")
        # replace 算 1 added + 1 deleted
        self.assertEqual(s["added"], 1)
        self.assertEqual(s["deleted"], 1)


class HasChangesTest(unittest.TestCase):

    def test_same(self):
        self.assertFalse(has_changes("hello", "hello"))

    def test_different(self):
        self.assertTrue(has_changes("hello", "world"))

    def test_both_empty(self):
        self.assertFalse(has_changes("", ""))


class EdgeCaseTest(unittest.TestCase):

    def test_chinese_multiline(self):
        old = "第一段\n\n第二段很长很长的内容。\n\n第三段。"
        new = "第一段修改了。\n\n第二段很长很长的内容。\n\n新增第四段。"
        diff = compute_line_diff(old, new)
        tags = [d[0] for d in diff]
        # ndiff 会把"第一段"→"第一段修改了"看作 replace(整行不同);
        # 包含"add"/"replace"都算有变化
        self.assertIn("replace", tags)
        self.assertIn("equal", tags)

    def test_html_handles_empty_diff(self):
        html = render_diff_html("", "")
        self.assertIn("<!DOCTYPE html>", html)


if __name__ == "__main__":
    unittest.main()
