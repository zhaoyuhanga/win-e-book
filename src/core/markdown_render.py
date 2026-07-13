"""Mini-Markdown 渲染器(Phase 3c)。

不依赖第三方 markdown 库,手写一个支持常用语法的轻量版本。
目标场景:墨写写作时的实时预览,够用就行,不是要兼容 GFM 全部。

支持语法:
- 标题 h1-h6   : `# ` `## ` ... `###### `
- 粗体         : `**text**` `__text__`
- 斜体         : `*text*` `_text_`
- 删除线       : `~~text~~`
- 行内代码     : `` `code` ``
- 代码块       : ```` ```lang\ncode\n``` ````
- 引用         : `> text`(支持嵌套 `>>`)
- 无序列表     : `- item` `* item`
- 有序列表     : `1. item`
- 链接         : `[text](url)`
- 水平线       : `---` `***` `___`
- 段落         : 空行分隔

不自动 URL、不支持表格、不支持任务列表(简化)。
"""
from __future__ import annotations

import html
import re
from typing import List, Tuple


# ============================================================
# 块级解析
# ============================================================

class Block:
    """块级元素:paragraph/heading/codeblock/quote/ul/ol/hr。"""

    def __init__(self, kind: str, content=None, meta: dict = None):
        self.kind = kind
        self.content = content  # 段落:str  /  代码块:(lang, code)  /  列表:list[str]
        self.meta = meta or {}  # heading: {level: int}  /  list: {ordered: bool}

    def to_html(self, inline_parser) -> str:
        if self.kind == "paragraph":
            return f"<p>{inline_parser(self.content)}</p>"
        if self.kind == "heading":
            lvl = max(1, min(6, self.meta.get("level", 1)))
            text = self.content
            anchor = re.sub(r"[^\w\u4e00-\u9fa5\-]+", "-", text).strip("-").lower()[:50]
            return f'<h{lvl} id="{anchor}">{inline_parser(text)}</h{lvl}>'
        if self.kind == "codeblock":
            lang, code = self.content
            code_escaped = html.escape(code)
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            return f"<pre><code{cls}>{code_escaped}</code></pre>"
        if self.kind == "hr":
            return "<hr>"
        if self.kind == "quote":
            # content 是 inner blocks
            inner = "".join(b.to_html(inline_parser) for b in self.content)
            return f"<blockquote>{inner}</blockquote>"
        if self.kind == "list":
            tag = "ol" if self.meta.get("ordered") else "ul"
            items = "".join(f"<li>{inline_parser(it)}</li>" for it in self.content)
            return f"<{tag}>{items}</{tag}>"
        return ""


def _parse_blocks(text: str) -> List[Block]:
    """块级解析:把 markdown 文本切成块级元素。"""
    lines = text.split("\n")
    blocks: List[Block] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 空行:跳过
        if not stripped:
            i += 1
            continue

        # 代码块:```lang\n...\n```
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            j = i + 1
            code_lines: List[str] = []
            while j < n and not lines[j].strip().startswith("```"):
                code_lines.append(lines[j])
                j += 1
            blocks.append(Block("codeblock", (lang, "\n".join(code_lines))))
            i = j + 1
            continue

        # 水平线
        if re.match(r"^(\-{3,}|\*{3,}|_{3,})\s*$", stripped):
            blocks.append(Block("hr"))
            i += 1
            continue

        # 标题 # - ######
        m = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if m:
            level = len(m.group(1))
            blocks.append(Block("heading", m.group(2).strip(), {"level": level}))
            i += 1
            continue

        # 引用 >  (支持嵌套 >> >>>)
        if stripped.startswith(">"):
            quote_blocks: List[Block] = []
            j = i
            current_level = 0
            # 简化:把整段 > 文本视为一个段落;不递归
            # 实际:把连续 > 行收集,嵌套的展开
            while j < n and lines[j].strip().startswith(">"):
                content = re.sub(r"^>\s*", "", lines[j].strip())
                # 多层 > 时扁平化
                while content.startswith(">"):
                    content = re.sub(r"^>\s*", "", content)
                quote_blocks.append(Block("paragraph", content))
                j += 1
            blocks.append(Block("quote", quote_blocks))
            i = j
            continue

        # 列表(无序)
        if re.match(r"^[\-\*]\s+", stripped):
            items: List[str] = []
            j = i
            while j < n:
                m2 = re.match(r"^[\-\*]\s+(.*)$", lines[j].strip())
                if not m2:
                    break
                items.append(m2.group(1))
                j += 1
            blocks.append(Block("list", items, {"ordered": False}))
            i = j
            continue

        # 列表(有序)
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            j = i
            while j < n:
                m2 = re.match(r"^\d+\.\s+(.*)$", lines[j].strip())
                if not m2:
                    break
                items.append(m2.group(1))
                j += 1
            blocks.append(Block("list", items, {"ordered": True}))
            i = j
            continue

        # 段落:连续非空非特殊行
        para_lines = [stripped]
        j = i + 1
        while j < n and lines[j].strip() and not _is_block_start(lines[j].strip()):
            para_lines.append(lines[j].strip())
            j += 1
        blocks.append(Block("paragraph", " ".join(para_lines)))
        i = j

    return blocks


def _is_block_start(stripped: str) -> bool:
    """判断一行是否是新的块级元素起始(避免段落吞掉)。"""
    if stripped.startswith("```"):
        return True
    if re.match(r"^(\-{3,}|\*{3,}|_{3,})\s*$", stripped):
        return True
    if re.match(r"^#{1,6}\s+", stripped):
        return True
    if stripped.startswith(">"):
        return True
    if re.match(r"^[\-\*]\s+", stripped):
        return True
    if re.match(r"^\d+\.\s+", stripped):
        return True
    return False


# ============================================================
# 行级解析(inline)
# ============================================================

# 行内模式:顺序很重要 —— 行内代码最先(防 ** 内被吞)
INLINE_PATTERNS: List[Tuple[str, str]] = [
    # 行内代码(不能跨行,无嵌套)
    (r"`([^`]+)`", r"<code>\1</code>"),
    # 粗体(** 或 __)
    (r"\*\*(.+?)\*\*", r"<strong>\1</strong>"),
    (r"__(.+?)__", r"<strong>\1</strong>"),
    # 斜体(* 或 _)
    (r"(?<!\*)\*([^\*\n]+?)\*(?!\*)", r"<em>\1</em>"),
    (r"(?<![a-zA-Z0-9_])_([^_\n]+?)_(?![a-zA-Z0-9_])", r"<em>\1</em>"),
    # 删除线
    (r"~~(.+?)~~", r"<del>\1</del>"),
    # 链接
    (r"\[([^\]]+)\]\(([^\)]+)\)", r'<a href="\2">\1</a>'),
]


def _parse_inline(text: str) -> str:
    """行级解析:把段落/标题/列表项文本里的标记转 HTML。"""
    if not text:
        return ""
    # 1. 先转义所有 HTML 特殊字符
    out = html.escape(text)
    # 2. 还原我们要支持的标记(它们被转义成 &quot; 等,正则重新匹配)
    #    html.escape 不会转义 * # _ [ ] ( ) ` ~  > 这些 markdown 符号
    # 3. 跑行内模式
    for pat, repl in INLINE_PATTERNS:
        out = re.sub(pat, repl, out)
    return out


# ============================================================
# 公开 API
# ============================================================

def render_markdown(text: str) -> str:
    """把 Markdown 文本渲染成 HTML。"""
    blocks = _parse_blocks(text or "")
    body = "".join(b.to_html(_parse_inline) for b in blocks)
    return body


# GFM 风格 CSS(QTextBrowser 兼容版,inline 进 HTML)
_GFM_CSS = """
<style>
body { font-family: 'Georgia', 'Source Han Serif SC', 'Microsoft YaHei', serif; }
h1, h2, h3, h4, h5, h6 {
  font-weight: 700;
  margin: 1.2em 0 0.5em 0;
  line-height: 1.3;
  color: #1f2937;
}
h1 { font-size: 1.8em; border-bottom: 1px solid #e5e0d6; padding-bottom: 0.3em; }
h2 { font-size: 1.5em; border-bottom: 1px solid #f0ece2; padding-bottom: 0.2em; }
h3 { font-size: 1.25em; }
h4 { font-size: 1.1em; }
h5 { font-size: 1em; }
h6 { font-size: 0.9em; color: #6b7384; }
p { margin: 0.7em 0; line-height: 1.7; color: #1f2937; }
strong { font-weight: 700; color: #0f172a; }
em { font-style: italic; }
del { color: #9aa0ac; }
code {
  background: #f3eee4;
  color: #c8946e;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: 'Consolas', 'Cascadia Code', 'Courier New', monospace;
  font-size: 0.92em;
}
pre {
  background: #2a354a;
  color: #e2e8f0;
  padding: 12px 14px;
  border-radius: 6px;
  overflow-x: auto;
  line-height: 1.5;
  margin: 1em 0;
}
pre code {
  background: transparent;
  color: inherit;
  padding: 0;
  font-size: 0.9em;
}
blockquote {
  border-left: 3px solid #c8946e;
  padding: 0.2em 0 0.2em 12px;
  margin: 1em 0;
  color: #6b7384;
  background: #fbfaf7;
}
ul, ol { margin: 0.7em 0; padding-left: 2em; }
li { margin: 0.3em 0; line-height: 1.6; }
hr {
  border: none;
  border-top: 1px solid #e5e0d6;
  margin: 1.5em 0;
}
a { color: #c8946e; text-decoration: none; border-bottom: 1px solid rgba(200,148,110,0.4); }
a:hover { color: #a8754e; border-bottom-color: #a8754e; }
</style>
"""


def render_full_html(text: str, title: str = "预览") -> str:
    """渲染完整 HTML 文档(含 GFM CSS),给 QTextBrowser.setHtml。"""
    body = render_markdown(text)
    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/>
<title>{html.escape(title)}</title>
{_GFM_CSS}
</head>
<body>
{body}
</body>
</html>"""


# ============================================================
# 工具:提取纯文本(字数统计用)
# ============================================================

_PLAIN_STRIP_PATTERNS = [
    (r"^#{1,6}\s+", ""),         # 标题
    (r"^>\s*", ""),                # 引用
    (r"^[\-\*]\s+", ""),           # 无序列表
    (r"^\d+\.\s+", ""),            # 有序列表
    (r"^(\-{3,}|\*{3,}|_{3,})$", ""),  # hr
    (r"^```\w*$", ""),             # 代码块围栏
    (r"\*\*(.+?)\*\*", r"\1"),     # 粗体
    (r"__(.+?)__", r"\1"),
    (r"(?<!\*)\*([^\*\n]+?)\*(?!\*)", r"\1"),
    (r"(?<![a-zA-Z0-9_])_([^_\n]+?)_(?![a-zA-Z0-9_])", r"\1"),
    (r"~~(.+?)~~", r"\1"),         # 删除线
    (r"`([^`]+)`", r"\1"),         # 行内代码
    (r"\[([^\]]+)\]\([^\)]+\)", r"\1"),  # 链接
]


def strip_markdown(text: str) -> str:
    """把 markdown 简化为纯文本(用于字数统计等)。"""
    out = text or ""
    for pat, repl in _PLAIN_STRIP_PATTERNS:
        out = re.sub(pat, repl, out, flags=re.MULTILINE)
    # 去掉代码块围栏
    out = re.sub(r"```[^\n]*\n(.*?)```", r"\1", out, flags=re.DOTALL)
    return out
