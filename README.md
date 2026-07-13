# WinEBook · 墨读

> 一个轻量级 Windows 桌面电子书阅读器,本地书架 + 在线书库一站式,自动解析章节、记忆阅读位置、批量导入、按需下载。
>
> 单文件 exe,体积约 52MB,无 Python 环境也能直接运行。

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-6.6%2B-41cd52?logo=qt)](https://doc.qt.io/qtforpython-6/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078d4?logo=windows)](https://www.microsoft.com/windows)

---

## 📖 目录

- [项目简介](#项目简介)
- [核心功能](#核心功能)
- [界面预览](#界面预览)
- [技术栈](#技术栈)
- [目录结构](#目录结构)
- [快速开始](#快速开始)
- [打包为 EXE](#打包为-exe)
- [数据库设计](#数据库设计)
- [章节解析能力](#章节解析能力)
- [在线书库](#在线书库)
- [键盘快捷键](#键盘快捷键)
- [阅读主题](#阅读主题)
- [常见问题](#常见问题)
- [Roadmap](#roadmap)
- [开源协议](#开源协议)

---

## 项目简介

**WinEBook(墨读)** 是一个为 Windows 用户打造的本地电子书阅读器。它不只是一个 TXT 阅读器——你可以:

- 把你散落在硬盘各处的 `.txt`、`.epub` 一次性导入,自动按章节归类
- 关闭再打开,自动回到上次看到的章节和滚动位置
- 内置**在线书库**,粘贴一个 URL 就能从公开书站把整本小说拉下来

整个项目从零起步,坚持三个原则:**离线优先**(本地书库不依赖网络)、**单文件分发**(一个 exe 装好直接用)、**深色模式开箱即用**(墨读主题)。

---

## 核心功能

### 📚 本地书库

- 支持 **TXT / EPUB** 两种格式
- 拖拽文件夹 / 单文件导入,支持**递归扫描**(子文件夹里的书也一并扫到)
- 重复检测:同一本书的多个副本只入库一次,不会越用越乱
- 书架卡片显示:**书名 / 作者 / 进度条 / 阅读状态**(未开始 / 在读 / 已读完)

### ✂️ 自动章节解析

- TXT 支持 9 种章节标题格式自动识别(详见 [章节解析能力](#章节解析能力))
- EPUB 通过 `spine + toc` 还原目录结构,自动跳过 `nav.xhtml` 这类元数据页
- 章节标题去重:同一章在正文里出现多次只保留一个
- 智能过滤广告/作者水印行(如 "求推荐"、"PS"、"本章完" 等)
- **多编码自动识别**:GBK / GB18030 / UTF-8 三种编码试解 + 中文比例评分,告别乱码

### 💾 阅读进度记忆

- 关闭重开 → 自动回到上次章节 + 滚动位置
- 每次切章 / 滚动 / 退出,都写入 SQLite(异步,UI 不卡)
- **每本书独立进度**,不会互相串

### 🕘 历史记录

- 打开 / 切章 / 读完 都写入 `history` 表
- 主页提供"观看历史"分组,可一键回到上次看到哪

### 🌐 在线书库

- 内置源切换(默认 `00shu.la`,支持任意"笔趣阁类"站点)
- 搜索 / **粘 URL** / 在浏览器中打开 三种入口
- **整本 TXT 直链下载**:对 `00shu.la/txt/{id}/` 这种整本下载页,直接拉 4-5MB 完整 txt(详见 [在线书库](#在线书库))
- 下载进度条 + 完成后弹出文件位置

### 🎨 阅读体验

- 5 种阅读主题:**米白 / 纯白 / 薄荷 / 灰白 / 夜间**(详见 [阅读主题](#阅读主题))
- 字号 10-30 一键缩放
- **章末自动翻页**:看完一章自动跳到下一章
- 阅读区底栏:上一章 / 章节目录 / 下一章 / 进度百分比
- 顶部栏:封面缩略图 + 衬线体书名 + 章节下拉 + 字号 / 主题切换

### ⌨️ 键盘快捷键

| 快捷键 | 作用 |
|--------|------|
| `←` / `→` | 上一章 / 下一章 |
| `Ctrl + O` | 打开 / 导入文件 |
| `Ctrl + B` | 显示 / 隐藏侧栏 |
| `Ctrl + Alt + L` | 进入在线书库 |
| `Ctrl + T` | 切换阅读主题 |
| `Ctrl + =` / `Ctrl + -` | 字号放大 / 缩小 |

---

## 界面预览

> 截图待补充(本地 dev 环境跑起来后补)

- **主书架页**:墨读深色主题,卡片式书籍网格
- **阅读页**:5 种背景主题可选,顶部封面缩略 + 章节目录
- **在线书库页**:搜索 / 粘 URL / 整本下载

---

## 技术栈

本项目**完全使用开源技术**构建,无任何商业闭源组件。

### 框架与 UI

| 技术 | 用途 | 协议 |
|------|------|------|
| [Python 3.10+](https://www.python.org/) | 主语言 | PSF |
| [PySide6 6.6+](https://doc.qt.io/qtforpython-6/) | Qt6 官方 Python 绑定,GUI 框架 | LGPL 3.0 |
| Qt Stylesheet (QSS) | 主题系统(墨读深色 + 5 种阅读背景) | LGPL |

### 文本与编码

| 技术 | 用途 | 协议 |
|------|------|------|
| [ebooklib](https://github.com/aerkalov/ebooklib) | EPUB 元数据 + spine/toc 解析 | AGPL-3.0 |
| [lxml](https://lxml.de/) | 底层 HTML/XML 解析(被 ebooklib + bs4 共用) | BSD |
| [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) | 在线书站 HTML 抓取 / 解析 | MIT |
| [chardet](https://github.com/chardet/chardet) | 编码检测(备选,我们用多编码试解更准) | LGPL |

### 在线书库

| 技术 | 用途 | 协议 |
|------|------|------|
| [requests](https://requests.readthedocs.io/) | HTTP 客户端 | Apache-2.0 |
| [fake-useragent](https://github.com/fake-useragent/fake-useragent) | 随机 User-Agent(规避风控) | Apache-2.0 |

### 持久化

| 技术 | 用途 | 协议 |
|------|------|------|
| SQLite 3 (stdlib) | 书库 + 阅读历史 | Public Domain |
| [QSettings](https://doc.qt.io/qt-6/qsettings.html) (PySide6) | 窗口状态 / 阅读主题持久化 | LGPL |

### 打包与发布

| 技术 | 用途 | 协议 |
|------|------|------|
| [PyInstaller](https://pyinstaller.org/) 6.x | 打包为单文件 exe | GPL-2.0 with special bootloader exception |
| [UPX](https://upx.github.io/) 4.x | exe 压缩(可执行文件级,PyInstaller 自动调用) | GPL-2.0 |
| GitHub Releases | 版本分发 | — |

---

## 目录结构

```
win-e-book/
├── src/                              # 主代码
│   ├── __init__.py
│   ├── main.py                       # 程序入口(sys.path hack + QApplication)
│   ├── core/                         # 业务核心(无 UI 依赖)
│   │   ├── __init__.py
│   │   ├── parser.py                 # TXT/EPUB 章节解析(9 种格式 + 编码探测)
│   │   ├── storage.py                # SQLite 持久化(books + history 表)
│   │   ├── library.py                # 库门面(Facade) — 调 storage + parser
│   │   └── online.py                 # 在线书源 + 00shu 整本下载
│   └── ui/                           # UI 层(PySide6)
│       ├── __init__.py
│       ├── theme.py                  # 墨读 QSS + 5 种阅读主题
│       ├── main_window.py            # 主窗口 + QStackedWidget(书架/阅读/在线)
│       ├── library_view.py           # 书架页(BookCard 卡片网格)
│       ├── reader_view.py            # 阅读页(QTextBrowser + 主题切换)
│       └── online_view.py            # 在线书库页(搜索/粘 URL/下载)
├── tests/                            # 单元测试
│   ├── test_parser.py                # 14 个 case,含 4 本真实小说回归
│   └── smoke_e2e.py                  # 端到端冒烟测试
├── data/                             # 开发期数据目录(运行时自动创建)
├── dist/                             # PyInstaller 打包产物(已包含在仓库)
│   └── WinEBook.exe                  # 52MB 单文件,双击即用
├── build/                            # PyInstaller 临时构建目录(.gitignore)
├── .venv/                            # Python 虚拟环境(.gitignore)
├── win-e-book.spec                   # PyInstaller 打包配置
├── requirements.txt                  # 第三方依赖
├── .gitignore
├── README.md
└── LICENSE
```

---

## 快速开始

### 环境要求

- **Windows 10 / 11**(主要目标平台)
- **Python 3.10+**(开发需要;终端用户可直接用打包好的 exe)
- 约 **300MB** 磁盘空间(venv + 源码 + 打包产物)

### 1. 克隆仓库

```bash
git clone https://github.com/zhaoyuhanga/win-e-book.git
cd win-e-book
```

### 2. 创建虚拟环境

**Windows (PowerShell)**:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 运行

有三种方式启动:

```bash
# 方式一(推荐):模块运行,absolute import 自动解析
python -m src.main

# 方式二:直接跑脚本(main.py 内部有 sys.path hack)
python src/main.py

# 方式三(终端用户):直接双击打包好的 exe
.\dist\WinEBook.exe
```

> 💡 第一次启动会自动在 `%APPDATA%\WinEBook\` 下创建数据目录和 SQLite 数据库。

### 5. 运行测试

```bash
python -m pytest tests/ -v
```

---

## 打包为 EXE

整个项目打包成**单个 52MB 的 exe** 即可分发,无需任何运行时依赖。

### 准备工作

```bash
pip install pyinstaller
# (可选)UPX 4.x:https://github.com/upx/upx/releases
#  下载 upx.exe 放到 PATH 即可,PyInstaller 会自动调用
```

### 一键打包

```bash
pyinstaller win-e-book.spec --noconfirm --clean
```

产物在 `dist/WinEBook.exe`。

### spec 配置要点

`win-e-book.spec` 里的关键决策:

| 配置项 | 取值 | 说明 |
|--------|------|------|
| `pathex` | `[PROJECT_ROOT]` | **必须**:让 PyInstaller 把 `src` 识别为 regular package,否则 `from src.core import ...` 会失败 |
| `hiddenimports` | `src.*` 显式列出 | 保险起见把 core / ui 全部子模块列出来,防止遗漏 |
| `excludes` | 大量 `PySide6.Qt3D*` / `QtMultimedia` / `QtWebEngine*` 等 | **关键的体积优化**:PySide6 全家桶几百 MB,我们用 `excludes` 砍掉用不到的 Qt 模块 |
| `console` | `False` | GUI 程序,不弹黑窗 |
| `upx` | `True` | 调用 UPX 压缩,进一步减小 exe 体积 |
| `icon` | 留空(填 `.ico` 路径可换图标) | — |

### 体积优化对照

| 步骤 | 大小 |
|------|------|
| 原始 `Analysis` 后未压缩 | ~250MB |
| 启用 excludes 砍掉不用的 Qt 模块 | ~120MB |
| 启用 UPX 压缩 | **~52MB** |

### 常见打包问题

| 问题 | 解决 |
|------|------|
| 启动报 `ImportError: cannot import name 'X' from 'src.core'` | 确认 `pathex` 包含项目根,`hiddenimports` 里有 `src.core.X` |
| 启动报 `ModuleNotFoundError: No module named 'ebooklib'` | `hiddenimports` 加上 `'ebooklib'` 和子模块 |
| exe 闪退 | 把 `console=True` 临时打开看 stack trace;常见是 `lxml` 没打进 PYZ |
| exe 体积 > 100MB | `excludes` 没加 `PySide6.Qt3D*` / `QtWebEngine*` 等大块 |
| 杀毒软件报毒 | PyInstaller 的 bootloader 偶尔被误报,可加数字签名或换分发渠道 |

---

## 数据库设计

使用 SQLite,存放在 `%APPDATA%\WinEBook\library.db`(开发期为 `./data/library.db`)。

### 表:`books`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `title` | TEXT | 书名 |
| `author` | TEXT | 作者 |
| `path` | TEXT UNIQUE | 文件绝对路径(用于去重) |
| `format` | TEXT | `txt` / `epub` |
| `size_bytes` | INTEGER | 文件大小 |
| `cover_data` | BLOB | 封面缩略图(可选) |
| `added_at` | INTEGER | 入库时间(unix timestamp) |
| `last_read_at` | INTEGER | 最后阅读时间 |
| `current_chapter` | INTEGER | 当前章节下标 |
| `scroll_pos` | REAL | 滚动位置 0-1 |
| `total_chapters` | INTEGER | 总章节数 |
| `is_finished` | INTEGER 0/1 | 是否读完 |

### 表:`history`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `book_id` | INTEGER FK | 关联 books.id |
| `chapter` | INTEGER | 章节下标 |
| `chapter_title` | TEXT | 章节标题 |
| `opened_at` | INTEGER | 打开时间 |

### 索引

- `books.path`(UNIQUE 自动建索引)
- `history.book_id`(便于按书查历史)
- `history.opened_at DESC`(便于"最近阅读"排序)

### 线程安全

`Storage` 类内部用 `threading.RLock` 保护所有写操作,QThread 后台任务和主线程可以同时调,不会写坏数据库。

---

## 章节解析能力

### TXT 支持的章节标题格式

| 类型 | 示例 |
|------|------|
| `===...===` / `***...***` 包围 | `=== 第一章 楔子 ===` |
| 中文方括号 | `【第一章 楔子】` |
| `正文 第N章` | `正文 第一章 楔子` |
| 裸 `第N章` | `第一章 楔子` |
| `回/节/卷/篇/部/集/话` 变体 | `第一回`、`第三卷`、`第十五话` |
| 特殊章节名 | `楔子`、`序章`、`终章`、`番外` |
| 英文 `Chapter N` | `Chapter 1` |
| 嵌套卷标 | `卷一 第一章` |
| 兜底 | 大段空行 / 长分隔线 / 固定字符数 |

### 自动过滤的 JUNK 行

- 模板广告:`求推荐`、`请收藏`、`天才一秒记住`、`首发网址`
- 章节标记:`本章完`、`本章未完`
- 元数据:`PS`、`P.S.`

### EPUB 解析

- 通过 `spine`(spine 顺序)拿章节
- 通过 `toc`(目录)拿标题
- 自动跳过 `nav.xhtml`、`cover.xhtml` 这类元数据
- 保留内联样式(部分 EPUB 的字体颜色),但用我们的主题色覆盖背景

---

## 在线书库

### 工作原理

很多笔趣阁类小说站用 **JavaScript 渲染**,直接 `requests` 抓只能拿到空 HTML 壳。所以我们走两条路:

1. **搜索 + 粘 URL**:在浏览器里打开站点 → 找到想下的书 → 复制 URL → 粘到在线书库页
2. **整本 TXT 直链**(针对 `00shu.la` 这类站):`/txt/{id}/` 是整本下载页,直链 `https://down.00shu.la/modules/article/txtarticle.php?id={id}` 直接返回 4-5MB 的完整 txt

### 00shu 整本下载流程

```
用户粘 URL:  https://www.00shu.la/txt/53054/
        ↓
正则匹配:    /txt/{id}/ 模式
        ↓
GET 一次首页:  拿到 <h1> 书名 + meta description
        ↓
构造直链:    https://down.00shu.la/modules/article/txtarticle.php?id=53054
        ↓
stream 下载:  64KB/chunk, 进度条实时刷新
        ↓
保存到:      %USERPROFILE%/Downloads/WinEBook/吞噬星空2起源大陆.txt
        ↓
一键导入:    弹"是否立即导入书库"对话框
```

### 性能参考(实测)

- 网络 10Mbps:4-5MB 全本约 **20-30 秒**下完
- 网络 100Mbps:约 **5-10 秒**
- API 探测(`api.github.com`)稳定 0.5-1s 响应

### 切换书源

UI 顶部"书源"下拉框,默认 `00shu.la`。改成别的笔趣阁类站点也可以,只是目录页结构未必能解析,搜索结果可能为空——建议用"粘 URL" 入口。

### 风控与礼貌

- `fake-useragent` 提供随机 User-Agent
- `Accept-Language: zh-CN` 模拟中文浏览器
- 下载章节时 `min_delay_sec=0.05` 礼貌 delay(可在源码里调)

---

## 阅读主题

5 种背景主题,通过 `Ctrl+T` 快速切换,选择持久化到 `QSettings`:

| 主题 | 背景色 | 文字色 | 适用场景 |
|------|--------|--------|----------|
| **米白(默认)** | `#f7f1e3` | `#3a342a` | 长时间阅读,护眼 |
| **纯白** | `#ffffff` | `#222222` | 高对比,白天 |
| **薄荷** | `#e8f1ec` | `#1f3a32` | 清爽,适合夏天 |
| **灰白** | `#e8e6e1` | `#2d2d2d` | 中性,商务感 |
| **夜间** | `#1a1a1a` | `#c8c8c8` | 深夜阅读,护眼最强 |

### 主界面主题

主书架 / 在线书库 / 阅读页顶部固定走**墨读深色主题**:深蓝黑底 + 暖橙 `#c8946e` 高亮,与阅读区背景互不冲突。

### QSS 主题切换的小坑

PySide6 父子 QSS 级联在子 widget `setStyleSheet` 后**会失效**(全局 QSS 不会渗透到子 widget),所以阅读主题必须在 `ReaderView` 内联 `setStyleSheet`,而不是改全局。

---

## 常见问题

### Q: 启动后白屏 / 闪退?

A: 90% 是 PySide6 版本不匹配。运行 `pip show PySide6` 确认 ≥ 6.6。如果是从源码运行,试 `pip install -r requirements.txt --upgrade`。

### Q: 导入 TXT 后章节全是空的?

A: 检查文件编码。如果是 UTF-16 / 罕见编码,`parser.py` 里的多编码试解会兜底,但极端情况可能识别失败。可以先在记事本另存为 UTF-8 再导入。

### Q: 在线书库搜索结果为空?

A: 笔趣阁类站点搜索页是 JS 渲染,`requests` 拿不到结果。**用"粘 URL"入口**:浏览器打开站点 → 找到书 → 复制 URL → 粘进来。

### Q: 打包后 exe 报"无法启动此程序"?

A: VC++ Redistributable 没装。Windows 10 1803+ 自带,Win 7/8 需要装 [VC++ 2015-2022 Redist](https://aka.ms/vs/17/release/vc_redist.x64.exe)。

### Q: 数据库存在哪?怎么备份?

A: `%APPDATA%\WinEBook\library.db`。整个 `WinEBook` 文件夹备份即可,包含数据库 + 设置 + 导入历史。

### Q: 能加 xxx 功能吗?

A: 看 [Roadmap](#roadmap)。其他需求可以提 Issue。

---

## Roadmap

### v0.10(下一版)

- [ ] 书签 / 阅读笔记(每本书独立)
- [ ] 全文搜索(在书库内搜书名 / 章节内容)
- [ ] 字体选择(目前用系统默认衬线)
- [ ] 阅读统计(每日阅读时长 / 字数 / 章节数)
- [ ] 多选删除 / 批量移动到分组

### v0.11+

- [ ] 暗色模式阅读区(已有"夜间"主题,继续打磨)
- [ ] 多书源并发搜索
- [ ] OPDS 远程书库订阅
- [ ] 翻译(英文 / 日文电子书)
- [ ] 云同步(可选,自托管服务器)

### 长期

- [ ] macOS / Linux 支持(理论 PySide6 跨平台,需要适配打包)
- [ ] 插件机制(用户自定义章节识别 / 书源)
- [ ] TTS 朗读(用 Qt TTS 框架)

---

## 开源协议

本项目基于 **MIT License** 开源,详见 [LICENSE](LICENSE)。

第三方依赖各自的协议见 [技术栈](#技术栈) 表格。商业闭源分发前请确认:
- **PySide6**:LGPL 3.0 — 动态链接 OK,改源码需要开源
- **ebooklib**:AGPL-3.0 — 网络分发需开源(本项目是桌面应用,无此问题)
- **lxml**:BSD — 无限制
- **bs4**:MIT — 无限制
- **chardet**:LGPL — 动态链接 OK
- **PyInstaller**:GPL-2.0 with bootloader exception — 仅打包工具,不影响最终 exe

---

## 致谢

- [Qt Project](https://www.qt.io/) — 跨平台 GUI 框架,PySide6 绑定
- [ebooklib](https://github.com/aerkalov/ebooklib) — EPUB 解析
- [00shu.la](https://www.00shu.la/) — 整本 TXT 来源
- 所有贡献者

---

**Made with ❤️ by zhaoyuhanga**
