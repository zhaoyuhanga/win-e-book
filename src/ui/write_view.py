"""墨写 WriteView:文件树 + 编辑器 + AI 助手 三栏布局。

参考设计图:
- 左侧:文件树(write_workspace / bdh-docs / a-book 风格)
- 中间:文档编辑区(顶部工具栏 + 正文)
- 右侧:AI 写作助手面板(预设动作 + 输入框 + 流式响应)
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional, List

from PySide6.QtCore import Qt, Signal, QThread, QObject, QSettings, QDir, QSize
from PySide6.QtGui import QAction, QFont, QTextCursor, QKeySequence
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QLineEdit, QTextEdit,
    QPlainTextEdit, QTreeView, QFileSystemModel, QPushButton, QFileDialog,
    QMessageBox, QSizePolicy, QSplitter, QToolButton, QApplication, QComboBox,
    QScrollArea,
)

from src.core.llm import (
    LLMClient, LLMConfig, load_config, save_config, build_messages,
    WRITE_PRESETS, LLMError,
)
from src.ui.theme import (
    BG, SURFACE, SURFACE_RAISED, BORDER, BORDER_FOCUS, ACCENT, ACCENT_HOVER,
    TEXT, TEXT_SECONDARY, TEXT_MUTED, FONT_HEADING, FONT_BODY, RADIUS, RADIUS_SM,
    SUCCESS, DANGER, TAG_BG,
)


# ============================================================
# 工作区根目录
# ============================================================

def default_workspace() -> Path:
    """墨写 workspace 默认放 ~/Documents/墨写。"""
    docs = Path(os.path.expanduser("~/Documents"))
    p = docs / "墨写"
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)
    return p


# ============================================================
# 后台 LLM 流式 worker
# ============================================================

class _LLMWorker(QObject):
    """在 QThread 里跑流式 LLM,逐 chunk 发射 signal。"""

    chunk = Signal(str)            # 增量文本
    finished = Signal(str)         # 全部内容
    failed = Signal(str)           # 错误消息

    def __init__(self, client: LLMClient, messages: list):
        super().__init__()
        self._client = client
        self._messages = messages
        self._buf: list[str] = []

    def run(self):
        try:
            for delta in self._client.chat_stream(self._messages):
                self._buf.append(delta)
                self.chunk.emit(delta)
            self.finished.emit("".join(self._buf))
        except LLMError as e:
            self.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"未知错误: {e}")


# ============================================================
# 左侧:文件树
# ============================================================

class FileTreePanel(QFrame):
    """左侧文件树:基于 QFileSystemModel + QTreeView。"""

    file_opened = Signal(str)  # 选中一个文件

    def __init__(self, root: Path, parent=None):
        super().__init__(parent)
        self.setObjectName("FileTreePanel")
        self.setProperty("role", "side-panel")
        self.setStyleSheet(f"""
            QFrame#FileTreePanel {{
                background: {SURFACE};
                border-right: 1px solid {BORDER};
            }}
        """)
        self.setMinimumWidth(180)
        self.setMaximumWidth(240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 6)
        layout.setSpacing(6)

        # 顶部:工作区名 + 新建/刷新按钮
        head = QHBoxLayout()
        head.setSpacing(4)
        self.title = QLabel(root.name)
        self.title.setStyleSheet(f"""
            QLabel {{
                color: {TEXT};
                font-family: {FONT_HEADING};
                font-size: 12px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
        """)
        head.addWidget(self.title, 1)

        self.btn_new = QToolButton()
        self.btn_new.setText("+")
        self.btn_new.setToolTip("新建文件")
        self.btn_new.setCursor(Qt.PointingHandCursor)
        self.btn_new.setFixedSize(22, 22)
        self.btn_new.setStyleSheet(_TOOLBTN_QSS)
        self.btn_new.clicked.connect(self._on_new_file)
        head.addWidget(self.btn_new)

        self.btn_refresh = QToolButton()
        self.btn_refresh.setText("⟳")
        self.btn_refresh.setToolTip("刷新")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setFixedSize(22, 22)
        self.btn_refresh.setStyleSheet(_TOOLBTN_QSS)
        self.btn_refresh.clicked.connect(self._refresh)
        head.addWidget(self.btn_refresh)

        layout.addLayout(head)

        # 树
        self.model = QFileSystemModel()
        self.model.setRootPath(str(root))
        # 过滤:只显示 .txt / .md
        self.model.setNameFilters(["*.txt", "*.md"])
        self.model.setNameFilterDisables(False)

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(str(root)))
        self.tree.setHeaderHidden(True)
        # 隐藏 size / type / modified 三列,只留 Name
        for col in (1, 2, 3):
            self.tree.hideColumn(col)
        self.tree.setAnimated(True)
        self.tree.setIndentation(14)
        self.tree.setStyleSheet(f"""
            QTreeView {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                outline: 0;
                font-size: 12px;
            }}
            QTreeView::item {{
                padding: 3px 6px;
                border-radius: 4px;
            }}
            QTreeView::item:hover {{
                background: {SURFACE_RAISED};
                color: {TEXT};
            }}
            QTreeView::item:selected {{
                background: {ACCENT_SUBTLE_BACK};
                color: {ACCENT};
            }}
            QTreeView::branch {{
                background: transparent;
            }}
        """)
        self.tree.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.tree, 1)

        # 底部路径
        self.path_label = QLabel(str(root))
        self.path_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 9px;
                background: transparent;
                border: none;
            }}
        """)
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

    def set_root(self, root: Path):
        self.model.setRootPath(str(root))
        self.tree.setRootIndex(self.model.index(str(root)))
        self.title.setText(root.name)
        self.path_label.setText(str(root))

    def _on_double_click(self, idx):
        path = self.model.filePath(idx)
        if os.path.isfile(path):
            self.file_opened.emit(path)

    def _on_new_file(self):
        root = Path(self.model.rootPath())
        ts = time.strftime("%Y%m%d-%H%M%S")
        path = root / f"未命名-{ts}.txt"
        path.write_text("", encoding="utf-8")
        self._refresh()
        self.file_opened.emit(str(path))

    def _refresh(self):
        self.model.setRootPath(self.model.rootPath())  # 触发刷新


# ============================================================
# 中间:编辑器
# ============================================================

class EditorPanel(QFrame):
    """中部文档编辑区。"""

    content_changed = Signal()  # 文本变更
    file_renamed = Signal(str)  # 改名/新文件

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: #fbfaf7;
                border-right: 1px solid {BORDER};
            }}
        """)
        self._file_path: Optional[str] = None
        self._live_mode = True  # Live 模式:改动后自动保存(延迟 800ms)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---------- 顶部工具栏 ----------
        toolbar = QFrame()
        toolbar.setFixedHeight(44)
        toolbar.setStyleSheet(f"""
            QFrame {{
                background: #ffffff;
                border-bottom: 1px solid #e5e0d6;
            }}
        """)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 0, 14, 0)
        tb.setSpacing(10)

        # 文件名(可点击重命名)
        self.file_label = QLabel("未命名文档")
        self.file_label.setStyleSheet(f"""
            QLabel {{
                color: #1f2937;
                font-family: {FONT_HEADING};
                font-size: 13px;
                font-weight: 700;
                background: transparent;
            }}
        """)
        tb.addWidget(self.file_label)

        # Live 切换
        self.live_toggle = QToolButton()
        self.live_toggle.setText("Live")
        self.live_toggle.setCheckable(True)
        self.live_toggle.setChecked(True)
        self.live_toggle.setCursor(Qt.PointingHandCursor)
        self.live_toggle.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: 1px solid #d4cfc0;
                border-radius: {RADIUS_XS}px;
                padding: 3px 9px;
                font-size: 11px;
            }}
            QToolButton:checked {{
                color: #fff;
                background: {SUCCESS};
                border: 1px solid {SUCCESS};
            }}
        """)
        tb.addWidget(self.live_toggle)

        # 字号
        self.font_minus = QToolButton()
        self.font_minus.setText("−")
        self.font_minus.setFixedSize(24, 24)
        self.font_minus.setStyleSheet(_TOOLBTN_QSS)
        self.font_minus.clicked.connect(lambda: self._change_font(-1))
        tb.addWidget(self.font_minus)

        self.font_label = QLabel("14")
        self.font_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_SECONDARY};
                font-size: 11px;
                background: transparent;
                min-width: 20px;
            }}
        """)
        self.font_label.setAlignment(Qt.AlignCenter)
        tb.addWidget(self.font_label)

        self.font_plus = QToolButton()
        self.font_plus.setText("+")
        self.font_plus.setFixedSize(24, 24)
        self.font_plus.setStyleSheet(_TOOLBTN_QSS)
        self.font_plus.clicked.connect(lambda: self._change_font(+1))
        tb.addWidget(self.font_plus)

        tb.addStretch(1)

        # 只读切换
        self.readonly_toggle = QToolButton()
        self.readonly_toggle.setText("只读")
        self.readonly_toggle.setCheckable(True)
        self.readonly_toggle.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: 1px solid #d4cfc0;
                border-radius: {RADIUS_XS}px;
                padding: 3px 9px;
                font-size: 11px;
            }}
            QToolButton:checked {{
                color: #fff;
                background: {BORDER_FOCUS};
                border: 1px solid {BORDER_FOCUS};
            }}
        """)
        self.readonly_toggle.toggled.connect(self._on_readonly_toggled)
        tb.addWidget(self.readonly_toggle)

        # 导出
        self.btn_export = QToolButton()
        self.btn_export.setText("⤓ 导出")
        self.btn_export.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: 1px solid #d4cfc0;
                border-radius: {RADIUS_XS}px;
                padding: 3px 9px;
                font-size: 11px;
            }}
            QToolButton:hover {{
                color: {ACCENT};
                border: 1px solid {ACCENT};
            }}
        """)
        self.btn_export.clicked.connect(self._on_export)
        tb.addWidget(self.btn_export)

        layout.addWidget(toolbar)

        # ---------- 编辑器 ----------
        self.editor = QPlainTextEdit()
        self.editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background: #fbfaf7;
                color: #1f2937;
                font-family: 'Georgia', 'Source Han Serif SC', 'Microsoft YaHei', serif;
                font-size: 14px;
                border: none;
                padding: 16px 28px;
                line-height: 1.65;
                selection-background-color: rgba(200, 148, 110, 0.25);
            }}
        """)
        self.editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.editor, 1)

        # ---------- 底部状态栏 ----------
        statusbar = QFrame()
        statusbar.setFixedHeight(24)
        statusbar.setStyleSheet(f"""
            QFrame {{
                background: #f3eee4;
                border-top: 1px solid #e5e0d6;
            }}
        """)
        sb = QHBoxLayout(statusbar)
        sb.setContentsMargins(20, 0, 16, 0)

        self.status_label = QLabel("字数: 0")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_SECONDARY};
                font-size: 10px;
                background: transparent;
            }}
        """)
        sb.addWidget(self.status_label)

        self.save_label = QLabel("")
        self.save_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 10px;
                background: transparent;
            }}
        """)
        sb.addStretch(1)
        sb.addWidget(self.save_label)

        layout.addWidget(statusbar)

    # ---------- 操作 ----------
    def open_file(self, path: str):
        """加载文件内容。"""
        try:
            text = Path(path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = Path(path).read_text(encoding="gbk", errors="replace")
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"{path}\n\n{e}")
            return
        self._file_path = path
        self.file_label.setText(Path(path).name)
        # 屏蔽 textChanged 防触发 auto-save
        self.editor.blockSignals(True)
        self.editor.setPlainText(text)
        self.editor.blockSignals(False)
        self._update_word_count()
        self.save_label.setText("已加载")

    def selected_text(self) -> str:
        return self.editor.textCursor().selectedText()

    def insert_text(self, text: str):
        """把文本插入到光标位置。"""
        cursor = self.editor.textCursor()
        cursor.insertText(text)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def _on_text_changed(self):
        self._update_word_count()
        if self._live_mode and self._file_path and self.live_toggle.isChecked():
            self._save_label_delayed()

    def _save_label_delayed(self):
        self.save_label.setText("保存中…")
        # 用 singleShot 简单 debounce
        from PySide6.QtCore import QTimer
        if not hasattr(self, "_save_timer"):
            self._save_timer = QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.timeout.connect(self._auto_save)
        self._save_timer.start(800)

    def _auto_save(self):
        if not self._file_path:
            return
        try:
            Path(self._file_path).write_text(
                self.editor.toPlainText(), encoding="utf-8")
            ts = time.strftime("%H:%M:%S")
            self.save_label.setText(f"已保存 {ts}")
        except Exception as e:  # noqa: BLE001
            self.save_label.setText(f"保存失败: {e}")

    def _change_font(self, delta: int):
        font = self.editor.font()
        cur = font.pointSize() or 14
        new_size = max(10, min(28, cur + delta))
        font.setPointSize(new_size)
        self.editor.setFont(font)
        self.font_label.setText(str(new_size))

    def _on_readonly_toggled(self, checked: bool):
        self.editor.setReadOnly(checked)

    def _on_export(self):
        if not self._file_path:
            path, _ = QFileDialog.getSaveFileName(
                self, "导出", "untitled.txt", "Text Files (*.txt);;Markdown (*.md)")
            if not path:
                return
            self._file_path = path
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "导出为", self._file_path,
                "Text Files (*.txt);;Markdown (*.md)")
            if not path:
                return
        try:
            Path(path).write_text(self.editor.toPlainText(), encoding="utf-8")
            self.save_label.setText(f"已导出 → {Path(path).name}")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "导出失败", str(e))

    def _update_word_count(self):
        text = self.editor.toPlainText()
        n = len([c for c in text if c.strip()])
        self.status_label.setText(f"字数: {n}")


# ============================================================
# 右侧:AI 助手面板
# ============================================================

class AssistantPanel(QFrame):
    """右侧 AI 写作助手。"""

    def __init__(self, editor: EditorPanel, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setObjectName("AssistantPanel")
        self.setStyleSheet(f"""
            QFrame#AssistantPanel {{
                background: {SURFACE};
                border-left: 1px solid {BORDER};
            }}
        """)
        self.setMinimumWidth(280)
        self.setMaximumWidth(380)

        self._llm_cfg: LLMConfig = load_config()
        self._thread: Optional[QThread] = None
        self._worker: Optional[_LLMWorker] = None
        self._current_preset: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(8)

        # ---------- 顶部:标题 + 文件路径 ----------
        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel("✨ 写作助手")
        self.title.setStyleSheet(f"""
            QLabel {{
                color: {TEXT};
                font-family: {FONT_HEADING};
                font-size: 14px;
                font-weight: 700;
                background: transparent;
            }}
        """)
        head.addWidget(self.title)
        head.addStretch(1)
        self.btn_settings = QToolButton()
        self.btn_settings.setText("⚙")
        self.btn_settings.setToolTip("LLM 设置")
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setFixedSize(24, 24)
        self.btn_settings.setStyleSheet(_TOOLBTN_QSS)
        self.btn_settings.clicked.connect(self._open_settings)
        head.addWidget(self.btn_settings)
        layout.addLayout(head)

        # 当前文档路径
        self.doc_path = QLabel("海鲸/海鲸:海军史上最大败类.txt")
        self.doc_path.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 10px;
                background: transparent;
                border: 1px solid {BORDER};
                border-radius: {RADIUS_XS}px;
                padding: 3px 7px;
            }}
        """)
        self.doc_path.setWordWrap(True)
        layout.addWidget(self.doc_path)

        # ---------- 大提示区 ----------
        self.hint_box = QFrame()
        self.hint_box.setStyleSheet(f"""
            QFrame {{
                background: {SURFACE_RAISED};
                border: 1px solid {BORDER};
                border-radius: {RADIUS}px;
                padding: 10px 12px;
            }}
        """)
        hb = QVBoxLayout(self.hint_box)
        hb.setSpacing(4)
        self.hint_icon = QLabel("✨")
        self.hint_icon.setStyleSheet(f"""
            QLabel {{
                color: {ACCENT};
                font-size: 14px;
                background: transparent;
            }}
        """)
        hb.addWidget(self.hint_icon)
        self.hint_title = QLabel("写作助手待命中")
        self.hint_title.setStyleSheet(f"""
            QLabel {{
                color: {TEXT};
                font-family: {FONT_HEADING};
                font-size: 12px;
                font-weight: 700;
                background: transparent;
            }}
        """)
        hb.addWidget(self.hint_title)
        self.hint_desc = QLabel(
            "它不会抢占写作空间。选中文本后点「引用」,或直接选下方动作。"
        )
        self.hint_desc.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_SECONDARY};
                font-size: 10.5px;
                background: transparent;
                line-height: 1.5;
            }}
        """)
        self.hint_desc.setWordWrap(True)
        hb.addWidget(self.hint_desc)
        layout.addWidget(self.hint_box)

        # ---------- 预设动作 ----------
        preset_label = QLabel("快捷动作")
        preset_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 10px;
                background: transparent;
                padding-top: 4px;
            }}
        """)
        layout.addWidget(preset_label)

        self.preset_buttons: List[QFrame] = []
        # 只显示 3 个最常用的(图里能看到 3 个)
        for key in ["总结", "大纲", "润色"]:
            btn = self._make_preset_btn(key, WRITE_PRESETS[key])
            layout.addWidget(btn)
            self.preset_buttons.append(btn)

        # ---------- 响应区(可滚动) ----------
        self.response = QTextEdit()
        self.response.setReadOnly(True)
        self.response.setStyleSheet(f"""
            QTextEdit {{
                background: {BG};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: {RADIUS}px;
                padding: 8px 10px;
                font-size: 12px;
                line-height: 1.6;
                selection-background-color: {ACCENT};
            }}
        """)
        self.response.setMinimumHeight(120)
        self.response.setPlaceholderText("(响应会显示在这里)")
        layout.addWidget(self.response, 1)

        # ---------- 输入框 ----------
        self.input = QTextEdit()
        self.input.setPlaceholderText("向智能体提问…")
        self.input.setFixedHeight(64)
        self.input.setStyleSheet(f"""
            QTextEdit {{
                background: {BG};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: {RADIUS}px;
                padding: 6px 8px;
                font-size: 12px;
            }}
            QTextEdit:focus {{
                border: 1px solid {ACCENT};
            }}
        """)
        layout.addWidget(self.input)

        # ---------- 发送 / 引用 / 插入 ----------
        action_row = QHBoxLayout()
        action_row.setSpacing(6)

        self.btn_quote = QPushButton("📎 引用")
        self.btn_quote.setCursor(Qt.PointingHandCursor)
        self.btn_quote.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_SM}px;
                padding: 4px 9px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: {ACCENT};
                border: 1px solid {ACCENT};
            }}
        """)
        self.btn_quote.clicked.connect(self._on_quote)
        action_row.addWidget(self.btn_quote)

        self.btn_insert = QPushButton("↳ 插入")
        self.btn_insert.setCursor(Qt.PointingHandCursor)
        self.btn_insert.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_SM}px;
                padding: 4px 9px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: {ACCENT};
                border: 1px solid {ACCENT};
            }}
            QPushButton:disabled {{
                color: {TEXT_MUTED};
            }}
        """)
        self.btn_insert.setEnabled(False)
        self.btn_insert.clicked.connect(self._on_insert)
        action_row.addWidget(self.btn_insert)

        action_row.addStretch(1)

        self.btn_send = QPushButton("发送  ⏎")
        self.btn_send.setCursor(Qt.PointingHandCursor)
        self.btn_send.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: #0f1724;
                border: none;
                border-radius: {RADIUS_SM}px;
                padding: 4px 14px;
                font-size: 11px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: {ACCENT_HOVER};
            }}
            QPushButton:disabled {{
                background: {BORDER};
                color: {TEXT_MUTED};
            }}
        """)
        self.btn_send.clicked.connect(self._on_send)
        action_row.addWidget(self.btn_send)
        layout.addLayout(action_row)

        # ---------- 底部:模型显示 ----------
        self.model_label = QLabel()
        self._update_model_label()
        self.model_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 9px;
                background: transparent;
            }}
        """)
        self.model_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self.model_label)

    # ---------- 预设按钮 ----------
    def _make_preset_btn(self, key: str, meta: dict):
        """预设动作卡(QFrame 替代 QPushButton,正确处理内部 layout)。"""
        label = meta["label"]
        desc_map = {
            "总结": "提炼结构、主题和缺口",
            "大纲": "整理标题和段落推进",
            "润色": "先选中文本会自动带引用",
        }
        desc = desc_map.get(key, "")

        btn = QFrame()
        btn.setObjectName(f"PresetBtn_{key}")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(48)
        btn.setStyleSheet(f"""
            QFrame#PresetBtn_{key} {{
                background: {SURFACE_RAISED};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_SM}px;
            }}
            QFrame#PresetBtn_{key}:hover {{
                border: 1px solid {ACCENT};
                background: {BG};
            }}
        """)

        wrap = QVBoxLayout(btn)
        wrap.setContentsMargins(12, 6, 12, 6)
        wrap.setSpacing(1)

        t = QLabel(label)
        t.setStyleSheet(
            f"color: {TEXT}; font-size: 12px; font-weight: 600;"
            f" background: transparent; border: none;"
        )
        wrap.addWidget(t)

        d = QLabel(desc)
        d.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px;"
            f" background: transparent; border: none;"
        )
        wrap.addWidget(d)

        # 自己处理 click
        def _click(ev, k=key):
            if ev.button() == Qt.LeftButton:
                self._run_preset(k)
        btn.mousePressEvent = _click
        return btn

    # 兼容老接口(如果在外部调用 .clicked)
    def _click(self):
        pass

    # ---------- 状态 ----------
    def _update_model_label(self):
        if self._llm_cfg.is_valid():
            self.model_label.setText(
                f"模型: {self._llm_cfg.model}  ·  {self._llm_cfg.provider}  ·  超清"
            )
        else:
            self.model_label.setText("⚠ 未配置 LLM(点 ⚙ 设置)")

    def refresh_config(self):
        self._llm_cfg = load_config()
        self._update_model_label()

    def set_doc_path(self, path: str):
        # 显示成 "海鲸/海鲸:海军史上最大败类.txt" 风格
        p = Path(path)
        try:
            rel = p.relative_to(default_workspace().parent)
        except ValueError:
            rel = p
        parts = list(rel.parts)
        if len(parts) > 1:
            text = "/".join(parts[:-1]) + "/" + parts[-1]
        else:
            text = parts[-1] if parts else p.name
        self.doc_path.setText(text)
        self.doc_path.setToolTip(str(p))

    # ---------- 交互 ----------
    def _on_quote(self):
        sel = self.editor.selected_text()
        if not sel:
            QMessageBox.information(self, "无选中文本", "请先在编辑器里选中要引用的文本。")
            return
        cur = self.input.toPlainText().rstrip()
        quote = "\n\n> " + sel.replace("\n", "\n> ")
        self.input.setPlainText((cur + quote) if cur else quote.lstrip())
        self.input.setFocus()

    def _on_insert(self):
        text = self.response.toPlainText().strip()
        if not text:
            return
        self.editor.insert_text("\n\n" + text + "\n\n")
        self.btn_insert.setEnabled(False)

    def _on_send(self):
        question = self.input.toPlainText().strip()
        if not question:
            return
        if not self._llm_cfg.is_valid():
            QMessageBox.warning(
                self, "未配置 LLM",
                "请先在右上角「⚙」配置 API key / base_url / model。")
            return
        # 自定义提问 → 用 "问答" 预设
        ctx = self.editor.toPlainText()
        if len(ctx) > 8000:
            ctx = ctx[:8000] + "…(已截断)"
        messages = build_messages(
            "问答",
            question=f"{question}\n\n---\n(以下为当前文档内容供参考,可能很长)\n\n{ctx}",
        )
        self._current_preset = "问答"
        self._start_stream(messages)

    def _run_preset(self, key: str):
        if self._thread is not None and self._thread.isRunning():
            return  # 忙碌中
        if not self._llm_cfg.is_valid():
            QMessageBox.warning(
                self, "未配置 LLM",
                "请先在右上角「⚙」配置 API key / base_url / model。")
            return
        self._current_preset = key
        ctx = self.editor.toPlainText()
        sel = self.editor.selected_text()
        # 截断过长上下文
        if len(ctx) > 12000:
            ctx = ctx[:12000] + "…(已截断)"
        if key == "润色":
            if not sel:
                QMessageBox.information(self, "无选中文本", "请先在编辑器里选中要润色的文本。")
                return
            messages = build_messages(key, selection=sel)
        else:
            messages = build_messages(key, context=ctx, anchor="此处", length="800")
        self._start_stream(messages)

    # ---------- 流式 ----------
    def _start_stream(self, messages: list):
        # 上一个还在跑就停了
        self._stop_stream()
        self.response.clear()
        self._set_busy(True)
        client = LLMClient(self._llm_cfg)
        self._thread = QThread(self)
        self._worker = _LLMWorker(client, messages)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.chunk.connect(self._on_chunk)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _stop_stream(self):
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)
        self._cleanup_thread()

    def _cleanup_thread(self):
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if self._thread:
            self._thread.deleteLater()
            self._thread = None

    def _on_chunk(self, delta: str):
        # 追加到 response
        cur = self.response.toPlainText()
        self.response.setPlainText(cur + delta)
        # 自动滚到底
        sb = self.response.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_finished(self, full: str):
        self._set_busy(False)
        self.btn_insert.setEnabled(bool(full.strip()))

    def _on_failed(self, err: str):
        self._set_busy(False)
        QMessageBox.warning(self, "LLM 错误", err)
        self.response.append(f"\n\n[错误] {err}")

    def _set_busy(self, busy: bool):
        self.btn_send.setEnabled(not busy)
        self.btn_send.setText("生成中…" if busy else "发送  ⏎")
        for b in self.preset_buttons:
            # QFrame 没有 setEnabled,改用 setProperty + 改 cursor
            b.setProperty("busy", busy)
            b.setCursor(Qt.ArrowCursor if busy else Qt.PointingHandCursor)
            b.setStyleSheet(b.styleSheet())  # 触发 refresh

    # ---------- 设置 ----------
    def _open_settings(self):
        # 防止连点 / 之前的 dialog 没关
        if hasattr(self, "_settings_dlg") and self._settings_dlg is not None:
            try:
                self._settings_dlg.raise_()
                self._settings_dlg.activateWindow()
                return
            except RuntimeError:
                self._settings_dlg = None
        try:
            from src.ui.llm_settings_dialog import LLMSettingsDialog
            dlg = LLMSettingsDialog(self._llm_cfg, self)
            self._settings_dlg = dlg
            # 用 open() 非阻塞模态,避免 exe 模式下 exec() 卡住
            dlg.finished.connect(self._on_settings_finished)
            dlg.open()
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "设置弹窗错误", f"无法打开设置:{e}")

    def _on_settings_finished(self, result: int):
        try:
            if result and self._settings_dlg is not None:
                self._llm_cfg = self._settings_dlg.get_config()
                save_config(self._llm_cfg)
                self._update_model_label()
                # 状态栏提示(在 main_window 那边)
                try:
                    from PySide6.QtWidgets import QApplication
                    top = self.window()  # MainWindow
                    if hasattr(top, "status_label"):
                        top.status_label.setText("LLM 配置已保存")
                except Exception:  # noqa: BLE001
                    pass
        finally:
            self._settings_dlg = None

    def shutdown(self):
        self._stop_stream()


# ============================================================
# 主容器
# ============================================================

# 一些 QSS 片段
ACCENT_SUBTLE_BACK = "rgba(200, 148, 110, 0.16)"
RADIUS_XS = 5

_TOOLBTN_QSS = f"""
    QToolButton {{
        background: transparent;
        color: {TEXT_SECONDARY};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_XS}px;
        font-size: 14px;
        font-weight: 600;
    }}
    QToolButton:hover {{
        color: {ACCENT};
        border: 1px solid {ACCENT};
    }}
"""


class WriteView(QWidget):
    """墨写主页面(三栏)。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workspace = default_workspace()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {BORDER};
            }}
        """)

        # 左
        self.file_tree = FileTreePanel(self._workspace)
        splitter.addWidget(self.file_tree)

        # 中
        self.editor = EditorPanel()
        splitter.addWidget(self.editor)

        # 右
        self.assistant = AssistantPanel(self.editor)
        splitter.addWidget(self.assistant)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([200, 800, 320])

        root.addWidget(splitter)

        # 信号
        self.file_tree.file_opened.connect(self._on_file_opened)

    def _on_file_opened(self, path: str):
        self.editor.open_file(path)
        self.assistant.set_doc_path(path)
        self.editor.setFocus()

    def shutdown(self):
        self.assistant.shutdown()
