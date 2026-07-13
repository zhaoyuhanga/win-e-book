"""PDF 阅读核心(Phase 3d)。

依赖 PyMuPDF(fitz)。提供:
- 打开 PDF,获取页数
- 渲染单页到 QImage(给 QLabel 显示)
- 提取文本(可选,给搜索/复制用)
- 渲染缩放(zoom = 1.0 / 1.5 / 2.0 / 3.0)

不做:
- 章节解析(PDF 没用统一章节结构,代价高)
- 表单 / 注释
- 加密 PDF(只支持无密码)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple

# PyMuPDF 延迟导入(避免没装就炸)
try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:  # noqa: BLE001
    fitz = None
    HAS_FITZ = False


# ============================================================
# 缩放档位(约 DPI 倍率)
# ============================================================

ZOOM_LEVELS = {
    "缩": 1.0,     # 75 DPI,适合快速浏览
    "适": 1.5,     # 112 DPI
    "原": 2.0,     # 150 DPI(默认)
    "大": 3.0,     # 225 DPI
    "巨": 4.0,     # 300 DPI,打印级
}

DEFAULT_ZOOM_NAME = "原"


def _zoom_to_matrix(zoom: float):
    """把缩放倍率转 fitz.Matrix(zoom, zoom)。"""
    if not HAS_FITZ:
        raise RuntimeError("PyMuPDF 未安装,无法渲染 PDF")
    return fitz.Matrix(zoom, zoom)


# ============================================================
# 数据类
# ============================================================

@dataclass
class PageInfo:
    """一页 PDF 的元信息。"""
    index: int           # 0-based
    width_pt: float      # 原始宽度(磅)
    height_pt: float     # 原始高度(磅)
    rotation: int        # 0/90/180/270
    text_chars: int      # 该页字符数


@dataclass
class PDFDocument:
    """打开的 PDF 文档句柄。"""
    path: str
    page_count: int
    title: str
    author: str
    pages: List[PageInfo]
    _doc: object  # fitz.Document

    def close(self):
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass

    def get_text(self, page_index: int) -> str:
        if not (0 <= page_index < self.page_count):
            return ""
        try:
            return self._doc.load_page(page_index).get_text()
        except Exception:
            return ""

    def render_pixmap(self, page_index: int, zoom_name: str = DEFAULT_ZOOM_NAME):
        """渲染单页为 fitz.Pixmap(返回原对象,UI 自己转 QImage)。"""
        if not (0 <= page_index < self.page_count):
            raise ValueError(f"页码越界: {page_index} / {self.page_count}")
        zoom = ZOOM_LEVELS.get(zoom_name, ZOOM_LEVELS[DEFAULT_ZOOM_NAME])
        page = self._doc.load_page(page_index)
        return page.get_pixmap(matrix=_zoom_to_matrix(zoom))

    def render_image(self, page_index: int, zoom_name: str = DEFAULT_ZOOM_NAME):
        """渲染单页为 QImage(给 Qt UI 用)。"""
        from PySide6.QtGui import QImage
        pm = self.render_pixmap(page_index, zoom_name)
        # pm.samples: bytes; pm.stride: 行字节数; pm.width/height: 像素
        # 通道数:pm.n(1/3/4)
        fmt = {1: QImage.Format_Grayscale8, 3: QImage.Format_RGB888, 4: QImage.Format_RGBA8888}.get(pm.n)
        if fmt is None:
            raise ValueError(f"不支持的通道数: {pm.n}")
        img = QImage(
            pm.samples, pm.width, pm.height, pm.stride, fmt,
        )
        # pixmap 数据由 Python bytes 持有,QImage 不复制 → 立刻 copy 一份防止野指针
        return img.copy()


# ============================================================
# 公开 API
# ============================================================

def is_available() -> bool:
    """PyMuPDF 是否可用(用于 UI 隐藏入口)。"""
    return HAS_FITZ


def open_pdf(path: str | Path) -> PDFDocument:
    """打开一个 PDF 文件。"""
    if not HAS_FITZ:
        raise RuntimeError("PyMuPDF 未安装,无法打开 PDF。请运行: pip install pymupdf")
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"PDF 不存在: {path}")
    if p.suffix.lower() != ".pdf":
        raise ValueError(f"非 PDF 文件: {path}")
    doc = fitz.open(str(p))
    if doc.is_encrypted:
        # 不支持加密 PDF,直接关掉
        doc.close()
        raise RuntimeError(f"PDF 已加密,暂不支持: {p.name}")
    # 元数据
    meta = doc.metadata or {}
    title = meta.get("title") or p.stem
    author = meta.get("author") or "未知"
    # 逐页信息(轻量,不渲染)
    pages: List[PageInfo] = []
    for i in range(doc.page_count):
        try:
            page = doc.load_page(i)
            rect = page.rect
            text = page.get_text()
            pages.append(PageInfo(
                index=i,
                width_pt=rect.width,
                height_pt=rect.height,
                rotation=page.rotation,
                text_chars=len(text),
            ))
        except Exception:
            pages.append(PageInfo(
                index=i, width_pt=0, height_pt=0, rotation=0, text_chars=0,
            ))
    return PDFDocument(
        path=str(p),
        page_count=doc.page_count,
        title=title,
        author=author,
        pages=pages,
        _doc=doc,
    )


def page_count(path: str | Path) -> int:
    """只读页数(打开 → 读 → 关)。"""
    if not HAS_FITZ:
        return 0
    try:
        doc = fitz.open(str(path))
        n = doc.page_count
        doc.close()
        return n
    except Exception:
        return 0
