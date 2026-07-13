"""Markdown 语法高亮(QSyntaxHighlighter 实现)。

在编辑器内对 Markdown 标记上色,**粗体** *斜体* # 标题 等,
不修改文本,只染色,符合"Live 预览"的视觉感。
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QTextDocument,
)


# ============================================================
# 配色(墨读深色主题适配)
# ============================================================

# 主题色(从 theme.py 同款)
C_HEADING = QColor("#d4a87c")     # 暖橙(主色)
C_BOLD = QColor("#e6ded2")        # 暖白
C_ITALIC = QColor("#c8b89c")      # 浅米
C_CODE = QColor("#7c9bc4")        # 蓝灰
C_CODE_BG = QColor("#1a2336")
C_LINK = QColor("#5a9bd4")
C_QUOTE = QColor("#9aa0ac")
C_LIST = QColor("#d4a87c")
C_RULE = QColor("#6b7384")


def _fmt(color: QColor, *, bold=False, italic=False,
         bg: QColor = None, size: int = None) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(color)
    if bold:
        f.setFontWeight(QFont.Bold)
    if italic:
        f.setFontItalic(True)
    if bg is not None:
        f.setBackground(bg)
    if size is not None:
        f.setFontPointSize(size)
    return f


# ============================================================
# 规则(顺序:先大后小,优先级高在前)
# ============================================================

class MarkdownHighlighter(QSyntaxHighlighter):
    """Markdown 语法高亮。"""

    def __init__(self, doc: QTextDocument):
        super().__init__(doc)
        self._build_rules()

    def _build_rules(self):
        # 标题(1-6 级)
        self._heading_rules: List[Tuple[QRegularExpression, QTextCharFormat]] = []
        for level in range(1, 7):
            pat = QRegularExpression(rf"^#{{{level}}}\s+.*$")
            size = {1: 22, 2: 19, 3: 16, 4: 14, 5: 13, 6: 12}[level]
            fmt = _fmt(C_HEADING, bold=True, size=size)
            self._heading_rules.append((pat, fmt))

        # 粗体 **...**
        self._bold_rule = (
            QRegularExpression(r"\*\*[^*\n]{1,200}\*\*|__[^_\n]{1,200}__"),
            _fmt(C_BOLD, bold=True),
        )
        # 斜体 *...* / _..._
        self._italic_rule = (
            QRegularExpression(r"(?<!\*)\*[^*\n]{1,200}\*(?!\*)|(?<!_)_[^_\n]{1,200}_(?!_)"),
            _fmt(C_ITALIC, italic=True),
        )
        # 行内代码 `...`
        self._code_rule = (
            QRegularExpression(r"`[^`\n]{1,200}`"),
            _fmt(C_CODE, bg=C_CODE_BG),
        )
        # 链接 [text](url)
        self._link_rule = (
            QRegularExpression(r"\[[^\]\n]{1,80}\]\([^\s)]+\)"),
            _fmt(C_LINK, italic=False),
        )
        # 引用 > 开头
        self._quote_rule = (
            QRegularExpression(r"^>\s+.*$"),
            _fmt(C_QUOTE, italic=True),
        )
        # 列表标记:数字./-/+
        self._list_rule = (
            QRegularExpression(r"^\s*([-*+]|\d+\.)\s+"),
            _fmt(C_LIST, bold=True),
        )
        # 分隔线 ---
        self._rule_rule = (
            QRegularExpression(r"^[-*_]{3,}\s*$"),
            _fmt(C_RULE, bold=True),
        )
        # 代码块 ```...```(整段标灰)
        self._codeblock_start = QRegularExpression(r"^```")
        # 图片 ![](url)
        self._image_rule = (
            QRegularExpression(r"!\[[^\]\n]{0,80}\]\([^\s)]+\)"),
            _fmt(C_LINK),
        )

        # 复合规则(按优先级排)
        self._rules: List[Tuple[QRegularExpression, QTextCharFormat]] = [
            *self._heading_rules,
            self._bold_rule,
            self._italic_rule,
            self._code_rule,
            self._link_rule,
            self._image_rule,
            self._quote_rule,
            self._list_rule,
            self._rule_rule,
        ]

        # 代码块状态
        self._in_codeblock = False

    def highlightBlock(self, text: str):  # noqa: N802
        # 1) 代码块优先
        if self._in_codeblock:
            fmt = _fmt(C_CODE, bg=C_CODE_BG)
            self.setFormat(0, len(text), fmt)
            if text.strip().startswith("```"):
                self._in_codeblock = False
            return
        if text.strip().startswith("```"):
            self._in_codeblock = True
            fmt = _fmt(C_CODE, bg=C_CODE_BG)
            self.setFormat(0, len(text), fmt)
            return

        # 2) 其他规则
        for pat, fmt in self._rules:
            it = pat.globalMatch(text)
            while it.hasNext():
                m = it.next()
                start = m.capturedStart()
                length = m.capturedLength()
                self.setFormat(start, length, fmt)
