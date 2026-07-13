"""端到端冒烟测试:模拟导入 → 加载 → 切章 → 进度保存 → 历史查询。"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from src.core import Library, Storage  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as d:
        # 准备一个示例 txt
        book_path = os.path.join(d, "《测试书》 - 测试作者.txt")
        Path(book_path).write_text(
            """《测试书》 - 测试作者

楔子

这是开篇。

第一章 启程

第一段内容。

第二章 遇险

第二段内容。

第三章 归途

第三段内容。
""",
            encoding="utf-8",
        )

        db_path = os.path.join(d, "library.db")
        storage = Storage(db_path)
        lib = Library(storage)

        # 1. 导入
        rec = lib.import_path(book_path)
        print(f"[导入] id={rec.id} title={rec.title} author={rec.author}")
        assert rec.title == "测试书"
        assert rec.author == "测试作者"

        # 2. 加载用于阅读
        rec2, book = lib.load_for_reading(rec.id)
        print(f"[加载] 共 {len(book.chapters)} 章")
        assert len(book.chapters) >= 4

        # 3. 切到第 2 章(索引 1)
        lib.save_position(
            book_id=rec.id, chapter_index=1,
            offset_in_chapter=10, progress=0.3,
            chapter_title=book.chapters[1].title, action="chapter",
        )

        # 4. 滚动更新
        lib.storage.save_position(rec.id, 1, 50, 0.35)

        # 5. 再切到第 3 章
        lib.save_position(
            book_id=rec.id, chapter_index=2,
            offset_in_chapter=0, progress=0.6,
            chapter_title=book.chapters[2].title, action="chapter",
        )

        # 6. 重新查询
        rec3 = lib.get_book(rec.id)
        assert rec3 is not None
        print(f"[持久化] chapter={rec3.last_chapter_index} "
              f"offset={rec3.last_offset_in_chapter} progress={rec3.last_progress:.2f}")
        assert rec3.last_chapter_index == 2
        assert rec3.last_offset_in_chapter == 0
        assert abs(rec3.last_progress - 0.6) < 0.01

        # 7. 历史
        hist = lib.history(rec.id)
        print(f"[历史] 共 {len(hist)} 条:")
        for h in hist:
            print(f"  - {h.action}  ch={h.chapter_index}  {h.chapter_title}")
        assert len(hist) >= 3  # 1 open + 2 chapter

        # 8. 全部书列表
        all_books = lib.list_books()
        print(f"[书库] {len(all_books)} 本")
        assert len(all_books) == 1

        # 9. 移除
        lib.remove(rec.id)
        assert lib.list_books() == []
        print("[移除] OK")

        storage.close()
    print("\nE2E SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
