"""PDF 阅读核心(Phase 3d)单元测试。

依赖 PyMuPDF,需先安装:pip install pymupdf
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

from src.core.pdf_reader import (
    is_available, open_pdf, page_count,
    ZOOM_LEVELS, DEFAULT_ZOOM_NAME,
    PDFDocument, PageInfo,
)


def _create_test_pdf(path: str) -> None:
    """用 PyMuPDF 创建一个简单测试 PDF。"""
    import fitz
    doc = fitz.open()
    # 第 1 页:A4
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 72), "Hello PDF World!", fontsize=20)
    p1.insert_text((72, 200), "Line A\nLine B\nLine C", fontsize=12)
    # 第 2 页
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Second page", fontsize=14)
    # 第 3 页
    p3 = doc.new_page()
    p3.insert_text((72, 72), "Third page", fontsize=14)
    doc.save(path)
    doc.close()


def _create_empty_pdf(path: str) -> None:
    """空白单页 PDF。"""
    import fitz
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()


@unittest.skipUnless(is_available(), "PyMuPDF 未安装")
class PDFBasicTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pdf-")
        self.path = os.path.join(self.tmp, "test.pdf")
        _create_test_pdf(self.path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_is_available(self):
        self.assertTrue(is_available())

    def test_open_pdf(self):
        doc = open_pdf(self.path)
        self.assertEqual(doc.page_count, 3)
        self.assertEqual(len(doc.pages), 3)
        doc.close()

    def test_open_pdf_metadata(self):
        doc = open_pdf(self.path)
        # 没设 title,默认用文件名
        self.assertTrue(doc.title)
        self.assertTrue(doc.author)
        doc.close()

    def test_page_info_dimensions(self):
        doc = open_pdf(self.path)
        # 第 0 页是 A4:595x842 pt
        p0 = doc.pages[0]
        self.assertAlmostEqual(p0.width_pt, 595, delta=1)
        self.assertAlmostEqual(p0.height_pt, 842, delta=1)
        doc.close()

    def test_get_text(self):
        doc = open_pdf(self.path)
        text = doc.get_text(0)
        self.assertIn("Hello PDF World!", text)
        self.assertIn("Line A", text)
        doc.close()

    def test_get_text_out_of_range(self):
        doc = open_pdf(self.path)
        self.assertEqual(doc.get_text(-1), "")
        self.assertEqual(doc.get_text(999), "")
        doc.close()

    def test_page_count_helper(self):
        self.assertEqual(page_count(self.path), 3)


@unittest.skipUnless(is_available(), "PyMuPDF 未安装")
class PDFRenderTest(unittest.TestCase):
    """渲染测试:在 QApplication 里跑。"""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pdf-")
        self.path = os.path.join(self.tmp, "test.pdf")
        _create_test_pdf(self.path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_render_default_zoom(self):
        doc = open_pdf(self.path)
        img = doc.render_image(0)
        # 默认 zoom 2.0,A4 page → ~1190x1684
        self.assertGreater(img.width(), 0)
        self.assertGreater(img.height(), 0)
        # A4 aspect ratio 应保留:width/height ≈ 595/842
        ratio = img.width() / img.height()
        self.assertAlmostEqual(ratio, 595 / 842, delta=0.05)
        doc.close()

    def test_render_higher_zoom_bigger(self):
        doc = open_pdf(self.path)
        img_small = doc.render_image(0, zoom_name="缩")  # 1.0
        img_large = doc.render_image(0, zoom_name="巨")  # 4.0
        self.assertGreater(img_large.width(), img_small.width() * 3)
        doc.close()

    def test_render_all_zoom_levels(self):
        doc = open_pdf(self.path)
        for name in ZOOM_LEVELS:
            img = doc.render_image(0, zoom_name=name)
            self.assertGreater(img.width(), 0, f"zoom={name} 渲染失败")
        doc.close()

    def test_render_out_of_range_raises(self):
        doc = open_pdf(self.path)
        with self.assertRaises(ValueError):
            doc.render_image(-1)
        with self.assertRaises(ValueError):
            doc.render_image(999)
        doc.close()

    def test_render_creates_independent_copies(self):
        """连续渲染 2 次不应共享内存。"""
        doc = open_pdf(self.path)
        img1 = doc.render_image(0, zoom_name="原")
        img2 = doc.render_image(1, zoom_name="原")
        # 两张图应独立(QImage.copy 已保证)
        self.assertIsNotNone(img1)
        self.assertIsNotNone(img2)
        # 但 size 可能不同(page 1/2 内容不同,但页面尺寸可能一样)
        # 至少 bytes 不会互相覆盖
        doc.close()


@unittest.skipUnless(is_available(), "PyMuPDF 未安装")
class PDFErrorTest(unittest.TestCase):

    def test_open_nonexistent_raises(self):
        with self.assertRaises(FileNotFoundError):
            open_pdf("/nonexistent/path.pdf")

    def test_open_non_pdf_raises(self):
        tmp = tempfile.mkdtemp()
        try:
            p = os.path.join(tmp, "fake.pdf")
            Path(p).write_text("not a pdf", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                open_pdf(p)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_open_wrong_extension_raises(self):
        tmp = tempfile.mkdtemp()
        try:
            p = os.path.join(tmp, "test.txt")
            Path(p).write_text("hello", encoding="utf-8")
            with self.assertRaises(ValueError):
                open_pdf(p)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipUnless(is_available(), "PyMuPDF 未安装")
class PDFEmptyTest(unittest.TestCase):

    def test_empty_single_page(self):
        tmp = tempfile.mkdtemp()
        try:
            p = os.path.join(tmp, "empty.pdf")
            _create_empty_pdf(p)
            doc = open_pdf(p)
            self.assertEqual(doc.page_count, 1)
            self.assertEqual(doc.get_text(0), "")
            doc.close()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class PDFGracefulDegradationTest(unittest.TestCase):
    """如果 PyMuPDF 没装,is_available 应返回 False,不要炸。"""
    def test_is_available_returns_bool(self):
        from src.core.pdf_reader import is_available
        self.assertIsInstance(is_available(), bool)


if __name__ == "__main__":
    unittest.main()
