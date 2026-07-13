# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置:win-e-book.spec

打包命令:
    pip install pyinstaller
    pyinstaller win-e-book.spec
"""
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# 把项目根加进 pathex,这样 PyInstaller 会把 `src` 识别为 regular package
PROJECT_ROOT = 'D:\\awork\\win-e-book'

a = Analysis(
    ['src/main.py'],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[
        # 强制把 src 包及其子模块打进 PYZ(PyInstaller 6 通常会自动抓,这里保险)
        'src',
        'src.main',
        'src.core',
        'src.core.parser',
        'src.core.storage',
        'src.core.library',
        'src.core.online',
        'src.core.llm',
        'src.core.write_agent',
        'src.core.bm25',
        'src.ui',
        'src.ui.main_window',
        'src.ui.library_view',
        'src.ui.reader_view',
        'src.ui.online_view',
        'src.ui.home_view',
        'src.ui.write_view',
        'src.ui.llm_settings_dialog',
        'src.ui.markdown_highlighter',
        'src.ui.theme',
        # 第三方依赖
        'ebooklib',
        'ebooklib.epub',
        'lxml',
        'lxml._elementpath',
        'lxml.etree',
        'bs4',
        'chardet',
        'fake_useragent',
        'requests',
        'urllib3',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'PySide6.Qt3DAnimation',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DExtras',
        'PySide6.QtBluetooth',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtNetwork',
        'PySide6.QtPositioning',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtSql',
        'PySide6.QtTest',
        'PySide6.QtWebChannel',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebSockets',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WinEBook',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # GUI 程序
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,               # 有 .ico 后填: 'assets/app.ico'
)
