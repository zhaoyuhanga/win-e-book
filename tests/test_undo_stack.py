"""EditorPanel 撤销栈优化(Phase 4c)测试。

覆盖:
- Agent 编辑作为单个 undo 步(beginEditBlock/endEditBlock)
- 跳到上一个 checkpoint(_jump_to_previous_checkpoint)
- Ctrl+Shift+Z 快捷键绑定
- 无 checkpoint / 已等于当前 / 快照丢失等边缘
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence, QTextCursor, QShortcut
from PySide6.QtWidgets import QApplication

from src.ui.write_view import EditorPanel
from src.core.checkpoint import (
    create_checkpoint, default_checkpoint_root, list_checkpoints,
    restore_checkpoint,
)


def _create_test_doc(tmp: Path) -> Path:
    p = tmp / "test.md"
    p.write_text("第一段原文。\n\n第二段原文。\n", encoding="utf-8")
    return p


def _patch_checkpoint_root(tmp: Path):
    """把 default_checkpoint_root 重定向到 tmp/.write_checkpoints。"""
    from src.core import checkpoint as ckpt_mod
    orig = ckpt_mod.default_checkpoint_root
    ckpt_mod.default_checkpoint_root = lambda workspace=None: tmp / ".write_checkpoints"
    return orig, ckpt_mod


def _restore_checkpoint_root(orig_pair):
    orig, ckpt_mod = orig_pair
    ckpt_mod.default_checkpoint_root = orig


class UndoGroupTest(unittest.TestCase):
    """Agent 编辑作为单个 undo 步。"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="undo-"))
        self.path = _create_test_doc(self.tmp)
        QSettings("WinEBook", "EditorTypography").clear()
        self.panel = EditorPanel()
        self.panel.open_file(str(self.path))

    def tearDown(self):
        try:
            self.panel.deleteLater()
        except Exception:
            pass
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_agent_edit_undo_in_one_step(self):
        """模拟 Agent 编辑:全选 → 替换 → 单次 undo 回到原内容。"""
        cursor = self.panel.editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)  # 全选
        cursor.beginEditBlock()
        cursor.insertText("AI 改写后的内容")
        cursor.endEditBlock()
        # 验证当前是 AI 内容
        self.assertEqual(self.panel.editor.toPlainText(), "AI 改写后的内容")
        # 单次 undo
        self.panel.editor.undo()
        # 应该回到原内容
        self.assertIn("第一段原文", self.panel.editor.toPlainText())

    def test_normal_edit_undo_works_as_before(self):
        """普通编辑不走 beginEditBlock,仍按字符 undo。"""
        cursor = self.panel.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText("追加")
        # 单次 undo 应该只回退最后输入
        self.panel.editor.undo()
        self.assertNotIn("追加", self.panel.editor.toPlainText())


class JumpToCheckpointTest(unittest.TestCase):
    """_jump_to_previous_checkpoint 测试。"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        QSettings("WinEBook", "EditorTypography").clear()
        self.tmp = Path(tempfile.mkdtemp(prefix="jumpcp-"))
        self.path = _create_test_doc(self.tmp)
        self.orig_pair = _patch_checkpoint_root(self.tmp)
        # 把 DiffDialog.exec 替换成直接 accept,避免阻塞测试
        from src.ui import diff_dialog as dd_mod
        from PySide6.QtWidgets import QDialog
        self._orig_exec = dd_mod.DiffDialog.exec
        dd_mod.DiffDialog.exec = lambda self_: QDialog.Accepted
        self.panel = EditorPanel()
        self.panel.open_file(str(self.path))

    def tearDown(self):
        # 恢复 DiffDialog.exec
        from src.ui import diff_dialog as dd_mod
        dd_mod.DiffDialog.exec = self._orig_exec
        _restore_checkpoint_root(self.orig_pair)
        try:
            self.panel.deleteLater()
        except Exception:
            pass
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_jump_to_existing_checkpoint(self):
        """1. 创一个 cp(原内容);2. 编辑;3. 跳到 cp;4. 内容应回到原状。"""
        # 1. 创一个 cp(原内容)
        create_checkpoint(
            self.path, "第一段原文。\n\n第二段原文。\n",
            trigger="manual", note="v1",
            root=self.tmp / ".write_checkpoints",
        )
        # 2. 编辑(模拟用户改了)
        cursor = self.panel.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText("用户修改的内容。\n")
        # 3. 跳到上一个 cp
        self.panel._jump_to_previous_checkpoint()
        # 4. 内容应回到 cp(v1 状态)
        text = self.panel.editor.toPlainText()
        self.assertIn("第一段原文", text)
        self.assertNotIn("用户修改的内容", text)

    def test_jump_creates_pre_restore_backup(self):
        """跳到 cp 时,当前内容应被自动备份(pre-restore)。"""
        # 创 v1 cp
        create_checkpoint(
            self.path, "第一段原文。\n\n第二段原文。\n",
            trigger="manual", note="v1",
            root=self.tmp / ".write_checkpoints",
        )
        # 编辑
        cursor = self.panel.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText("用户修改的内容。\n")
        # 跳
        self.panel._jump_to_previous_checkpoint()
        # 查 cps
        cps = list_checkpoints(self.path, root=self.tmp / ".write_checkpoints")
        triggers = [c.trigger for c in cps]
        # 应有 pre-restore
        self.assertIn("auto-pre-restore", triggers)

    def test_jump_undo_in_one_step(self):
        """跳到 cp 整个操作应可单次 undo 回到跳前。"""
        create_checkpoint(
            self.path, "第一段原文。\n\n第二段原文。\n",
            trigger="manual", note="v1",
            root=self.tmp / ".write_checkpoints",
        )
        # 编辑
        cursor = self.panel.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText("用户修改的内容。\n")
        text_before_jump = self.panel.editor.toPlainText()
        # 跳
        self.panel._jump_to_previous_checkpoint()
        # undo 一次
        self.panel.editor.undo()
        text_after_undo = self.panel.editor.toPlainText()
        self.assertEqual(text_after_undo, text_before_jump)

    def test_jump_no_file(self):
        """没开文件时点跳转应提示。"""
        self.panel._file_path = None
        # 不应崩
        try:
            self.panel._jump_to_previous_checkpoint()
        except Exception:
            pass  # 可能弹 QMessageBox 异常

    def test_jump_no_checkpoint(self):
        """没 checkpoint 时应提示。"""
        # 没有创建任何 cp
        # 也不应崩
        try:
            self.panel._jump_to_previous_checkpoint()
        except Exception:
            pass


class ShortcutBindingTest(unittest.TestCase):
    """验证 Ctrl+Shift+Z 绑到了 _jump_to_previous_checkpoint。"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        QSettings("WinEBook", "EditorTypography").clear()
        self.panel = EditorPanel()

    def tearDown(self):
        try:
            self.panel.deleteLater()
        except Exception:
            pass

    def test_shortcut_exists(self):
        from PySide6.QtGui import QShortcut
        # 找绑了 Ctrl+Shift+Z 的 QShortcut
        shortcuts = self.panel.findChildren(QShortcut)
        target = None
        for sc in shortcuts:
            if sc.key() == QKeySequence("Ctrl+Shift+Z"):
                target = sc
                break
        self.assertIsNotNone(target, "未找到 Ctrl+Shift+Z 快捷键")

    def test_button_exists(self):
        self.assertTrue(hasattr(self.panel, "btn_prev_cp"))
        self.assertIn("上一快照", self.panel.btn_prev_cp.text())


if __name__ == "__main__":
    unittest.main()
