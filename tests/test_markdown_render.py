"""Mini-Markdown 渲染器(Phase 3c)单元测试。

覆盖:
- 块级:段落/标题 h1-h6/代码块/引用/无序列表/有序列表/水平线
- 行内:粗体/斜体/删除线/行内代码/链接
- HTML 转义防注入
- 嵌套(引用套段落)
- strip_markdown 工具
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from src.core.markdown_render import (
    render_markdown, render_full_html, strip_markdown,
)


class HeadingTest(unittest.TestCase):

    def test_h1(self):
        h = render_markdown("# 你好")
        self.assertIn("<h1", h)
        self.assertIn("你好", h)

    def test_h6(self):
        h = render_markdown("###### 小标题")
        self.assertIn("<h6", h)
        self.assertIn("小标题", h)

    def test_heading_has_anchor(self):
        h = render_markdown("## 测试标题")
        self.assertIn('id="', h)

    def test_heading_truncates_long_anchor(self):
        long_title = "测试" * 50
        h = render_markdown(f"## {long_title}")
        # 锚点应被截短到 ~50 字符
        import re
        m = re.search(r'id="([^"]+)"', h)
        self.assertIsNotNone(m)
        self.assertLessEqual(len(m.group(1)), 60)


class ParagraphTest(unittest.TestCase):

    def test_simple_paragraph(self):
        h = render_markdown("这是一段普通文字。")
        self.assertIn("<p>", h)
        self.assertIn("这是一段普通文字。", h)

    def test_paragraph_splits_on_blank_line(self):
        h = render_markdown("第一段。\n\n第二段。")
        self.assertIn("第一段。", h)
        self.assertIn("第二段。", h)
        # 应有两个 <p>
        self.assertEqual(h.count("<p>"), 2)


class InlineTest(unittest.TestCase):

    def test_bold(self):
        h = render_markdown("这是 **重要** 内容")
        self.assertIn("<strong>重要</strong>", h)

    def test_bold_underscore(self):
        h = render_markdown("这是 __重要__ 内容")
        self.assertIn("<strong>重要</strong>", h)

    def test_italic(self):
        h = render_markdown("这是 *强调* 内容")
        self.assertIn("<em>强调</em>", h)

    def test_italic_underscore(self):
        h = render_markdown("这是 _强调_ 内容")
        self.assertIn("<em>强调</em>", h)

    def test_strikethrough(self):
        h = render_markdown("~~旧的~~")
        self.assertIn("<del>旧的</del>", h)

    def test_inline_code(self):
        h = render_markdown("用 `print()` 输出")
        self.assertIn("<code>print()</code>", h)

    def test_link(self):
        h = render_markdown("访问 [百度](https://baidu.com)")
        self.assertIn('<a href="https://baidu.com">百度</a>', h)


class CodeBlockTest(unittest.TestCase):

    def test_python_codeblock(self):
        md = "```python\ndef hello():\n    pass\n```"
        h = render_markdown(md)
        self.assertIn("<pre>", h)
        self.assertIn("<code", h)
        self.assertIn('language-python', h)
        self.assertIn("def hello():", h)

    def test_codeblock_no_lang(self):
        md = "```\nraw code\n```"
        h = render_markdown(md)
        self.assertIn("<pre>", h)
        self.assertIn("raw code", h)


class QuoteTest(unittest.TestCase):

    def test_single_quote(self):
        h = render_markdown("> 引用文字")
        self.assertIn("<blockquote>", h)
        self.assertIn("引用文字", h)

    def test_multi_line_quote(self):
        h = render_markdown("> 第一行\n> 第二行")
        self.assertIn("<blockquote>", h)
        self.assertIn("第一行", h)
        self.assertIn("第二行", h)


class ListTest(unittest.TestCase):

    def test_unordered(self):
        h = render_markdown("- 第一项\n- 第二项\n- 第三项")
        self.assertIn("<ul>", h)
        self.assertIn("</ul>", h)
        self.assertEqual(h.count("<li>"), 3)

    def test_ordered(self):
        h = render_markdown("1. 第一步\n2. 第二步")
        self.assertIn("<ol>", h)
        self.assertIn("</ol>", h)
        self.assertIn("第一步", h)
        self.assertIn("第二步", h)


class HrTest(unittest.TestCase):

    def test_dash_hr(self):
        h = render_markdown("---")
        self.assertIn("<hr>", h)

    def test_asterisk_hr(self):
        h = render_markdown("***")
        self.assertIn("<hr>", h)

    def test_underscore_hr(self):
        h = render_markdown("___")
        self.assertIn("<hr>", h)


class EscapeTest(unittest.TestCase):

    def test_xss_script_escaped(self):
        md = "<script>alert(1)</script>"
        h = render_markdown(md)
        self.assertNotIn("<script>", h)
        self.assertIn("&lt;script&gt;", h)

    def test_special_chars_escaped(self):
        md = "3 < 5 & 5 > 3"
        h = render_markdown(md)
        self.assertIn("&lt;", h)
        self.assertIn("&amp;", h)
        self.assertIn("&gt;", h)


class FullHtmlTest(unittest.TestCase):

    def test_full_html_structure(self):
        h = render_full_html("# 标题\n\n内容")
        self.assertIn("<!DOCTYPE html>", h)
        self.assertIn("<style>", h)
        self.assertIn("<h1", h)
        self.assertIn("<p>", h)

    def test_full_html_includes_gfm_css(self):
        h = render_full_html("hello")
        self.assertIn("Georgia", h)  # CSS 里有 Georgia
        self.assertIn("blockquote", h)
        self.assertIn("pre", h)


class StripTest(unittest.TestCase):

    def test_strip_basic(self):
        plain = strip_markdown("# 标题\n\n**重要** 文字")
        self.assertIn("标题", plain)
        self.assertIn("重要", plain)
        self.assertIn("文字", plain)
        self.assertNotIn("**", plain)
        self.assertNotIn("#", plain)

    def test_strip_list(self):
        plain = strip_markdown("- 一\n- 二")
        self.assertIn("一", plain)
        self.assertIn("二", plain)
        self.assertNotIn("-", plain)

    def test_strip_codeblock(self):
        plain = strip_markdown("```python\ndef f():\n    pass\n```")
        self.assertIn("def f():", plain)
        self.assertIn("pass", plain)
        self.assertNotIn("```", plain)

    def test_strip_link_keeps_text(self):
        plain = strip_markdown("[百度](https://baidu.com)")
        self.assertIn("百度", plain)
        self.assertNotIn("https://", plain)


class EdgeCaseTest(unittest.TestCase):

    def test_empty_input(self):
        h = render_markdown("")
        self.assertEqual(h, "")

    def test_none_input(self):
        h = render_markdown(None)  # type: ignore
        self.assertEqual(h, "")

    def test_mixed_content(self):
        md = """# 标题

这是段落 **粗体** 和 *斜体*。

## 列表

- 1
- 2

> 引用
"""
        h = render_markdown(md)
        self.assertIn("<h1", h)
        self.assertIn("<h2", h)
        self.assertIn("<strong>粗体</strong>", h)
        self.assertIn("<em>斜体</em>", h)
        self.assertIn("<ul>", h)
        self.assertIn("<blockquote>", h)


if __name__ == "__main__":
    unittest.main()
