"""DiffDialog 集成测试(Phase 4a)。

需要在 QApplication 里跑,验证:
- 构造(空/相同/有差异)
- was_accepted() 默认 False
- 接受/拒绝流程
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from src.ui.diff_dialog import DiffDialog


class DiffDialogBasicTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_construct_identical(self):
        dlg = DiffDialog("hello", "hello")
        self.assertFalse(dlg.was_accepted())

    def test_construct_with_diff(self):
        dlg = DiffDialog("hello", "world")
        self.assertFalse(dlg.was_accepted())
        # 验证 HTML 已注入
        html = dlg.browser.toHtml()
        self.assertIn("hello", html)
        self.assertIn("world", html)
        # 验证 summary 标签
        self.assertIn("新增", html)
        self.assertIn("删除", html)

    def test_construct_chinese(self):
        dlg = DiffDialog("第一段内容。\n第二段内容。", "第一段修改了。\n第二段内容。")
        html = dlg.browser.toHtml()
        self.assertIn("第一段", html)
        self.assertIn("第二段", html)

    def test_construct_empty(self):
        dlg = DiffDialog("", "")
        # 不应崩
        self.assertFalse(dlg.was_accepted())

    def test_title_in_html(self):
        dlg = DiffDialog("a", "b", title="我的 Diff")
        html = dlg.browser.toHtml()
        self.assertIn("我的 Diff", html)

    def test_modal(self):
        dlg = DiffDialog("a", "b")
        self.assertTrue(dlg.isModal())


class DiffDialogAcceptRejectTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_accept_sets_flag(self):
        dlg = DiffDialog("a", "b")
        dlg._on_accept()
        self.assertTrue(dlg.was_accepted())

    def test_reject_sets_flag(self):
        dlg = DiffDialog("a", "b")
        dlg._on_reject()
        self.assertFalse(dlg.was_accepted())

    def test_accept_returns_accepted(self):
        dlg = DiffDialog("a", "b")
        dlg._on_accept()
        # 直接 exec() 会卡,但调 accept 槽后会设 result=Accepted
        # 这里只测槽函数行为,不跑 exec
        self.assertTrue(dlg.was_accepted())


if __name__ == "__main__":
    unittest.main()
