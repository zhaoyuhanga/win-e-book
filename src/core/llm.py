"""LLM 客户端:OpenAI 兼容协议(DeepSeek / 通义千问 / 智谱 / 月之暗面 等)。

设计要点:
- 流式:用 requests + iter_lines,自己解 SSE
- 配置:LLMConfig dataclass + load/save(默认 QSettings,允许注入其他存储)
- 依赖:仅 requests(已是项目依赖,无需新增)
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Callable, Generator, List, Optional, Dict, Any

import requests

# 预置常用 provider(用户可在 UI 里改 base_url/model,不强制限定)
PRESET_PROVIDERS: List[Dict[str, str]] = [
    {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    {
        "name": "通义千问 DashScope(OpenAI 兼容)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    {
        "name": "智谱 GLM(OpenAI 兼容)",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
    {
        "name": "月之暗面 Moonshot(OpenAI 兼容)",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    {
        "name": "本地 Ollama(OpenAI 兼容)",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "qwen2.5:7b",
    },
]


@dataclass
class LLMConfig:
    provider: str = "DeepSeek"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout_sec: float = 60.0

    def is_valid(self) -> bool:
        return bool(self.api_key) and bool(self.base_url) and bool(self.model)


class LLMError(RuntimeError):
    """LLM 调用错误。"""


class LLMClient:
    """OpenAI 兼容 chat completions 客户端(支持流式 SSE)。"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._session = requests.Session()

    # ---------- 入口 ----------
    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        on_delta: Optional[Callable[[str], None]] = None,
    ) -> Generator[str, None, None]:
        """流式调用。逐 chunk yield 增量文本,可选 on_delta 回调。

        messages: [{"role": "system"/"user"/"assistant", "content": "..."}]
        """
        if not self.config.is_valid():
            raise LLMError("LLM 未配置(api_key / base_url / model 任一为空)")
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        body = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        try:
            with self._session.post(
                url, headers=headers, json=body,
                timeout=self.config.timeout_sec, stream=True,
            ) as r:
                if r.status_code >= 400:
                    # 读 body 给用户看具体错误
                    err_text = r.text[:500] if r.text else "(空响应)"
                    raise LLMError(f"HTTP {r.status_code}: {err_text}")
                # SSE 逐行解
                for raw in r.iter_lines(decode_unicode=True):
                    if not raw:
                        continue
                    line = raw.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    # 提取 delta.content
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    chunk = delta.get("content") or ""
                    if chunk:
                        if on_delta:
                            try:
                                on_delta(chunk)
                            except Exception:  # noqa: BLE001
                                pass
                        yield chunk
        except requests.RequestException as e:
            raise LLMError(f"网络错误: {e}") from e

    def chat(self, messages: List[Dict[str, str]]) -> str:
        """非流式:整段返回。"""
        return "".join(self.chat_stream(messages))


# ============================================================
# 配置持久化(QSettings 包装)
# ============================================================

def _settings():  # type: ignore
    from PySide6.QtCore import QSettings
    return QSettings("WinEBook", "LLM")


def load_config() -> LLMConfig:
    """从 QSettings 读 LLMConfig。没设过返回默认值。"""
    s = _settings()
    cfg = LLMConfig(
        provider=str(s.value("provider", "DeepSeek")),
        api_key=str(s.value("api_key", "")),
        base_url=str(s.value("base_url", "https://api.deepseek.com/v1")),
        model=str(s.value("model", "deepseek-chat")),
        temperature=float(s.value("temperature", 0.7)),
        max_tokens=int(s.value("max_tokens", 2048)),
    )
    return cfg


def save_config(cfg: LLMConfig) -> None:
    s = _settings()
    s.setValue("provider", cfg.provider)
    s.setValue("api_key", cfg.api_key)
    s.setValue("base_url", cfg.base_url)
    s.setValue("model", cfg.model)
    s.setValue("temperature", cfg.temperature)
    s.setValue("max_tokens", cfg.max_tokens)
    s.sync()


# ============================================================
# 写作助手的预设 prompt 模板
# ============================================================

WRITE_PRESETS: Dict[str, Dict[str, str]] = {
    "续写": {
        "label": "续写小说",
        "system": (
            "你是一位中文小说家,擅长承接上下文、用细腻笔触续写故事。"
            "保持原作品的文风、人称、节奏,自然衔接上一段。"
            "不要重复前文、不要复述指令、不要用'好的''以下是'开头。"
        ),
        "user_template": (
            "以下是小说当前的章节内容(可能较长):\n\n"
            "{context}\n\n"
            "请在【{anchor}】处向后续写 {length} 字左右。"
            "直接输出续写正文,不要解释。"
        ),
    },
    "大纲": {
        "label": "提炼大纲",
        "system": (
            "你是叙事结构分析师,擅长把一篇长文压缩成层级化大纲。"
            "输出 Markdown,一级标题用 '#',二级用 '##',三级用 '###'。"
        ),
        "user_template": (
            "请把以下文本提炼成结构化大纲,保留关键情节、人物、地点、转折点:\n\n"
            "{context}"
        ),
    },
    "润色": {
        "label": "润色文本",
        "system": (
            "你是一位文学编辑,擅长在保留原意和文风的前提下润色文字。"
            "减少重复、收紧节奏、调整不通顺的句子。"
            "不要改变故事走向、不要扩写或缩写超过 20%。"
        ),
        "user_template": (
            "请润色以下文本(保留原意,只调整表达):\n\n"
            "{selection}"
        ),
    },
    "总结": {
        "label": "总结当前文档",
        "system": (
            "你是一位阅读助手,擅长用简洁中文总结文章。"
            "聚焦:核心主题、关键论点、结构脉络、未展开的缺口。"
        ),
        "user_template": (
            "请总结以下文档(约 200-400 字):\n\n"
            "{context}"
        ),
    },
    "翻译": {
        "label": "中英互译",
        "system": (
            "你是一位中英文互译专家,保留文学性,直译不通顺时用意译。"
        ),
        "user_template": (
            "请把以下文本{'中译英' if 'Chinese' in '...' else '英译中'}:\n\n"
            "{selection}"
        ),
    },
    "问答": {
        "label": "向智能体提问",
        "system": (
            "你是一位知识渊博的中文助手。"
            "回答简洁、有条理,必要时用 Markdown。"
        ),
        "user_template": "{question}",
    },
}


def build_messages(preset_key: str, **vars) -> List[Dict[str, str]]:
    """根据 preset_key 构造 messages 列表。"""
    p = WRITE_PRESETS[preset_key]
    user = p["user_template"].format(**vars)
    return [
        {"role": "system", "content": p["system"]},
        {"role": "user", "content": user},
    ]
