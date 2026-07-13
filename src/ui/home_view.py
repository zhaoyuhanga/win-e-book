"""首页"墨软":墨读 + 墨写 两张大卡片入口。

参考设计图:
- 顶栏下方大留白
- 中部两张大卡片水平排列
- 卡片:渐变背景 + 大图标 + 模块名 + 描述 + 数据 + 进入按钮
- 风格:墨读深色主题(深蓝黑底 + 暖橙 #c8946e 高亮)
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QSizePolicy, QSpacerItem,
)

from src.ui.theme import (
    BG, SURFACE, SURFACE_RAISED, BORDER, BORDER_FOCUS, ACCENT, ACCENT_HOVER,
    TEXT, TEXT_SECONDARY, TEXT_MUTED, FONT_HEADING, RADIUS, RADIUS_SM,
)


# ============================================================
# 大卡片
# ============================================================

class ModuleCard(QFrame):
    """一个模块入口卡(墨读 / 墨写)。

    视觉:180x320 大卡片,圆角,深色,hover 时浮起 + 边框变暖橙。
    """

    clicked = Signal()  # 点击卡片本身(整个区域可点)

    def __init__(self, title: str, glyph: str, accent: str, accent2: str,
                 description: str, stats_text: str, cta: str = "进入",
                 parent=None):
        super().__init__(parent)
        self.setObjectName("ModuleCard")
        self.setProperty("role", "module-card")
        self.setFixedSize(280, 360)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame#ModuleCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {SURFACE}, stop:1 {SURFACE_RAISED});
                border: 1px solid {BORDER};
                border-radius: 14px;
            }}
            QFrame#ModuleCard:hover {{
                border: 1px solid {ACCENT};
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {SURFACE_RAISED}, stop:1 #243149);
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 28, 26, 22)
        layout.setSpacing(0)

        # 大图标(渐变方块 + 单字/双字)
        self.icon = QLabel(glyph)
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setFixedSize(64, 64)
        self.icon.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {accent}, stop:1 {accent2});
                color: #fff;
                border-radius: 12px;
                font-family: {FONT_HEADING};
                font-size: 30px;
                font-weight: 700;
            }}
        """)
        layout.addWidget(self.icon, 0, Qt.AlignLeft)

        # 间距
        layout.addSpacing(20)

        # 模块名
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT};
                font-family: {FONT_HEADING};
                font-size: 26px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
        """)
        layout.addWidget(self.title_label)

        # 描述
        self.desc = QLabel(description)
        self.desc.setWordWrap(True)
        self.desc.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_SECONDARY};
                font-size: 12px;
                line-height: 1.55;
                background: transparent;
                border: none;
                padding-top: 6px;
            }}
        """)
        layout.addSpacing(6)
        layout.addWidget(self.desc)

        # 自适应
        layout.addStretch(1)

        # 数据
        self.stats = QLabel(stats_text)
        self.stats.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 10px;
                background: transparent;
                border: none;
                padding-bottom: 10px;
            }}
        """)
        layout.addWidget(self.stats)

        # 按钮
        self.cta_btn = QPushButton(cta + "  →")
        self.cta_btn.setCursor(Qt.PointingHandCursor)
        self.cta_btn.setFixedHeight(36)
        self.cta_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {ACCENT};
                border: 1px solid {ACCENT};
                border-radius: {RADIUS_SM}px;
                font-size: 12px;
                font-weight: 600;
                padding: 0 16px;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {ACCENT};
                color: #0f1724;
            }}
        """)
        self.cta_btn.clicked.connect(self.clicked)
        layout.addWidget(self.cta_btn)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)

    def set_stats(self, text: str):
        self.stats.setText(text)


# ============================================================
# 首页
# ============================================================

class HomeView(QWidget):
    """墨软首页。"""

    enter_read = Signal()  # 进入墨读
    enter_write = Signal()  # 进入墨写

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 24)
        root.setSpacing(0)

        # ---------- 顶部欢迎区 ----------
        head = QVBoxLayout()
        head.setSpacing(4)

        brand = QLabel("墨软")
        brand.setStyleSheet(f"""
            QLabel {{
                color: {TEXT};
                font-family: {FONT_HEADING};
                font-size: 32px;
                font-weight: 700;
                background: transparent;
            }}
        """)
        head.addWidget(brand)

        sub = QLabel("经典阅读  ·  智能写作")
        sub.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 12px;
                background: transparent;
                letter-spacing: 2px;
            }}
        """)
        head.addWidget(sub)

        root.addLayout(head)
        root.addSpacing(36)

        # ---------- 两张卡片 ----------
        cards_row = QHBoxLayout()
        cards_row.setSpacing(24)

        self.card_read = ModuleCard(
            title="墨读",
            glyph="读",
            accent=ACCENT,
            accent2="#a07352",
            description=(
                "本地书架 + 在线书库。\n"
                "支持 txt / epub,自动解析章节,记忆阅读位置,5 种阅读背景主题。"
            ),
            stats_text="本地书库 · 章节自动解析 · 离线优先",
            cta="进入墨读",
        )
        self.card_read.clicked.connect(self.enter_read)
        cards_row.addWidget(self.card_read)

        self.card_write = ModuleCard(
            title="墨写",
            glyph="写",
            accent="#7c9bc4",     # 偏蓝灰(跟墨读的暖橙形成对比)
            accent2="#5a78a0",
            description=(
                "配置大模型 API 续写小说、提炼大纲、润色文本。\n"
                "支持 OpenAI 兼容协议:DeepSeek / 通义千问 / 智谱 / Ollama。"
            ),
            stats_text="LLM 写作助手 · 流式响应 · 引用上下文",
            cta="进入墨写",
        )
        self.card_write.clicked.connect(self.enter_write)
        cards_row.addWidget(self.card_write)

        # 居中容器
        cards_wrapper = QHBoxLayout()
        cards_wrapper.addStretch(1)
        cards_wrapper.addLayout(cards_row)
        cards_wrapper.addStretch(1)
        root.addLayout(cards_wrapper)

        root.addStretch(1)

        # ---------- 底部 tip ----------
        tip = QLabel("提示:首次进入墨写时,请在「设置」中配置你的大模型 API")
        tip.setAlignment(Qt.AlignCenter)
        tip.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 12px;
                background: transparent;
            }}
        """)
        root.addWidget(tip)
