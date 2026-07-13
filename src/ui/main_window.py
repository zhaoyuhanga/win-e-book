"""主窗口:用 QStackedWidget 实现多页切换。

Page 0 = 首页(墨软,墨读/墨写入口)
Page 1 = 书库(LibraryList)
Page 2 = 阅读详情页(ReaderView)
Page 3 = 在线书库(OnlineView)
Page 4 = 墨写(WriteView)
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut, QFont, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QStatusBar, QMessageBox, QLabel, QWidget, QToolButton,
    QVBoxLayout, QHBoxLayout, QLineEdit, QFrame, QStackedWidget,
)

from src.core import Library, BookRecord, Book
from src.ui.library_view import LibraryList
from src.ui.reader_view import ReaderView
from src.ui.online_view import OnlineView
from src.ui.home_view import HomeView
from src.ui.write_view import WriteView
from src.ui.theme import THEME_QSS, FONT_HEADING, ACCENT, TEXT_SECONDARY, SURFACE, BORDER


# ============================================================
# 顶栏(品牌条)
# ============================================================

class TopBar(QFrame):
    """顶部品牌条(56px)。"""

    home_clicked = Signal()  # 用户点了"墨软 / 返回首页"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "topbar")
        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(14)

        # logo(可点击,作"返回首页"按钮)
        self.logo = QLabel("墨")
        self.logo.setAlignment(Qt.AlignCenter)
        self.logo.setFixedSize(36, 36)
        self.logo.setCursor(Qt.PointingHandCursor)
        self.logo.setStyleSheet(
            "QLabel {"
            " background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            "   stop:0 #c8946e, stop:1 #a07352);"
            " color: #fff; border-radius: 6px;"
            " font-family: 'Georgia', 'Times New Roman', 'Noto Serif SC', serif;"
            " font-size: 20px; font-weight: 700;"
            "}"
        )
        layout.addWidget(self.logo)

        # 品牌名(也可点回首页)
        self.brand_name = QLabel("墨软")
        self.brand_name.setProperty("role", "brand-name")
        self.brand_name.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.brand_name)

        # tagline
        tagline = QLabel("·  经典阅读  ·  智能写作")
        tagline.setStyleSheet(
            "QLabel { color: #6b7384; font-size: 12px; background: transparent; }"
        )
        layout.addWidget(tagline)

        # 搜索框(主页用)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索书名、作者…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMaximumWidth(360)
        layout.addWidget(self.search_input, 1, Qt.AlignCenter)

        layout.addStretch(1)

        # 返回首页按钮(只在非首页时显示)
        self.btn_home = QToolButton()
        self.btn_home.setText("⌂  墨软")
        self.btn_home.setToolTip("返回首页(墨读 / 墨写 入口)")
        self.btn_home.setCursor(Qt.PointingHandCursor)
        self.btn_home.setStyleSheet(
            "QToolButton {"
            f"  background: transparent; color: {TEXT_SECONDARY};"
            f"  border: 1px solid {BORDER}; border-radius: 5px;"
            "  padding: 4px 10px; font-size: 12px;"
            "}"
            f"QToolButton:hover {{ color: {ACCENT}; border: 1px solid {ACCENT}; }}"
        )
        self.btn_home.clicked.connect(self.home_clicked)
        self.btn_home.hide()  # 默认隐藏
        layout.addWidget(self.btn_home)

        # 右侧
        self.subtitle = QLabel("v1.0 · dev-v1")
        self.subtitle.setStyleSheet(
            "QLabel { color: #6b7384; font-size: 11px; background: transparent; }"
        )
        layout.addWidget(self.subtitle)

    def mousePressEvent(self, ev):
        # 点 logo / 品牌名 → 返回首页
        if ev.button() == Qt.LeftButton and self.underMouse():
            self.home_clicked.emit()
        super().mousePressEvent(ev)


# ============================================================
# 主窗口
# ============================================================

class MainWindow(QMainWindow):
    PAGE_HOME    = 0  # 墨软首页
    PAGE_LIBRARY = 1  # 墨读书库
    PAGE_READER  = 2  # 阅读详情页
    PAGE_ONLINE  = 3  # 在线书库
    PAGE_WRITE   = 4  # 墨写

    def __init__(self, library: Library):
        super().__init__()
        self.library = library
        self.setWindowTitle("墨软 · 墨读 + 墨写")
        self.resize(1280, 820)
        self.setStyleSheet(THEME_QSS)

        # 中央(顶栏 + QStackedWidget)
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # 顶栏(多页共用)
        self.topbar = TopBar()
        self.topbar.home_clicked.connect(self._go_home)
        # 让 logo / 品牌名 也可点击回首页
        for w in (self.topbar.logo, self.topbar.brand_name):
            w.mousePressEvent = self._logo_clicked
        central_layout.addWidget(self.topbar)

        # Stacked pages
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_home_page())    # 0
        self.stack.addWidget(self._build_library_page()) # 1
        self.stack.addWidget(self._build_reader_page())  # 2
        self.stack.addWidget(self._build_online_page())  # 3
        self.stack.addWidget(self._build_write_page())   # 4
        central_layout.addWidget(self.stack, 1)

        self.setCentralWidget(central)

        # 菜单
        self._build_menu()

        # 状态栏
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #9aa0ac;")
        self.status.addPermanentWidget(self.status_label, 1)

        # 快捷键
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._import_via_shortcut)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._go_online)
        QShortcut(QKeySequence("Ctrl+Alt+L"), self, activated=self._go_online)
        QShortcut(QKeySequence("Ctrl+Alt+W"), self, activated=self._go_write)
        QShortcut(QKeySequence("Ctrl+Alt+H"), self, activated=self._go_home)
        QShortcut(QKeySequence("Ctrl+Alt+R"), self, activated=self._go_library)

        # 默认在首页
        self.stack.setCurrentIndex(self.PAGE_HOME)
        self._update_topbar_for_page()

    def _build_home_page(self) -> QWidget:
        """墨软首页。"""
        self.home_view = HomeView()
        self.home_view.enter_read.connect(self._go_library)
        self.home_view.enter_write.connect(self._go_write)
        return self.home_view

    def _build_write_page(self) -> QWidget:
        """墨写页(三栏:文件树/编辑器/AI 助手)。"""
        self.write_view = WriteView()
        return self.write_view

    def _build_library_page(self) -> QWidget:
        """主页:书库网格。"""
        self.library_view = LibraryList()
        self.library_view.set_library(self.library)
        self.library_view.book_selected.connect(self._on_book_selected)
        self.library_view.books_imported.connect(self._refresh_reader_history)
        # 同步搜索框 — 主页激活时启用,在 reader/online 页禁用
        self.topbar.search_input.textChanged.connect(self._on_search_changed)
        return self.library_view

    def _build_reader_page(self) -> QWidget:
        """阅读页。"""
        self.reader_view = ReaderView()
        self.reader_view.set_library(self.library)
        self.reader_view.position_changed.connect(self._on_position_changed)
        self.reader_view.back_requested.connect(self._back_to_library)
        return self.reader_view

    def _build_online_page(self) -> QWidget:
        """在线书库页:搜索 + 目录 + 在线阅读 + 下载。"""
        self.online_view = OnlineView()
        # 默认源
        from PySide6.QtCore import QSettings
        s = QSettings("WinEBook", "Main")
        last_url = str(s.value("online_base_url", "https://www.biququ.com"))
        self.online_view.set_base_url(last_url)
        # 下载完成信号
        self.online_view.book_downloaded.connect(self._on_book_downloaded)
        self.online_view.source_combo.currentIndexChanged.connect(self._save_online_url)
        return self.online_view

    def _save_online_url(self, *_args):
        url = self.online_view.source_combo.currentData() or self.online_view.base_url_input.text().strip()
        if url:
            from PySide6.QtCore import QSettings
            QSettings("WinEBook", "Main").setValue("online_base_url", url)

    def _on_book_downloaded(self, file_path: str):
        """在线页下载完成后:导入到本地书库 + 切回主页。"""
        try:
            self.library.import_path(file_path)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"下载完成但导入失败:\n{e}")
            return
        # 切回主页 + 刷新
        self.stack.setCurrentIndex(self.PAGE_LIBRARY)
        self.library_view.refresh()
        self._update_topbar_for_page()
        QMessageBox.information(self, "✓ 导入成功",
                               f"已加入书库:\n{os.path.basename(file_path)}")

    def _on_search_changed(self, text: str):
        """主页搜索:文本匹配书名/作者,hide 不匹配的卡片。"""
        q = text.strip().lower()
        if not q:
            for i in range(self.library_view.list.count()):
                self.library_view.list.item(i).setHidden(False)
            return
        for i in range(self.library_view.list.count()):
            item = self.library_view.list.item(i)
            widget = self.library_view.list.itemWidget(item)
            if widget is None:
                continue
            title = getattr(widget.record, "title", "")
            author = getattr(widget.record, "author", "")
            visible = (q in title.lower()) or (q in author.lower())
            item.setHidden(not visible)

    # ---------- 菜单 ----------
    def _build_menu(self):
        m = self.menuBar()
        file_menu = m.addMenu("文件(&F)")
        act_import = QAction("导入电子书(&I)", self)
        act_import.setShortcut("Ctrl+O")
        act_import.triggered.connect(self._import_via_shortcut)
        file_menu.addAction(act_import)
        file_menu.addSeparator()
        act_quit = QAction("退出(&Q)", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        view_menu = m.addMenu("视图(&V)")

        act_soft = QAction("墨软首页(&M)  Ctrl+Alt+H", self)
        act_soft.setShortcut("Ctrl+Alt+H")
        act_soft.triggered.connect(self._go_home)
        view_menu.addAction(act_soft)

        act_lib = QAction("墨读·本地书库(&L)  Ctrl+Alt+R", self)
        act_lib.setShortcut("Ctrl+Alt+R")
        act_lib.triggered.connect(self._go_library)
        view_menu.addAction(act_lib)

        act_write = QAction("墨写·写作助手(&W)  Ctrl+Alt+W", self)
        act_write.setShortcut("Ctrl+Alt+W")
        act_write.triggered.connect(self._go_write)
        view_menu.addAction(act_write)

        act_online = QAction("在线书库(&O)  Ctrl+Alt+L", self)
        act_online.setShortcut("Ctrl+Alt+L")
        act_online.triggered.connect(self._go_online)
        view_menu.addAction(act_online)

        help_menu = m.addMenu("帮助(&H)")
        act_about = QAction("关于(&A)", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    # ---------- 行为 ----------
    def _import_via_shortcut(self):
        self.stack.setCurrentIndex(self.PAGE_LIBRARY)
        self.library_view._on_import_clicked()

    def _go_home(self):
        """切到墨软首页。"""
        self.stack.setCurrentIndex(self.PAGE_HOME)
        self.status_label.setText("墨软  ·  选择模块:墨读 / 墨写")
        self._update_topbar_for_page()

    def _logo_clicked(self, ev):
        if ev.button() == Qt.LeftButton:
            self._go_home()

    def _go_library(self):
        """切到墨读书库。"""
        self.stack.setCurrentIndex(self.PAGE_LIBRARY)
        self.status_label.setText("墨读  ·  本地书库")
        self._update_topbar_for_page()

    def _go_write(self):
        """切到墨写。"""
        self.stack.setCurrentIndex(self.PAGE_WRITE)
        self.status_label.setText("墨写  ·  LLM 写作助手")
        self._update_topbar_for_page()

    def _go_online(self):
        """切到在线书库页。"""
        self.stack.setCurrentIndex(self.PAGE_ONLINE)
        self.status_label.setText("在线书库(联网请选择来源 + 搜索关键字)")
        self._update_topbar_for_page()

    def _update_topbar_for_page(self):
        """根据当前页更新顶栏:在首页时隐藏"返回首页"按钮,其他页显示。"""
        if self.stack.currentIndex() == self.PAGE_HOME:
            self.topbar.btn_home.hide()
        else:
            self.topbar.btn_home.show()

    def _auto_open_last_or_library(self):
        """(保留兼容)原本用于自动开上次读的书,新版默认停在首页不自动开。"""
        recs = self.library.list_books()
        if not recs:
            self.status_label.setText("欢迎使用墨软  ·  点击「墨读」或「墨写」卡片开始  ·  Ctrl+Alt+L 联网搜书")
            return
        n_books = len(recs)
        self.status_label.setText(f"墨软  ·  书库共 {n_books} 本书  ·  点击卡片开始")

    def _on_book_selected(self, book_id: int):
        try:
            rec, book = self.library.load_for_reading(book_id)
        except Exception as e:
            QMessageBox.critical(self, "打开失败", str(e))
            return
        self.reader_view.open_book(rec, book)
        self.stack.setCurrentIndex(self.PAGE_READER)
        self.status_label.setText(
            f"《{book.title}》共 {len(book.chapters)} 章 · "
            f"上次读到第 {rec.last_chapter_index + 1} 章 "
            f"({int(rec.last_progress * 100)}%)"
        )

    def _on_position_changed(self, _idx, _offset, _prog):
        if self.reader_view._book is None:
            return
        idx = self.reader_view.chapter_combo.currentIndex()
        ch = self.reader_view._book.chapters[idx]
        self.status_label.setText(
            f"《{self.reader_view._book.title}》 第 {idx + 1}/{len(self.reader_view._book.chapters)} 章  ·  "
            f"{ch.title}  ·  {int(_prog * 100)}%"
        )

    def _back_to_library(self):
        self.status_label.setText("就绪")
        self.stack.setCurrentIndex(self.PAGE_LIBRARY)
        self.library_view.refresh()
        self._update_topbar_for_page()

    def _refresh_reader_history(self):
        if self.reader_view._record is not None:
            self.reader_view._refresh_history()

    def _show_about(self):
        QMessageBox.about(
            self, "关于 墨读",
            "墨读 · WinEBook  本地电子书阅读器\n\n"
            "格式:txt / epub\n"
            "功能:章节解析、阅读进度记忆、历史回看\n"
            "在线:搜索/目录/在线阅读/批量下载(笔趣阁类源)\n"
            "数据:本地 SQLite"
        )

    def closeEvent(self, ev):
        try:
            self.reader_view._flush_position()
        except Exception:
            pass
        try:
            # 关闭墨写后台 LLM 线程
            if hasattr(self, "write_view"):
                self.write_view.shutdown()
        except Exception:
            pass
        try:
            self.library.storage.close()
        except Exception:
            pass
        super().closeEvent(ev)
