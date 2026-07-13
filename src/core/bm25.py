"""BM25 工作区检索(PRD §10)。

实现要点:
- 中文分词:1-gram 中文 + 2-gram 中文 + 英文/数字单词(不依赖 jieba)
- 索引:{term: {doc_id: tf}} + 元数据
- 缓存:30s TTL,按工作区分片
- 限制:最多 160 文件,每文件 600KB,720 chunks
"""
from __future__ import annotations

import math
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ============================================================
# 中文分词(简化版)
# ============================================================

# 停用词:常见虚词/标点(注意:不要包含"我/你/他"等人称代词,会影响 BM25 命中)
_STOPWORDS = set(
    "的 了 是 在 有 和 就 不 都 一 一个 上 也 很 到 说 要 去 会 着 "
    "没有 看 好 自己 这 那 但 与 或 之 为 于 而 及 以 把 被 让 给 向 从".split()
)
_PUNCT = set("，。、！？：；…—·《》「」（）()【】[]\n\r\t\"'`")

# 中文 Unicode 范围
_CJK = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> List[str]:
    """中文 1-gram + 2-gram + 英文/数字单词。

    步骤:
    1. 提取连续中文 → 1-gram + 2-gram
    2. 提取连续英文/数字 → 单词
    3. 过滤停用词 / 标点
    """
    tokens: List[str] = []
    # 1) 中文 N-gram
    cjk_runs = re.findall(r"[\u4e00-\u9fff]+", text)
    for run in cjk_runs:
        # 1-gram
        for ch in run:
            if ch in _STOPWORDS or ch in _PUNCT:
                continue
            tokens.append(ch)
        # 2-gram(只在 run 长度 >= 2 时)
        if len(run) >= 2:
            for i in range(len(run) - 1):
                bg = run[i:i+2]
                if bg in _STOPWORDS or any(c in _PUNCT for c in bg):
                    continue
                tokens.append(bg)
    # 2) 英文/数字单词
    en_runs = re.findall(r"[A-Za-z0-9]+", text)
    for w in en_runs:
        w_lower = w.lower()
        if w_lower in _STOPWORDS:
            continue
        if len(w_lower) < 2:
            continue
        tokens.append(w_lower)
    return tokens


# ============================================================
# 工作区扫描 + 分块
# ============================================================

# 限制
MAX_FILES = 160
MAX_FILE_SIZE = 600 * 1024  # 600KB
MAX_CHUNKS = 720
CHUNK_SIZE = 900
MIN_CHUNK_SIZE = 48

# 跳过的目录/文件
SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", "vendor", "venv", ".venv",
    "__pycache__", ".idea", ".vscode", ".next", "target", ".cache",
    "$RECYCLE.BIN", "System Volume Information",
}
SKIP_EXT = {
    ".pyc", ".so", ".dll", ".exe", ".bin", ".jpg", ".jpeg", ".png",
    ".gif", ".webp", ".mp4", ".webm", ".mov", ".mp3", ".wav",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".pdf",
}


@dataclass
class Chunk:
    """分块:含 doc_id, doc_path, content, start_offset。"""
    doc_id: int
    doc_path: str
    content: str
    start: int


@dataclass
class SearchHit:
    """检索命中:含 doc_path, content, score。"""
    doc_path: str
    content: str
    score: float
    chunk_start: int = 0


def _read_text(path: Path) -> Optional[str]:
    """读文件,GBK/UTF-8 容错。"""
    try:
        size = path.stat().st_size
        if size > MAX_FILE_SIZE:
            with path.open("rb") as f:
                data = f.read(MAX_FILE_SIZE)
        else:
            with path.open("rb") as f:
                data = f.read()
    except OSError:
        return None
    # 编码探测
    for enc in ("utf-8", "utf-8-sig", "gbk", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _chunk_text(text: str) -> List[Tuple[int, str]]:
    """按 900 字符分块,保留 start_offset。"""
    chunks: List[Tuple[int, str]] = []
    n = len(text)
    if n == 0:
        return chunks
    # 按段落切(空行)
    paragraphs: List[Tuple[int, str]] = []
    cur_start = 0
    for m in re.finditer(r"\n\s*\n", text):
        end = m.start()
        para = text[cur_start:end]
        if para.strip():
            paragraphs.append((cur_start, para))
        cur_start = m.end()
    if cur_start < n:
        rest = text[cur_start:]
        if rest.strip():
            paragraphs.append((cur_start, rest))
    # 合并/拆分
    buf_start = 0
    buf: List[str] = []
    for p_start, p in paragraphs:
        if len("".join(buf)) + len(p) > CHUNK_SIZE and buf:
            content = "\n\n".join(buf).strip()
            if len(content) >= MIN_CHUNK_SIZE:
                chunks.append((buf_start, content))
            buf = [p]
            buf_start = p_start
        else:
            if not buf:
                buf_start = p_start
            buf.append(p)
    if buf:
        content = "\n\n".join(buf).strip()
        if len(content) >= MIN_CHUNK_SIZE:
            chunks.append((buf_start, content))
    return chunks


def scan_workspace(root: Path) -> List[Chunk]:
    """扫描工作区,返回 chunk 列表。"""
    root = Path(root)
    if not root.exists():
        return []
    chunks: List[Chunk] = []
    doc_id = 0
    files_seen = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_EXT:
            continue
        if files_seen >= MAX_FILES:
            break
        files_seen += 1
        text = _read_text(path)
        if text is None or not text.strip():
            continue
        for start, content in _chunk_text(text):
            chunks.append(Chunk(
                doc_id=doc_id,
                doc_path=str(path),
                content=content,
                start=start,
            ))
            doc_id += 1
            if len(chunks) >= MAX_CHUNKS:
                return chunks
    return chunks


# ============================================================
# BM25 索引
# ============================================================

@dataclass
class BM25Index:
    """倒排索引 + BM25 评分。

    fields:
        tf: {term: {doc_id: tf}}
        df: {term: doc_freq}
        doc_lens: {doc_id: token_count}
        avgdl: float
        n_docs: int
        chunks: [Chunk]  (按 doc_id 索引)
    """
    tf: Dict[str, Dict[int, int]] = field(default_factory=dict)
    df: Dict[str, int] = field(default_factory=dict)
    doc_lens: Dict[int, int] = field(default_factory=dict)
    avgdl: float = 0.0
    n_docs: int = 0
    chunks: List[Chunk] = field(default_factory=list)

    @classmethod
    def build(cls, chunks: List[Chunk]) -> "BM25Index":
        idx = cls()
        idx.chunks = chunks
        idx.n_docs = len(chunks)
        if not chunks:
            return idx
        total_len = 0
        for ch in chunks:
            tokens = tokenize(ch.content)
            tf_dict = Counter(tokens)
            idx.doc_lens[ch.doc_id] = len(tokens)
            total_len += len(tokens)
            for term, cnt in tf_dict.items():
                idx.tf.setdefault(term, {})[ch.doc_id] = cnt
                idx.df[term] = idx.df.get(term, 0) + 1
        idx.avgdl = total_len / max(1, idx.n_docs)
        return idx

    def search(self, query: str, k: int = 3, snippet_chars: int = 520) -> List[SearchHit]:
        """BM25 检索。返回 top-K SearchHit。"""
        if self.n_docs == 0 or not query.strip():
            return []
        k1 = 1.2
        b = 0.75
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        scores: Dict[int, float] = {}
        for term in set(q_tokens):
            if term not in self.tf:
                continue
            postings = self.tf[term]
            df = self.df[term]
            idf = max(0.01, math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1.0))
            for doc_id, tf in postings.items():
                doc_len = self.doc_lens[doc_id]
                norm = 1 - b + b * doc_len / max(1.0, self.avgdl)
                s = idf * (tf * (k1 + 1)) / (tf + k1 * norm)
                scores[doc_id] = scores.get(doc_id, 0.0) + s
        # 排序
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:k]
        hits: List[SearchHit] = []
        for doc_id, score in ranked:
            ch = self.chunks[doc_id]
            content = ch.content
            if len(content) > snippet_chars:
                content = content[:snippet_chars] + "…"
            hits.append(SearchHit(
                doc_path=ch.doc_path,
                content=content,
                score=score,
                chunk_start=ch.start,
            ))
        return hits


# ============================================================
# 工作区分片缓存
# ============================================================

_CACHE: Dict[str, Tuple[float, BM25Index]] = {}
_CACHE_TTL = 30.0  # 秒


def get_index(workspace_root: Path, *, force: bool = False) -> BM25Index:
    """获取工作区索引(带 30s TTL 缓存)。"""
    key = str(Path(workspace_root).resolve())
    now = time.time()
    if not force and key in _CACHE:
        ts, idx = _CACHE[key]
        if now - ts < _CACHE_TTL:
            return idx
    # 重建
    chunks = scan_workspace(Path(workspace_root))
    idx = BM25Index.build(chunks)
    _CACHE[key] = (now, idx)
    return idx


def invalidate_cache(workspace_root: Optional[Path] = None) -> None:
    """清缓存。None = 清全部。"""
    global _CACHE
    if workspace_root is None:
        _CACHE = {}
    else:
        key = str(Path(workspace_root).resolve())
        _CACHE.pop(key, None)


def search_workspace(
    workspace_root: Path,
    query: str,
    k: int = 3,
    snippet_chars: int = 520,
) -> List[SearchHit]:
    """便捷接口:检索工作区(自动管理缓存)。"""
    idx = get_index(workspace_root)
    return idx.search(query, k=k, snippet_chars=snippet_chars)


# ============================================================
# 格式化(给 LLM 看的 snippet 文本)
# ============================================================

def format_hits_for_prompt(hits: List[SearchHit], max_total_chars: int = 2000) -> str:
    """把检索命中格式化成 LLM 友好的 snippet 文本。"""
    if not hits:
        return ""
    parts: List[str] = []
    total = 0
    for i, h in enumerate(hits, 1):
        from pathlib import Path
        rel = h.doc_path
        # 简化路径
        try:
            rel = str(Path(h.doc_path).relative_to(Path(h.doc_path).parents[len(Path(h.doc_path).parts) - 2]))
        except (ValueError, IndexError):
            pass
        block = f"[相关片段 {i}] (来自: {rel}, score={h.score:.2f})\n{h.content}"
        if total + len(block) > max_total_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n---\n\n".join(parts)
