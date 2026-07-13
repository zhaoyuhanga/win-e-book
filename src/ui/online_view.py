"""在线书库页面:搜索 → 目录 → 在线阅读,支持下整本到本地。"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QThread, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame,
    QListWidget, QListWidgetItem, QMessageBox, QProgressDialog, QComboBox,
    QToolButton, QSizePolicy, QApplication, QPlainTextEdit, QDialog, QDialogButtonBox,
)

from src.core.online import (
    NovelSource, NovelInfo, NovelDetail, ChapterInfo, DownloadProgress, NetworkError,
)


# 常用的小说源 base_url 候选(都是免费源,域名会变,用户可在 UI 改)
DEFAULT_SOURCES = [
    ("笔趣阁类(默认)", "https://www.biququ.com"),
    ("备用 A",            "https://www.biququ.la"),
    ("备用 B",            "https://www.50zw.la"),
    ("备用 C",            "https://www.69shu.pro"),
    ("自定义…",           ""),
]

DOWNLOAD_DIR = Path.home() / "Downloads" / "WinEBook"


class _DownloadWorker(QThread):
    """后台下载线程 — 不阻塞 UI。"""

    progress = Signal(object)   # DownloadProgress
    done = Signal(str)          # 完成的文件路径
    error = Signal(str)

    def __init__(self, source: NovelSource, novel_url: str, save_dir: Path):
        super().__init__()
        self.source = source
        self.novel_url = novel_url
        self.save_dir = save_dir

    def run(self):
        try:
            path = self.source.download_novel(
                self.novel_url, self.save_dir,
                on_progress=lambda p: self.progress.emit(p),
            )
            self.done.emit(str(path))
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


class _SearchWorker(QThread):
    """后台搜索 — 不阻塞 UI。"""
    results = Signal(list)       # List[NovelInfo]
    error = Signal(str)
    def __init__(self, source: NovelSource, keyword: str):
        super().__init__()
        self.source = source
        self.keyword = keyword
    def run(self):
        try:
            res = self.source.search(self.keyword)
            self.results.emit(res)
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


class _CatalogWorker(QThread):
    """后台加载目录。"""
    detail = Signal(object)      # NovelDetail
    error = Signal(str)
    def __init__(self, source: NovelSource, novel_url: str):
        super().__init__()
        self.source = source
        self.novel_url = novel_url
    def run(self):
        try:
            d = self.source.get_catalog(self.novel_url)
            self.detail.emit(d)
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


class _ChapterWorker(QThread):
    """后台加载章节正文。"""
    chapter = Signal(str, str)   # url, raw_text
    error = Signal(str)
    def __init__(self, source: NovelSource, chapter_url: str):
        super().__init__()
        self.source = source
        self.chapter_url = chapter_url
    def run(self):
        try:
            t, body = self.source.get_chapter(self.chapter_url)
            self.chapter.emit(self.chapter_url, body)
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


class OnlineView(QWidget):
    """在线书库页面:搜索 → 选书 → 目录 → 章节(在线阅读/批量下载)。"""

    # 完成下载后,主窗口把文件导入书库用
    book_downloaded = Signal(str)   # txt 文件路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source: Optional[NovelSource] = None
        self._cur_novel: Optional[NovelDetail] = None
        self._mode = "search"   # search / catalog / reader
        self._workers: list[QThread] = []
        self._last_downloaded_file: Optional[str] = None
        self._temp_source: Optional[NovelSource] = None
        self._dlg = None
        self._build_ui()
        self._apply_dark_style()

    def set_base_url(self, base_url: str):
        """主窗口开页面时调用一次。"""
        # 选最匹配的下拉项
        for i in range(self.source_combo.count() - 1):
            label, url = DEFAULT_SOURCES[i]
            if url and url.rstrip("/") == base_url.rstrip("/"):
                self.source_combo.setCurrentIndex(i)
                return
        # 自定义:显示在 input
        self.source_combo.setCurrentIndex(len(DEFAULT_SOURCES) - 1)
        self.base_url_input.setText(base_url)
        self._source = NovelSource(base_url)
        self.status_label.setText(f"站点:{base_url}")

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 12)
        root.setSpacing(12)

        # ---------- 顶栏:站点 + 搜索 ----------
        bar = QFrame()
        bar.setProperty("role", "search-bar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(10)

        bl.addWidget(QLabel("🌐 来源:"))
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(180)
        for label, url in DEFAULT_SOURCES:
            self.source_combo.addItem(label, userData=url)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        bl.addWidget(self.source_combo)

        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("小说站 base_url(选'自定义'后填)")
        self.base_url_input.setMinimumWidth(280)
        self.base_url_input.setVisible(False)
        bl.addWidget(self.base_url_input, 1)

        bl.addSpacing(8)
        bl.addWidget(QLabel("🔍"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索书名或作者(可能命中不强,推荐用下面的粘 URL)")
        self.search_input.returnPressed.connect(self._on_search)
        self.search_input.setMaximumWidth(260)
        bl.addWidget(self.search_input)

        self.btn_search = QPushButton("搜索")
        self.btn_search.clicked.connect(self._on_search)
        bl.addWidget(self.btn_search)

        bl.addStretch(1)
        self.btn_open_browser = QPushButton("🌐 浏览器搜")
        self.btn_open_browser.setToolTip("打开默认浏览器,你可以用百度等搜索引擎找到小说目录页 URL")
        self.btn_open_browser.setProperty("compact", "true")
        self.btn_open_browser.clicked.connect(self._open_browser_home)
        bl.addWidget(self.btn_open_browser)

        root.addWidget(bar)

        # ---------- 状态条 ----------
        status = QHBoxLayout()
        self.btn_back = QPushButton("← 返回")
        self.btn_back.setProperty("compact", "true")
        self.btn_back.setVisible(False)
        self.btn_back.clicked.connect(self._go_back)
        status.addWidget(self.btn_back)

        self.status_label = QLabel("选择一个来源,输入关键字搜索")
        self.status_label.setProperty("role", "subtitle")
        status.addWidget(self.status_label, 1)

        self.btn_download = QPushButton("⤓ 整本下载")
        self.btn_download.setProperty("compact", "true")
        self.btn_download.setVisible(False)
        self.btn_download.clicked.connect(self._on_download_novel)
        status.addWidget(self.btn_download)

        self.btn_import = QPushButton("📥 导入到书库")
        self.btn_import.setProperty("compact", "true")
        self.btn_import.setVisible(False)
        self.btn_import.clicked.connect(self._on_import_downloaded)
        status.addWidget(self.btn_import)
        root.addLayout(status)

        # ---------- 粘 URL 条(替代/补充搜索) ----------
        url_bar = QFrame()
        url_bar.setStyleSheet(
            "QFrame { background: #1a2336; border: 1px solid #2a354a; border-radius: 8px; padding: 4px; }"
            "QLineEdit { background: transparent; border: none; padding: 4px; }"
        )
        ub = QHBoxLayout(url_bar)
        ub.setContentsMargins(12, 4, 12, 4)
        ub.setSpacing(8)
        ub.addWidget(QLabel("📋 粘目录 URL:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(
            "把小说目录页 URL 直接粘到这里(浏览器搜到的目录页,推荐方式)"
        )
        self.url_input.returnPressed.connect(self._on_open_url)
        ub.addWidget(self.url_input, 1)
        self.btn_open_url = QPushButton("打开")
        self.btn_open_url.setProperty("primary", "true")
        self.btn_open_url.clicked.connect(self._on_open_url)
        ub.addWidget(self.btn_open_url)
        self.btn_debug = QPushButton("调试")
        self.btn_debug.setProperty("compact", "true")
        self.btn_debug.setToolTip("看该 URL 返回了什么 HTML")
        self.btn_debug.clicked.connect(self._show_debug_html)
        ub.addWidget(self.btn_debug)
        root.addWidget(url_bar)

        # ---------- 内容区(根据模式切换) ----------
        self.content = QStackedLayout()

        # 模式 1:搜索结果列表
        self.search_list = QListWidget()
        self.search_list.setStyleSheet(
            "QListWidget { background: transparent; border: none; padding: 8px; }"
            "QListWidget::item { padding: 18px 20px; border-radius: 8px;"
            "  color: #e6ded2; margin: 6px 4px; background: #1a2336;"
            "  border: 1px solid #2a354a; }"
            "QListWidget::item:hover { border-color: #c8946e; background: #1f2a3d; }"
            "QListWidget::item:selected { border-color: #c8946e; border-width: 2px;"
            "  background: rgba(200, 148, 110, 0.12); }"
        )
        self.search_list.itemClicked.connect(self._on_search_item_clicked)
        self.content.addWidget(self.search_list)

        # 模式 2:目录
        self.catalog_view = self._build_catalog_view()
        self.content.addWidget(self.catalog_view)

        # 模式 3:在线阅读
        self.reader_view = self._build_reader_view()
        self.content.addWidget(self.reader_view)

        root.addLayout(self.content, 1)

    def _build_catalog_view(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(8)
        # 标题信息
        self.catalog_header = QFrame()
        self.catalog_header.setStyleSheet(
            "QFrame { background: #1a2336; border: 1px solid #2a354a;"
            "         border-radius: 10px; padding: 16px; }"
            "QLabel { background: transparent; border: none; }"
        )
        chl = QVBoxLayout(self.catalog_header)
        chl.setSpacing(6)
        self.catalog_title = QLabel("书名")
        f = QFont(); f.setPointSize(18); f.setBold(True)
        self.catalog_title.setFont(f)
        self.catalog_title.setStyleSheet("color: #e6ded2;")
        chl.addWidget(self.catalog_title)
        self.catalog_author = QLabel("")
        self.catalog_author.setStyleSheet("color: #9aa0ac; font-size: 12px;")
        chl.addWidget(self.catalog_author)
        self.catalog_desc = QLabel("")
        self.catalog_desc.setStyleSheet("color: #6b7384; font-size: 12px;")
        self.catalog_desc.setWordWrap(True)
        chl.addWidget(self.catalog_desc)
        l.addWidget(self.catalog_header)

        # 章节目录
        self.catalog_list = QListWidget()
        self.catalog_list.setStyleSheet(self.search_list.styleSheet())
        self.catalog_list.itemClicked.connect(self._on_catalog_item_clicked)
        l.addWidget(self.catalog_list, 1)
        return w

    def _build_reader_view(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)
        bar = QHBoxLayout()
        self.reader_chapter_title = QLabel("章节标题")
        f = QFont(); f.setPointSize(14); f.setBold(True)
        self.reader_chapter_title.setFont(f)
        self.reader_chapter_title.setStyleSheet("color: #e6ded2; background: transparent;")
        bar.addWidget(self.reader_chapter_title, 1)
        self.btn_prev_chap = QPushButton("⟨ 上一章")
        self.btn_next_chap = QPushButton("下一章 ⟩")
        self.btn_prev_chap.setProperty("compact", "true")
        self.btn_next_chap.setProperty("compact", "true")
        self.btn_prev_chap.clicked.connect(self._on_prev_chap)
        self.btn_next_chap.clicked.connect(self._on_next_chap)
        bar.addWidget(self.btn_prev_chap)
        bar.addWidget(self.btn_next_chap)
        l.addLayout(bar)

        # 正文(用 QTextEdit 只读,scrolled)
        from PySide6.QtWidgets import QTextEdit
        self.reader_text = QTextEdit()
        self.reader_text.setReadOnly(True)
        self.reader_text.setStyleSheet(
            "QTextEdit { background: #f5ede0; color: #2a2520;"
            "  border: 1px solid #d8d3c0; border-radius: 8px;"
            "  padding: 32px 48px; font-size: 15px;"
            "  selection-background-color: rgba(200, 148, 110, 0.18); }"
            "QTextEdit QScrollBar:vertical { background: transparent; width: 10px; }"
            "QTextEdit QScrollBar::handle:vertical { background: #c8c0a8;"
            "  border-radius: 5px; min-height: 30px; }"
        )
        l.addWidget(self.reader_text, 1)

        self._reader_idx = -1  # 在 _cur_novel.chapters 里的 index
        return w

    def _apply_dark_style(self):
        """局部暗色样式(继承全局,但加强输入体验)。"""
        # QLineEdit 已有全局样式;这里只针对 search_input / source_combo 微调
        # 实际上不做特殊处理,让全局 QSS 起作用
        pass

    # ---------- 来源切换 ----------
    def _on_source_changed(self, idx: int):
        url = self.source_combo.itemData(idx) or ""
        if url:
            # 选预设
            self.base_url_input.setVisible(False)
            self._source = NovelSource(url)
            self.status_label.setText(f"来源:{url}")
        else:
            # 自定义
            self.base_url_input.setVisible(True)
            self.base_url_input.setFocus()
            custom = self.base_url_input.text().strip()
            if custom:
                self._source = NovelSource(custom)
                self.status_label.setText(f"来源:{custom}")

    def _resolve_source(self) -> Optional[NovelSource]:
        if self._source is None:
            # 用当前下拉/输入
            idx = self.source_combo.currentIndex()
            url = self.source_combo.itemData(idx) or self.base_url_input.text().strip()
            if not url:
                QMessageBox.information(self, "提示", "请先选择一个来源或填入自定义 base_url")
                return None
            self._source = NovelSource(url)
        return self._source

    # ---------- 搜索 ----------
    def _on_search(self):
        kw = self.search_input.text().strip()
        if not kw:
            return
        src = self._resolve_source()
        if src is None:
            return
        self._enter_search_mode()
        self.status_label.setText(f"正在搜索:{kw}...")
        self.search_list.clear()
        w = _SearchWorker(src, kw)
        w.results.connect(self._on_search_results)
        w.error.connect(lambda e: self._on_search_error(str(e)))
        self._workers.append(w)
        w.start()

    # ---------- 粘 URL(替代方案:浏览器搜 + 粘 URL) ----------
    def _on_open_url(self):
        url = self.url_input.text().strip()
        if not url:
            self.status_label.setText("请先在 URL 框里粘贴一个链接")
            return
        # 自动补 base(若用户只填了 /book/12345 这类)
        if url.startswith("/"):
            base = self.source_combo.currentData() or "https://www.00shu.la"
            url = base.rstrip("/") + url
        if not url.startswith(("http://", "https://")):
            QMessageBox.warning(self, "URL 格式不对",
                                "请粘贴完整 URL(以 http:// 或 https:// 开头)")
            self.status_label.setText("URL 格式不对")
            return
        from urllib.parse import urlparse
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        from src.core.online import NovelSource
        self._temp_source = NovelSource(base)
        self.status_label.setText(f"正在加载:{url}")
        self._url_load_in_progress = True
        try:
            w = _CatalogWorker(self._temp_source, url)
            w.detail.connect(self._on_catalog_loaded_from_url)
            w.error.connect(self._on_catalog_url_error)
            w.finished.connect(lambda: setattr(self, "_url_load_in_progress", False))
            self._workers.append(w)
            w.start()
        except Exception as e:  # noqa: BLE001
            self._url_load_in_progress = False
            self.status_label.setText(f"加载失败:{e}")
            QMessageBox.warning(self, "加载失败", str(e))

    def _on_catalog_loaded_from_url(self, detail: NovelDetail):
        try:
            self._on_catalog_loaded_from_url_inner(detail)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            self.status_label.setText(f"❌ 加载失败:{e}")
            QMessageBox.warning(self, "加载失败", f"{e}\n\n用「调试」按钮看 HTML 找原因。")

    def _on_catalog_loaded_from_url_inner(self, detail: NovelDetail):
        if not detail:
            return
        self._source = self._temp_source
        base = self._source.base_url
        self._enter_catalog_mode()
        self.catalog_list.clear()
        self.catalog_title.setText(detail.title or "未知书名")
        self.catalog_author.setText(
            f"作者:{detail.author}" if detail.author else "作者未知"
        )
        # ---------- 特殊模式:整本 TXT 下载页(00shu /txt/{id}/) ----------
        if detail.download_url and not detail.chapters:
            self.catalog_desc.setText(
                (detail.description or "（这是一个整本 TXT 下载页）")
                + "\n\n📦 该站提供整本 TXT 直链(无需逐章爬),"
                + "点右上角「⤓ 整本下载」一键下载完整 txt。\n"
                + "⏱ 通常 4-5 MB,几秒下载完。"
            )
            # 章节列表给个提示项(不卡主线程)
            tip = QListWidgetItem("💡 点右上角「⤓ 整本下载」开始下载")
            tip.setFlags(Qt.NoItemFlags)  # 不可选
            self.catalog_list.addItem(tip)
            self.status_label.setText(
                f"✓ 《{detail.title}》整本下载页就绪 · 点「整本下载」"
            )
            self._cur_novel = detail
            self._last_downloaded_file = None
            self.btn_import.setVisible(False)
            return
        # ---------- 常规目录 ----------
        self.catalog_desc.setText(detail.description or "（无简介）")
        if not detail.chapters:
            self.status_label.setText(
                f"《{detail.title}》目录为空 — 该站可能用 JS 渲染,试试用「调试」按钮看 HTML"
            )
            return
        for ch in detail.chapters:
            it = QListWidgetItem(f"第 {ch.index + 1:04d} 章   {ch.title}")
            it.setData(Qt.UserRole, ch.url)
            self.catalog_list.addItem(it)
        self.status_label.setText(
            f"《{detail.title}》共 {len(detail.chapters)} 章 · 来源 {base}"
        )

    def _on_catalog_url_error(self, err: str):
        QMessageBox.warning(self, "加载目录失败",
                            f"无法加载该 URL 的目录页。\n\n{err}\n\n"
                            f"提示:很多小说站用 JS 渲染,需要先用浏览器打开点几下通过验证,"
                            f"再复制完整 URL(含任何 hash 参数)。")

    def _open_browser_home(self):
        """打开默认浏览器到当前源的首页(用户可在浏览器搜索并复制 URL)。"""
        url = self.source_combo.currentData() or self.base_url_input.text().strip() or "https://www.baidu.com"
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(url))

    def _show_debug_html(self):
        url = self.url_input.text().strip()
        if not url:
            url = self.source_combo.currentData() or ""
        if not url:
            QMessageBox.information(self, "调试", "先在 URL 框里输入要调试的 URL,或选一个来源")
            return
        if url.startswith("/"):
            url = (self.source_combo.currentData() or "").rstrip("/") + url
        # 弹窗显示前 2000 字 HTML
        dlg = QDialog(self)
        dlg.setWindowTitle(f"调试:{url[:80]}")
        dlg.resize(700, 500)
        v = QVBoxLayout(dlg)
        info = QLabel(f"URL: {url}\nstatus: ", self)
        v.addWidget(info)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #d4d0c8;"
            " font-family: 'Consolas', monospace; font-size: 12px; }"
        )
        v.addWidget(text, 1)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)

        def fetch():
            try:
                src = self._resolve_source() or NovelSource(url)
                html = src._get(url)
                info.setText(f"URL: {url}\nstatus: 200 · bytes: {len(html)}")
                text.setPlainText(html[:20000])
            except Exception as e:
                info.setText(f"URL: {url}\nstatus: ERROR")
                text.setPlainText(str(e))
        fetch()
        dlg.exec()

    def _on_search_results(self, results: list):
        self.search_list.clear()
        if not results:
            self.status_label.setText("没有找到结果。换个源或关键字试试?")
            return
        for n in results:
            line1 = n.title
            line2 = n.author or ""
            if n.latest_chapter:
                line2 += f"  ·  {n.latest_chapter}" if line2 else n.latest_chapter
            it = QListWidgetItem(f"{line1}\n    {line2}")
            it.setData(Qt.UserRole, n.url)
            self.search_list.addItem(it)
        self.status_label.setText(f"找到 {len(results)} 本小说")

    def _on_search_error(self, err: str):
        QMessageBox.warning(self, "搜索失败",
                            f"无法访问该小说站。\n\n{err}\n\n"
                            f"可尝试:换一个 base_url(下拉菜单) 或检查网络")
        self.status_label.setText("搜索失败,查看错误提示")

    # ---------- 点击搜索结果 → 加载目录 ----------
    def _on_search_item_clicked(self, item):
        url = item.data(Qt.UserRole)
        self._load_catalog(url)

    def _load_catalog(self, novel_url: str):
        src = self._resolve_source()
        if src is None:
            return
        self._enter_catalog_mode()
        self.status_label.setText("正在加载目录...")
        # 清空旧
        self.catalog_list.clear()
        self.catalog_title.setText("加载中...")
        self.catalog_author.setText("")
        self.catalog_desc.setText("")
        w = _CatalogWorker(src, novel_url)
        w.detail.connect(self._on_catalog_loaded)
        w.error.connect(lambda e: QMessageBox.warning(self, "加载目录失败", e))
        self._workers.append(w)
        w.start()

    def _on_catalog_loaded(self, detail: NovelDetail):
        self._cur_novel = detail
        self.catalog_title.setText(detail.title)
        self.catalog_author.setText(
            f"作者:{detail.author}" if detail.author else "作者未知"
        )
        self.catalog_desc.setText(detail.description or "（无简介）")
        self.catalog_list.clear()
        if not detail.chapters:
            self.status_label.setText("该小说站没找到章节链接,可能模板不一样")
            return
        for ch in detail.chapters:
            it = QListWidgetItem(f"第 {ch.index + 1:04d} 章   {ch.title}")
            it.setData(Qt.UserRole, ch.url)
            self.catalog_list.addItem(it)
        self.status_label.setText(f"《{detail.title}》共 {len(detail.chapters)} 章")

    # ---------- 在线阅读 ----------
    def _on_catalog_item_clicked(self, item):
        url = item.data(Qt.UserRole)
        # 找 index
        for i in range(self.catalog_list.count()):
            if self.catalog_list.item(i) is item:
                self._reader_idx = i
                break
        self._load_chapter(url, item.text())

    def _load_chapter(self, url: str, fallback_title: str = ""):
        src = self._resolve_source()
        if src is None:
            return
        self._enter_reader_mode()
        self.reader_text.setPlainText("加载中...")
        self.reader_chapter_title.setText(fallback_title or "加载中...")
        w = _ChapterWorker(src, url)
        w.chapter.connect(self._on_chapter_loaded)
        w.error.connect(lambda e: self.reader_text.setPlainText(f"加载失败:\n{e}"))
        self._workers.append(w)
        w.start()

    def _on_chapter_loaded(self, url: str, body: str):
        title = ""
        if self._cur_novel and 0 <= self._reader_idx < len(self._cur_novel.chapters):
            title = self._cur_novel.chapters[self._reader_idx].title
        if not title:
            from PySide6.QtCore import QUrl
            title = QUrl(url).path.split("/")[-1] or "章节"
        self.reader_chapter_title.setText(title)
        # HTML 渲染(分段)
        import html as html_mod
        paragraphs = [html_mod.escape(p) for p in body.split("\n") if p.strip()]
        body_html = "\n".join(
            f'<p style="line-height: 1.95; text-indent: 2em; margin: 8px 0;">{p}</p>'
            for p in paragraphs
        )
        self.reader_text.setHtml(
            f'<div style="max-width: 720px; margin: 0 auto; font-family: Microsoft YaHei, sans-serif;">'
            f'<h2 style="text-align: center; font-size: 22px; margin: 0 0 20px 0; color: #3a2f1c;">{html_mod.escape(title)}</h2>'
            f'{body_html}</div>'
        )
        # 同步章节列表选中
        if self._cur_novel:
            for i in range(self.catalog_list.count()):
                if self._cur_novel and i == self._reader_idx:
                    self.catalog_list.setCurrentRow(i)
                    break

    def _on_prev_chap(self):
        if not self._cur_novel or self._reader_idx <= 0:
            return
        self._reader_idx -= 1
        ch = self._cur_novel.chapters[self._reader_idx]
        self._load_chapter(ch.url, ch.title)

    def _on_next_chap(self):
        if not self._cur_novel or self._reader_idx >= len(self._cur_novel.chapters) - 1:
            return
        self._reader_idx += 1
        ch = self._cur_novel.chapters[self._reader_idx]
        self._load_chapter(ch.url, ch.title)

    # ---------- 下载 ----------
    def _on_download_novel(self):
        if not self._cur_novel:
            return
        # ---------- 整本 TXT 直链(00shu 等) ----------
        if self._cur_novel.download_url:
            self._download_full_txt(self._cur_novel)
            return
        # ---------- 常规逐章下载 ----------
        if not self._cur_novel.chapters:
            QMessageBox.information(self, "提示", "当前没有可下载的章节")
            return
        total = len(self._cur_novel.chapters)
        if QMessageBox.question(
            self, "下载确认",
            f"将下载《{self._cur_novel.title}》共 {total} 章。\n"
            f"保存目录:{DOWNLOAD_DIR}\n\n"
            f"耗时视章节数,大约 {total // 30 + 1} 分钟。\n"
            f"继续吗?",
        ) != QMessageBox.Yes:
            return

        src = self._resolve_source()
        if src is None:
            return

        self.status_label.setText(f"开始下载 {total} 章...")
        from PySide6.QtWidgets import QProgressDialog
        self._dlg = QProgressDialog(
            f"正在下载《{self._cur_novel.title}》\n准备中...",
            "取消", 0, total, self,
        )
        self._dlg.setWindowModality(Qt.WindowModal)
        self._dlg.setMinimumDuration(0)
        self._dlg.setValue(0)

        self._last_downloaded_file: Optional[str] = None

        w = _DownloadWorker(src, self._cur_novel.url, DOWNLOAD_DIR)
        def on_prog(p: DownloadProgress):
            if self._dlg.wasCanceled():
                w.requestInterruption()
                return
            self._dlg.setValue(p.current)
            self._dlg.setLabelText(
                f"《{self._cur_novel.title}》\n"
                f"第 {p.current}/{p.total} 章:{p.current_title[:30]}\n"
                f"失败:{p.failed}"
            )
        w.progress.connect(on_prog)
        w.done.connect(self._on_download_done)
        w.error.connect(self._on_download_error)
        self._workers.append(w)
        w.start()

    def _download_full_txt(self, detail: NovelDetail):
        """整本 TXT 直链下载(00shu 等)。"""
        import shutil
        safe_title = re.sub(r"[\\/:*?\"<>|]", "_", detail.title).strip() or "novel"
        out_path = DOWNLOAD_DIR / f"{safe_title}.txt"
        if QMessageBox.question(
            self, "整本下载",
            f"将整本下载《{detail.title}》为 txt。\n"
            f"保存路径:{out_path}\n\n"
            f"这是一键整本下载(约 4-5 MB),几秒完成。\n"
            f"下载完成后会自动通知主窗口导入到书库。\n\n继续?",
        ) != QMessageBox.Yes:
            return
        self.status_label.setText(f"整本下载 {detail.title}...")
        from PySide6.QtWidgets import QProgressDialog
        # 进度按字节(分阶段: indeterminate → 确定)
        self._dlg = QProgressDialog(
            f"整本下载《{detail.title}》\n准备中...",
            "取消", 0, 0, self,
        )
        self._dlg.setWindowModality(Qt.WindowModal)
        self._dlg.setMinimumDuration(0)
        self._dlg.setValue(0)

        # 启动一个普通 QThread(用 Python threading 或自己继承)
        from PySide6.QtCore import QThread

        class _FullTxtWorker(QThread):
            done = Signal(str)
            error = Signal(str)
            def __init__(self, src: NovelSource, url: str, path: Path):
                super().__init__()
                self.src = src
                self.url = url
                self.path = path
            def run(self):
                try:
                    self.src.download_full_txt(
                        self.url, self.path,
                        on_progress=lambda w, t: None,  # 进度条已在 UI 上 indeterminate
                    )
                    self.done.emit(str(self.path))
                except Exception as e:  # noqa: BLE001
                    self.error.emit(str(e))

        w = _FullTxtWorker(self._source, detail.download_url, out_path)
        w.done.connect(self._on_download_done)
        w.error.connect(self._on_download_error)
        self._workers.append(w)
        w.start()

    def _on_download_done(self, path: str):
        self._last_downloaded_file = path
        if not self._dlg.wasCanceled():
            self._dlg.setValue(self._dlg.maximum())
        self._dlg.close()
        self.status_label.setText(f"✓ 下载完成:{os.path.basename(path)}")
        QMessageBox.information(
            self, "下载完成",
            f"已保存到:\n{path}\n\n点击「导入到书库」即可加入阅读列表。",
        )
        self.btn_import.setVisible(True)
        self.btn_import.setProperty("ready", True)

    def _on_download_error(self, err: str):
        self._dlg.close()
        QMessageBox.warning(self, "下载失败", err)
        self.status_label.setText(f"下载失败:{err[:60]}")

    def _on_import_downloaded(self):
        if not self._last_downloaded_file or not Path(self._last_downloaded_file).exists():
            QMessageBox.warning(self, "提示", "文件不存在")
            return
        self.book_downloaded.emit(self._last_downloaded_file)
        QMessageBox.information(self, "已发送", "已通知主窗口导入到书库,切回「我的书库」即可看到。")

    # ---------- 模式切换 ----------
    def _go_back(self):
        # 从当前模式退回上一步
        if self._mode == "reader":
            # 退到目录
            self._enter_catalog_mode()
            self.btn_back.setVisible(True)
            self.status_label.setText("返回目录")
        elif self._mode == "catalog":
            # 退到搜索结果
            self._enter_search_mode()
            self.btn_back.setVisible(False)
            self.status_label.setText("返回搜索结果")

    def _enter_search_mode(self):
        self._mode = "search"
        self.content.setCurrentIndex(0)
        self.btn_back.setVisible(False)
        self.btn_download.setVisible(False)
        self.btn_import.setVisible(False)
        # 搜索栏可用
        self.search_input.setReadOnly(False)

    def _enter_catalog_mode(self):
        self._mode = "catalog"
        self.content.setCurrentIndex(1)
        self.btn_back.setVisible(True)
        self.btn_download.setVisible(True)
        self.btn_import.setVisible(self._last_downloaded_file is not None)
        self.search_input.setReadOnly(True)

    def _enter_reader_mode(self):
        self._mode = "reader"
        self.content.setCurrentIndex(2)
        self.btn_back.setVisible(True)
        self.btn_download.setVisible(False)
        self.btn_import.setVisible(self._last_downloaded_file is not None)


# 为了能用 QStackedLayout 在本文件内引用,做小 import shim
from PySide6.QtWidgets import QStackedLayout  # noqa: E402
