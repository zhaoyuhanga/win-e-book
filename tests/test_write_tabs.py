"""WriteView 多 Tab 集成测试(Phase 4b)。

需要 QApplication + 临时 workspace。
验证:
- 初始 1 个空白 tab
- _add_new_tab / _current_editor
- _find_tab_by_path 去重
- _save_tabs / _restore_tabs 持久化
- _on_close_tab 至少留 1 个 tab
- _on_file_opened 切到已开 / 新开
- 兼容旧 API:self.editor
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
from PySide6.QtWidgets import QApplication

# 替身 default_workspace 之前 import
from src.ui import write_view as wv_mod
from src.ui.write_view import WriteView, EditorPanel


def _create_workspace() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="wv-tabs-"))
    (tmp / "doc1.md").write_text("# 第一章\n\n第一段内容。", encoding="utf-8")
    (tmp / "doc2.md").write_text("# 第一章\n\n第二段内容。", encoding="utf-8")
    (tmp / "doc3.md").write_text("notes", encoding="utf-8")
    return tmp


def _patch_workspace(tmp: Path):
    """把 default_workspace 指到 tmp。"""
    orig = wv_mod.default_workspace
    wv_mod.default_workspace = lambda: tmp
    # WriteView.__init__ 里调 default_workspace,需要替换属性
    return orig


def _restore_workspace(orig):
    wv_mod.default_workspace = orig


class WriteViewTabBasicTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        QSettings("WinEBook", WriteView._TABS_KEY).clear()
        self.tmp = _create_workspace()
        self._orig_ws = _patch_workspace(self.tmp)

    def tearDown(self):
        _restore_workspace(self._orig_ws)
        if hasattr(self, "view"):
            try:
                self.view.deleteLater()
            except Exception:
                pass
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        QSettings("WinEBook", WriteView._TABS_KEY).clear()

    def test_initial_one_tab(self):
        self.view = WriteView()
        self.assertEqual(self.view.tabs.count(), 1)
        self.assertIsInstance(self.view._current_editor(), EditorPanel)

    def test_initial_tab_is_empty(self):
        self.view = WriteView()
        ed = self.view._current_editor()
        self.assertIsNone(ed._file_path)
        self.assertEqual(ed.editor.toPlainText(), "")

    def test_legacy_editor_property(self):
        self.view = WriteView()
        # 兼容旧 API:self.editor 应返回当前 tab 的 editor
        self.assertIs(self.view.editor, self.view._current_editor())


class WriteViewTabAddTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        QSettings("WinEBook", WriteView._TABS_KEY).clear()
        self.tmp = _create_workspace()
        self._orig_ws = _patch_workspace(self.tmp)
        self.view = WriteView()

    def tearDown(self):
        _restore_workspace(self._orig_ws)
        try:
            self.view.deleteLater()
        except Exception:
            pass
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        QSettings("WinEBook", WriteView._TABS_KEY).clear()

    def test_add_blank_tab(self):
        before = self.view.tabs.count()
        idx = self.view._add_new_tab()
        self.assertEqual(self.view.tabs.count(), before + 1)
        self.assertEqual(self.view.tabs.tabText(idx), "未命名")

    def test_add_file_tab(self):
        path = str(self.tmp / "doc1.md")
        idx = self.view._add_new_tab(path)
        self.assertEqual(self.view.tabs.tabText(idx), "doc1.md")
        ed = self.view.tabs.widget(idx)
        self.assertEqual(ed._file_path, path)
        self.assertIn("第一段", ed.editor.toPlainText())

    def test_add_file_then_switch(self):
        idx1 = self.view._add_new_tab(str(self.tmp / "doc1.md"))
        idx2 = self.view._add_new_tab(str(self.tmp / "doc2.md"))
        # 当前应该是新加的 tab
        self.assertEqual(self.view.tabs.currentIndex(), idx2)
        # 切到 idx1
        self.view.tabs.setCurrentIndex(idx1)
        ed = self.view._current_editor()
        self.assertEqual(ed._file_path, str(self.tmp / "doc1.md"))


class WriteViewTabFindTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        QSettings("WinEBook", WriteView._TABS_KEY).clear()
        self.tmp = _create_workspace()
        self._orig_ws = _patch_workspace(self.tmp)
        self.view = WriteView()
        self.view._add_new_tab(str(self.tmp / "doc1.md"))
        self.view._add_new_tab(str(self.tmp / "doc2.md"))

    def tearDown(self):
        _restore_workspace(self._orig_ws)
        try:
            self.view.deleteLater()
        except Exception:
            pass
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        QSettings("WinEBook", WriteView._TABS_KEY).clear()

    def test_find_existing(self):
        idx = self.view._find_tab_by_path(str(self.tmp / "doc1.md"))
        self.assertGreaterEqual(idx, 0)
        self.assertEqual(self.view.tabs.tabText(idx), "doc1.md")

    def test_find_nonexistent(self):
        idx = self.view._find_tab_by_path(str(self.tmp / "doc3.md"))
        self.assertEqual(idx, -1)

    def test_find_case_insensitive(self):
        # Windows 路径不区分大小写
        idx = self.view._find_tab_by_path(str(self.tmp / "DOC1.MD"))
        self.assertGreaterEqual(idx, 0)


class WriteViewTabCloseTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        QSettings("WinEBook", WriteView._TABS_KEY).clear()
        self.tmp = _create_workspace()
        self._orig_ws = _patch_workspace(self.tmp)
        self.view = WriteView()
        self.view._add_new_tab(str(self.tmp / "doc1.md"))
        self.view._add_new_tab(str(self.tmp / "doc2.md"))

    def tearDown(self):
        _restore_workspace(self._orig_ws)
        try:
            self.view.deleteLater()
        except Exception:
            pass
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        QSettings("WinEBook", WriteView._TABS_KEY).clear()

    def test_close_last_tab_clears_instead(self):
        # 先关到只剩 1 个 tab
        while self.view.tabs.count() > 1:
            self.view._on_close_tab(0)
        # 现在 1 个 tab,再关应该清空内容(不删除 tab)
        self.assertEqual(self.view.tabs.count(), 1)
        ed = self.view._current_editor()
        ed.editor.setPlainText("test content")
        self.view._on_close_tab(0)
        self.assertEqual(self.view.tabs.count(), 1)
        self.assertEqual(ed.editor.toPlainText(), "")
        self.assertIsNone(ed._file_path)

    def test_close_middle_tab(self):
        # 3 个 tab(初始 1 + 加 2)
        self.assertEqual(self.view.tabs.count(), 3)
        # 关掉 idx=1(中间那个)
        self.view._on_close_tab(1)
        self.assertEqual(self.view.tabs.count(), 2)


class WriteViewTabPersistenceTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        QSettings("WinEBook", WriteView._TABS_KEY).clear()
        self.tmp = _create_workspace()
        self._orig_ws = _patch_workspace(self.tmp)
        self.view = WriteView()
        self.view._add_new_tab(str(self.tmp / "doc1.md"))
        self.view._add_new_tab(str(self.tmp / "doc2.md"))
        self.view.tabs.setCurrentIndex(1)

    def tearDown(self):
        _restore_workspace(self._orig_ws)
        try:
            self.view.deleteLater()
        except Exception:
            pass
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        QSettings("WinEBook", WriteView._TABS_KEY).clear()

    def test_save_and_restore(self):
        # 1. 持久化
        self.view._save_tabs()
        s = QSettings("WinEBook", WriteView._TABS_KEY)
        paths = s.value("paths", [], type=list)
        self.assertEqual(len(paths), 2)
        self.assertIn(str(self.tmp / "doc1.md"), paths)
        self.assertIn(str(self.tmp / "doc2.md"), paths)
        self.assertEqual(int(s.value("current", 0)), 1)

    def test_restore_after_reopen(self):
        # 保存
        self.view._save_tabs()
        # 销毁旧 view
        try:
            self.view.deleteLater()
        except Exception:
            pass
        import gc; gc.collect()
        # 新 view,应自动恢复
        self.view = WriteView()
        # 应该有 2 个文件 tab(初始空白 + 2 个恢复的),但 _add_new_tab 是手动加的,
        # _restore_tabs 用 addTab,初始的 1 个空白还在
        # 实际:__init__ 先 _add_new_tab()(1 个空白),然后 _restore_tabs 加 2 个 → 3 个
        # 第一个是空 tab,后两个是 doc1 / doc2
        self.assertGreaterEqual(self.view.tabs.count(), 2)
        # 找到 doc1 的 tab
        idx = self.view._find_tab_by_path(str(self.tmp / "doc1.md"))
        self.assertGreaterEqual(idx, 0)

    def test_restore_skips_missing(self):
        # 保存,删 doc2
        self.view._save_tabs()
        try:
            (self.tmp / "doc2.md").unlink()
        except OSError:
            pass
        try:
            self.view.deleteLater()
        except Exception:
            pass
        import gc; gc.collect()
        self.view = WriteView()
        # doc1 应在,doc2 应被跳过
        self.assertGreaterEqual(self.view._find_tab_by_path(str(self.tmp / "doc1.md")), 0)
        self.assertEqual(self.view._find_tab_by_path(str(self.tmp / "doc2.md")), -1)


class WriteViewFileOpenedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        QSettings("WinEBook", WriteView._TABS_KEY).clear()
        self.tmp = _create_workspace()
        self._orig_ws = _patch_workspace(self.tmp)
        self.view = WriteView()

    def tearDown(self):
        _restore_workspace(self._orig_ws)
        try:
            self.view.deleteLater()
        except Exception:
            pass
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        QSettings("WinEBook", WriteView._TABS_KEY).clear()

    def test_open_new_file_creates_tab(self):
        before = self.view.tabs.count()
        self.view._on_file_opened(str(self.tmp / "doc1.md"))
        self.assertEqual(self.view.tabs.count(), before + 1)

    def test_open_existing_file_switches(self):
        self.view._on_file_opened(str(self.tmp / "doc1.md"))
        n_after_first = self.view.tabs.count()
        # 再开同一个文件,不应创建新 tab
        self.view._on_file_opened(str(self.tmp / "doc1.md"))
        self.assertEqual(self.view.tabs.count(), n_after_first)

    def test_open_different_files_separate_tabs(self):
        self.view._on_file_opened(str(self.tmp / "doc1.md"))
        self.view._on_file_opened(str(self.tmp / "doc2.md"))
        # 至少 2 个(初始空白 + 2 个)
        self.assertGreaterEqual(self.view.tabs.count(), 2)


if __name__ == "__main__":
    unittest.main()
