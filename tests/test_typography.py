"""排版字体预设(Phase 3a)单元测试。

测试范围:
- TYPOGRAPHY_PRESETS 数据完整性(4 套、字段齐全)
- _font_size_range 浮动范围
- _default_preset_name 兜底
- _apply_preset / _change_font 在 mock QSettings 下表现(需要 QApplication)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 把项目根加进 sys.path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# 测试不依赖 Qt GUI,只测纯数据部分
from src.ui.write_view import (
    TYPOGRAPHY_PRESETS,
    _default_preset_name,
    _font_size_range,
)


def test_presets_count():
    assert len(TYPOGRAPHY_PRESETS) == 4, f"期望 4 套预设,实际 {len(TYPOGRAPHY_PRESETS)}"


def test_presets_keys():
    assert set(TYPOGRAPHY_PRESETS.keys()) == {"护眼", "紧凑", "学术", "手稿"}


def test_presets_fields_complete():
    """每套预设都有:字体族/基准字号/行距/段距/上下边距/左右边距/背景/前景色。"""
    required = {"font_family", "base_size", "line_height", "para_margin",
                "padding_v", "padding_h", "background", "color"}
    for name, p in TYPOGRAPHY_PRESETS.items():
        missing = required - set(p.keys())
        assert not missing, f"[{name}] 缺字段: {missing}"


def test_presets_values_sane():
    """所有数值字段都在合理范围。"""
    for name, p in TYPOGRAPHY_PRESETS.items():
        assert 10 <= p["base_size"] <= 22, f"[{name}] base_size 异常: {p['base_size']}"
        assert 1.2 <= p["line_height"] <= 2.5, f"[{name}] line_height 异常: {p['line_height']}"
        assert 0 <= p["para_margin"] <= 32, f"[{name}] para_margin 异常: {p['para_margin']}"
        assert 4 <= p["padding_v"] <= 64, f"[{name}] padding_v 异常: {p['padding_v']}"
        assert 8 <= p["padding_h"] <= 96, f"[{name}] padding_h 异常: {p['padding_h']}"
        assert p["font_family"], f"[{name}] font_family 为空"
        assert p["background"].startswith("#"), f"[{name}] background 不是 hex: {p['background']}"
        assert p["color"].startswith("#"), f"[{name}] color 不是 hex: {p['color']}"


def test_presets_unique_backgrounds():
    """每套预设的背景色应该不同(避免切换无视觉反馈)。"""
    bgs = [p["background"] for p in TYPOGRAPHY_PRESETS.values()]
    assert len(set(bgs)) >= 3, f"预设背景色太相似: {bgs}"


def test_default_preset_name_returns_known():
    n = _default_preset_name()
    assert n in TYPOGRAPHY_PRESETS
    assert n == "护眼"


def test_font_size_range_includes_base():
    """每套预设的浮动范围要包含自己的 base_size。"""
    for name, p in TYPOGRAPHY_PRESETS.items():
        lo, hi = _font_size_range(name)
        assert lo <= p["base_size"] <= hi, (
            f"[{name}] base={p['base_size']} 不在范围 [{lo}, {hi}]"
        )


def test_font_size_range_lower_bound_safe():
    """下限不低于 9,保证可读性。"""
    for name in TYPOGRAPHY_PRESETS:
        lo, _ = _font_size_range(name)
        assert lo >= 9, f"[{name}] 下限 {lo} < 9"


def test_font_size_range_upper_bound_room():
    """上限至少 >= base+2,保证可放大。"""
    for name, p in TYPOGRAPHY_PRESETS.items():
        _, hi = _font_size_range(name)
        assert hi >= p["base_size"] + 2, f"[{name}] 上限 {hi} 放不大"


def test_presets_serializable():
    """预设字典可 round-trip 走 JSON(为未来用户自定义预设铺路)。"""
    import json
    blob = json.dumps(TYPOGRAPHY_PRESETS, ensure_ascii=False, sort_keys=True)
    restored = json.loads(blob)
    assert restored == TYPOGRAPHY_PRESETS


# ============================================================
# 以下测试需要 QApplication,只在我们能起 GUI 时跑
# ============================================================

def test_apply_preset_with_qt():
    """在真实 QApplication 里调 _apply_preset,验证 stylesheet / defaultStyleSheet 注入。"""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QSettings

    # 清理之前的设置
    QSettings("WinEBook", "EditorTypography").clear()

    app = QApplication.instance() or QApplication(sys.argv)

    # 直接 import write_view(需要 QApplication 已被初始化)
    from src.ui.write_view import WriteView
    from src.ui.write_view import EditorPanel  # 私有但可访问,内部用

    # 构造一个最小化的 EditorPanel
    panel = EditorPanel()
    for name in TYPOGRAPHY_PRESETS:
        panel._apply_preset(name, _save=True)
        # 验证 stylesheet 包含 preset 的背景色
        ss = panel.editor.styleSheet()
        assert TYPOGRAPHY_PRESETS[name]["background"] in ss, \
            f"[{name}] stylesheet 未注入背景色"
        # 验证 default stylesheet 包含 line-height
        dss = panel.editor.document().defaultStyleSheet()
        assert f"line-height: {TYPOGRAPHY_PRESETS[name]['line_height']}" in dss, \
            f"[{name}] defaultStyleSheet 未注入行距"
        # 验证菜单项 checked
        assert panel._preset_actions[name].isChecked()
        # 验证 QSettings 持久化
        cs = QSettings("WinEBook", "EditorTypography")
        assert cs.value("preset", "", type=str) == name


def test_change_font_offset_in_range():
    """_change_font 在 preset 浮动范围内 ±1 不会越界。"""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QSettings
    QSettings("WinEBook", "EditorTypography").clear()
    app = QApplication.instance() or QApplication(sys.argv)

    from src.ui.write_view import EditorPanel
    panel = EditorPanel()
    panel._apply_preset("护眼", _save=True)
    base = TYPOGRAPHY_PRESETS["护眼"]["base_size"]
    # 连续按 +20 次
    for _ in range(20):
        panel._change_font(+1)
    # 应该到上限
    _, hi = _font_size_range("护眼")
    assert panel._size_offset + base == hi, \
        f"上调未到上限: offset={panel._size_offset}, base={base}, hi={hi}"
    # 连续按 -20 次
    for _ in range(30):
        panel._change_font(-1)
    lo, _ = _font_size_range("护眼")
    assert panel._size_offset + base == lo, \
        f"下调未到下限: offset={panel._size_offset}, base={base}, lo={lo}"
