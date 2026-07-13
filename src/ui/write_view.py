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

from PySide6.QtCore import Qt, Signal, QThread, QObject, QSettings, QDir, QSize, QTimer
from PySide6.QtGui import QAction, QFont, QTextCursor, QKeySequence
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QLineEdit, QTextEdit,
    QPlainTextEdit, QTreeView, QFileSystemModel, QPushButton, QFileDialog,
    QMessageBox, QSizePolicy, QSplitter, QToolButton, QApplication, QComboBox,
    QScrollArea, QMenu, QListWidget, QListWidgetItem, QLineEdit, QTabWidget,
)

from src.core.llm import (
    LLMClient, LLMConfig, load_config, save_config, build_messages,
    WRITE_PRESETS, LLMError,
)
from src.core.write_agent import (
    BUILTIN_PRESETS, QUICK_ACTIONS, QuickAction, WriteAgentPreset,
    get_preset, get_quick_action, build_agent_system, load_active_preset,
    save_active_preset,
)
from src.ui.theme import (
    BG, SURFACE, SURFACE_RAISED, BORDER, BORDER_FOCUS, ACCENT, ACCENT_HOVER,
    TEXT, TEXT_SECONDARY, TEXT_MUTED, FONT_HEADING, FONT_BODY, RADIUS, RADIUS_SM,
    SUCCESS, DANGER, TAG_BG,
)
from src.ui.markdown_highlighter import MarkdownHighlighter


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
# 排版字体预设(Phase 3a)
# ============================================================

# 4 套排版预设:字体族 / 基准字号 / 行距 / 段距 / 边距 / 配色
# 用户通过工具栏"排版"下拉切换,持久化到 QSettings。
TYPOGRAPHY_PRESETS: dict[str, dict] = {
    "护眼": {
        "font_family": "Georgia, 'Source Han Serif SC', 'Microsoft YaHei', serif",
        "base_size": 14,
        "line_height": 1.65,
        "para_margin": 8,
        "padding_v": 16,
        "padding_h": 28,
        "background": "#fbfaf7",
        "color": "#1f2937",
    },
    "紧凑": {
        "font_family": "'Consolas', 'Cascadia Code', 'Microsoft YaHei', 'Courier New', monospace",
        "base_size": 12,
        "line_height": 1.45,
        "para_margin": 4,
        "padding_v": 10,
        "padding_h": 20,
        "background": "#fefdfa",
        "color": "#1f2937",
    },
    "学术": {
        "font_family": "'Times New Roman', 'SimSun', 'Noto Serif SC', serif",
        "base_size": 13,
        "line_height": 1.75,
        "para_margin": 12,
        "padding_v": 24,
        "padding_h": 40,
        "background": "#ffffff",
        "color": "#1a1a1a",
    },
    "手稿": {
        "font_family": "'Caveat', 'KaiTi', 'STKaiti', 'Microsoft YaHei', cursive",
        "base_size": 16,
        "line_height": 1.9,
        "para_margin": 16,
        "padding_v": 32,
        "padding_h": 52,
        "background": "#fdf8ef",
        "color": "#3a2e1f",
    },
}


def _default_preset_name() -> str:
    return "护眼"


def _font_size_range(preset_name: str) -> tuple[int, int]:
    """在当前 preset 基准上允许 ±6 浮动。"""
    p = TYPOGRAPHY_PRESETS.get(preset_name, TYPOGRAPHY_PRESETS[_default_preset_name()])
    base = p["base_size"]
    return max(9, base - 6), base + 8  # 9 ~ base+8, 留出上调空间


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
        self.live_toggle.toggled.connect(self._on_live_toggled)
        tb.addWidget(self.live_toggle)

        # 排版预设下拉(Phase 3a)
        self.preset_btn = QToolButton()
        self.preset_btn.setText("排版")
        self.preset_btn.setCursor(Qt.PointingHandCursor)
        self.preset_btn.setStyleSheet(_TOOLBTN_QSS)
        self.preset_btn.setPopupMode(QToolButton.InstantPopup)
        preset_menu = QMenu(self.preset_btn)
        # 4 套预设 → 单选菜单项
        self._preset_actions: dict[str, QAction] = {}
        for name in TYPOGRAPHY_PRESETS:
            act = QAction(name, preset_menu)
            act.setCheckable(True)
            act.triggered.connect(lambda _checked=False, n=name: self._apply_preset(n))
            preset_menu.addAction(act)
            self._preset_actions[name] = act
        self.preset_btn.setMenu(preset_menu)
        tb.addWidget(self.preset_btn)

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

        # Checkpoint 历史(Phase 3b)
        self.btn_history = QToolButton()
        self.btn_history.setText("⏱ 历史")
        self.btn_history.setCheckable(True)
        self.btn_history.setStyleSheet(_TOOLBTN_QSS)
        self.btn_history.toggled.connect(self._on_history_toggled)
        tb.addWidget(self.btn_history)

        # 实时预览(Phase 3c)
        self.btn_preview = QToolButton()
        self.btn_preview.setText("📄 预览")
        self.btn_preview.setCheckable(True)
        self.btn_preview.setStyleSheet(_TOOLBTN_QSS)
        self.btn_preview.toggled.connect(self._on_preview_toggled)
        tb.addWidget(self.btn_preview)

        layout.addWidget(toolbar)

        # ---------- 编辑器 + 预览(splitter) ----------
        self.editor = QPlainTextEdit()
        # 排版预设:从 QSettings 读取(Phase 3a)
        cs_t = QSettings("WinEBook", "EditorTypography")
        self._current_preset: str = cs_t.value("preset", _default_preset_name(), type=str)
        if self._current_preset not in TYPOGRAPHY_PRESETS:
            self._current_preset = _default_preset_name()
        self._size_offset: int = cs_t.value("size_offset", 0, type=int)  # 在 preset 基础上的微调
        self._apply_preset(self._current_preset, _save=False)
        # 同步 preset 菜单的 checked 状态
        for n, a in self._preset_actions.items():
            a.setChecked(n == self._current_preset)
        self.editor.textChanged.connect(self._on_text_changed)

        # 预览面板(Phase 3c):QTextBrowser
        from PySide6.QtWidgets import QTextBrowser
        self.preview_browser = QTextBrowser()
        self.preview_browser.setOpenExternalLinks(False)  # 不让外部链接直接打开
        self.preview_browser.setStyleSheet(f"""
            QTextBrowser {{
                background: #ffffff;
                border-left: 1px solid {BORDER};
                border: none;
                padding: 20px 32px;
            }}
        """)
        self.preview_browser.hide()  # 默认隐藏

        # Splitter(默认只装 editor)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.editor)
        self.splitter.addWidget(self.preview_browser)
        self.splitter.setStretchFactor(0, 3)  # editor 占 3/4
        self.splitter.setStretchFactor(1, 1)  # preview 占 1/4
        self.splitter.setSizes([600, 200])
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        # 读 QSettings:上次预览状态
        cs_p = QSettings("WinEBook", "PreviewPanel")
        self._preview_enabled: bool = cs_p.value("enabled", False, type=bool)
        layout.addWidget(self.splitter, 1)

        # 预览 debounce timer
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._render_preview)

        # 同步 toolbar 状态
        self.btn_preview.setChecked(self._preview_enabled)
        if self._preview_enabled:
            self.preview_browser.show()
            self._render_preview()

        # Live 模式下的 Markdown 高亮
        self._highlighter = MarkdownHighlighter(self.editor.document())
        self._highlighter.setDocument(self.editor.document())

        # 在线补全(短 + 长):浮动 ghost 文本
        self._ghost_label = QLabel(self.editor)
        self._ghost_label.setStyleSheet(
            "QLabel {"
            " color: #9aa0ac;"
            " font-style: italic;"
            " background: transparent;"
            " border: none;"
            " padding: 0;"
            "}"
        )
        self._ghost_label.hide()
        self._ghost_text: str = ""
        self._ghost_anchor: int = 0  # ghost 锚点位置
        # 短补全 timer
        self._short_timer = QTimer(self)
        self._short_timer.setSingleShot(True)
        self._short_timer.timeout.connect(lambda: self._trigger_completion("short"))
        # 长补全 timer(段落级)
        self._long_timer = QTimer(self)
        self._long_timer.setSingleShot(True)
        self._long_timer.timeout.connect(lambda: self._trigger_completion("long"))
        self._completion_thread: Optional[QThread] = None
        self._completion_worker: Optional[_LLMWorker] = None
        self._completion_mode: str = ""  # "short" / "long"
        # 默认 debounce
        cs = QSettings("WinEBook", "InlineCompletion")
        self._completion_enabled: bool = cs.value("enabled", True, type=bool)
        self._short_debounce_ms: int = cs.value("short_debounce_ms", 800, type=int)
        self._long_debounce_ms: int = cs.value("long_debounce_ms", 2500, type=int)

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
        # Checkpoint 状态(Phase 3b)
        self.checkpoint_label = QLabel("")
        self.checkpoint_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_SECONDARY};
                font-size: 10px;
                background: transparent;
                padding-right: 8px;
            }}
        """)
        sb.addStretch(1)
        sb.addWidget(self.checkpoint_label)
        sb.addWidget(self.save_label)

        layout.addWidget(statusbar)

        # 初始化内联 Agent 编辑
        self._setup_inline_agent()

        # Checkpoint 面板(浮层,默认隐藏)
        self._checkpoint_panel: Optional["CheckpointPanel"] = None

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
        # 加载完立即渲染一次预览
        if hasattr(self, "_preview_enabled") and self._preview_enabled:
            self._render_preview()
        # 加载完更新 checkpoint 状态
        if hasattr(self, "_update_checkpoint_label"):
            self._update_checkpoint_label()

    def selected_text(self) -> str:
        return self.editor.textCursor().selectedText()

    def insert_text(self, text: str):
        """把文本插入到光标位置。"""
        cursor = self.editor.textCursor()
        cursor.insertText(text)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def _on_text_changed(self):
        # 防御:初始化期间可能触发
        if not hasattr(self, "status_label") or self.status_label is None:
            return
        self._update_word_count()
        if self._live_mode and self._file_path and self.live_toggle.isChecked():
            self._save_label_delayed()
        # 预览面板(Phase 3c):开启时 300ms debounce 渲染
        if hasattr(self, "_preview_enabled") and self._preview_enabled:
            if hasattr(self, "_preview_timer"):
                self._preview_timer.start(300)
        # 触发在线补全(短 + 长)
        if self._completion_enabled and self.live_toggle.isChecked():
            self._hide_ghost()
            # 取消两个 timer
            self._short_timer.stop()
            self._long_timer.stop()
            # 检测是否在段落结尾(决定启动短还是长)
            cursor = self.editor.textCursor()
            pos = cursor.position()
            full = self.editor.toPlainText()
            prefix = full[max(0, pos - 100):pos]
            at_para_end = bool(prefix) and prefix[-1] in "。！？.!?\n…"
            if at_para_end and len(prefix.rstrip()) >= 5:
                # 段落结尾 + 一定长度 → 长补全
                self._long_timer.start(self._long_debounce_ms)
            else:
                # 普通停顿时短补全
                self._short_timer.start(self._short_debounce_ms)

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
            # Checkpoint(Phase 3b):根据触发策略自动 snapshot
            self._maybe_create_checkpoint()
        except Exception as e:  # noqa: BLE001
            self.save_label.setText(f"保存失败: {e}")

    def _maybe_create_checkpoint(self, trigger: str = "auto-chars", note: str = ""):
        """根据策略创建一条 checkpoint,自动更新状态栏。"""
        if not self._file_path:
            return
        try:
            from src.core.checkpoint import (
                create_checkpoint, default_checkpoint_root,
                should_create_checkpoint, last_checkpoint,
            )
            content = self.editor.toPlainText()
            root = default_checkpoint_root()
            # 手动保存 / 还原后 → 总是创建(跳过触发判断)
            if trigger in ("manual", "auto-pre-restore"):
                cp = create_checkpoint(
                    self._file_path, content, trigger=trigger,
                    note=note, root=root)
            else:
                # 自动:先判断是否到阈值
                if not should_create_checkpoint(self._file_path, root=root):
                    return
                cp = create_checkpoint(
                    self._file_path, content, trigger=trigger,
                    note=note, root=root)
            if cp is None:
                return  # 去重跳过
            self._update_checkpoint_label()
            # 通知 checkpoint panel 刷新
            if hasattr(self, "_checkpoint_panel") and self._checkpoint_panel:
                self._checkpoint_panel.refresh()
        except Exception as e:  # noqa: BLE001
            # checkpoint 失败不影响主保存
            pass

    def _update_checkpoint_label(self):
        """状态栏:显示最近 checkpoint 时间。"""
        if not self._file_path:
            self.checkpoint_label.setText("")
            return
        try:
            from src.core.checkpoint import last_checkpoint, default_checkpoint_root
            cp = last_checkpoint(self._file_path, root=default_checkpoint_root())
            if cp is None:
                self.checkpoint_label.setText("⏱ 尚无快照")
            else:
                ago = int(time.time()) - cp.ts
                if ago < 60:
                    ago_str = f"{ago}秒前"
                elif ago < 3600:
                    ago_str = f"{ago // 60}分钟前"
                elif ago < 86400:
                    ago_str = f"{ago // 3600}小时前"
                else:
                    ago_str = f"{ago // 86400}天前"
                self.checkpoint_label.setText(f"⏱ 上次快照 {ago_str} · {cp.short_hash()}")
        except Exception:
            self.checkpoint_label.setText("⏱ 快照:—")

    def _change_font(self, delta: int):
        """在当前 preset 基础上 ±1 字号,持久化偏移。"""
        preset = TYPOGRAPHY_PRESETS.get(
            self._current_preset, TYPOGRAPHY_PRESETS[_default_preset_name()])
        lo, hi = _font_size_range(self._current_preset)
        new_offset = max(-6, min(8, self._size_offset + delta))
        new_size = max(lo, min(hi, preset["base_size"] + new_offset))
        # 算出实际达到的 offset(可能被 range 截断)
        actual_offset = new_size - preset["base_size"]
        if actual_offset == self._size_offset:
            return
        self._size_offset = actual_offset
        cs_t = QSettings("WinEBook", "EditorTypography")
        cs_t.setValue("size_offset", self._size_offset)
        font = self.editor.font()
        font.setPointSize(new_size)
        self.editor.setFont(font)
        self.font_label.setText(str(new_size))

    def _apply_preset(self, name: str, _save: bool = True):
        """应用一套排版预设:字体族 / 字号 / 行距 / 段距 / 边距 / 配色。"""
        if name not in TYPOGRAPHY_PRESETS:
            return
        self._current_preset = name
        p = TYPOGRAPHY_PRESETS[name]
        # 1. 字体 + 字号
        font = QFont()
        font.setStyleHint(QFont.Serif if "serif" in p["font_family"].lower() else QFont.AnyStyle)
        font.setPointSize(p["base_size"] + self._size_offset)
        self.editor.setFont(font)
        self.font_label.setText(str(p["base_size"] + self._size_offset))
        # 2. 编辑器整体样式(背景/颜色/字体族/边距)
        self.editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {p["background"]};
                color: {p["color"]};
                font-family: {p["font_family"]};
                border: none;
                padding: {p["padding_v"]}px {p["padding_h"]}px;
                selection-background-color: rgba(200, 148, 110, 0.25);
            }}
        """)
        # 3. 段落级样式:行距 + 段距(通过 document 的 defaultStyleSheet)
        #    Qt 的 QPlainTextEdit 支持 line-height / margin CSS
        self.editor.document().setDefaultStyleSheet(
            f"p {{ line-height: {p['line_height']}; margin: 0 0 {p['para_margin']}px 0; }}"
        )
        # 4. 同步菜单的 checked
        for n, a in self._preset_actions.items():
            a.setChecked(n == name)
        # 5. 持久化
        if _save:
            cs_t = QSettings("WinEBook", "EditorTypography")
            cs_t.setValue("preset", name)
            cs_t.setValue("size_offset", self._size_offset)

    def _on_live_toggled(self, checked: bool):
        """Live 模式:开关 Markdown 实时高亮 + 在线补全。"""
        if checked:
            self._highlighter.setDocument(self.editor.document())
        else:
            self._highlighter.setDocument(None)
            self._hide_ghost()
            self._short_timer.stop()
            self._long_timer.stop()
        self._highlighter.rehighlight()

    # ---------- 在线补全(短 + 长) ----------
    def _trigger_completion(self, mode: str = "short"):
        """防抖到期:取上下文,调 LLM 拿补全。

        mode:
        - short:短补全,8-80 字,800ms 防抖
        - long: 长补全,段落级,200-800 字,2500ms 防抖
        """
        from src.core.llm import LLMClient, load_config
        cfg = load_config()
        if not cfg.is_valid():
            return
        cursor = self.editor.textCursor()
        pos = cursor.position()
        full = self.editor.toPlainText()
        # 长补全:抽更多上下文
        if mode == "long":
            pre_n, suf_n = 2500, 200
            max_tok = 1024
            sys_prompt = (
                "你是一位中文写作助手,任务是根据上下文续写下一段。"
                "输出**整段内容**,保持原文的文风、节奏、人称。"
                "不要重复前缀或后缀,不要解释,不要带引号。"
                "长度 200-800 字。"
            )
        else:
            pre_n, suf_n = 1500, 500
            max_tok = 128
            sys_prompt = (
                "你是一位中文写作助手,任务是根据上下文续写下一句或下一段。"
                "只输出续写的内容,不要重复前缀或后缀,不要解释,不要带引号。"
                "长度控制在 8-80 字以内。"
            )
        prefix = full[max(0, pos - pre_n):pos]
        suffix = full[pos:pos + suf_n]
        if not prefix.strip():
            return
        if cursor.hasSelection():
            return
        cache_key = (mode, pos, hash(prefix[-100:]))
        if cache_key == getattr(self, "_last_completion_key", None):
            return
        self._last_completion_key = cache_key

        # BM25 检索(用工作区)
        from src.core.bm25 import search_workspace, format_hits_for_prompt
        from src.core.write_agent import default_workspace_root
        ctx_text = ""
        try:
            ws_root = default_workspace_root()
            hits = search_workspace(ws_root, prefix[-300:], k=2, snippet_chars=400)
            ctx_text = format_hits_for_prompt(hits, max_total_chars=800)
        except Exception:  # noqa: BLE001
            ctx_text = ""

        user = (
            f"<<< PREFIX\n{prefix}\n<<< SUFFIX\n{suffix}\n"
            f"<<< CONTINUE\n请续写 PREFIX 与 SUFFIX 之间的衔接文字。"
        )
        if ctx_text:
            user = user + "\n\n<<< WORKSPACE_CONTEXT\n" + ctx_text

        cfg.max_tokens = max_tok
        cfg.temperature = 0.6
        client = LLMClient(cfg)
        self._stop_completion()
        self._completion_mode = mode
        self._completion_thread = QThread(self)
        self._completion_worker = _LLMWorker(client, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user},
        ])
        self._completion_worker.moveToThread(self._completion_thread)
        self._completion_thread.started.connect(self._completion_worker.run)
        self._completion_worker.finished.connect(self._on_completion_done)
        self._completion_worker.failed.connect(self._on_completion_failed)
        self._completion_worker.finished.connect(self._completion_thread.quit)
        self._completion_worker.failed.connect(self._completion_thread.quit)
        self._completion_thread.finished.connect(self._cleanup_completion_thread)
        self._completion_thread.start()
        self._ghost_anchor = pos

    def _on_completion_done(self, full: str):
        if not full.strip():
            return
        # 截掉多余的引号/前缀
        text = full.strip()
        for prefix in ("```", "「", "「「"):
            if text.startswith(prefix):
                text = text[len(prefix):]
        text = text.split("\n\n")[0]  # 只取第一段
        if not text:
            return
        self._ghost_text = text
        self._show_ghost()

    def _on_completion_failed(self, err: str):
        # 静默失败
        self._hide_ghost()

    def _stop_completion(self):
        if self._completion_thread and self._completion_thread.isRunning():
            self._completion_thread.quit()
            self._completion_thread.wait(500)
        self._cleanup_completion_thread()

    def _cleanup_completion_thread(self):
        if self._completion_worker:
            self._completion_worker.deleteLater()
            self._completion_worker = None
        if self._completion_thread:
            self._completion_thread.deleteLater()
            self._completion_thread = None

    def _show_ghost(self):
        """把 ghost 文本浮在光标位置。"""
        if not self._ghost_text:
            return
        # 取光标在 viewport 中的矩形
        cursor = self.editor.textCursor()
        rect = self.editor.cursorRect(cursor)
        # 转为编辑器 widget 坐标
        x = rect.right() + 2
        y = rect.top()
        self._ghost_label.setText(self._ghost_text)
        self._ghost_label.adjustSize()
        # 限制 ghost 宽度,避免溢出
        max_w = self.editor.viewport().width() - x - 16
        if self._ghost_label.width() > max_w > 100:
            self._ghost_label.setFixedWidth(max_w)
            self._ghost_label.setWordWrap(True)
        else:
            self._ghost_label.setWordWrap(False)
        self._ghost_label.move(x, y)
        self._ghost_label.raise_()
        self._ghost_label.show()

    def _hide_ghost(self):
        self._ghost_text = ""
        self._ghost_label.hide()

    def _accept_ghost(self):
        """Tab:接受 ghost 文本。"""
        if not self._ghost_text:
            return False
        cursor = self.editor.textCursor()
        cursor.insertText(self._ghost_text)
        self._hide_ghost()
        return True

    def keyPressEvent(self, ev):  # noqa: N802
        # Tab 接受 ghost
        if ev.key() == Qt.Key_Tab and self._ghost_text:
            if self._accept_ghost():
                ev.accept()
                return
        # Esc 取消 ghost
        if ev.key() == Qt.Key_Escape and self._ghost_text:
            self._hide_ghost()
            ev.accept()
            return
        super().keyPressEvent(ev)

    # ---------- 内联 Agent 编辑(浮动窗) ----------
    def _setup_inline_agent(self):
        # ✨ 浮动按钮(选区时显示)
        self._btn_ai_edit = QToolButton(self.editor)
        self._btn_ai_edit.setText("✨")
        self._btn_ai_edit.setToolTip("AI 改写选区")
        self._btn_ai_edit.setCursor(Qt.PointingHandCursor)
        self._btn_ai_edit.setFixedSize(28, 28)
        self._btn_ai_edit.setStyleSheet(f"""
            QToolButton {{
                background: {ACCENT};
                color: #0f1724;
                border: none;
                border-radius: 14px;
                font-size: 14px;
                font-weight: 700;
            }}
            QToolButton:hover {{
                background: {ACCENT_HOVER};
            }}
        """)
        self._btn_ai_edit.hide()
        self._btn_ai_edit.clicked.connect(self._show_inline_agent)

        # 浮动 Agent 框
        self._inline_agent = QFrame(self.editor)
        self._inline_agent.setObjectName("InlineAgent")
        self._inline_agent.setStyleSheet(f"""
            QFrame#InlineAgent {{
                background: {SURFACE};
                border: 1px solid {ACCENT};
                border-radius: 8px;
            }}
        """)
        self._inline_agent.setFixedWidth(380)
        self._inline_agent.setFixedHeight(280)
        ial = QVBoxLayout(self._inline_agent)
        ial.setContentsMargins(10, 8, 10, 8)
        ial.setSpacing(6)

        # 顶部:标题 + 关闭
        head = QHBoxLayout()
        head.setSpacing(6)
        title = QLabel("✨ AI 改写")
        title.setStyleSheet(f"color: {TEXT}; font-size: 12px; font-weight: 700;"
                           f" background: transparent; border: none;")
        head.addWidget(title)
        head.addStretch(1)
        self._ia_close = QToolButton()
        self._ia_close.setText("×")
        self._ia_close.setFixedSize(18, 18)
        self._ia_close.setCursor(Qt.PointingHandCursor)
        self._ia_close.setStyleSheet(
            f"QToolButton {{ background: transparent; color: {TEXT_MUTED};"
            f"  border: none; font-size: 14px; padding: 0; }}"
            f"QToolButton:hover {{ color: {DANGER}; }}"
        )
        self._ia_close.clicked.connect(self._hide_inline_agent)
        head.addWidget(self._ia_close)
        ial.addLayout(head)

        # 选区预览
        self._ia_selection = QLabel("(选区)")
        self._ia_selection.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; background: {SURFACE_RAISED};"
            f" border: 1px solid {BORDER}; border-radius: 4px; padding: 4px 6px;"
        )
        self._ia_selection.setWordWrap(True)
        self._ia_selection.setMaximumHeight(40)
        ial.addWidget(self._ia_selection)

        # 输入框
        self._ia_input = QLineEdit()
        self._ia_input.setPlaceholderText("输入改写指令,如:改得更正式 / 加一个比喻 / 缩短一半…")
        self._ia_input.setStyleSheet(f"""
            QLineEdit {{
                background: {BG};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 11px;
            }}
            QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
        """)
        self._ia_input.returnPressed.connect(self._send_inline_agent)
        ial.addWidget(self._ia_input)

        # 发送按钮
        send_row = QHBoxLayout()
        send_row.setSpacing(6)
        send_row.addStretch(1)
        self._ia_send = QPushButton("发送")
        self._ia_send.setCursor(Qt.PointingHandCursor)
        self._ia_send.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {ACCENT};
                border: 1px solid {ACCENT}; border-radius: 4px;
                padding: 3px 12px; font-size: 11px;
            }}
            QPushButton:hover {{ background: {ACCENT}; color: #0f1724; }}
            QPushButton:disabled {{ color: {TEXT_MUTED}; border: 1px solid {TEXT_MUTED}; }}
        """)
        self._ia_send.clicked.connect(self._send_inline_agent)
        send_row.addWidget(self._ia_send)
        ial.addLayout(send_row)

        # 结果区
        ial.addWidget(QLabel("生成结果:"))
        self._ia_result = QTextEdit()
        self._ia_result.setReadOnly(True)
        self._ia_result.setStyleSheet(f"""
            QTextEdit {{
                background: {BG}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 4px;
                padding: 5px 7px; font-size: 11px; line-height: 1.5;
            }}
        """)
        self._ia_result.setPlaceholderText("(等待生成)")
        ial.addWidget(self._ia_result, 1)

        # 应用/重生成
        apply_row = QHBoxLayout()
        apply_row.setSpacing(6)
        self._ia_apply = QPushButton("✓ 应用到选区")
        self._ia_apply.setCursor(Qt.PointingHandCursor)
        self._ia_apply.setEnabled(False)
        self._ia_apply.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT}; color: #0f1724; border: none;
                border-radius: 4px; padding: 4px 10px; font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {ACCENT_HOVER}; }}
            QPushButton:disabled {{ background: {BORDER}; color: {TEXT_MUTED}; }}
        """)
        self._ia_apply.clicked.connect(self._apply_inline_agent)
        apply_row.addWidget(self._ia_apply)

        self._ia_regen = QPushButton("↻ 重生成")
        self._ia_regen.setCursor(Qt.PointingHandCursor)
        self._ia_regen.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_SECONDARY};
                border: 1px solid {BORDER}; border-radius: 4px;
                padding: 4px 10px; font-size: 11px;
            }}
            QPushButton:hover {{ color: {ACCENT}; border: 1px solid {ACCENT}; }}
        """)
        self._ia_regen.clicked.connect(self._send_inline_agent)
        apply_row.addWidget(self._ia_regen)
        apply_row.addStretch(1)
        ial.addLayout(apply_row)

        self._inline_agent.hide()
        self._ia_original: str = ""
        self._ia_thread: Optional[QThread] = None
        self._ia_worker: Optional[_LLMWorker] = None
        # selectionChanged 信号
        self.editor.selectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self):
        cursor = self.editor.textCursor()
        if cursor.hasSelection() and len(cursor.selectedText()) >= 2:
            rect = self.editor.cursorRect(cursor)
            # 选区上方一点点
            x = max(0, rect.left() - 30)
            y = max(0, rect.top() - 32)
            self._btn_ai_edit.move(x, y)
            self._btn_ai_edit.show()
        else:
            self._btn_ai_edit.hide()
            # 不自动关 inline_agent,让用户自己决定

    def _show_inline_agent(self):
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            return
        sel = cursor.selectedText()
        self._ia_original = sel
        # 预览:截前 80 字
        preview = sel.replace("\n", " ")
        if len(preview) > 80:
            preview = preview[:80] + "…"
        self._ia_selection.setText(f"选区: {preview}")
        # 定位到选区下方
        rect = self.editor.cursorRect(cursor)
        x = max(0, rect.left())
        y = rect.bottom() + 6
        # 不要超出编辑器
        max_x = self.editor.viewport().width() - self._inline_agent.width()
        if x > max_x:
            x = max(0, max_x)
        self._inline_agent.move(x, y)
        self._inline_agent.show()
        self._inline_agent.raise_()
        self._ia_input.clear()
        self._ia_input.setFocus()
        self._ia_result.clear()
        self._ia_apply.setEnabled(False)

    def _hide_inline_agent(self):
        self._inline_agent.hide()
        self._stop_inline_agent()

    def _send_inline_agent(self):
        if self._ia_thread and self._ia_thread.isRunning():
            return
        from src.core.llm import LLMClient, load_config
        cfg = load_config()
        if not cfg.is_valid():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "未配置 LLM", "请先在助手面板右上角「⚙」配置。")
            return
        instruction = self._ia_input.text().strip() or "润色这段文本,保持原意"
        system = (
            "你是一位行内编辑。任务是根据用户指令改写指定文本。\n"
            "保持原意,只调整表达、节奏、措辞。\n"
            f"用户指令:{instruction}\n"
            "输出**仅修改后的文本**,不带引号、不带解释、不带'改写后:'等前缀。"
        )
        user = f"原文:\n{self._ia_original}"
        client = LLMClient(cfg)
        self._ia_result.clear()
        self._ia_apply.setEnabled(False)
        self._ia_send.setEnabled(False)
        self._ia_send.setText("生成中…")
        self._ia_thread = QThread(self)
        self._ia_worker = _LLMWorker(client, [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        self._ia_worker.moveToThread(self._ia_thread)
        self._ia_thread.started.connect(self._ia_worker.run)
        self._ia_worker.chunk.connect(self._ia_on_chunk)
        self._ia_worker.finished.connect(self._ia_on_done)
        self._ia_worker.failed.connect(self._ia_on_failed)
        self._ia_worker.finished.connect(self._ia_thread.quit)
        self._ia_worker.failed.connect(self._ia_thread.quit)
        self._ia_thread.finished.connect(self._cleanup_ia_thread)
        self._ia_thread.start()

    def _ia_on_chunk(self, delta: str):
        cur = self._ia_result.toPlainText()
        self._ia_result.setPlainText(cur + delta)
        sb = self._ia_result.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _ia_on_done(self, full: str):
        self._ia_send.setEnabled(True)
        self._ia_send.setText("发送")
        self._ia_apply.setEnabled(bool(full.strip()))

    def _ia_on_failed(self, err: str):
        self._ia_send.setEnabled(True)
        self._ia_send.setText("发送")
        self._ia_result.setPlainText(f"[错误] {err}")

    def _apply_inline_agent(self):
        new_text = self._ia_result.toPlainText().strip()
        if not new_text or not self._ia_original:
            return
        # Phase 4a:先弹 Diff 对话框让用户确认(红绿对比)
        if new_text != self._ia_original:
            from src.ui.diff_dialog import DiffDialog
            dlg = DiffDialog(
                self._ia_original, new_text,
                title="AI 修改预览",
                parent=self,
            )
            if dlg.exec() != DiffDialog.Accepted:
                return  # 用户拒绝
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(new_text)
        else:
            self.editor.insert_text(new_text)
        self._hide_inline_agent()

    def _stop_inline_agent(self):
        if self._ia_thread and self._ia_thread.isRunning():
            self._ia_thread.quit()
            self._ia_thread.wait(500)
        self._cleanup_ia_thread()

    def _cleanup_ia_thread(self):
        if self._ia_worker:
            self._ia_worker.deleteLater()
            self._ia_worker = None
        if self._ia_thread:
            self._ia_thread.deleteLater()
            self._ia_thread = None

    def _on_readonly_toggled(self, checked: bool):
        self.editor.setReadOnly(checked)

    def _on_history_toggled(self, checked: bool):
        """显示 / 隐藏 CheckpointPanel(Phase 3b)。"""
        if checked:
            if self._checkpoint_panel is None:
                self._checkpoint_panel = CheckpointPanel(self)
                # 浮在 editor 顶部
                self._checkpoint_panel.move(
                    (self.width() - 480) // 2,
                    60,
                )
            self._checkpoint_panel.refresh()
            self._checkpoint_panel.show()
            self._checkpoint_panel.raise_()
        else:
            if self._checkpoint_panel:
                self._checkpoint_panel.hide()

    def _on_preview_toggled(self, checked: bool):
        """显示 / 隐藏 Markdown 实时预览(Phase 3c)。"""
        self._preview_enabled = checked
        if checked:
            self.preview_browser.show()
            self._render_preview()
        else:
            self.preview_browser.hide()
        # 持久化
        cs_p = QSettings("WinEBook", "PreviewPanel")
        cs_p.setValue("enabled", checked)

    def _render_preview(self):
        """把 editor 当前内容渲染到 QTextBrowser(带 GFM CSS)。"""
        from src.core.markdown_render import render_full_html
        text = self.editor.toPlainText()
        try:
            title = self.file_label.text() or "预览"
            html = render_full_html(text, title=title)
            self.preview_browser.setHtml(html)
        except Exception:  # noqa: BLE001
            # 渲染失败至少不崩
            pass

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
        if not hasattr(self, "status_label") or self.status_label is None:
            return
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
        self._active_agent: WriteAgentPreset = get_preset(load_active_preset())
        self._quotes: List[str] = []  # 引用选区列表
        self._max_quotes = 5
        self._quote_expanded: bool = False  # 引用列表是否展开

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

        # Agent 人设选择器
        agent_row = QHBoxLayout()
        agent_row.setSpacing(4)
        agent_lbl = QLabel("人设:")
        agent_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
        agent_row.addWidget(agent_lbl)

        self.cmb_agent = QComboBox()
        self.cmb_agent.setStyleSheet(f"""
            QComboBox {{
                background: {SURFACE_RAISED};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_XS}px;
                padding: 3px 8px;
                font-size: 11px;
            }}
            QComboBox:hover {{
                border: 1px solid {ACCENT};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 16px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {TEXT_MUTED};
                margin-right: 4px;
            }}
            QComboBox QAbstractItemView {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER};
                selection-background-color: {ACCENT};
                selection-color: #0f1724;
                padding: 4px;
                font-size: 11px;
            }}
        """)
        for p in BUILTIN_PRESETS:
            self.cmb_agent.addItem(f"{p.emoji}  {p.name}", p.id)
        idx = next((i for i, p in enumerate(BUILTIN_PRESETS) if p.id == self._active_agent.id), 0)
        self.cmb_agent.setCurrentIndex(idx)
        self.cmb_agent.currentIndexChanged.connect(self._on_agent_changed)
        agent_row.addWidget(self.cmb_agent, 1)
        layout.addLayout(agent_row)

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
        # 7 种快捷操作(对应 PRD §5.2)
        for action in QUICK_ACTIONS:
            btn = self._make_quick_action_btn(action)
            layout.addWidget(btn)
            self.preset_buttons.append(btn)

        # ---------- 引用选区列表(条件显示) ----------
        self.quote_box = QFrame()
        self.quote_box.setStyleSheet(f"""
            QFrame {{
                background: {SURFACE_RAISED};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_SM}px;
            }}
        """)
        qb = QVBoxLayout(self.quote_box)
        qb.setContentsMargins(8, 6, 8, 6)
        qb.setSpacing(3)
        self.quote_header = QLabel(f"引用 · 0/{self._max_quotes}")
        self.quote_header.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        qb.addWidget(self.quote_header)
        self.quote_items_layout = QVBoxLayout()
        self.quote_items_layout.setSpacing(2)
        qb.addLayout(self.quote_items_layout)
        self.quote_box.hide()
        layout.addWidget(self.quote_box)

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

        self.btn_quote = QPushButton("📎 引用选区")
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

        self.btn_insert = QPushButton("↳ 应用替换")
        self.btn_insert.setCursor(Qt.PointingHandCursor)
        self.btn_insert.setToolTip("用 AI 响应替换编辑器中的原选区")
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

    # ---------- 快捷操作按钮 ----------
    def _make_quick_action_btn(self, action: QuickAction):
        """快捷操作按钮(QFrame 替代 QPushButton,正确处理内部 layout)。"""
        btn = QFrame()
        btn.setObjectName(f"QuickAction_{action.id}")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(42)
        btn.setStyleSheet(f"""
            QFrame#QuickAction_{action.id} {{
                background: {SURFACE_RAISED};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_SM}px;
            }}
            QFrame#QuickAction_{action.id}:hover {{
                border: 1px solid {ACCENT};
                background: {BG};
            }}
        """)

        # 横向布局:左标签,右模式徽标
        h = QHBoxLayout(btn)
        h.setContentsMargins(10, 4, 8, 4)
        h.setSpacing(6)

        t = QLabel(f"{action.label}  ·  {action.desc}")
        t.setStyleSheet(
            f"color: {TEXT}; font-size: 11px;"
            f" background: transparent; border: none;"
        )
        h.addWidget(t, 1)

        # 模式徽标(chat/edit)
        mode_badge = QLabel(action.mode)
        mode_badge.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 600;"
            f" background: transparent; border: 1px solid {BORDER};"
            f" border-radius: 3px; padding: 1px 4px;"
        )
        h.addWidget(mode_badge)

        # 处理 click
        def _click(ev, a=action):
            if ev.button() == Qt.LeftButton:
                self._run_quick_action(a)
        btn.mousePressEvent = _click
        return btn

    # 兼容老接口
    def _click(self):
        pass

    # ---------- Agent 人设切换 ----------
    def _on_agent_changed(self, idx: int):
        pid = self.cmb_agent.itemData(idx)
        if pid:
            self._active_agent = get_preset(pid)
            save_active_preset(pid)

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

    def set_editor(self, editor: "EditorPanel"):
        """Phase 4b 多 Tab:切换当前 tab 的 editor 引用。"""
        self.editor = editor
        if editor and editor._file_path:
            self.set_doc_path(editor._file_path)

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

    # ---------- 引用选区(折叠分页) ----------
    def _on_quote(self):
        sel = self.editor.selected_text()
        if not sel:
            QMessageBox.information(self, "无选中文本", "请先在编辑器里选中要引用的文本。")
            return
        if len(self._quotes) >= self._max_quotes:
            # 超过上限:清掉最旧的(保留最新的)
            self._quotes.pop(0)
        self._quotes.append(sel)
        self._render_quotes()

    def _render_quotes(self):
        # 清空旧的
        while self.quote_items_layout.count():
            it = self.quote_items_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        # 重新填充
        n = len(self._quotes)
        self.quote_header.setText(f"引用 · {n}/{self._max_quotes}")
        # 折叠:超过 _collapsed_show 条时折叠
        collapsed_show = 3
        show_all = self._quote_expanded or n <= collapsed_show
        items = list(enumerate(self._quotes))
        if not show_all:
            items = items[:collapsed_show]
        for i, q in items:
            row = QHBoxLayout()
            row.setSpacing(4)
            preview = q.replace("\n", " ")
            if len(preview) > 60:
                preview = preview[:60] + "…"
            lbl = QLabel(f"{i+1}. {preview}")
            lbl.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;"
                f" border: none;"
            )
            lbl.setToolTip(q)
            row.addWidget(lbl, 1)
            del_btn = QToolButton()
            del_btn.setText("×")
            del_btn.setFixedSize(16, 16)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet(
                f"QToolButton {{ background: transparent; color: {TEXT_MUTED};"
                f"  border: none; font-size: 13px; padding: 0; }}"
                f"QToolButton:hover {{ color: {DANGER}; }}"
            )
            del_btn.clicked.connect(lambda _, idx=i: self._del_quote(idx))
            row.addWidget(del_btn)
            wrap = QWidget()
            wrap.setStyleSheet("background: transparent; border: none;")
            wrap.setLayout(row)
            self.quote_items_layout.addWidget(wrap)
        # 折叠/展开按钮
        if n > collapsed_show:
            toggle_text = ("收起" if show_all
                           else f"…展开剩余 {n - collapsed_show} 条")
            toggle_btn = QToolButton()
            toggle_btn.setText(toggle_text)
            toggle_btn.setCursor(Qt.PointingHandCursor)
            toggle_btn.setStyleSheet(
                f"QToolButton {{ background: transparent; color: {ACCENT};"
                f"  border: none; font-size: 10px; padding: 2px 4px; text-align: left; }}"
                f"QToolButton:hover {{ color: {ACCENT_HOVER}; }}"
            )
            toggle_btn.clicked.connect(self._toggle_quotes_expand)
            self.quote_items_layout.addWidget(toggle_btn)
        # 控制显隐
        if self._quotes:
            self.quote_box.show()
        else:
            self.quote_box.hide()

    def _toggle_quotes_expand(self):
        self._quote_expanded = not self._quote_expanded
        self._render_quotes()

    def _del_quote(self, idx: int):
        if 0 <= idx < len(self._quotes):
            self._quotes.pop(idx)
            self._render_quotes()

    # ---------- 交互 ----------
    def _on_quote_OLD_KEEP_COMPAT(self):  # 占位防止被覆盖(实际已被 _on_quote 替换)
        pass

    def _on_insert(self):
        """edit 模式:用 AI 输出替换编辑器选区;chat 模式:插入到光标。"""
        text = self.response.toPlainText().strip()
        if not text:
            return
        if getattr(self, "_edit_action_mode", False):
            # 替换原选区
            cursor = self.editor.editor.textCursor()
            if cursor.hasSelection():
                cursor.insertText(text)
            else:
                self.editor.insert_text(text)
        else:
            # 插入到光标
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
        # 自定义提问 → 用当前人设作为 system
        ctx = self.editor.toPlainText()
        if len(ctx) > 8000:
            ctx = ctx[:8000] + "…(已截断)"
        user_msg = f"{question}\n\n---\n(以下为当前文档内容供参考,可能很长)\n\n{ctx}"
        if self._quotes:
            quote_text = "\n\n".join(
                f"> {q[:300]}{'…' if len(q) > 300 else ''}"
                for q in self._quotes
            )
            user_msg = f"{user_msg}\n\n---\n用户引用的选区:\n{quote_text}"
        agent_system = build_agent_system(self._active_agent)
        messages = [
            {"role": "system", "content": agent_system},
            {"role": "user", "content": user_msg},
        ]
        self._current_preset = "问答"
        self._edit_action_mode = False
        self._start_stream(messages)

    def _run_quick_action(self, action: QuickAction):
        """执行快捷操作。"""
        if self._thread is not None and self._thread.isRunning():
            return
        if not self._llm_cfg.is_valid():
            QMessageBox.warning(
                self, "未配置 LLM",
                "请先在右上角「⚙」配置 API key / base_url / model。")
            return
        sel = self.editor.selected_text()
        if action.mode == "edit" and not sel:
            QMessageBox.information(
                self, "无选中文本",
                f"「{action.label}」需要先在编辑器里选中要操作的文本。")
            return

        self._current_preset = action.id
        # 构造 system prompt:人设 + 快捷操作 prompt
        agent_system = build_agent_system(self._active_agent)
        if action.mode == "edit":
            # edit 模式:对选区做改写,要求模型只输出结果
            user_msg = f"{action.prompt}\n\n---\n选中文本:\n{sel}"
        else:
            # chat 模式:解释/批评,基于选区或全文
            if sel:
                user_msg = f"{action.prompt}\n\n---\n选中内容:\n{sel}"
            else:
                ctx = self.editor.toPlainText()
                if len(ctx) > 12000:
                    ctx = ctx[:12000] + "…(已截断)"
                user_msg = f"{action.prompt}\n\n---\n当前文档:\n{ctx}"
        # 加引用选区(如果有)
        if self._quotes:
            quote_text = "\n\n".join(
                f"> {q[:300]}{'…' if len(q) > 300 else ''}"
                for q in self._quotes
            )
            user_msg = f"{user_msg}\n\n---\n用户引用的选区:\n{quote_text}"
        # BM25 工作区上下文(chat 模式 + 文档大时)
        if action.mode == "chat":
            try:
                from src.core.bm25 import search_workspace, format_hits_for_prompt
                from src.core.write_agent import default_workspace_root
                ws_root = default_workspace_root()
                query = sel[:200] if sel else self.editor.toPlainText()[:200]
                hits = search_workspace(ws_root, query, k=3, snippet_chars=520)
                ctx = format_hits_for_prompt(hits, max_total_chars=1500)
                if ctx:
                    user_msg = f"{user_msg}\n\n---\n[工作区相关片段,供参考]\n{ctx}"
            except Exception:  # noqa: BLE001
                pass

        messages = [
            {"role": "system", "content": agent_system},
            {"role": "user", "content": user_msg},
        ]
        # edit 模式 → 流式完后提供"应用替换"按钮
        self._edit_action_mode = (action.mode == "edit")
        self._edit_action_original = sel
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


# ============================================================
# Checkpoint 面板(Phase 3b)
# ============================================================

class CheckpointPanel(QFrame):
    """浮层,显示当前文档的所有 checkpoint 列表 + 操作。"""

    def __init__(self, editor: "EditorPanel", parent=None):
        super().__init__(parent)
        self._editor = editor
        self.setFixedSize(480, 460)
        self.setStyleSheet(f"""
            QFrame {{
                background: #ffffff;
                border: 1px solid {BORDER};
                border-radius: {RADIUS}px;
            }}
        """)
        # 阴影
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        from PySide6.QtGui import QColor
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.setGraphicsEffect(shadow)

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(8)

        # 标题
        title = QLabel("⏱ 文档历史快照")
        title.setStyleSheet(f"""
            QLabel {{
                color: {TEXT};
                font-family: {FONT_HEADING};
                font-size: 14px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
        """)
        v.addWidget(title)

        hint = QLabel("每 5 分钟或累积 200 字符自动保存。手动保存可加备注。")
        hint.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 10px;
                background: transparent;
                border: none;
            }}
        """)
        hint.setWordWrap(True)
        v.addWidget(hint)

        # 列表
        self.list = QListWidget()
        self.list.setStyleSheet(f"""
            QListWidget {{
                background: #fbfaf7;
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_SM}px;
                font-size: 11px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-bottom: 1px solid #f0ece2;
            }}
            QListWidget::item:selected {{
                background: {ACCENT_SUBTLE};
                color: {TEXT};
            }}
        """)
        self.list.itemDoubleClicked.connect(self._on_preview)
        v.addWidget(self.list, 1)

        # 操作按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.btn_preview = self._make_btn("👁 预览", self._on_preview)
        self.btn_restore = self._make_btn("↩ 还原", self._on_restore, primary=True)
        self.btn_delete = self._make_btn("🗑 删除", self._on_delete)
        btn_row.addWidget(self.btn_preview)
        btn_row.addWidget(self.btn_restore)
        btn_row.addWidget(self.btn_delete)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        # 手动保存区
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {BORDER}; background: {BORDER};")
        sep.setFixedHeight(1)
        v.addWidget(sep)

        manual_row = QHBoxLayout()
        manual_row.setSpacing(6)
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("备注(可选)…")
        self.note_input.setStyleSheet(f"""
            QLineEdit {{
                background: #fbfaf7;
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_XS}px;
                padding: 5px 8px;
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border: 1px solid {BORDER_FOCUS};
            }}
        """)
        self.note_input.returnPressed.connect(self._on_manual_save)
        manual_row.addWidget(self.note_input, 1)
        self.btn_manual = self._make_btn("📌 手动保存", self._on_manual_save, primary=True)
        manual_row.addWidget(self.btn_manual)
        v.addLayout(manual_row)

        # 关闭按钮(右上)
        self.btn_close = QToolButton(self)
        self.btn_close.setText("×")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                font-size: 18px;
                font-weight: 700;
            }}
            QToolButton:hover {{
                color: {DANGER if 'DANGER' in dir() else '#ef4444'};
            }}
        """)
        self.btn_close.move(self.width() - 32, 6)
        self.btn_close.clicked.connect(self._on_close)

    def _make_btn(self, text, slot, primary=False):
        from src.ui.theme import DANGER
        btn = QToolButton()
        btn.setText(text)
        btn.setCursor(Qt.PointingHandCursor)
        if primary:
            btn.setStyleSheet(f"""
                QToolButton {{
                    background: {ACCENT};
                    color: #ffffff;
                    border: 1px solid {ACCENT};
                    border-radius: {RADIUS_XS}px;
                    padding: 4px 10px;
                    font-size: 11px;
                }}
                QToolButton:hover {{
                    background: {ACCENT_HOVER};
                    border: 1px solid {ACCENT_HOVER};
                }}
            """)
        else:
            btn.setStyleSheet(_TOOLBTN_QSS)
        btn.clicked.connect(slot)
        return btn

    def _on_close(self):
        if self._editor and self._editor.btn_history.isChecked():
            self._editor.btn_history.setChecked(False)

    def set_editor(self, editor: "EditorPanel"):
        """Phase 4b 多 Tab:切换当前 tab 的 editor 引用。"""
        self._editor = editor
        # 关掉历史按钮(checkpoint 是绑在 editor 上的)
        if editor and editor.btn_history.isChecked():
            editor.btn_history.setChecked(False)
        # 刷新列表
        if self.isVisible():
            self.refresh()

    def refresh(self):
        """从 checkpoint 引擎读最新列表,刷新 UI。"""
        self.list.clear()
        fp = self._editor._file_path if self._editor else None
        if not fp:
            placeholder = QListWidgetItem("未打开文档")
            placeholder.setFlags(Qt.NoItemFlags)
            self.list.addItem(placeholder)
            return
        try:
            from src.core.checkpoint import list_checkpoints, default_checkpoint_root
            cps = list_checkpoints(fp, root=default_checkpoint_root())
        except Exception as e:  # noqa: BLE001
            err = QListWidgetItem(f"读取失败: {e}")
            err.setFlags(Qt.NoItemFlags)
            self.list.addItem(err)
            return
        if not cps:
            empty = QListWidgetItem("暂无快照 · 编辑几分钟后会自动出现")
            empty.setFlags(Qt.NoItemFlags)
            self.list.addItem(empty)
            return
        # 倒序显示(最新在最上面)
        for cp in reversed(cps):
            trigger_label = {
                "manual": "📌 手动",
                "auto-chars": "✍ 自动(字符)",
                "auto-time": "⏰ 自动(时间)",
                "auto-pre-restore": "↩ 还原前",
            }.get(cp.trigger, cp.trigger)
            note = f" · {cp.note}" if cp.note else ""
            label = (
                f"{cp.display_time()}  ·  {cp.char_count}字  "
                f"({cp.char_delta:+d})  ·  {trigger_label}{note}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, cp.ts)
            self.list.addItem(item)

    def _selected_ts(self) -> Optional[int]:
        item = self.list.currentItem()
        if not item:
            return None
        ts = item.data(Qt.UserRole)
        return int(ts) if ts is not None else None

    def _on_preview(self, *_):
        ts = self._selected_ts()
        if ts is None:
            return
        fp = self._editor._file_path
        try:
            from src.core.checkpoint import load_checkpoint_content, default_checkpoint_root
            content = load_checkpoint_content(fp, ts, root=default_checkpoint_root())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "预览失败", str(e))
            return
        if content is None:
            QMessageBox.warning(self, "预览失败", "快照内容丢失(可能被清理)")
            return
        # 简单弹窗预览(前 2000 字)
        preview = content[:2000] + ("\n\n… (已截断)" if len(content) > 2000 else "")
        QMessageBox.information(
            self, f"快照预览 · {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}",
            preview,
        )

    def _on_restore(self):
        ts = self._selected_ts()
        if ts is None:
            return
        fp = self._editor._file_path
        if not fp:
            return
        # 二次确认
        ret = QMessageBox.question(
            self, "还原快照",
            f"将把文档还原到 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))} 的状态。\n"
            "当前内容会自动保存为新快照(可找回)。\n\n确认还原?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        try:
            from src.core.checkpoint import restore_checkpoint, default_checkpoint_root
            ok = restore_checkpoint(fp, ts, root=default_checkpoint_root())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "还原失败", str(e))
            return
        if not ok:
            QMessageBox.warning(self, "还原失败", "找不到该快照")
            return
        # 重新加载到 editor
        try:
            text = Path(fp).read_text(encoding="utf-8")
            self._editor.editor.blockSignals(True)
            self._editor.editor.setPlainText(text)
            self._editor.editor.blockSignals(False)
            self._editor._update_word_count()
            self._editor._update_checkpoint_label()
            self.refresh()
            QMessageBox.information(self, "已还原", "文档已还原到所选快照。\n旧内容已自动备份。")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "刷新失败", str(e))

    def _on_delete(self):
        ts = self._selected_ts()
        if ts is None:
            return
        ret = QMessageBox.question(
            self, "删除快照",
            f"确认删除 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))} 的快照?\n"
            "(不会影响当前文档)",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        fp = self._editor._file_path
        try:
            from src.core.checkpoint import delete_checkpoint, default_checkpoint_root
            ok = delete_checkpoint(fp, ts, root=default_checkpoint_root())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "删除失败", str(e))
            return
        if ok:
            self._editor._update_checkpoint_label()
            self.refresh()
        else:
            QMessageBox.warning(self, "删除失败", "找不到该快照")

    def _on_manual_save(self):
        fp = self._editor._file_path
        if not fp:
            QMessageBox.information(self, "提示", "请先打开或新建一个文档")
            return
        note = self.note_input.text().strip()
        self.note_input.clear()
        # 复用 editor 的 _maybe_create_checkpoint
        self._editor._maybe_create_checkpoint(trigger="manual", note=note)
        self.refresh()

    def moveEvent(self, ev):
        super().moveEvent(ev)
        # 关闭按钮跟随移动
        if hasattr(self, "btn_close"):
            self.btn_close.move(self.width() - 32, 6)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if hasattr(self, "btn_close"):
            self.btn_close.move(self.width() - 32, 6)


class WriteView(QWidget):
    """墨写主页面(三栏:文件树 / 多 Tab 编辑器 / AI 助手)。"""

    # Tab 持久化的 QSettings key
    _TABS_KEY = "WriteTabs"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workspace = default_workspace()
        # __init__ 期间屏蔽 _save_tabs(避免初始 _add_new_tab 写空 list 覆盖上次持久化)
        self._suspend_save = True

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

        # 中:QTabWidget(Phase 4b 多 Tab)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: #fbfaf7;
            }}
            QTabBar::tab {{
                background: #f3eee4;
                color: {TEXT_SECONDARY};
                padding: 6px 14px;
                margin-right: 2px;
                border: 1px solid {BORDER};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 11px;
                min-width: 80px;
                max-width: 200px;
            }}
            QTabBar::tab:selected {{
                background: #fbfaf7;
                color: {TEXT};
                font-weight: 600;
            }}
            QTabBar::tab:hover {{
                background: #fefdfa;
            }}
            QTabBar::close-button {{
                image: none;
                subcontrol-position: right;
            }}
        """)
        # 信号
        self.tabs.tabCloseRequested.connect(self._on_close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        splitter.addWidget(self.tabs)

        # 右
        # 初始时建 1 个空白 tab
        self._add_new_tab()
        first_editor = self._current_editor()
        self.assistant = AssistantPanel(first_editor) if first_editor else None
        if self.assistant:
            splitter.addWidget(self.assistant)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([200, 800, 320])

        root.addWidget(splitter)

        # 信号
        self.file_tree.file_opened.connect(self._on_file_opened)
        # 恢复上次的 tab 列表
        self._restore_tabs()
        # 解除屏蔽(用户操作现在开始持久化)
        self._suspend_save = False

    # ============================================================
    # Tab 管理(Phase 4b)
    # ============================================================

    def _add_new_tab(self, path: Optional[str] = None) -> int:
        """新建一个 tab(可指定 path),返回 tab index。"""
        ed = EditorPanel()
        title = "未命名"
        if path:
            try:
                ed.open_file(path)
                title = Path(path).name
            except Exception:
                pass
        idx = self.tabs.addTab(ed, title)
        ed.file_label.setText(title)
        # Tab 提示
        if path:
            self.tabs.setTabToolTip(idx, path)
        # 默认切到新 tab(避免 addTab 不切的问题)
        self.tabs.setCurrentIndex(idx)
        return idx

    def _current_editor(self) -> Optional["EditorPanel"]:
        w = self.tabs.currentWidget()
        return w if isinstance(w, EditorPanel) else None

    def _find_tab_by_path(self, path: str) -> int:
        """查找已打开该 path 的 tab index,没找到返回 -1。"""
        target = str(Path(path).resolve()).lower()
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, EditorPanel) and w._file_path:
                if str(Path(w._file_path).resolve()).lower() == target:
                    return i
        return -1

    def _on_tab_changed(self, idx: int):
        """tab 切换:通知 assistant / checkpoint panel。"""
        ed = self._current_editor()
        if ed is None:
            return
        if hasattr(self, "assistant") and self.assistant:
            self.assistant.set_editor(ed)
        # CheckpointPanel(如果它存在并显示)也要切
        cp = getattr(ed, "_checkpoint_panel", None)
        if cp and cp.isVisible():
            cp.set_editor(ed)
        self._save_tabs()

    def _on_close_tab(self, idx: int):
        """关闭一个 tab(弹确认 → 移除 → 至少留 1 个空 tab)。"""
        ed = self.tabs.widget(idx)
        if not isinstance(ed, EditorPanel):
            return
        # 至少留 1 个 tab
        if self.tabs.count() <= 1:
            # 是最后一个,清空内容
            ed.editor.blockSignals(True)
            ed.editor.setPlainText("")
            ed.editor.blockSignals(False)
            ed._file_path = None
            ed.file_label.setText("未命名文档")
            self.tabs.setTabText(idx, "未命名")
            ed._update_word_count()
            return
        # 弹确认(虽然有 live save,但关闭 tab 也会让 autosave 失效,这里仅问是否关)
        path = ed._file_path
        if path:
            ret = QMessageBox.question(
                self, "关闭标签",
                f"关闭当前标签?\n{Path(path).name}\n\n"
                "(Live 模式已自动保存,内容不会丢失)",
                QMessageBox.Yes | QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return
        # 移除
        self.tabs.removeTab(idx)
        ed.deleteLater()
        # 通知 assistant 切到新 tab
        new_ed = self._current_editor()
        if new_ed and self.assistant:
            self.assistant.set_editor(new_ed)
        self._save_tabs()

    def _on_file_opened(self, path: str):
        """文件树双击:如果已开,切到该 tab;否则新建。"""
        idx = self._find_tab_by_path(path)
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)
        else:
            self._add_new_tab(path)
            self.tabs.setCurrentIndex(self.tabs.count() - 1)
        ed = self._current_editor()
        if ed:
            if self.assistant:
                self.assistant.set_doc_path(path)
            ed.setFocus()
        self._save_tabs()

    # ============================================================
    # 持久化
    # ============================================================

    def _save_tabs(self):
        """把当前打开的文件列表存到 QSettings。"""
        if getattr(self, "_suspend_save", False):
            return
        paths = []
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, EditorPanel) and w._file_path:
                paths.append(w._file_path)
        s = QSettings("WinEBook", self._TABS_KEY)
        s.setValue("paths", paths)
        s.setValue("current", self.tabs.currentIndex())
        s.sync()

    def _restore_tabs(self):
        """从 QSettings 恢复上次的 tab 列表(找不到的文件静默跳过)。"""
        s = QSettings("WinEBook", self._TABS_KEY)
        paths = s.value("paths", [], type=list) or []
        current = int(s.value("current", 0))
        # 至少留 1 个 tab
        if not paths:
            return
        # 依次打开
        opened = 0
        for p in paths:
            if not p or not Path(p).exists():
                continue
            self._add_new_tab(str(p))
            opened += 1
        # 切到上次 current(钳到有效范围)
        if opened > 0 and 0 <= current < self.tabs.count():
            self.tabs.setCurrentIndex(current)
        self._save_tabs()

    # ============================================================
    # 兼容旧 API
    # ============================================================

    @property
    def editor(self) -> Optional["EditorPanel"]:
        """向后兼容:返回当前 tab 的 editor。"""
        return self._current_editor()

    def shutdown(self):
        # 关闭所有 editor 关联的后台线程
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, EditorPanel):
                try:
                    # 调一次 _auto_save 确保落盘
                    w._auto_save()
                except Exception:
                    pass
        if self.assistant:
            self.assistant.shutdown()
