"""程序入口。

支持三种运行方式(全部 OK):
  1. python -m src.main            (从项目根)
  2. python src/main.py            (直接跑脚本)
  3. WinEBook.exe                  (PyInstaller 打包后)

关键:所有 import 都用 absolute import,并通过 sys.path hack
确保 src 包在所有环境下都能解析。
"""
from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# 关键:把项目根加进 sys.path,这样 "from src.core import ..." 等 absolute import
# 在直接运行 main.py(exe 模式)时也能解析。-m 模式下 Python 会自动把 src/ 的
# 父目录加到 sys.path,所以这步是幂等无害的。
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_THIS_DIR)
for _p in (_THIS_DIR, _PARENT_DIR):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.core import Library, Storage  # noqa: E402
from src.core.storage import default_db_path  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402


def _app_data_dir() -> str:
    """跨平台数据目录:Windows 下放 %APPDATA%/WinEBook。"""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "WinEBook")
    # 开发期:用工程目录下 data/
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "data"))


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("WinEBook")
    app.setOrganizationName("WinEBook")

    data_dir = _app_data_dir()
    db_path = default_db_path(data_dir)
    storage = Storage(db_path)
    library = Library(storage)

    win = MainWindow(library)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
