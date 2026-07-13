"""PDF 阅读 UI(Phase 3d)。

独立 view,不挂书库,直接打开本地 PDF 文件。
设计:顶栏(返回 + 文件名 + 缩放 + 页码跳转) + 中部(QScrollArea 包 QLabel 显示页)
进度持久化:QSettings('WinEBook', 'PdfReader') 按文件路径 hash 存页码 + 缩放。
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QSettings
from PySide6.QtGui import QPixmap, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox, QSpinBox,
    QToolButton, QScrollArea, QMessageBox, QSizePolicy,
)

from src.core import pdf_reader
from src.ui.theme import (
    BG, SURFACE, SURFACE_RAISED, BORDER, BORDER_FOCUS, ACCENT, ACCENT_HOVER,
    TEXT, TEXT_SECONDARY, TEXT_MUTED, FONT_HEADING, FONT_BODY, RADIUS, RADIUS_SM, RADIUS_XS,
    SUCCESS,
)


_TOOLBTN_QSS = f"""
    QToolButton {{
        background: transparent;
        color: {TEXT_SECONDARY};
        border: 1px solid #d4cfc0;
        border-radius: {RADIUS_XS}px;
        padding: 4px 10px;
        font-size: 11px;
    }}
    QToolButton:hover {{
        color: {ACCENT};
        border: 1px solid {ACCENT};
    }}
    QToolButton:checked {{
        color: #fff;
        background: {ACCENT};
        border: 1px solid {ACCENT};
    }}
"""


class PdfReaderView(QWidget):
    """单 PDF 文件的阅读视图。"""

    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc: Optional[pdf_reader.PDFDocument] = None
        self._current_path: str = ""
        self._current_zoom: str = pdf_reader.DEFAULT_ZOOM_NAME
        self._current_page: int = 0
        self._rendering = False  # 防重入
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------- 顶栏 ----------
        topbar = QFrame()
        topbar.setFixedHeight(56)
        topbar.setStyleSheet(f"""
            QFrame {{
                background: {SURFACE};
                border-bottom: 1px solid {BORDER};
            }}
        """)
        tl = QHBoxLayout(topbar)
        tl.setContentsMargins(16, 0, 16, 0)
        tl.setSpacing(10)

        # 返回
        self.btn_back = QToolButton()
        self.btn_back.setText("← 返回")
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.setStyleSheet(_TOOLBTN_QSS)
        self.btn_back.clicked.connect(self._on_back)
        tl.addWidget(self.btn_back)

        # 文件名(占位)
        self.file_label = QLabel("未打开 PDF")
        self.file_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT};
                font-family: {FONT_HEADING};
                font-size: 14px;
                font-weight: 700;
                background: transparent;
            }}
        """)
        tl.addWidget(self.file_label)

        self.meta_label = QLabel("")
        self.meta_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 11px;
                background: transparent;
            }}
        """)
        tl.addWidget(self.meta_label)

        tl.addStretch(1)

        # 缩放下拉
        zoom_lbl = QLabel("缩放")
        zoom_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        tl.addWidget(zoom_lbl)
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(list(pdf_reader.ZOOM_LEVELS.keys()))
        self.zoom_combo.setCurrentText(pdf_reader.DEFAULT_ZOOM_NAME)
        self.zoom_combo.setStyleSheet(f"""
            QComboBox {{
                background: {SURFACE_RAISED};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_XS}px;
                padding: 3px 8px;
                font-size: 11px;
                min-width: 50px;
            }}
        """)
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_changed)
        tl.addWidget(self.zoom_combo)

        tl.addSpacing(10)

        # 跳转页码
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.setStyleSheet(f"""
            QSpinBox {{
                background: {SURFACE_RAISED};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_XS}px;
                padding: 3px 8px;
                font-size: 11px;
                min-width: 60px;
            }}
        """)
        self.page_spin.valueChanged.connect(self._on_page_spin_changed)
        tl.addWidget(self.page_spin)

        self.total_label = QLabel("/ 1")
        self.total_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        tl.addWidget(self.total_label)

        root.addWidget(topbar)

        # ---------- 滚动区 + 页面标签 ----------
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{
                background: #2a354a;
                border: none;
            }}
            QScrollBar:vertical {{
                background: {SURFACE};
                width: 12px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {SURFACE_RAISED};
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {BORDER_FOCUS};
            }}
        """)
        self.page_label = QLabel()
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setStyleSheet("background: #2a354a;")
        self.page_label.setText("请打开一个 PDF 文件")
        self.page_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.scroll.setWidget(self.page_label)
        root.addWidget(self.scroll, 1)

        # ---------- 底部进度条(用 status bar) ----------
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_SECONDARY};
                font-size: 11px;
                background: {SURFACE};
                padding: 4px 16px;
                border-top: 1px solid {BORDER};
            }}
        """)
        self.status_label.setFixedHeight(24)
        root.addWidget(self.status_label)

        # 快捷键
        QShortcut(QKeySequence("PgDown"), self, activated=self._next_page)
        QShortcut(QKeySequence("Space"), self, activated=self._next_page)
        QShortcut(QKeySequence("PgUp"), self, activated=self._prev_page)
        QShortcut(QKeySequence("Right"), self, activated=self._next_page)
        QShortcut(QKeySequence("Left"), self, activated=self._prev_page)
        QShortcut(QKeySequence("Esc"), self, activated=self._on_back)
        QShortcut(QKeySequence("Home"), self, activated=lambda: self._goto_page(0))
        QShortcut(QKeySequence("End"), self, activated=self._goto_last)

    # ============================================================
    # 公开 API
    # ============================================================

    def open_pdf(self, path: str) -> bool:
        """打开一个 PDF 文件。返回是否成功。"""
        # 先关掉旧的
        self.close_pdf()
        try:
            self._doc = pdf_reader.open_pdf(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "打开失败", f"{Path(path).name}\n\n{e}")
            self._doc = None
            return False
        self._current_path = path
        self.file_label.setText(Path(path).name)
        self.meta_label.setText(
            f"· {self._doc.title}  ·  {self._doc.author}  ·  {self._doc.page_count} 页"
        )
        self.page_spin.setMaximum(self._doc.page_count)
        self.total_label.setText(f"/ {self._doc.page_count}")
        # 恢复上次的页码 / 缩放
        page, zoom = self._load_progress(path)
        if zoom in pdf_reader.ZOOM_LEVELS:
            self._current_zoom = zoom
            self.zoom_combo.setCurrentText(zoom)
        self._current_page = max(0, min(page, self._doc.page_count - 1))
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(self._current_page + 1)
        self.page_spin.blockSignals(False)
        self._render_current_page()
        return True

    def close_pdf(self):
        """关闭当前 PDF(切走前调用)。"""
        if self._doc:
            self._save_progress()
            try:
                self._doc.close()
            except Exception:
                pass
            self._doc = None
        self._current_path = ""
        self.page_label.clear()
        self.page_label.setText("请打开一个 PDF 文件")
        self.file_label.setText("未打开 PDF")
        self.meta_label.setText("")

    # ============================================================
    # 内部:渲染 / 翻页 / 缩放
    # ============================================================

    def _render_current_page(self):
        if not self._doc or self._rendering:
            return
        self._rendering = True
        try:
            img = self._doc.render_image(self._current_page, self._current_zoom)
            pm = QPixmap.fromImage(img)
            self.page_label.setPixmap(pm)
            self.page_label.setText("")
            # 状态栏
            self.status_label.setText(
                f"第 {self._current_page + 1} / {self._doc.page_count} 页  ·  "
                f"缩放: {self._current_zoom} ({pdf_reader.ZOOM_LEVELS[self._current_zoom]:.1f}×)  ·  "
                f"分辨率: {img.width()}×{img.height()}"
            )
        except Exception as e:  # noqa: BLE001
            self.page_label.setText(f"渲染失败: {e}")
        finally:
            self._rendering = False

    def _next_page(self):
        if not self._doc:
            return
        if self._current_page < self._doc.page_count - 1:
            self._current_page += 1
            self.page_spin.blockSignals(True)
            self.page_spin.setValue(self._current_page + 1)
            self.page_spin.blockSignals(False)
            self._render_current_page()
            self._save_progress()

    def _prev_page(self):
        if not self._doc:
            return
        if self._current_page > 0:
            self._current_page -= 1
            self.page_spin.blockSignals(True)
            self.page_spin.setValue(self._current_page + 1)
            self.page_spin.blockSignals(False)
            self._render_current_page()
            self._save_progress()

    def _goto_page(self, idx: int):
        if not self._doc:
            return
        idx = max(0, min(idx, self._doc.page_count - 1))
        if idx == self._current_page:
            return
        self._current_page = idx
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(idx + 1)
        self.page_spin.blockSignals(False)
        self._render_current_page()
        self._save_progress()

    def _goto_last(self):
        if not self._doc:
            return
        self._goto_page(self._doc.page_count - 1)

    def _on_page_spin_changed(self, value: int):
        self._goto_page(value - 1)

    def _on_zoom_changed(self, name: str):
        if name in pdf_reader.ZOOM_LEVELS and name != self._current_zoom:
            self._current_zoom = name
            self._render_current_page()
            self._save_progress()

    def _on_back(self):
        self.close_pdf()
        self.back_requested.emit()

    # ============================================================
    # 进度持久化
    # ============================================================

    @staticmethod
    def _progress_key(path: str) -> str:
        """按文件绝对路径的 sha256 前 16 位做 key。"""
        p = str(Path(path).resolve())
        return hashlib.sha256(p.encode("utf-8")).hexdigest()[:16]

    def _load_progress(self, path: str) -> tuple[int, str]:
        """读上次页码 + 缩放。返回 (page_0based, zoom_name)。"""
        s = QSettings("WinEBook", "PdfReader")
        key = self._progress_key(path)
        page = int(s.value(f"p_{key}", 0))
        zoom = str(s.value(f"z_{key}", pdf_reader.DEFAULT_ZOOM_NAME))
        return page, zoom

    def _save_progress(self):
        if not self._current_path:
            return
        s = QSettings("WinEBook", "PdfReader")
        key = self._progress_key(self._current_path)
        s.setValue(f"p_{key}", self._current_page)
        s.setValue(f"z_{key}", self._current_zoom)

    def shutdown(self):
        """应用退出时调用,确保关掉 doc。"""
        self.close_pdf()
