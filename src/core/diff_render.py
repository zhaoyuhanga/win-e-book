"""Diff 渲染(Phase 4a)。

不引入第三方 diff 库,用 stdlib 的 difflib 把两段文本转成红绿对比的 HTML。
- 红底 = 原文有但新文没有(删除)
- 绿底 = 新文有但原文没有(新增)
- 同行同字 = 灰色背景(unchanged)
- 行级 diff + 词级高亮(用 SequenceMatcher)

输出:HTML 字符串,给 QTextBrowser 显示。
"""
from __future__ import annotations

import difflib
import html
import re
from typing import List, Tuple


# ============================================================
# 颜色 + CSS(QTextBrowser 兼容)
# ============================================================

_DIFF_CSS = """
<style>
body { font-family: 'Consolas', 'Cascadia Code', 'Microsoft YaHei', monospace; font-size: 12px; }
table { border-collapse: collapse; width: 100%; }
td { vertical-align: top; padding: 2px 6px; font-family: inherit; }
td.gutter { width: 40px; text-align: right; color: #9aa0ac; user-select: none;
            background: #f3eee4; border-right: 1px solid #e5e0d6; }
td.line-old { width: 50%; background: #fbfaf7; }
td.line-new { width: 50%; background: #fbfaf7; }
tr.del td.line-old { background: #fde2e2; color: #b91c1c; }
tr.add td.line-new { background: #d4f4dd; color: #15803d; }
tr.both td.line-old, tr.both td.line-new { color: #1f2937; }
.word-del { background: #fca5a5; color: #7f1d1d; padding: 0 2px; border-radius: 2px; }
.word-add { background: #86efac; color: #14532d; padding: 0 2px; border-radius: 2px; }
</style>
"""


# ============================================================
# 核心
# ============================================================

def _tokenize_for_word_diff(text: str) -> List[str]:
    """把文本切成 token(英文按单词 + 标点,中文按字)。"""
    # 中文字符 / 英文单词 / 数字 / 标点 / 空白
    pattern = re.compile(r"([\u4e00-\u9fa5])|([a-zA-Z]+)|([0-9]+)|(\s+)|([^\w\s])")
    out: List[str] = []
    for m in pattern.finditer(text):
        out.append(m.group(0))
    return out


def _word_level_inline_diff(old: str, new: str) -> Tuple[str, str]:
    """对单行做词级 diff,返回 (old_html, new_html)。"""
    old_tokens = _tokenize_for_word_diff(old)
    new_tokens = _tokenize_for_word_diff(new)
    sm = difflib.SequenceMatcher(a=old_tokens, b=new_tokens, autojunk=False)
    old_parts: List[str] = []
    new_parts: List[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            old_parts.append(html.escape("".join(old_tokens[i1:i2])))
            new_parts.append(html.escape("".join(new_tokens[j1:j2])))
        elif tag == "delete":
            old_parts.append(f'<span class="word-del">{html.escape("".join(old_tokens[i1:i2]))}</span>')
        elif tag == "insert":
            new_parts.append(f'<span class="word-add">{html.escape("".join(new_tokens[j1:j2]))}</span>')
        elif tag == "replace":
            old_parts.append(f'<span class="word-del">{html.escape("".join(old_tokens[i1:i2]))}</span>')
            new_parts.append(f'<span class="word-add">{html.escape("".join(new_tokens[j1:j2]))}</span>')
    return "".join(old_parts), "".join(new_parts)


def compute_line_diff(old: str, new: str) -> List[Tuple[str, int, str, int, str, str]]:
    """行级 diff,返回 [(tag, old_no, old_line, new_no, new_line, html_old, html_new), ...]。

    tag: "equal" / "delete" / "add" / "replace"
    """
    old_lines = old.splitlines(keepends=False)
    new_lines = new.splitlines(keepends=False)
    # difflib.ndiff 给出带 - / + / 空格 的序列
    ndiff = list(difflib.ndiff(old_lines, new_lines, linejunk=None, charjunk=None))
    out: List[Tuple[str, int, str, int, str, str, str]] = []

    old_no = 0
    new_no = 0
    i = 0
    while i < len(ndiff):
        line = ndiff[i]
        if line.startswith("  "):  # equal
            content = line[2:]
            old_no += 1
            new_no += 1
            esc = html.escape(content)
            out.append(("equal", old_no, content, new_no, content, esc, esc))
            i += 1
        elif line.startswith("- "):
            # 看下一行是不是 + (replace)
            del_line = line[2:]
            del_html_old, del_html_new = _word_level_inline_diff(del_line, "")
            old_no += 1
            if i + 1 < len(ndiff) and ndiff[i + 1].startswith("+ "):
                add_line = ndiff[i + 1][2:]
                add_html_old, add_html_new = _word_level_inline_diff(del_line, add_line)
                new_no += 1
                out.append(("replace", old_no, del_line, new_no, add_line, add_html_old, add_html_new))
                i += 2
            else:
                out.append(("delete", old_no, del_line, None, "", del_html_old, ""))
                i += 1
        elif line.startswith("+ "):
            content = line[2:]
            new_no += 1
            esc = html.escape(content)
            out.append(("add", None, "", new_no, content, "", esc))
            i += 1
        else:
            i += 1  # skip "? " 信息行
    return out


def _summary(diff: List[Tuple]) -> dict:
    """统计新增/删除/未变行数。"""
    added = sum(1 for d in diff if d[0] in ("add", "replace"))
    deleted = sum(1 for d in diff if d[0] in ("delete", "replace"))
    unchanged = sum(1 for d in diff if d[0] == "equal")
    return {"added": added, "deleted": deleted, "unchanged": unchanged, "total": len(diff)}


# ============================================================
# 公开 API
# ============================================================

def render_diff_html(old: str, new: str, title: str = "Diff") -> str:
    """把 (old, new) 渲染成完整 HTML 文档,左右两栏显示。"""
    diff = compute_line_diff(old, new)
    s = _summary(diff)
    rows: List[str] = []
    for tag, ono, oline, nno, nline, old_html, new_html in diff:
        if tag == "equal":
            cls = "both"
        elif tag == "delete":
            cls = "del"
        elif tag == "add":
            cls = "add"
        else:  # replace
            cls = "del"  # CSS 用 del + 另一行 add
        old_gutter = str(ono) if ono else ""
        new_gutter = str(nno) if nno else ""
        # 保留空格
        old_html_disp = old_html or "&nbsp;" if tag in ("delete", "replace") else old_html
        new_html_disp = new_html or "&nbsp;" if tag in ("add", "replace") else new_html
        # replace 用 tr.del + 紧接 tr.add 的 CSS 不太直观;改用 inline 高亮
        if tag == "replace":
            rows.append(
                f'<tr class="del"><td class="gutter">{old_gutter}</td>'
                f'<td class="line-old">{old_html_disp}</td>'
                f'<td class="gutter"></td><td class="line-new">&nbsp;</td></tr>'
                f'<tr class="add"><td class="gutter"></td>'
                f'<td class="line-old">&nbsp;</td>'
                f'<td class="gutter">{new_gutter}</td>'
                f'<td class="line-new">{new_html_disp}</td></tr>'
            )
        else:
            rows.append(
                f'<tr class="{cls}">'
                f'<td class="gutter">{old_gutter}</td>'
                f'<td class="line-old">{old_html_disp}</td>'
                f'<td class="gutter">{new_gutter}</td>'
                f'<td class="line-new">{new_html_disp}</td>'
                f'</tr>'
            )
    summary_html = (
        f'<div style="padding:8px 12px;background:#f3eee4;'
        f'border-bottom:1px solid #e5e0d6;font-size:11px;color:#1f2937;">'
        f'<b>{html.escape(title)}</b>  ·  '
        f'<span style="color:#15803d;">+ 新增 {s["added"]} 行</span>  ·  '
        f'<span style="color:#b91c1c;">− 删除 {s["deleted"]} 行</span>  ·  '
        f'<span style="color:#6b7384;">未变 {s["unchanged"]} 行</span>'
        f'</div>'
    )
    body = (
        f'<!DOCTYPE html><html><head><meta charset="utf-8"/>'
        f'<title>{html.escape(title)}</title>{_DIFF_CSS}</head><body>'
        f'{summary_html}<table>'
        + "".join(rows)
        + '</table></body></html>'
    )
    return body


def diff_summary(old: str, new: str) -> dict:
    """只取统计(给状态栏等用)。"""
    return _summary(compute_line_diff(old, new))


def has_changes(old: str, new: str) -> bool:
    """两段文本是否有差异。"""
    return old != new
