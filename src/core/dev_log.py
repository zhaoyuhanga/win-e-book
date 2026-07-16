"""开发者错误日志(Phase 重构 — 用户反馈「点发送没反应」需要可查)。

设计:
- 默认开启(所有用户都能用,不区分 dev 模式)
- 文件路径:%APPDATA%/WinEBook/dev.log
- 写入:append 模式,带时间戳 + 等级 + 消息 + 异常 traceback
- 暴露:log_info / log_warn / log_error / tail(n) / path
- 容量控制:超过 1MB 自动 rotate(留 .log.1)

不在这里做 UI。UI 在 LLM 设置弹窗里加「打开日志目录」按钮,顺手看。
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

MAX_BYTES = 1 * 1024 * 1024  # 1MB
BACKUP_NAME = "dev.log.1"


def log_path() -> Path:
    """日志文件位置。"""
    base = Path(os.environ.get("APPDATA") or Path.home())
    d = base / "WinEBook"
    d.mkdir(parents=True, exist_ok=True)
    return d / "dev.log"


def _rotate_if_needed(p: Path) -> None:
    if not p.exists():
        return
    try:
        if p.stat().st_size > MAX_BYTES:
            backup = p.with_name(BACKUP_NAME)
            if backup.exists():
                backup.unlink()
            p.rename(backup)
    except OSError:
        pass  # 不让日志本身把 app 弄崩


def _write_line(level: str, msg: str, exc: Optional[BaseException] = None) -> None:
    p = log_path()
    _rotate_if_needed(p)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    if exc is not None:
        line += "\n" + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        with open(p, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # 写不进就跳过,别把 UI 弄崩


def info(msg: str) -> None:
    _write_line("INFO", msg)


def warn(msg: str, exc: Optional[BaseException] = None) -> None:
    _write_line("WARN", msg, exc)


def error(msg: str, exc: Optional[BaseException] = None) -> None:
    _write_line("ERROR", msg, exc)


def tail(n: int = 200) -> str:
    """返回最近 n 行日志,给 UI 显示用。"""
    p = log_path()
    if not p.exists():
        return "(暂无日志)"
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except OSError as e:
        return f"(读取失败:{e})"


def clear() -> None:
    p = log_path()
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass
