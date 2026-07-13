"""书库面板:用墨读风格的书籍网格卡片展示已导入的电子书。"""
from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QEnterEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QFileDialog, QMessageBox, QMenu, QAbstractItemView, QToolButton,
    QFrame, QProgressBar, QGridLayout, QApplication, QCheckBox,
)

from src.core import BookRecord
from src.ui.theme import pick_cover_gradient, FONT_HEADING


# ============================================================
# 单本书卡片(对应 v2.html 的 .book-card)
# ============================================================

class BookCard(QFrame):
    """单本书的封面卡片 widget。"""

    activated = Signal(int)   # book_id
    remove_requested = Signal(int)  # book_id

    def __init__(self, record: BookRecord, parent=None):
        super().__init__(parent)
        self.record = record
        self.setObjectName("BookCard")
        self.setProperty("role", "book-card")
        self.setFixedSize(180, 290)
        self.setCursor(Qt.PointingHandCursor)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 封面(渐变 + 书名 + 进度条) ----
        cover = QFrame()
        cover.setProperty("role", "book-cover")
        cover.setFixedHeight(220)
        # 用 inline style 设置渐变(QSS 不直接支持 inline background-image,但
        # Qt 5.14+ 的 setStyleSheet 支持 qlineargradient;我们用 inline style)
        cover.setStyleSheet(
            f"QFrame[role=\"book-cover\"] {{ background: {pick_cover_gradient(record.title)}; }}"
        )
        cv = QVBoxLayout(cover)
        cv.setContentsMargins(12, 12, 12, 0)
        cv.setSpacing(0)

        cv.addStretch(1)
        title_in_cover = QLabel(_first_chars(record.title, 4))
        title_in_cover.setProperty("role", "book-cover-title")
        title_in_cover.setAlignment(Qt.AlignCenter)
        title_in_cover.setWordWrap(True)
        cv.addWidget(title_in_cover)
        cv.addSpacing(8)

        # 进度条(只在有进度时显示)
        if record.last_progress and record.last_progress > 0:
            prog = QProgressBar()
            prog.setProperty("role", "book-progress")
            prog.setRange(0, 100)
            prog.setValue(int(record.last_progress * 100))
            prog.setTextVisible(False)
            # 让它贴在底部
            cv.addStretch(1)
            cv.addWidget(prog)
        else:
            cv.addStretch(1)

        root.addWidget(cover)

        # ---- 底部信息(title / author / tag / progress%) ----
        info = QFrame()
        info.setStyleSheet("QFrame { background: transparent; border: none; }")
        iv = QVBoxLayout(info)
        iv.setContentsMargins(12, 10, 12, 10)
        iv.setSpacing(4)

        title_label = QLabel(record.title)
        title_label.setProperty("role", "book-title")
        title_label.setMaximumWidth(156)
        title_label.setWordWrap(False)
        title_label.setTextFormat(Qt.PlainText)
        # 截断长标题
        fm = title_label.fontMetrics()
        elided = fm.elidedText(record.title, Qt.ElideRight, 156)
        title_label.setText(elided)
        iv.addWidget(title_label)

        author_label = QLabel(record.author if record.author else "未知作者")
        author_label.setProperty("role", "book-author")
        author_label.setMaximumWidth(156)
        author_label.setTextFormat(Qt.PlainText)
        elided2 = fm.elidedText(record.author if record.author else "未知作者",
                                Qt.ElideRight, 156)
        author_label.setText(elided2)
        iv.addWidget(author_label)

        # tag + progress% row
        meta = QHBoxLayout()
        meta.setSpacing(8)

        # tag
        tag_label = QLabel(_book_tag(record))
        tag_label.setProperty("role", _book_tag_role(record))
        meta.addWidget(tag_label)
        meta.addStretch(1)

        # progress text
        if record.last_progress and record.last_progress > 0:
            pct = QLabel(f"{int(record.last_progress * 100)}%")
            pct.setProperty("role", "book-meta")
            meta.addWidget(pct)
        iv.addLayout(meta)

        root.addWidget(info)

    def enterEvent(self, event: QEnterEvent):
        self.setProperty("hovered", True)
        self.style().unpolish(self)
        self.style().polish(self)

    def leaveEvent(self, event):
        self.setProperty("hovered", False)
        self.setProperty("selected", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.activated.emit(self.record.id)
        elif ev.button() == Qt.RightButton:
            self.contextMenuEvent = lambda e: self._show_context_menu(e)
            self._show_context_menu(ev)
        super().mousePressEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        self.activated.emit(self.record.id)
        super().mouseDoubleClickEvent(ev)

    def _show_context_menu(self, ev):
        menu = QMenu(self)
        act_open = menu.addAction("打开")
        act_remove = menu.addAction("从书库移除")
        chosen = menu.exec(self.mapToGlobal(ev.pos()))
        if chosen is act_open:
            self.activated.emit(self.record.id)
        elif chosen is act_remove:
            self.remove_requested.emit(self.record.id)


def _first_chars(s: str, n: int) -> str:
    """取书名前 N 个字符(中文也按字符算)。"""
    if not s:
        return "?"
    return s[:n]


def _book_tag(record: BookRecord) -> str:
    """书的状态 tag 文字。"""
    if record.last_progress is None or record.last_progress <= 0:
        return "未开始"
    if record.last_progress >= 0.99:
        return "已读完"
    return "在读"


def _book_tag_role(record: BookRecord) -> str:
    """书的状态 tag QSS role。"""
    if record.last_progress is None or record.last_progress <= 0:
        return "book-tag"
    if record.last_progress >= 0.99:
        return "book-tag-done"
    return "book-tag-reading"


# ============================================================
# 书库列表(QListWidget IconMode)
# ============================================================

class LibraryList(QWidget):
    """左侧书库面板:网格卡片列表。"""

    book_selected = Signal(int)
    books_imported = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._library = None  # type: ignore[assignment]
        self._book_cards: dict[int, BookCard] = {}
        self._build_ui()

    def set_library(self, library):
        self._library = library
        self.refresh()

    # ---------- UI 构建 ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 8)
        root.setSpacing(12)

        # 标题行
        title_row = QHBoxLayout()
        title = QLabel("我的书架")
        title.setProperty("role", "page-title")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.count_label = QLabel("0 本")
        self.count_label.setProperty("role", "page-sub")
        title_row.addWidget(self.count_label)
        root.addLayout(title_row)

        # 副标题
        sub = QLabel("点击书卡打开阅读 · 右键移除")
        sub.setProperty("role", "page-sub")
        root.addWidget(sub)

        # 按钮行(右上角操作)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_import = QPushButton("📄 导入文件")
        self.btn_import.setProperty("compact", "true")
        self.btn_import.clicked.connect(self._on_import_clicked)
        btn_row.addWidget(self.btn_import)

        self.btn_import_dir = QPushButton("📁 批量导入")
        self.btn_import_dir.setProperty("compact", "true")
        self.btn_import_dir.clicked.connect(self._on_import_dir_clicked)
        btn_row.addWidget(self.btn_import_dir)
        root.addLayout(btn_row)

        # 网格列表(QListWidget IconMode)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setSpacing(14)
        self.list.setGridSize(QSize(196, 308))  # BookCard 大小 + 间距
        self.list.setUniformItemSizes(True)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.itemActivated.connect(self._on_item_activated)
        self.list.itemClicked.connect(self._on_item_clicked)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        root.addWidget(self.list, 1)

    # ---------- 行为 ----------

    def refresh(self):
        self.list.clear()
        self._book_cards.clear()
        if self._library is None:
            return
        records: List[BookRecord] = self._library.list_books()
        for rec in records:
            item = QListWidgetItem(self.list)
            item.setSizeHint(QSize(196, 308))
            item.setData(Qt.UserRole, rec.id)
            card = BookCard(rec, parent=self.list)
            card.activated.connect(self.book_selected.emit)
            card.remove_requested.connect(self._on_card_remove_requested)
            self.list.addItem(item)
            self.list.setItemWidget(item, card)
            self._book_cards[rec.id] = card
        self.count_label.setText(f"共 {len(records)} 本")

    def select_first(self):
        if self.list.count() > 0:
            self.list.setCurrentRow(0)
            self._emit_selected(0)

    def select_book_id(self, book_id: int):
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(Qt.UserRole) == book_id:
                self.list.setCurrentRow(i)
                self._update_card_selected(book_id)
                return

    def _update_card_selected(self, selected_id: int):
        for bid, card in self._book_cards.items():
            is_sel = (bid == selected_id)
            card.setProperty("selected", is_sel)
            card.style().unpolish(card)
            card.style().polish(card)

    def _on_item_activated(self, item):
        self._emit_selected(self.list.row(item))

    def _on_item_clicked(self, item):
        self._emit_selected(self.list.row(item))

    def _on_card_remove_requested(self, book_id: int):
        """BookCard 右键"移除"信号触发。"""
        self._remove_book(book_id)

    def _emit_selected(self, row: int):
        item = self.list.item(row)
        if item is None:
            return
        book_id = int(item.data(Qt.UserRole))
        self._update_card_selected(book_id)
        self.book_selected.emit(book_id)

    def _on_import_clicked(self):
        if self._library is None:
            return
        exts = self._library.supported_extensions()
        filt = f"电子书 ({' '.join('*' + e for e in exts)});;所有文件 (*)"
        paths, _ = QFileDialog.getOpenFileNames(self, "选择电子书文件", "", filt)
        if not paths:
            return
        ok, fail = 0, []
        for p in paths:
            try:
                self._library.import_path(p)
                ok += 1
            except Exception as e:  # noqa: BLE001
                fail.append((p, str(e)))
        self.refresh()
        if fail:
            msg = "\n".join(f"• {os.path.basename(p)}: {e}" for p, e in fail)
            QMessageBox.warning(self, "部分导入失败", msg)
        if ok:
            self.books_imported.emit()

    def _on_import_dir_clicked(self):
        if self._library is None:
            return
        directory = QFileDialog.getExistingDirectory(
            self, "选择电子书文件夹", "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if not directory:
            return
        recursive = QMessageBox.question(
            self, "导入选项",
            f"是否包含子文件夹?\n\n扫描:\n{directory}\n\n"
            f"「Yes」:递归子文件夹\n「No」:只当前目录",
        ) == QMessageBox.Yes

        exts = self._library.supported_extensions()
        files: List[str] = []
        if recursive:
            for root, _dirs, names in os.walk(directory):
                for n in names:
                    if n.lower().endswith(exts):
                        files.append(os.path.join(root, n))
        else:
            for n in os.listdir(directory):
                p = os.path.join(directory, n)
                if os.path.isfile(p) and n.lower().endswith(exts):
                    files.append(p)

        if not files:
            QMessageBox.information(
                self, "未找到文件", f"该目录下没有 .txt / .epub。\n\n{directory}",
            )
            return

        files.sort()

        from PySide6.QtWidgets import QProgressDialog
        progress = QProgressDialog(
            f"正在导入 {len(files)} 个文件...", "取消", 0, len(files), self,
        )
        progress.setWindowTitle("批量导入")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        ok, fail, skipped = 0, [], 0
        for i, p in enumerate(files):
            if progress.wasCanceled():
                break
            progress.setLabelText(f"({i + 1}/{len(files)}) {os.path.basename(p)}")
            try:
                if self._library.storage.get_book_by_path(p):
                    skipped += 1
                else:
                    self._library.import_path(p)
                    ok += 1
            except Exception as e:  # noqa: BLE001
                fail.append((p, str(e)))
            progress.setValue(i + 1)
            QApplication.processEvents()

        progress.close()
        self.refresh()
        self.books_imported.emit()

        msg_parts = [f"扫描到 {len(files)} 个文件"]
        if ok:    msg_parts.append(f"✅ 成功导入 {ok} 本")
        if skipped: msg_parts.append(f"⏭ 跳过 {skipped} 本(已在书库)")
        if fail:  msg_parts.append(f"❌ 失败 {len(fail)} 本")
        msg = "\n".join(msg_parts)
        if fail:
            msg += "\n\n失败明细:\n" + "\n".join(
                f"• {os.path.basename(p)}: {e}" for p, e in fail[:10]
            )
            if len(fail) > 10: msg += f"\n... 共 {len(fail)} 条"
            QMessageBox.warning(self, "批量导入完成(有失败)", msg)
        else:
            QMessageBox.information(self, "批量导入完成", msg)

    def _remove_book(self, book_id: int):
        if self._library is None:
            return
        rec = self._library.storage.get_book(book_id)
        if rec is None:
            return
        if QMessageBox.question(
            self, "确认移除", f"确定从书库移除《{rec.title}》?\n(不会删除源文件)"
        ) != QMessageBox.Yes:
            return
        self._library.remove(book_id)
        self.refresh()
        self.books_imported.emit()

    def _on_remove_clicked(self):
        item = self.list.currentItem()
        if item is None:
            return
        book_id = int(item.data(Qt.UserRole))
        self._remove_book(book_id)

    def _on_context_menu(self, pos):
        item = self.list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        act_open = menu.addAction("打开")
        act_remove = menu.addAction("从书库移除")
        chosen = menu.exec(self.list.mapToGlobal(pos))
        if chosen is act_open:
            self._emit_selected(self.list.row(item))
        elif chosen is act_remove:
            book_id = int(item.data(Qt.UserRole))
            self._remove_book(book_id)
