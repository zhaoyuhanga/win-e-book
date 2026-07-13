"""Checkpoint 引擎(Phase 3b)单元测试。

覆盖:
- create_checkpoint / list / load / restore / delete
- should_create_checkpoint 三种触发条件
- cleanup_old 容量控制(优先保 manual)
- 去重(同 hash 跳过)
- 原子写(meta + 内容)
- 损坏 meta.jsonl 行不抛
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from src.core.checkpoint import (
    Checkpoint,
    TRIGGER_CHARS_DELTA,
    TRIGGER_INTERVAL_SEC,
    MAX_CHECKPOINTS_PER_FILE,
    default_checkpoint_root,
    doc_id_for,
    should_create_checkpoint,
    create_checkpoint,
    list_checkpoints,
    load_checkpoint_content,
    restore_checkpoint,
    delete_checkpoint,
    cleanup_old,
    last_checkpoint,
    checkpoint_stats,
    purge_document,
)


class CheckpointBasicTest(unittest.TestCase):
    """基础 CRUD 测试。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ckpt-")
        self.root = Path(self.tmp) / ".write_checkpoints"
        self.root.mkdir(parents=True, exist_ok=True)
        self.doc = Path(self.tmp) / "novel.md"
        self.doc.write_text("第一章 开篇\n\n风起云涌。", encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_and_list(self):
        cp = create_checkpoint(
            self.doc, "第一章 开篇\n\n风起云涌。",
            trigger="manual", root=self.root, now=1000,
        )
        self.assertIsNotNone(cp)
        self.assertEqual(cp.ts, 1000)
        self.assertEqual(cp.trigger, "manual")
        cps = list_checkpoints(self.doc, root=self.root)
        self.assertEqual(len(cps), 1)
        self.assertEqual(cps[0].sha256, cp.sha256)

    def test_create_dedup(self):
        """同样的内容第二次创建应被去重。"""
        c1 = create_checkpoint(
            self.doc, "内容1", trigger="manual", root=self.root, now=1000)
        c2 = create_checkpoint(
            self.doc, "内容1", trigger="manual", root=self.root, now=2000)
        self.assertIsNotNone(c1)
        self.assertIsNone(c2)
        cps = list_checkpoints(self.doc, root=self.root)
        self.assertEqual(len(cps), 1)

    def test_create_different_content(self):
        c1 = create_checkpoint(
            self.doc, "内容1", root=self.root, now=1000)
        c2 = create_checkpoint(
            self.doc, "内容1修改", root=self.root, now=2000)
        self.assertIsNotNone(c1)
        self.assertIsNotNone(c2)
        self.assertEqual(len(list_checkpoints(self.doc, root=self.root)), 2)

    def test_load_content(self):
        create_checkpoint(
            self.doc, "hello world", trigger="manual",
            root=self.root, now=5000)
        body = load_checkpoint_content(self.doc, 5000, root=self.root)
        self.assertEqual(body, "hello world")

    def test_load_missing_returns_none(self):
        body = load_checkpoint_content(self.doc, 9999, root=self.root)
        self.assertIsNone(body)

    def test_delete_checkpoint(self):
        create_checkpoint(self.doc, "v1", root=self.root, now=1000)
        create_checkpoint(self.doc, "v2", root=self.root, now=2000)
        ok = delete_checkpoint(self.doc, 1000, root=self.root)
        self.assertTrue(ok)
        cps = list_checkpoints(self.doc, root=self.root)
        self.assertEqual(len(cps), 1)
        self.assertEqual(cps[0].ts, 2000)

    def test_delete_missing(self):
        ok = delete_checkpoint(self.doc, 9999, root=self.root)
        self.assertFalse(ok)


class CheckpointRestoreTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ckpt-")
        self.root = Path(self.tmp) / ".write_checkpoints"
        self.root.mkdir(parents=True, exist_ok=True)
        self.doc = Path(self.tmp) / "novel.md"
        self.doc.write_text("v3 最新", encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_restore_creates_pre_restore(self):
        """还原旧版本前,应先把当前内容做一条 auto-pre-restore。"""
        # 1. 旧版本
        create_checkpoint(
            self.doc, "v1 老版本", trigger="manual",
            root=self.root, now=1000)
        # 2. 当前是新版本
        create_checkpoint(
            self.doc, "v3 最新", trigger="manual",
            root=self.root, now=3000)
        # 3. 还原到 v1
        ok = restore_checkpoint(self.doc, 1000, root=self.root)
        self.assertTrue(ok)
        # 4. 文件应回到 v1
        self.assertEqual(self.doc.read_text(encoding="utf-8"), "v1 老版本")
        # 5. meta 里应多了 1 条 auto-pre-restore
        cps = list_checkpoints(self.doc, root=self.root)
        triggers = [c.trigger for c in cps]
        self.assertIn("auto-pre-restore", triggers)

    def test_restore_missing_returns_false(self):
        ok = restore_checkpoint(self.doc, 9999, root=self.root)
        self.assertFalse(ok)


class ShouldCreateTest(unittest.TestCase):
    """触发策略测试。"""

    def test_no_history_returns_true(self):
        tmp = tempfile.mkdtemp()
        try:
            doc = Path(tmp) / "x.md"
            doc.write_text("x", encoding="utf-8")
            self.assertTrue(should_create_checkpoint(
                doc, last_ts=None, last_chars=None,
                current_chars=1, now=1000))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_time_trigger(self):
        tmp = tempfile.mkdtemp()
        try:
            root = Path(tmp) / ".write_checkpoints"
            root.mkdir()
            doc = Path(tmp) / "x.md"
            doc.write_text("abc", encoding="utf-8")
            create_checkpoint(doc, "abc", root=root, now=1000)
            # 距 5 分钟以上
            self.assertTrue(should_create_checkpoint(
                doc, now=1000 + TRIGGER_INTERVAL_SEC + 1, root=root))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_chars_trigger(self):
        tmp = tempfile.mkdtemp()
        try:
            root = Path(tmp) / ".write_checkpoints"
            root.mkdir()
            doc = Path(tmp) / "x.md"
            doc.write_text("a", encoding="utf-8")
            create_checkpoint(doc, "a", root=root, now=1000)
            # 时间不达标但字符数变化达标
            content = "a" * (1 + TRIGGER_CHARS_DELTA)
            self.assertTrue(should_create_checkpoint(
                doc, last_ts=1000, last_chars=1,
                current_chars=len(content),
                now=1000 + 30, root=root))  # 仅 30 秒
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_no_trigger(self):
        tmp = tempfile.mkdtemp()
        try:
            root = Path(tmp) / ".write_checkpoints"
            root.mkdir()
            doc = Path(tmp) / "x.md"
            doc.write_text("abc", encoding="utf-8")
            create_checkpoint(doc, "abc", root=root, now=1000)
            # 时间未到 + 字符未变
            self.assertFalse(should_create_checkpoint(
                doc, last_ts=1000, last_chars=3,
                current_chars=3, now=1100, root=root))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class CleanupTest(unittest.TestCase):
    """容量控制:超 keep 时优先删旧非 manual。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ckpt-")
        self.root = Path(self.tmp) / ".write_checkpoints"
        self.root.mkdir(parents=True, exist_ok=True)
        self.doc = Path(self.tmp) / "x.md"
        self.doc.write_text("x", encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cleanup_keeps_manual(self):
        # 5 manual + 8 auto
        for i in range(5):
            create_checkpoint(
                self.doc, f"m{i}", trigger="manual",
                root=self.root, now=1000 + i)
        for i in range(8):
            create_checkpoint(
                self.doc, f"a{i}", trigger="auto-chars",
                root=self.root, now=2000 + i)
        # keep=6:应保留 5 manual + 1 最新 auto
        deleted = cleanup_old(self.doc, keep=6, root=self.root)
        self.assertGreater(deleted, 0)
        cps = list_checkpoints(self.doc, root=self.root)
        self.assertEqual(len(cps), 6)
        triggers = [c.trigger for c in cps]
        # 5 manual 全在
        self.assertEqual(triggers.count("manual"), 5)
        # 剩 1 个 auto
        self.assertEqual(triggers.count("auto-chars"), 1)

    def test_cleanup_noop_under_limit(self):
        for i in range(3):
            create_checkpoint(
                self.doc, f"c{i}", trigger="manual",
                root=self.root, now=1000 + i)
        deleted = cleanup_old(self.doc, keep=10, root=self.root)
        self.assertEqual(deleted, 0)


class CorruptionTest(unittest.TestCase):
    """损坏的 meta.jsonl 行不抛。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ckpt-")
        self.root = Path(self.tmp) / ".write_checkpoints"
        self.root.mkdir(parents=True, exist_ok=True)
        self.doc = Path(self.tmp) / "x.md"
        self.doc.write_text("x", encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_corrupted_lines_skipped(self):
        d = self.root / doc_id_for(self.doc)
        d.mkdir(parents=True, exist_ok=True)
        # 手写一个混合文件:1 行正常 + 1 行垃圾 + 1 行正常
        good = Checkpoint(
            ts=1000, char_count=1, char_delta=1, trigger="manual",
            size=1, sha256="a" * 64, file="1000.md")
        with open(d / "meta.jsonl", "w", encoding="utf-8") as f:
            f.write(good.to_jsonl() + "\n")
            f.write("{this is not valid json\n")
            f.write(good.to_jsonl() + "\n")
        cps = list_checkpoints(self.doc, root=self.root)
        self.assertEqual(len(cps), 2)


class StatsTest(unittest.TestCase):

    def test_stats_empty(self):
        tmp = tempfile.mkdtemp()
        try:
            doc = Path(tmp) / "x.md"
            doc.write_text("x", encoding="utf-8")
            root = Path(tmp) / ".write_checkpoints"
            root.mkdir()
            stats = checkpoint_stats(doc, root=root)
            self.assertEqual(stats["count"], 0)
            self.assertEqual(stats["last_ts"], 0)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_last_checkpoint(self):
        tmp = tempfile.mkdtemp()
        try:
            doc = Path(tmp) / "x.md"
            doc.write_text("x", encoding="utf-8")
            root = Path(tmp) / ".write_checkpoints"
            root.mkdir()
            create_checkpoint(doc, "a", root=root, now=1000)
            create_checkpoint(doc, "b", root=root, now=2000)
            last = last_checkpoint(doc, root=root)
            self.assertEqual(last.ts, 2000)
            self.assertEqual(last.char_count, 1)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class PurgeTest(unittest.TestCase):

    def test_purge_removes_all(self):
        tmp = tempfile.mkdtemp()
        try:
            doc = Path(tmp) / "x.md"
            doc.write_text("x", encoding="utf-8")
            root = Path(tmp) / ".write_checkpoints"
            root.mkdir()
            create_checkpoint(doc, "a", root=root, now=1000)
            create_checkpoint(doc, "b", root=root, now=2000)
            n = purge_document(doc, root=root)
            self.assertEqual(n, 2)
            cps = list_checkpoints(doc, root=root)
            self.assertEqual(len(cps), 0)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
