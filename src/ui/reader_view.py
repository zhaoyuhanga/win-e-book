"""阅读详情页:单本书的封面 + 章节列表 + 正文 + 进度。

设计对应 v2.html 的"详情页"风格 — 顶栏 56px 有封面缩略 + 衬线大字书名 +
返回按钮 + 字号/章节控制;主体左章节目录 / 右阅读区;底部进度条。
"""
from __future__ import annotations

import html as html_mod
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QUrl
from PySide6.QtGui import QFont, QTextOption, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QTextEdit, QTextBrowser, QProgressBar, QListWidget, QListWidgetItem, QTabWidget,
    QCheckBox, QToolButton, QFrame,
)

from src.core import Book, BookRecord, Chapter
from src.ui.theme import (
    NEXT_CHAPTER_BUTTON_HTML, LAST_CHAPTER_HTML, FONT_HEADING, pick_cover_gradient,
    READING_THEMES, DEFAULT_READING_THEME,
)


class ReaderView(QWidget):
    """单本书的阅读详情页。"""

    position_changed = Signal(int, int, float)
    back_requested = Signal()     # 用户点"返回书库"或按 Esc

    SAVE_DEBOUNCE_MS = 800
    MIN_FONT_SIZE = 11
    MAX_FONT_SIZE = 22
    DEFAULT_FONT_SIZE = 15

    def __init__(self, parent=None):
        super().__init__(parent)
        self._library = None  # type: ignore[assignment]
        self._record: Optional[BookRecord] = None
        self._book: Optional[Book] = None
        self._font_size = self.DEFAULT_FONT_SIZE
        self._auto_next_chapter = False
        # 读取持久化的阅读主题
        from PySide6.QtCore import QSettings
        s = QSettings("WinEBook", "Reader")
        self._reading_theme = str(s.value("reading_theme", DEFAULT_READING_THEME))
        if self._reading_theme not in READING_THEMES:
            self._reading_theme = DEFAULT_READING_THEME
        self._bottom_hint_timer = QTimer(self)
        self._bottom_hint_timer.setSingleShot(True)
        self._bottom_hint_timer.timeout.connect(self._maybe_auto_next)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush_position)
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ============ 顶栏(返回 + 封面 + 书名 + 控制) ============
        topbar = QFrame()
        topbar.setProperty("role", "topbar")
        topbar.setFixedHeight(96)
        tl = QHBoxLayout(topbar)
        tl.setContentsMargins(24, 12, 24, 12)
        tl.setSpacing(14)

        # 返回书库按钮
        self.btn_back = QPushButton("← 返回书库")
        self.btn_back.setProperty("compact", "true")
        self.btn_back.clicked.connect(self.back_requested.emit)
        self.btn_back.setFixedWidth(110)
        tl.addWidget(self.btn_back)

        # 封面小图(68x80 — 3:4 比例,缩略)
        self.cover_thumb = QFrame()
        self.cover_thumb.setProperty("role", "book-cover")
        self.cover_thumb.setFixedSize(68, 80)
        cv = QVBoxLayout(self.cover_thumb)
        cv.setContentsMargins(0, 0, 0, 0)
        self.cover_thumb_label = QLabel("📖")
        self.cover_thumb_label.setAlignment(Qt.AlignCenter)
        self.cover_thumb_label.setStyleSheet(
            "font-size: 28px; background: transparent;"
        )
        cv.addWidget(self.cover_thumb_label)
        tl.addWidget(self.cover_thumb)

        # 标题区(纵向:书名 + 作者)
        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        self.title_label = QLabel("未打开书籍")
        self.title_label.setStyleSheet(
            f"font-family: '{FONT_HEADING}'; font-size: 20px; font-weight: 700;"
            f" color: #e6ded2; background: transparent;"
            f" letter-spacing: 0.5px;"
        )
        self.title_label.setMaximumWidth(380)
        title_col.addWidget(self.title_label)
        self.author_label = QLabel("")
        self.author_label.setStyleSheet(
            "color: #9aa0ac; font-size: 12px; background: transparent;"
        )
        title_col.addWidget(self.author_label)
        tl.addLayout(title_col)

        tl.addStretch(1)

        # 上一章 / 下一章
        self.btn_prev = QPushButton("⟨ 上一章")
        self.btn_next = QPushButton("下一章 ⟩")
        self.btn_prev.setProperty("compact", "true")
        self.btn_next.setProperty("compact", "true")
        self.btn_prev.clicked.connect(self.prev_chapter)
        self.btn_next.clicked.connect(self.next_chapter)
        tl.addWidget(self.btn_prev)
        tl.addWidget(self.btn_next)

        # 章节选择
        tl.addSpacing(12)
        tl.addWidget(QLabel("章节:"))
        self.chapter_combo = QComboBox()
        self.chapter_combo.setMinimumWidth(220)
        self.chapter_combo.currentIndexChanged.connect(self._on_chapter_changed)
        tl.addWidget(self.chapter_combo)

        # 字号
        tl.addSpacing(12)
        self.btn_font_smaller = QToolButton()
        self.btn_font_smaller.setText("A-")
        self.btn_font_smaller.setToolTip("缩小字号 (Ctrl + -)")
        self.btn_font_smaller.clicked.connect(self._font_smaller)
        tl.addWidget(self.btn_font_smaller)

        self.font_label = QLabel(f"{self._font_size}")
        self.font_label.setMinimumWidth(24)
        self.font_label.setAlignment(Qt.AlignCenter)
        self.font_label.setStyleSheet(
            "color: #9aa0ac; font-size: 11px; background: transparent;"
        )
        tl.addWidget(self.font_label)

        self.btn_font_larger = QToolButton()
        self.btn_font_larger.setText("A+")
        self.btn_font_larger.setToolTip("放大字号 (Ctrl + +)")
        self.btn_font_larger.clicked.connect(self._font_larger)
        tl.addWidget(self.btn_font_larger)

        # 主题下拉
        tl.addSpacing(12)
        from PySide6.QtWidgets import QComboBox as _CB
        self.theme_combo = _CB()
        self.theme_combo.setMinimumWidth(140)
        self.theme_combo.setToolTip("阅读背景主题")
        for key, theme in READING_THEMES.items():
            self.theme_combo.addItem(theme["name"], userData=key)
        # 选中持久化的主题
        idx = list(READING_THEMES.keys()).index(self._reading_theme)
        self.theme_combo.setCurrentIndex(idx)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        tl.addWidget(self.theme_combo)

        root.addWidget(topbar)

        # ============ 中间选项条 ============
        opts_bar = QFrame()
        opts_bar.setStyleSheet(
            "QFrame { background: #0f1724; border-bottom: 1px solid #2a354a; }"
        )
        ol = QHBoxLayout(opts_bar)
        ol.setContentsMargins(24, 8, 24, 8)
        self.chk_auto_next = QCheckBox("滚到底自动加载下一章")
        self.chk_auto_next.setToolTip("开启后,读到当前章节末尾自动跳到下一章")
        self.chk_auto_next.toggled.connect(self._on_auto_next_toggled)
        ol.addWidget(self.chk_auto_next)
        ol.addStretch(1)
        hint = QLabel("← → 切章 · Esc 返回书库 · Ctrl++/-- 字号 · 双击历史回看")
        hint.setStyleSheet("color: #6b7384; font-size: 11px;")
        ol.addWidget(hint)
        root.addWidget(opts_bar)

        # ============ 主体:左侧栏 / 右阅读 ============
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # 左侧栏(surface 色,290px)
        side = QFrame()
        side.setFixedWidth(290)
        side.setStyleSheet(
            "QFrame { background: #1a2336; border-right: 1px solid #2a354a; }"
        )
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)

        self.side_tabs = QTabWidget()
        self.side_tabs.setStyleSheet(
            "QTabWidget::pane { background: #1a2336; border: none; top: 0; }"
            "QTabBar { background: #1a2336; }"
            "QTabBar::tab { background: transparent; padding: 10px 18px;"
            "  color: #9aa0ac; min-width: 50px; font-size: 12px; }"
            "QTabBar::tab:selected { background: #1f2a3d; color: #c8946e;"
            "  font-weight: 600; border-bottom: 2px solid #c8946e; }"
        )
        self.chapter_list = QListWidget()
        self.chapter_list.setStyleSheet(
            "QListWidget { background: transparent; border: none; padding: 6px; }"
            "QListWidget::item { padding: 9px 10px; border-radius: 5px;"
            "  margin: 2px 4px; color: #9aa0ac; font-size: 12px; }"
            "QListWidget::item:hover { background: #1f2a3d; color: #e6ded2; }"
            "QListWidget::item:selected { background: #c8946e; color: #fff;"
            "  font-weight: 600; }"
        )
        self.chapter_list.itemClicked.connect(self._on_chapter_list_clicked)
        self.side_tabs.addTab(self.chapter_list, "📖 目录")
        self.history_list = QListWidget()
        self.history_list.setStyleSheet(self.chapter_list.styleSheet())
        self.history_list.itemDoubleClicked.connect(self._on_history_activated)
        self.side_tabs.addTab(self.history_list, "🕓 历史")
        sl.addWidget(self.side_tabs)
        body.addWidget(side)

        # 右侧:阅读正文 + 底部进度
        right = QWidget()
        right.setStyleSheet("background: #0f1724;")
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(0)

        self.text = QTextBrowser()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QTextEdit.WidgetWidth)
        self.text.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.text.setOpenLinks(False)
        self.text.setOpenExternalLinks(False)
        self._apply_font_size()
        self.text.anchorClicked.connect(self._on_anchor_clicked)
        self.text.verticalScrollBar().valueChanged.connect(self._on_scroll)
        right_l.addWidget(self.text, 1)

        # 底部进度
        prog_bar = QFrame()
        prog_bar.setStyleSheet(
            "QFrame { background: #1a2336; border-top: 1px solid #2a354a; }"
        )
        pl = QHBoxLayout(prog_bar)
        pl.setContentsMargins(24, 8, 24, 8)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        pl.addWidget(self.progress, 1)
        self.progress_label = QLabel("0%")
        self.progress_label.setMinimumWidth(50)
        self.progress_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.progress_label.setStyleSheet("color: #9aa0ac; font-size: 12px;")
        pl.addWidget(self.progress_label)
        right_l.addWidget(prog_bar)

        body.addWidget(right, 1)
        root.addLayout(body, 1)

        # 快捷键
        QShortcut(QKeySequence("Right"), self, activated=self.next_chapter)
        QShortcut(QKeySequence("Left"), self, activated=self.prev_chapter)
        QShortcut(QKeySequence("Ctrl+Right"), self, activated=self.next_chapter)
        QShortcut(QKeySequence("Ctrl+Left"), self, activated=self.prev_chapter)
        QShortcut(QKeySequence("Ctrl+H"), self,
                  activated=lambda: self.side_tabs.setCurrentIndex(1))
        QShortcut(QKeySequence("Ctrl++"), self, activated=self._font_larger)
        QShortcut(QKeySequence("Ctrl+="), self, activated=self._font_larger)
        QShortcut(QKeySequence("Ctrl+-"), self, activated=self._font_smaller)
        QShortcut(QKeySequence("Ctrl+0"), self, activated=self._font_reset)
        QShortcut(QKeySequence("Escape"), self, activated=self.back_requested.emit)

        # 应用持久化的阅读主题(关键:开头就要应用,否则全局 QSS 接管)
        self._apply_reading_theme()

        self._set_actions_enabled(False)

    def set_library(self, library):
        self._library = library

    # ---------- 字号 ----------
    def _apply_font_size(self):
        f = QFont()
        f.setPointSize(self._font_size)
        self.text.setFont(f)
        self.font_label.setText(f"{self._font_size}")

    def _font_larger(self):
        if self._font_size < self.MAX_FONT_SIZE:
            self._font_size += 1
            self._apply_font_size()

    def _font_smaller(self):
        if self._font_size > self.MIN_FONT_SIZE:
            self._font_size -= 1
            self._apply_font_size()

    def _font_reset(self):
        self._font_size = self.DEFAULT_FONT_SIZE
        self._apply_font_size()

    def _on_auto_next_toggled(self, checked: bool):
        self._auto_next_chapter = checked

    # ---------- 阅读主题 ----------
    def _on_theme_changed(self, idx: int):
        key = self.theme_combo.itemData(idx)
        if not key or key not in READING_THEMES:
            return
        self._reading_theme = key
        from PySide6.QtCore import QSettings
        QSettings("WinEBook", "Reader").setValue("reading_theme", key)
        self._apply_reading_theme()
        # 如果当前打开了书,重新渲染章节(因为 HTML 用主题色)
        if self._book is not None:
            idx_now = self.chapter_combo.currentIndex()
            if idx_now >= 0:
                self._show_chapter(idx_now)

    def _apply_reading_theme(self):
        """应用阅读主题 — 用 inline style 强制 QTextBrowser 颜色,防 QSS cascade 失效。"""
        theme = READING_THEMES[self._reading_theme]
        bg = theme["bg"]
        text = theme["text"]
        scroll = theme["scroll"]
        border = theme["border"]
        # 强制设置(覆盖全局 QSS 和任何 parent cascade)
        self.text.setStyleSheet(
            f"QTextBrowser {{"
            f" background: {bg};"
            f" color: {text};"
            f" border: 1px solid {border};"
            f" border-radius: 8px;"
            f" padding: 32px 56px;"
            f" selection-background-color: {theme['next_btn_bg']};"
            f" selection-color: {theme['next_btn_text']};"
            f" }}"
            f"QTextBrowser QScrollBar:vertical {{"
            f" background: transparent; width: 10px;"
            f" }}"
            f"QTextBrowser QScrollBar::handle:vertical {{"
            f" background: {scroll};"
            f" border-radius: 5px; min-height: 30px;"
            f" }}"
            f"QTextBrowser QScrollBar::handle:vertical:hover {{"
            f" background: {theme['next_btn_bg']};"
            f" }}"
            f"QTextBrowser QScrollBar::add-line:vertical,"
            f"QTextBrowser QScrollBar::sub-line:vertical {{"
            f" height: 0;"
            f" }}"
        )

    # ---------- 加载/卸载 ----------
    def open_book(self, record: BookRecord, book: Book):
        self._record = record
        self._book = book

        # 顶栏书名
        self.title_label.setText(book.title)
        self.title_label.setToolTip(book.title)
        # 截断过长
        fm = self.title_label.fontMetrics()
        elided = fm.elidedText(book.title, Qt.ElideRight, 380)
        self.title_label.setText(elided)
        self.author_label.setText(
            f"作者: {book.author}" if book.author else "未知作者"
        )

        # 顶栏封面缩略(用 inline style 设渐变,因为需要按 book 动态选)
        self.cover_thumb.setStyleSheet(
            f"QFrame[role=\"book-cover\"] {{"
            f" background: {pick_cover_gradient(book.title)};"
            f" border: 1px solid #2a354a;"
            f" }}"
            f"QLabel {{ background: transparent; }}"
        )

        # 章节下拉
        self.chapter_combo.blockSignals(True)
        self.chapter_combo.clear()
        for i, ch in enumerate(book.chapters, start=1):
            label = f"第 {i:04d} 章 · {ch.title}"
            self.chapter_combo.addItem(label, userData=i - 1)
        self.chapter_combo.blockSignals(False)

        # 章节列表
        self.chapter_list.clear()
        for i, ch in enumerate(book.chapters, start=1):
            it = QListWidgetItem(f"第 {i:04d} 章   {ch.title}")
            it.setData(Qt.UserRole, i - 1)
            self.chapter_list.addItem(it)

        self._set_actions_enabled(True)
        self._refresh_history()

        # 定位上次阅读位置
        idx = max(0, min(record.last_chapter_index, len(book.chapters) - 1))
        self.chapter_combo.setCurrentIndex(idx)
        self._show_chapter(idx, restore_offset=record.last_offset_in_chapter)
        self._update_progress()

    def clear(self):
        self._record = None
        self._book = None
        self.title_label.setText("未打开书籍")
        self.author_label.setText("")
        self.chapter_combo.clear()
        self.chapter_list.clear()
        self.history_list.clear()
        self.text.clear()
        self.progress.setValue(0)
        self.progress_label.setText("0%")
        self._set_actions_enabled(False)

    # ---------- 章节切换 ----------
    def prev_chapter(self):
        if self._book is None:
            return
        i = self.chapter_combo.currentIndex()
        if i > 0:
            self.chapter_combo.setCurrentIndex(i - 1)

    def next_chapter(self):
        if self._book is None:
            return
        i = self.chapter_combo.currentIndex()
        if i < self.chapter_combo.count() - 1:
            self.chapter_combo.setCurrentIndex(i + 1)

    def _on_chapter_changed(self, idx: int):
        if self._book is None or idx < 0:
            return
        self._flush_position()
        self._show_chapter(idx, restore_offset=0)
        if self._library and self._record:
            ch = self._book.chapters[idx]
            self._library.save_position(
                book_id=self._record.id, chapter_index=idx,
                offset_in_chapter=0, progress=self._compute_progress(idx, 0),
                chapter_title=ch.title, action="chapter",
            )
            self._refresh_history()
        # 同步章节列表选中
        if idx >= 0 and idx < self.chapter_list.count():
            self.chapter_list.setCurrentRow(idx)

    def _on_chapter_list_clicked(self, item):
        idx = int(item.data(Qt.UserRole))
        if idx != self.chapter_combo.currentIndex():
            self.chapter_combo.setCurrentIndex(idx)

    def _on_anchor_clicked(self, url: QUrl):
        if url.toString() == "next-chapter":
            self.next_chapter()

    def _show_chapter(self, idx: int, restore_offset: int = 0):
        if self._book is None:
            return
        ch = self._book.chapters[idx]
        html = self._render_chapter_html(ch, idx)
        self.text.setHtml(html)
        if restore_offset > 0:
            block = self._find_block_by_offset(ch, restore_offset)
            if block is not None:
                # PySide6 的 QTextBrowser / QTextEdit 没有 scrollToBlock,
                # 用 cursor.setPosition + ensureCursorVisible 来滚动
                cursor = QTextCursor(block)
                self.text.setTextCursor(cursor)
                self.text.ensureCursorVisible()
        else:
            cursor = self.text.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.text.setTextCursor(cursor)

    def _render_chapter_html(self, ch: Chapter, idx: int = 0) -> str:
        # 用当前主题色渲染章节 HTML
        theme = READING_THEMES[self._reading_theme]
        title_color = theme["title"]
        text_color = theme["text"]
        next_btn_bg = theme["next_btn_bg"]
        next_btn_text = theme["next_btn_text"]
        next_card_border = theme["next_card_border"]
        next_card_text = theme["next_card_text"]
        next_card_caption = theme["next_card_caption"]
        last_card_border = next_card_border
        last_card_text = theme["title"]
        last_card_sub = next_card_caption

        safe_title = html_mod.escape(ch.title)
        body = ch.content.split("\n")
        parts = [
            '<div style="text-align:center; margin: 20px 0 28px 0;">',
            f'  <h1 style="font-family: {FONT_HEADING}; font-size: 26px;'
            f' color: {title_color}; margin: 0; font-weight: 700;'
            f' letter-spacing: 1px;">{safe_title}</h1>',
            f'  <div style="font-family: {FONT_HEADING}; font-size: 12px;'
            f' color: {next_card_caption}; margin-top: 10px; letter-spacing: 3px;">'
            f'第 {idx + 1} 章</div>',
            '</div>',
        ]
        for line in body:
            t = line.strip()
            if not t:
                continue
            parts.append(
                f'<p style="line-height: 1.95; text-indent: 2em; '
                f'font-size: {self._font_size}px; margin: 10px 0; '
                f'color: {text_color};">'
                f'{html_mod.escape(t)}</p>'
            )
        if self._book and idx < len(self._book.chapters) - 1:
            next_ch = self._book.chapters[idx + 1]
            next_title = html_mod.escape(next_ch.title)
            next_card = f'''
<div style="margin: 40px 0 16px 0; padding: 28px; text-align: center;
            background: {theme["subtle"]};
            border-radius: 8px; border: 1px solid {next_card_border};">
  <div style="font-family: {FONT_HEADING}; font-size: 11px;
              color: {next_card_caption}; margin-bottom: 6px;
              letter-spacing: 3px;">本章节结束</div>
  <div style="font-family: {FONT_HEADING}; font-size: 16px;
              font-weight: 700; color: {next_card_text}; margin-bottom: 18px;">
    下一章:{next_title}
  </div>
  <a href="next-chapter" style="display: inline-block; padding: 12px 36px;
            background: {next_btn_bg}; color: {next_btn_text};
            border-radius: 5px; font-weight: 600; font-size: 14px;
            text-decoration: none;">↓ 继续阅读 ↓</a>
  <div style="margin-top: 12px; font-size: 11px; color: {next_card_caption};">
    按 ← / → 键也可切章
  </div>
</div>'''
            parts.append(next_card)
        else:
            last_card = f'''
<div style="margin: 40px 0 16px 0; padding: 40px; text-align: center;
            background: {theme["bg"]};
            border-radius: 8px; border: 1px solid {last_card_border};">
  <div style="font-size: 28px; margin-bottom: 12px;">📜</div>
  <div style="font-family: {FONT_HEADING}; font-size: 20px;
              font-weight: 700; color: {last_card_text};
              margin-bottom: 8px;">恭喜!全书读完了</div>
  <div style="font-size: 13px; color: {last_card_sub};">
    已到达最后一章 — 你真是太自律了
  </div>
</div>'''
            parts.append(last_card)
        return (
            "<div style='font-family:\"Microsoft YaHei\",\"Source Han Sans SC\","
            "\"Noto Sans CJK SC\",\"Segoe UI\",sans-serif; max-width: 720px;"
            " margin: 0 auto; color: " + text_color + ";'>"
            + "\n".join(parts) + "</div>"
        )

    def _find_block_by_offset(self, ch: Chapter, offset: int):
        doc = self.text.document()
        cum = 0
        for i, para in enumerate(ch.content.split("\n")):
            t = para.strip()
            if not t:
                continue
            cum += len(t)
            if cum >= offset:
                block = doc.findBlockByNumber(i + 1)
                if block.isValid():
                    return block
                return None
        return None

    # ---------- 滚动 / 进度 ----------
    def _on_scroll(self, _value):
        if self._book is None:
            return
        self._update_progress()
        self._save_timer.start(self.SAVE_DEBOUNCE_MS)
        sb = self.text.verticalScrollBar()
        if sb.maximum() > 0 and sb.value() >= sb.maximum() - 40:
            self._bottom_hint_timer.start(600)

    def _maybe_auto_next(self):
        if not self._auto_next_chapter or self._book is None:
            return
        sb = self.text.verticalScrollBar()
        if sb.maximum() <= 0:
            return
        if sb.value() < sb.maximum() - 60:
            return
        i = self.chapter_combo.currentIndex()
        if i < self.chapter_combo.count() - 1:
            self.chapter_combo.setCurrentIndex(i + 1)

    def _compute_progress(self, chapter_idx: int, offset_in_chapter: int) -> float:
        if self._book is None or not self._book.chapters:
            return 0.0
        total = sum(len(c.content) for c in self._book.chapters) or 1
        done = sum(len(c.content) for c in self._book.chapters[:chapter_idx]) + offset_in_chapter
        return max(0.0, min(1.0, done / total))

    def _current_offset_in_chapter(self) -> int:
        if self._book is None:
            return 0
        idx = self.chapter_combo.currentIndex()
        if idx < 0 or idx >= len(self._book.chapters):
            return 0
        ch = self._book.chapters[idx]
        sb = self.text.verticalScrollBar()
        rng = max(1, sb.maximum() - sb.minimum())
        ratio = (sb.value() - sb.minimum()) / rng
        return int(ratio * len(ch.content))

    def _update_progress(self):
        if self._book is None:
            return
        idx = self.chapter_combo.currentIndex()
        if idx < 0:
            return
        offset = self._current_offset_in_chapter()
        prog = self._compute_progress(idx, offset)
        self.progress.setValue(int(prog * 1000))
        self.progress_label.setText(f"{int(prog * 100)}%")

    def _flush_position(self):
        if self._library is None or self._record is None or self._book is None:
            return
        idx = self.chapter_combo.currentIndex()
        if idx < 0:
            return
        offset = self._current_offset_in_chapter()
        prog = self._compute_progress(idx, offset)
        self.position_changed.emit(idx, offset, prog)
        self._library.storage.save_position(self._record.id, idx, offset, prog)

    # ---------- 历史 ----------
    def _refresh_history(self):
        self.history_list.clear()
        if self._library is None or self._record is None:
            return
        for h in self._library.history(self._record.id, limit=200):
            import datetime as _dt
            ts = _dt.datetime.fromtimestamp(h.opened_at).strftime("%m-%d %H:%M")
            action_cn = {"open": "打开", "chapter": "切章", "progress": "滚动"}.get(h.action, h.action)
            ch_label = h.chapter_title or f"第{h.chapter_index + 1}章"
            it = QListWidgetItem(f"[{ts}] {action_cn}  ·  {ch_label}")
            it.setData(Qt.UserRole, h.chapter_index)
            self.history_list.addItem(it)

    def _on_history_activated(self, item):
        idx = int(item.data(Qt.UserRole))
        if self._book and 0 <= idx < len(self._book.chapters):
            self.chapter_combo.setCurrentIndex(idx)

    # ---------- helpers ----------
    def _set_actions_enabled(self, enabled: bool):
        self.chapter_combo.setEnabled(enabled)
        self.btn_prev.setEnabled(enabled)
        self.btn_next.setEnabled(enabled)
        self.text.setEnabled(enabled)
