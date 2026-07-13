"""PdfReaderView 集成测试(Phase 3d)。

需要在 QApplication 里跑,验证:
- open_pdf 成功 / 失败
- 进度持久化(QSettings round-trip)
- 翻页 / 缩放
- 状态栏文本
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

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

from src.core import pdf_reader
from src.ui.pdf_reader_view import PdfReaderView


def _create_pdf(path: str, page_count: int = 5) -> None:
    import fitz
    doc = fitz.open()
    for i in range(page_count):
        p = doc.new_page()
        p.insert_text((72, 72), f"Page {i + 1}", fontsize=20)
    doc.save(path)
    doc.close()


@unittest.skipUnless(pdf_reader.is_available(), "PyMuPDF 未安装")
class PdfReaderViewBasicTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        # 清空 QSettings
        QSettings("WinEBook", "PdfReader").clear()
        self.tmp = tempfile.mkdtemp(prefix="pdfv-")
        self.path = os.path.join(self.tmp, "test.pdf")
        _create_pdf(self.path, page_count=5)

    def tearDown(self):
        # 关闭 view
        if hasattr(self, "view"):
            self.view.close_pdf()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_open_pdf_success(self):
        self.view = PdfReaderView()
        ok = self.view.open_pdf(self.path)
        self.assertTrue(ok)
        self.assertIsNotNone(self.view._doc)
        self.assertEqual(self.view._doc.page_count, 5)

    def test_open_pdf_failure(self):
        self.view = PdfReaderView()
        ok = self.view.open_pdf("/nonexistent/path.pdf")
        self.assertFalse(ok)
        self.assertIsNone(self.view._doc)

    def test_open_wrong_extension(self):
        self.view = PdfReaderView()
        # .txt 不算 PDF
        txt = os.path.join(self.tmp, "fake.pdf")
        Path(txt).write_text("not pdf", encoding="utf-8")
        ok = self.view.open_pdf(txt)
        self.assertFalse(ok)

    def test_page_spin_set_on_open(self):
        self.view = PdfReaderView()
        self.view.open_pdf(self.path)
        self.assertEqual(self.view.page_spin.maximum(), 5)
        self.assertEqual(self.view.page_spin.value(), 1)

    def test_file_label_set(self):
        self.view = PdfReaderView()
        self.view.open_pdf(self.path)
        self.assertIn("test.pdf", self.view.file_label.text())

    def test_meta_label_set(self):
        self.view = PdfReaderView()
        self.view.open_pdf(self.path)
        meta = self.view.meta_label.text()
        self.assertIn("5 页", meta)


@unittest.skipUnless(pdf_reader.is_available(), "PyMuPDF 未安装")
class PdfReaderViewNavigationTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        QSettings("WinEBook", "PdfReader").clear()
        self.tmp = tempfile.mkdtemp(prefix="pdfv-")
        self.path = os.path.join(self.tmp, "test.pdf")
        _create_pdf(self.path, page_count=5)
        self.view = PdfReaderView()
        self.view.open_pdf(self.path)

    def tearDown(self):
        self.view.close_pdf()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_next_page(self):
        self.view._next_page()
        self.assertEqual(self.view._current_page, 1)
        self.assertEqual(self.view.page_spin.value(), 2)

    def test_next_page_at_end_no_op(self):
        self.view._goto_page(4)  # 最后一页
        self.view._next_page()
        self.assertEqual(self.view._current_page, 4)  # 不变

    def test_prev_page(self):
        self.view._goto_page(3)
        self.view._prev_page()
        self.assertEqual(self.view._current_page, 2)

    def test_prev_page_at_start_no_op(self):
        self.view._prev_page()
        self.assertEqual(self.view._current_page, 0)

    def test_goto_page_clamps(self):
        self.view._goto_page(99)
        self.assertEqual(self.view._current_page, 4)  # 钳到最大
        self.view._goto_page(-5)
        self.assertEqual(self.view._current_page, 0)  # 钳到最小

    def test_goto_last(self):
        self.view._goto_last()
        self.assertEqual(self.view._current_page, 4)

    def test_status_label_updates(self):
        self.view._goto_page(2)
        self.assertIn("3 / 5", self.view.status_label.text())


@unittest.skipUnless(pdf_reader.is_available(), "PyMuPDF 未安装")
class PdfReaderViewZoomTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        QSettings("WinEBook", "PdfReader").clear()
        self.tmp = tempfile.mkdtemp(prefix="pdfv-")
        self.path = os.path.join(self.tmp, "test.pdf")
        _create_pdf(self.path, page_count=3)
        self.view = PdfReaderView()
        self.view.open_pdf(self.path)

    def tearDown(self):
        self.view.close_pdf()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_zoom_default(self):
        self.assertEqual(self.view._current_zoom, "原")

    def test_zoom_change_updates_state(self):
        self.view.zoom_combo.setCurrentText("巨")
        self.assertEqual(self.view._current_zoom, "巨")

    def test_zoom_invalid_ignored(self):
        # combo 只能选合法值,但万一调 _on_zoom_changed 传未知
        self.view._on_zoom_changed("未知")
        self.assertEqual(self.view._current_zoom, "原")  # 不变


@unittest.skipUnless(pdf_reader.is_available(), "PyMuPDF 未安装")
class PdfReaderViewProgressTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        QSettings("WinEBook", "PdfReader").clear()
        self.tmp = tempfile.mkdtemp(prefix="pdfv-")
        self.path = os.path.join(self.tmp, "test.pdf")
        _create_pdf(self.path, page_count=3)
        self.view = PdfReaderView()

    def tearDown(self):
        self.view.close_pdf()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_progress_persists_across_open(self):
        # 1. 打开 + 跳到第 3 页
        self.view.open_pdf(self.path)
        self.view._goto_page(2)
        self.view._save_progress()
        # 2. 关闭
        self.view.close_pdf()
        # 3. 重开,应回到第 3 页
        self.view.open_pdf(self.path)
        self.assertEqual(self.view._current_page, 2)

    def test_progress_includes_zoom(self):
        self.view.open_pdf(self.path)
        self.view.zoom_combo.setCurrentText("大")
        self.view._save_progress()
        self.view.close_pdf()
        self.view.open_pdf(self.path)
        self.assertEqual(self.view._current_zoom, "大")

    def test_progress_different_files_independent(self):
        # 路径 A
        path_b = os.path.join(self.tmp, "other.pdf")
        _create_pdf(path_b, page_count=10)
        # 在 A 上翻到第 2 页
        self.view.open_pdf(self.path)
        self.view._goto_page(1)
        self.view._save_progress()
        # 开 B 应从第 0 页开始(没有历史)
        self.view.open_pdf(path_b)
        self.assertEqual(self.view._current_page, 0)

    def test_progress_key_is_path_hash(self):
        key = PdfReaderView._progress_key(self.path)
        self.assertEqual(len(key), 16)
        # 同样路径生成同样 key
        key2 = PdfReaderView._progress_key(self.path)
        self.assertEqual(key, key2)


@unittest.skipUnless(pdf_reader.is_available(), "PyMuPDF 未安装")
class PdfReaderViewShutdownTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        QSettings("WinEBook", "PdfReader").clear()
        self.tmp = tempfile.mkdtemp(prefix="pdfv-")
        self.path = os.path.join(self.tmp, "test.pdf")
        _create_pdf(self.path)
        self.view = PdfReaderView()
        self.view.open_pdf(self.path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_shutdown_clears_state(self):
        self.view.shutdown()
        self.assertIsNone(self.view._doc)
        self.assertEqual(self.view._current_path, "")


if __name__ == "__main__":
    unittest.main()
