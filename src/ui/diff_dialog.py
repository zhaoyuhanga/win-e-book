"""Diff 对话框(Phase 4a)。

左右两栏,红绿对比,QTextBrowser 显示由 src.core.diff_render 生成的 HTML。
底部:✗ 拒绝 / ✓ 接受 按钮。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser,
    QDialogButtonBox, QWidget,
)

from src.core.diff_render import render_diff_html, diff_summary
from src.ui.theme import (
    BG, SURFACE, BORDER, ACCENT, ACCENT_HOVER, TEXT, TEXT_SECONDARY,
    TEXT_MUTED, DANGER, SUCCESS, FONT_HEADING, RADIUS, RADIUS_SM, RADIUS_XS,
)


class DiffDialog(QDialog):
    """展示 (old, new) 的差异,用户可接受或拒绝。"""

    def __init__(self, old: str, new: str, title: str = "查看修改",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(820, 560)
        self.setStyleSheet(f"""
            QDialog {{
                background: #fbfaf7;
            }}
        """)
        self._accepted = False
        self._old = old
        self._new = new

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # 顶部统计
        s = diff_summary(old, new)
        summary = QLabel(
            f'<span style="color:{TEXT}; font-family:{FONT_HEADING}; font-size:14px; font-weight:700;">'
            f'{title}</span>'
            f'&nbsp;&nbsp;'
            f'<span style="color:{SUCCESS}; font-size:12px;">+ 新增 {s["added"]} 行</span>'
            f'&nbsp;'
            f'<span style="color:{DANGER}; font-size:12px;">− 删除 {s["deleted"]} 行</span>'
            f'&nbsp;'
            f'<span style="color:{TEXT_MUTED}; font-size:12px;">未变 {s["unchanged"]} 行</span>'
        )
        summary.setContentsMargins(20, 16, 20, 12)
        summary.setStyleSheet(f"""
            QLabel {{
                background: {SURFACE};
                border-bottom: 1px solid {BORDER};
                padding: 12px 20px;
            }}
        """)
        v.addWidget(summary)

        # 浏览器
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setStyleSheet(f"""
            QTextBrowser {{
                background: #fbfaf7;
                color: {TEXT};
                border: none;
            }}
        """)
        self.browser.setHtml(render_diff_html(old, new, title=title))
        v.addWidget(self.browser, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 12, 20, 16)
        btn_row.setSpacing(10)
        btn_row.addStretch(1)

        self.btn_reject = QPushButton("✗ 拒绝")
        self.btn_reject.setCursor(Qt.PointingHandCursor)
        self.btn_reject.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {DANGER};
                border: 1px solid {DANGER};
                border-radius: {RADIUS_XS}px;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {DANGER};
                color: #fff;
            }}
        """)
        self.btn_reject.clicked.connect(self._on_reject)
        btn_row.addWidget(self.btn_reject)

        self.btn_accept = QPushButton("✓ 接受修改")
        self.btn_accept.setDefault(True)
        self.btn_accept.setCursor(Qt.PointingHandCursor)
        self.btn_accept.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: #fff;
                border: 1px solid {ACCENT};
                border-radius: {RADIUS_XS}px;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {ACCENT_HOVER};
                border: 1px solid {ACCENT_HOVER};
            }}
        """)
        self.btn_accept.clicked.connect(self._on_accept)
        btn_row.addWidget(self.btn_accept)
        v.addLayout(btn_row)

        # 快捷键
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._on_accept)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._on_accept)
        QShortcut(QKeySequence("Esc"), self, activated=self._on_reject)

    def _on_accept(self):
        self._accepted = True
        self.accept()

    def _on_reject(self):
        self._accepted = False
        self.reject()

    def was_accepted(self) -> bool:
        return self._accepted
