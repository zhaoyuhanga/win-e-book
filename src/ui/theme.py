"""墨读风格主题(暗色 + 暖橙主色 + 衬线标题)。

参考 v2.html 设计:深蓝黑底 + #c8946e 暖橙强调色 + Georgia/Noto Serif SC 衬线标题。
"""
from __future__ import annotations


# ============================================================
# 配色 / 字体 / 尺寸(对应 v2.html 的 :root CSS 变量)
# ============================================================
BG              = "#0f1724"   # 主背景
SURFACE         = "#1a2336"   # 面板/顶栏/侧栏
SURFACE_RAISED  = "#1f2a3d"   # hover / 高亮层
BORDER          = "#2a354a"   # 边框
BORDER_FOCUS    = "#c8946e"   # 焦点边框 = 主色
ACCENT          = "#c8946e"   # 主色(暖橙)
ACCENT_HOVER    = "#d4a87c"   # 主色 hover
ACCENT_SUBTLE   = "rgba(200, 148, 110, 0.12)"  # 主色 12% 背景
TEXT            = "#e6ded2"   # 主文字(暖白)
TEXT_SECONDARY  = "#9aa0ac"
TEXT_MUTED      = "#6b7384"
SUCCESS         = "#4ade80"
DANGER          = "#f87171"
TAG_BG          = "#1e293b"

RADIUS          = 10
RADIUS_SM       = 7
RADIUS_XS       = 5

# 衬线体用于标题/书名(书卷气),无衬线用于 UI/正文
FONT_HEADING    = "'Georgia','Times New Roman','Noto Serif SC',serif"
FONT_BODY       = "'Microsoft YaHei UI','Segoe UI',-apple-system,sans-serif"

# 阅读区用 sepia(暖米色),降低对比,护眼
READ_BG         = "#f5ede0"
READ_TEXT       = "#2a2520"
READ_TITLE      = "#3a2f1c"
READ_SUBTITLE   = "#8a7b65"


# ============================================================
# 全局 QSS
# ============================================================
THEME_QSS = f"""
/* ---------- 全局 ---------- */
* {{
    font-family: {FONT_BODY};
}}
QMainWindow, QWidget {{
    background: {BG};
    color: {TEXT};
}}

/* 主窗口去掉 Windows 默认边框后边框更干净 */
QMainWindow {{
    border: none;
}}

/* ---------- 顶栏 ---------- */
QWidget[role="topbar"] {{
    background: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}

/* ---------- 菜单/状态栏 ---------- */
QMenuBar {{
    background: transparent;
    padding: 4px 8px;
}}
QMenuBar::item {{
    padding: 6px 12px;
    border-radius: 4px;
    color: {TEXT_SECONDARY};
}}
QMenuBar::item:selected {{
    background: {SURFACE_RAISED};
    color: {TEXT};
}}

/* ===== 右键/下拉菜单 ===== */
QMenu {{
    background: {SURFACE_RAISED};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    padding: 6px 0;
    /* Windows 下需要指定 */
    menu-scrollable: 1;
}}
QMenu::item {{
    background: transparent;
    padding: 8px 28px 8px 20px;
    color: {TEXT_SECONDARY};
    margin: 2px 6px;
    border-radius: 4px;
    min-width: 120px;
}}
QMenu::item:selected {{
    background: {ACCENT_SUBTLE};
    color: {ACCENT};
    /* 左侧指示条 */
    border-left: 3px solid {ACCENT};
    padding-left: 17px;
}}
QMenu::item:disabled {{
    color: {TEXT_MUTED};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 6px 12px;
}}
QMenu::right-arrow {{
    image: none;
    width: 0; height: 0;
    border-left: 5px solid {TEXT_SECONDARY};
    border-top: 4px solid transparent;
    border-bottom: 4px solid transparent;
    margin-right: 4px;
}}

QStatusBar {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
    color: {TEXT_SECONDARY};
    font-size: 11px;
}}

/* ---------- 品牌顶部 ---------- */
QWidget[role="brand-logo"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {ACCENT}, stop:1 #a07352);
    border-radius: {RADIUS_XS}px;
}}
QLabel[role="brand-name"] {{
    font-family: {FONT_HEADING};
    font-size: 17px;
    font-weight: 700;
    color: {TEXT};
    letter-spacing: 1px;
}}

/* ---------- 按钮 ---------- */
QPushButton {{
    background: {SURFACE_RAISED};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_XS}px;
    padding: 7px 14px;
    font-size: 12px;
    min-height: 18px;
    font-weight: 500;
}}
QPushButton:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
    background: rgba(200, 148, 110, 0.08);
}}
QPushButton:pressed {{
    background: {ACCENT_SUBTLE};
    color: {ACCENT};
    padding-top: 8px;        /* 微下压感 */
    padding-bottom: 6px;
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    background: {SURFACE};
    border-color: {BORDER};
}}

/* 主色按钮(继续阅读 / 关键操作) */
QPushButton[primary="true"] {{
    background: {ACCENT};
    color: #fff;
    border: 1px solid {ACCENT};
    font-weight: 600;
    padding: 12px 28px;
    font-size: 14px;
    border-radius: {RADIUS_SM}px;
}}
QPushButton[primary="true"]:hover {{
    background: {ACCENT_HOVER};
}}

/* 紧凑按钮(标题栏用) */
QPushButton[compact="true"] {{
    padding: 5px 12px;
    font-size: 12px;
    min-height: 14px;
}}

/* ---------- 输入 ---------- */
QLineEdit, QComboBox, QSpinBox {{
    background: {BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_XS}px;
    padding: 6px 12px;
    min-height: 20px;
    selection-background-color: {ACCENT_SUBTLE};
    selection-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit::placeholder {{
    color: {TEXT_MUTED};
}}

/* ---------- 下拉(QComboBox) ---------- */
QComboBox {{
    background: {BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_XS}px;
    padding: 5px 12px;
    padding-right: 28px;          /* 给箭头留位 */
    min-height: 20px;
    selection-background-color: {ACCENT_SUBTLE};
    selection-color: {ACCENT};
}}
QComboBox:hover {{
    border-color: #4a566f;
}}
QComboBox:focus {{
    border-color: {ACCENT};
}}
/* 下拉箭头区域 */
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border: none;
    border-left: 1px solid {BORDER};
    background: transparent;
}}
/* 自定义下拉箭头(SVG 风格用 unicode 字符) */
QComboBox::down-arrow {{
    image: none;
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {TEXT_SECONDARY};
    margin-top: 2px;
}}
QComboBox::down-arrow:hover {{
    border-top-color: {ACCENT};
}}

/* ===== 下拉弹出列表(关键:用 surface 色 + accent 选中) ===== */
QComboBox QAbstractItemView {{
    background: {SURFACE_RAISED};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_XS}px;
    padding: 6px 0;
    outline: 0;
    selection-background-color: transparent;       /* 自定义指示器 */
}}
QComboBox QAbstractItemView::item {{
    padding: 8px 16px;
    border: none;
    min-height: 22px;
    color: {TEXT_SECONDARY};
    background: transparent;
}}
QComboBox QAbstractItemView::item:hover {{
    background: rgba(255, 255, 255, 0.04);
    color: {TEXT};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {ACCENT_SUBTLE};
    color: {ACCENT};
    font-weight: 600;
    /* 左侧出现指示器 */
    border-left: 3px solid {ACCENT};
    padding-left: 13px;
}}
QComboBox QAbstractItemView {{
    /* 弹出列表的滚动条 */
}}
QComboBox QAbstractItemView QScrollBar:vertical {{
    background: transparent;
    width: 8px;
}}
QComboBox QAbstractItemView QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
}}
QComboBox QAbstractItemView QScrollBar::handle:vertical:hover {{
    background: {ACCENT};
}}

/* ---------- 列表(用于网格卡片) ---------- */
QListWidget {{
    background: transparent;
    border: none;
    outline: 0;
}}
QListWidget::item {{
    background: transparent;
    padding: 0;
    margin: 0;
    border: none;
}}
QListWidget::item:selected {{
    background: transparent;
    border: none;
}}

/* ---------- 书籍卡片(自定义 widget) ---------- */
QFrame[role="book-card"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}
QFrame[role="book-card"]:hover {{
    border-color: {ACCENT};
    background: {SURFACE_RAISED};
    /* 阴影(Windows 上有限支持) */
    /* box-shadow 在 QSS 不支持,但 Qt 5+ QGraphicsDropShadowEffect 也可用 */
}}
QFrame[role="book-card"][selected="true"] {{
    border-color: {ACCENT};
    border-width: 2px;
    background: rgba(200, 148, 110, 0.06);
}}
QFrame[role="book-cover"] {{
    background: {SURFACE_RAISED};
    border-top-left-radius: {RADIUS}px;
    border-top-right-radius: {RADIUS}px;
}}
QLabel[role="book-cover-title"] {{
    font-family: {FONT_HEADING};
    font-size: 18px;
    font-weight: 700;
    color: {TEXT_SECONDARY};
    background: transparent;
    text-align: center;
}}
QProgressBar[role="book-progress"]::chunk {{
    background: {ACCENT};
}}
QProgressBar[role="book-progress"] {{
    background: {BORDER};
    border: none;
    height: 4px;
}}
QLabel[role="book-title"] {{
    font-size: 14px;
    font-weight: 600;
    color: {TEXT};
    background: transparent;
}}
QLabel[role="book-author"] {{
    font-size: 12px;
    color: {TEXT_MUTED};
    background: transparent;
}}
QLabel[role="book-tag"] {{
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 99px;
    background: {TAG_BG};
    color: {TEXT_MUTED};
}}
QLabel[role="book-tag-reading"] {{
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 99px;
    background: rgba(200, 148, 110, 0.15);
    color: {ACCENT};
}}
QLabel[role="book-tag-done"] {{
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 99px;
    background: rgba(74, 222, 128, 0.12);
    color: {SUCCESS};
}}
QLabel[role="book-meta"] {{
    font-size: 11px;
    color: {TEXT_MUTED};
    background: transparent;
}}

/* ---------- 工具按钮(字号 A-/A+ 等) ---------- */
QToolButton {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_XS}px;
    padding: 4px 10px;
    font-weight: 600;
}}
QToolButton:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
}}

/* ---------- 标签页 ---------- */
QTabWidget::pane {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    top: -1px;
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    padding: 8px 16px;
    color: {TEXT_SECONDARY};
    border-top-left-radius: {RADIUS_XS}px;
    border-top-right-radius: {RADIUS_XS}px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {SURFACE};
    color: {ACCENT};
    border: 1px solid {BORDER};
    border-bottom: 1px solid {SURFACE};
    font-weight: 600;
}}
QTabBar::tab:!selected:hover {{
    color: {TEXT};
    background: {SURFACE_RAISED};
}}

/* ---------- 分割条 ---------- */
QSplitter::handle {{
    background: {BORDER};
}}
QSplitter::handle:horizontal {{
    width: 1px;
}}
QSplitter::handle:vertical {{
    height: 1px;
}}
QSplitter::handle:hover {{
    background: {ACCENT};
}}

/* ---------- 进度条 ---------- */
QProgressBar {{
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 4px;
    text-align: center;
    color: {TEXT_SECONDARY};
    font-size: 10px;
    min-height: 16px;
}}
QProgressBar::chunk {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT}, stop:1 {ACCENT_HOVER});
    border-radius: 3px;
    margin: 1px;
}}
/* 小高度进度条(细线) */
QProgressBar[height="thin"] {{
    border: none;
    min-height: 4px;
    max-height: 4px;
    border-radius: 2px;
}}
QProgressBar[height="thin"]::chunk {{
    border-radius: 2px;
    margin: 0;
}}

/* ---------- 复选框 ---------- */
QCheckBox {{
    spacing: 8px;
    color: {TEXT_SECONDARY};
    font-size: 12px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background: {BG};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QCheckBox:hover {{
    color: {TEXT};
}}

/* ---------- 阅读区 ---------- */
QTextBrowser {{
    background: {READ_BG};
    color: {READ_TEXT};
    border: 1px solid #d8d3c0;
    border-radius: {RADIUS_SM}px;
    padding: 32px 56px;
    selection-background-color: {ACCENT_SUBTLE};
    selection-color: {READ_TITLE};
    font-family: {FONT_BODY};
}}
QTextBrowser QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}
QTextBrowser QScrollBar::handle:vertical {{
    background: #c8c0a8;
    border-radius: 5px;
    min-height: 30px;
}}
QTextBrowser QScrollBar::handle:vertical:hover {{
    background: {ACCENT};
}}
QTextBrowser QScrollBar::add-line:vertical,
QTextBrowser QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* 通用滚动条(暗色) */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT};
}}

/* ---------- Tooltip ---------- */
QToolTip {{
    background: #0a1422;
    color: {TEXT};
    border: 1px solid {ACCENT};
    border-radius: {RADIUS_XS}px;
    padding: 6px 10px;
    font-size: 11px;
}}

/* ---------- 对话框 ---------- */
QMessageBox {{
    background: {SURFACE};
}}
QMessageBox QLabel {{
    color: {TEXT};
}}
QMessageBox QPushButton {{
    min-width: 60px;
}}

/* ---------- 通用 label ---------- */
QLabel {{
    background: transparent;
    color: {TEXT};
}}
QLabel[role="title"] {{
    font-family: {FONT_HEADING};
    font-size: 18px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel[role="page-title"] {{
    font-family: {FONT_HEADING};
    font-size: 22px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel[role="page-sub"] {{
    font-size: 12px;
    color: {TEXT_SECONDARY};
}}
QLabel[role="subtitle"] {{
    font-size: 11px;
    color: {TEXT_MUTED};
}}
"""


# ============================================================
# 阅读区内的"下一章"卡片(用 sepia 主题配色 + 暖橙按钮)
# ============================================================
NEXT_CHAPTER_BUTTON_HTML = f"""
<div style="margin: 40px 0 16px 0; padding: 28px; text-align: center;
            background: linear-gradient(135deg, #fff7eb 0%, #f0dfc4 100%);
            border-radius: {RADIUS_SM}px; border: 1px solid #d4b88a;">
  <div style="font-family: {FONT_HEADING}; font-size: 11px;
              color: #a07752; margin-bottom: 6px;
              letter-spacing: 3px;">本章节结束</div>
  <div style="font-family: {FONT_HEADING}; font-size: 16px;
              font-weight: 700; color: #5c3a1a; margin-bottom: 18px;">
    下一章:{{next_title}}
  </div>
  <a href="next-chapter" style="display: inline-block; padding: 12px 36px;
            background: #c8946e; color: #fff;
            border-radius: {RADIUS_XS}px; font-weight: 600; font-size: 14px;
            text-decoration: none;
            box-shadow: 0 2px 8px rgba(200, 148, 110, 0.4);">
    ↓ 继续阅读 ↓
  </a>
  <div style="margin-top: 12px; font-size: 11px; color: #a89770;">
    按 ← / → 键也可切章
  </div>
</div>
"""

LAST_CHAPTER_HTML = f"""
<div style="margin: 40px 0 16px 0; padding: 40px; text-align: center;
            background: #ebe2cc;
            border-radius: {RADIUS_SM}px;
            border: 1px solid #d4b88a;">
  <div style="font-size: 28px; margin-bottom: 12px;">📜</div>
  <div style="font-family: {FONT_HEADING}; font-size: 20px;
              font-weight: 700; color: #5c3a1a;
              margin-bottom: 8px;">恭喜!全书读完了</div>
  <div style="font-size: 13px; color: #8a7048;">
    已到达最后一章 — 你真是太自律了
  </div>
</div>
"""


# ============================================================
# 书籍封面渐变色板(给每本书随机/按 hash 选一种)
# ============================================================
COVER_GRADIENTS = [
    "linear-gradient(150deg, #1a2740, #0d1b2a)",
    "linear-gradient(150deg, #2a1f1a, #1a1410)",
    "linear-gradient(150deg, #1f2833, #141a22)",
    "linear-gradient(150deg, #2a2520, #1a1612)",
    "linear-gradient(150deg, #2d1f1a, #1c1210)",
    "linear-gradient(150deg, #1a2a22, #101a16)",
    "linear-gradient(150deg, #2a1e14, #1a120c)",
    "linear-gradient(150deg, #1d2428, #14181c)",
    "linear-gradient(150deg, #2a1a26, #1a1018)",
    "linear-gradient(150deg, #1e1a2a, #12101a)",
]


def pick_cover_gradient(seed: str) -> str:
    """按书名稳定选一个渐变色(hash)。"""
    h = sum(ord(c) for c in (seed or "")) % len(COVER_GRADIENTS)
    return COVER_GRADIENTS[h]



# ============================================================
# 阅读区主题(5 种背景预设,可由用户切换)
# ============================================================
READING_THEMES = {
    "sepia": {
        "name": "📜 米白(护眼)",
        "bg":      "#f5ede0",
        "text":    "#2a2520",
        "title":   "#3a2f1c",
        "subtle":  "linear-gradient(135deg, #fff7eb 0%, #f0dfc4 100%)",
        "scroll":  "#c8c0a8",
        "border":  "#d8d3c0",
        "next_btn_bg": "#c8946e",
        "next_btn_text": "#fff",
        "next_card_border": "#d4b88a",
        "next_card_text":  "#5c3a1a",
        "next_card_caption": "#a07752",
    },
    "paper": {
        "name": "📄 纯白",
        "bg":      "#ffffff",
        "text":    "#1f1f1f",
        "title":   "#000000",
        "subtle":  "linear-gradient(135deg, #f9fafb 0%, #e5e7eb 100%)",
        "scroll":  "#c0c0c0",
        "border":  "#e5e7eb",
        "next_btn_bg": "#2563eb",
        "next_btn_text": "#fff",
        "next_card_border": "#d1d5db",
        "next_card_text":  "#111827",
        "next_card_caption": "#6b7280",
    },
    "mint": {
        "name": "🌿 薄荷(防疲劳)",
        "bg":      "#e8f5ec",
        "text":    "#1f3a2a",
        "title":   "#0d2818",
        "subtle":  "linear-gradient(135deg, #f0fdf4 0%, #d1fae5 100%)",
        "scroll":  "#9eb8a8",
        "border":  "#b6dcc4",
        "next_btn_bg": "#16a34a",
        "next_btn_text": "#fff",
        "next_card_border": "#86c79a",
        "next_card_text":  "#14532d",
        "next_card_caption": "#3f6b56",
    },
    "gray": {
        "name": "📰 灰白(中性)",
        "bg":      "#ececec",
        "text":    "#1a1a1a",
        "title":   "#000000",
        "subtle":  "linear-gradient(135deg, #f9fafb 0%, #d1d5db 100%)",
        "scroll":  "#a0a0a0",
        "border":  "#c0c0c0",
        "next_btn_bg": "#374151",
        "next_btn_text": "#fff",
        "next_card_border": "#9ca3af",
        "next_card_text":  "#1f2937",
        "next_card_caption": "#4b5563",
    },
    "dark": {
        "name": "🌙 夜间(黑底)",
        "bg":      "#1a1a1a",
        "text":    "#d4d0c8",
        "title":   "#f0e8d4",
        "subtle":  "linear-gradient(135deg, #2a2a2a 0%, #1a1a1a 100%)",
        "scroll":  "#555555",
        "border":  "#3a3a3a",
        "next_btn_bg": "#c8946e",
        "next_btn_text": "#fff",
        "next_card_border": "#555555",
        "next_card_text":  "#e0d5b8",
        "next_card_caption": "#9a8b6e",
    },
}

DEFAULT_READING_THEME = "sepia"
