"""墨写文档 Checkpoint 引擎(Phase 3b)。

不做真正的 git 集成,自己写轻量 snapshot 引擎:
- 每个文档独立目录:.write_checkpoints/<doc_id>/
- 一条 checkpoint = 一份完整 .md 副本 + meta.jsonl 的一行
- 触发策略:每 5 分钟 / 累积 ≥200 字符变化 / 手动
- 容量控制:每文件最多 50 条,超限自动删除最旧的非手动
- 用途:写作过程中误删/写错可一键回到 5min 前的版本

设计原则:
- 纯 stdlib(不引 git/dulwich/pygit2),不增加依赖
- 原子写:先写 .tmp 再 rename,避免半截文件
- meta.jsonl 是 append-only,删除通过重写整个文件
- 内容去重:如果新内容和最近一条完全一致(按 hash)就跳过
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List


# ============================================================
# 配置
# ============================================================

# 每隔多少字符变化触发一次(默认 200)
TRIGGER_CHARS_DELTA = 200

# 每隔多少秒触发一次(默认 300 = 5 分钟)
TRIGGER_INTERVAL_SEC = 300

# 每文件最多保留多少条(默认 50)
MAX_CHECKPOINTS_PER_FILE = 50

# meta.jsonl 单行最大长度(防止某条异常)
META_LINE_MAX = 4096


# ============================================================
# 数据类
# ============================================================

@dataclass
class Checkpoint:
    """一条 checkpoint 记录(对应一个时间点的快照)。"""
    ts: int                  # unix 时间戳(秒)
    char_count: int          # 文档字符数
    char_delta: int          # 距上一条的变化字符数(+/-)
    trigger: str             # "auto-time" / "auto-chars" / "manual"
    size: int                # 文件大小(字节)
    sha256: str              # 内容 sha256(去重用)
    note: str = ""           # 手动 checkpoint 的备注(可空)
    file: str = ""           # checkpoint 文件名(相对 doc_id 目录)

    def to_jsonl(self) -> str:
        """序列化为 meta.jsonl 一行。"""
        d = asdict(self)
        # file 可能很长,保留用于 UI 跳转
        line = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
        if len(line) > META_LINE_MAX:
            raise ValueError(f"meta 行超长: {len(line)} > {META_LINE_MAX}")
        return line

    @classmethod
    def from_jsonl(cls, line: str) -> "Checkpoint":
        d = json.loads(line)
        return cls(**d)

    def display_time(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.ts))

    def short_hash(self) -> str:
        return self.sha256[:8]


# ============================================================
# 路径工具
# ============================================================

def default_checkpoint_root(workspace: Optional[Path] = None) -> Path:
    """Checkpoint 根目录:<workspace>/.write_checkpoints/。

    workspace 不传时用 ~/Documents/墨写
    """
    if workspace is None:
        workspace = Path(os.path.expanduser("~/Documents/墨写"))
    root = workspace / ".write_checkpoints"
    root.mkdir(parents=True, exist_ok=True)
    return root


def doc_id_for(file_path: str | Path) -> str:
    """文档 ID:用文件绝对路径的 sha256 前 16 位(短而唯一)。"""
    p = Path(file_path).resolve()
    h = hashlib.sha256(str(p).encode("utf-8")).hexdigest()[:16]
    return h


def doc_dir(root: Path, file_path: str | Path) -> Path:
    """某文档的 checkpoint 目录:<root>/<doc_id>/。"""
    d = root / doc_id_for(file_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def checkpoint_filename(ts: int) -> str:
    """checkpoint 内容文件名:<ts>.md。"""
    return f"{ts}.md"


# ============================================================
# 核心操作
# ============================================================

def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()


def _meta_path(doc_dir_path: Path) -> Path:
    return doc_dir_path / "meta.jsonl"


def _append_meta(doc_dir_path: Path, cp: Checkpoint) -> None:
    """原子追加一行到 meta.jsonl。"""
    p = _meta_path(doc_dir_path)
    line = cp.to_jsonl() + "\n"
    with open(p, "a", encoding="utf-8") as f:
        f.write(line)


def _read_meta(doc_dir_path: Path) -> List[Checkpoint]:
    """读所有 checkpoint 元数据。文件不存在 → []。"""
    p = _meta_path(doc_dir_path)
    if not p.exists():
        return []
    out: List[Checkpoint] = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Checkpoint.from_jsonl(line))
            except (json.JSONDecodeError, TypeError, ValueError):
                # 跳过损坏行,不抛
                continue
    return out


def _write_meta_atomic(doc_dir_path: Path, cps: List[Checkpoint]) -> None:
    """原子重写整个 meta.jsonl(用于删除 checkpoint)。"""
    p = _meta_path(doc_dir_path)
    # 写临时文件再 rename
    fd, tmp = tempfile.mkstemp(prefix="meta-", suffix=".jsonl.tmp", dir=doc_dir_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for cp in cps:
                f.write(cp.to_jsonl() + "\n")
        os.replace(tmp, p)
    except Exception:
        # 清理临时文件
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _atomic_write(path: Path, content: str) -> None:
    """原子写文件:先写 .tmp 再 rename。"""
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + "-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ============================================================
# 公开 API
# ============================================================

def should_create_checkpoint(
    file_path: str | Path,
    last_ts: Optional[int] = None,
    last_chars: Optional[int] = None,
    current_chars: Optional[int] = None,
    now: Optional[int] = None,
    root: Optional[Path] = None,
) -> bool:
    """根据触发策略决定是否应创建 checkpoint。

    规则:
    1. 距上次 ≥ TRIGGER_INTERVAL_SEC 秒 → 触发
    2. 字符变化 ≥ TRIGGER_CHARS_DELTA → 触发
    3. 没有任何历史 → 立即触发(给个起点)
    """
    if now is None:
        now = int(time.time())
    cps = list_checkpoints(file_path, root=root)
    if not cps:
        return True
    last = cps[-1]
    if last_ts is None:
        last_ts = last.ts
    if last_chars is None:
        last_chars = last.char_count
    if current_chars is None:
        # 没传就当没变化,只根据时间触发
        current_chars = last_chars
    # 时间触发
    if now - last_ts >= TRIGGER_INTERVAL_SEC:
        return True
    # 字符触发
    if abs(current_chars - last_chars) >= TRIGGER_CHARS_DELTA:
        return True
    return False


def create_checkpoint(
    file_path: str | Path,
    content: str,
    trigger: str = "auto-chars",
    note: str = "",
    root: Optional[Path] = None,
    now: Optional[int] = None,
    dedupe: bool = True,
) -> Optional[Checkpoint]:
    """创建一条 checkpoint。返回 None 表示被去重跳过。"""
    if root is None:
        root = default_checkpoint_root()
    if now is None:
        now = int(time.time())
    d = doc_dir(root, file_path)
    h = _content_hash(content)
    # 总是读一份 meta(给 dedupe + delta 用)
    existing = _read_meta(d)
    # 去重:与最近一条 hash 相同就跳过
    if dedupe and existing and existing[-1].sha256 == h:
        return None
    # 写内容
    fname = checkpoint_filename(now)
    cp_path = d / fname
    _atomic_write(cp_path, content)
    # 计算 delta
    prev_count = existing[-1].char_count if existing else 0
    # 构造元数据
    cp = Checkpoint(
        ts=now,
        char_count=len(content),
        char_delta=len(content) - prev_count,
        trigger=trigger,
        size=len(content.encode("utf-8", errors="replace")),
        sha256=h,
        note=note,
        file=fname,
    )
    _append_meta(d, cp)
    # 容量控制
    cleanup_old(file_path, keep=MAX_CHECKPOINTS_PER_FILE, root=root)
    return cp


def list_checkpoints(
    file_path: str | Path,
    root: Optional[Path] = None,
) -> List[Checkpoint]:
    """列出该文件的所有 checkpoint(按时间升序)。"""
    if root is None:
        root = default_checkpoint_root()
    d = doc_dir(root, file_path)
    return _read_meta(d)


def load_checkpoint_content(
    file_path: str | Path,
    ts: int,
    root: Optional[Path] = None,
) -> Optional[str]:
    """加载某条 checkpoint 的内容(不存在 → None)。"""
    if root is None:
        root = default_checkpoint_root()
    d = doc_dir(root, file_path)
    p = d / checkpoint_filename(ts)
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="utf-8", errors="replace")


def restore_checkpoint(
    file_path: str | Path,
    ts: int,
    root: Optional[Path] = None,
) -> bool:
    """把 checkpoint 内容写回原文件。返回是否成功。

    副作用:会先给原文件当前内容做一条 "auto-pre-restore" checkpoint,
    避免还原后无法找回最新的内容。
    """
    if root is None:
        root = default_checkpoint_root()
    p = Path(file_path)
    content = load_checkpoint_content(file_path, ts, root=root)
    if content is None:
        return False
    # 先把当前内容做一条 auto checkpoint(dedupe=False, 强制写一条用于找回)
    if p.exists():
        try:
            current = p.read_text(encoding="utf-8")
            create_checkpoint(
                file_path, current, trigger="auto-pre-restore",
                note=f"还原到 {ts} 前自动保存", root=root,
                dedupe=False,
            )
        except Exception:
            pass
    # 写回
    _atomic_write(p, content)
    return True


def delete_checkpoint(
    file_path: str | Path,
    ts: int,
    root: Optional[Path] = None,
) -> bool:
    """删除单条 checkpoint(meta + 文件)。"""
    if root is None:
        root = default_checkpoint_root()
    d = doc_dir(root, file_path)
    p = d / checkpoint_filename(ts)
    # 删内容
    if p.exists():
        p.unlink()
    # 重写 meta
    cps = _read_meta(d)
    new = [c for c in cps if c.ts != ts]
    if len(new) == len(cps):
        return False
    _write_meta_atomic(d, new)
    return True


def cleanup_old(
    file_path: str | Path,
    keep: int = MAX_CHECKPOINTS_PER_FILE,
    root: Optional[Path] = None,
) -> int:
    """超过 keep 条时,删除最旧的非 manual checkpoint。

    返回删除的数量。
    """
    if root is None:
        root = default_checkpoint_root()
    d = doc_dir(root, file_path)
    cps = _read_meta(d)
    if len(cps) <= keep:
        return 0
    # 先找出要保留的(优先 manual,然后按时间倒序取 keep 条)
    manual_idx = [i for i, c in enumerate(cps) if c.trigger == "manual"]
    other_idx = [i for i, c in enumerate(cps) if c.trigger != "manual"]
    # 保留:所有 manual + 最新的 (keep - len(manual)) 条 other
    keep_other = max(0, keep - len(manual_idx))
    keep_other_idx = set(other_idx[-keep_other:])  # 取末尾(最新)
    keep_set = set(manual_idx) | keep_other_idx
    to_delete = [i for i in range(len(cps)) if i not in keep_set]
    # 从后往前删(避免 meta 重写时 index 错位)
    for i in sorted(to_delete, reverse=True):
        cp = cps[i]
        p = d / cp.file
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    # 重写 meta
    new = [c for i, c in enumerate(cps) if i in keep_set]
    _write_meta_atomic(d, new)
    return len(to_delete)


def last_checkpoint(
    file_path: str | Path,
    root: Optional[Path] = None,
) -> Optional[Checkpoint]:
    """最近一条 checkpoint,无则 None。"""
    cps = list_checkpoints(file_path, root=root)
    return cps[-1] if cps else None


def checkpoint_stats(
    file_path: str | Path,
    root: Optional[Path] = None,
) -> dict:
    """统计信息,给 UI 状态栏用。"""
    cps = list_checkpoints(file_path, root=root)
    if not cps:
        return {"count": 0, "last_ts": 0, "total_size": 0}
    total = sum(c.size for c in cps)
    return {
        "count": len(cps),
        "last_ts": cps[-1].ts,
        "total_size": total,
    }


# ============================================================
# 清理辅助
# ============================================================

def purge_document(
    file_path: str | Path,
    root: Optional[Path] = None,
) -> int:
    """删除一个文件的所有 checkpoint(慎重使用)。返回删除条数。"""
    if root is None:
        root = default_checkpoint_root()
    d = doc_dir(root, file_path)
    if not d.exists():
        return 0
    cps = _read_meta(d)
    cnt = len(cps)
    try:
        shutil.rmtree(d)
    except OSError:
        pass
    return cnt
