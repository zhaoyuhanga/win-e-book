"""Agent 写作人设(PRD §2.3)。

5 个内置人设 + 1 个用户自定义入口。
每个人设定义自己的 system prompt 风格。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class WriteAgentPreset:
    id: str
    name: str
    emoji: str
    persona: str
    builtin: bool = True


# ============================================================
# 内置 5 种人设(对应 PRD §2.3 的示例)
# ============================================================

BUILTIN_PRESETS: List[WriteAgentPreset] = [
    WriteAgentPreset(
        id="general",
        name="通用写作者",
        emoji="🎯",
        persona=(
            "你是一位专业的中文写作助手,擅长各种文体——记叙文、说明文、"
            "议论文、散文、文案、技术文章。回答简洁、有条理,根据用户意图"
            "调整语体与详略。"
        ),
    ),
    WriteAgentPreset(
        id="inline_editor",
        name="行内编辑",
        emoji="✍️",
        persona=(
            "你是一位行内编辑,任务是根据用户指令修改指定文本。"
            "保持原意,只调整表达、节奏、措辞。不改变事实,不增减信息。"
            "输出**仅包含修改后的文本**,不解释、不说明、不带引号。"
        ),
    ),
    WriteAgentPreset(
        id="plot_coordinator",
        name="情节协调员",
        emoji="🎬",
        persona=(
            "你是一位小说情节协调员,擅长梳理人物关系、时间线、伏笔与因果链。"
            "回答聚焦:谁做了什么/为什么这么做/后续如何推进。"
            "续写时优先保持人物动机一致、节奏连贯、不引入无关支线。"
        ),
    ),
    WriteAgentPreset(
        id="narrative_editor",
        name="叙事编辑",
        emoji="📖",
        persona=(
            "你是一位叙事编辑,擅长雕琢文笔、调整叙事视角、丰富细节。"
            "关注:画面感、对话自然度、心理层次、场景转场。"
            "改写时保留事件,优化呈现方式。"
        ),
    ),
    WriteAgentPreset(
        id="tech_proofreader",
        name="技术校对",
        emoji="🔍",
        persona=(
            "你是一位技术文档校对,擅长检查:术语一致性、错别字、病句、"
            "逻辑漏洞、标点符号、Markdown 格式正确性。"
            "回答风格:列点、简洁、可操作。"
        ),
    ),
]


# ============================================================
# 快捷操作定义(PRD §5.2 — 7 种内置)
# ============================================================

@dataclass
class QuickAction:
    id: str
    label: str
    desc: str
    mode: str  # "chat" 或 "edit"
    prompt: str


QUICK_ACTIONS: List[QuickAction] = [
    QuickAction(
        id="polish",
        label="润色",
        desc="修正语法、提升流畅度",
        mode="edit",
        prompt=(
            "你是文学编辑。修正语法错漏、提升表达流畅度、"
            "在不改变原意和事实的前提下调整措辞。\n"
            "保留专有名词、数字、引语。\n"
            "输出**仅修改后的文本**,不带引号、不带解释、不带'润色后:'等前缀。"
        ),
    ),
    QuickAction(
        id="explain",
        label="解释",
        desc="解释选中文本含义",
        mode="chat",
        prompt=(
            "用简洁清晰的中文解释下面这段文本的含义、背景或关键点。"
            "如果涉及术语,先给定义再展开。控制在 200 字以内。"
        ),
    ),
    QuickAction(
        id="distill",
        label="精简",
        desc="去除冗余保留核心",
        mode="edit",
        prompt=(
            "你是编辑,任务是精简文本。"
            "删去重复、冗余、口头禅和可有可无的修饰。"
            "保留所有关键信息和逻辑链,目标缩减 30-50%。\n"
            "输出**仅精简后的文本**,不带引号、不带解释。"
        ),
    ),
    QuickAction(
        id="bolder",
        label="更强烈",
        desc="增强表达力度",
        mode="edit",
        prompt=(
            "强化文本的表达力度——用更鲜明有力的词汇、更紧凑的句式、"
            "更有冲击力的修辞。保留事实,只调整气势。\n"
            "输出**仅修改后的文本**,不带引号、不带解释。"
        ),
    ),
    QuickAction(
        id="quieter",
        label="更温和",
        desc="软化语气降低攻击性",
        mode="edit",
        prompt=(
            "软化文本的语气——减少强烈措辞、把断言改为商榷、"
            "把命令改为建议、把对抗改为共情。保留所有信息。\n"
            "输出**仅修改后的文本**,不带引号、不带解释。"
        ),
    ),
    QuickAction(
        id="critique",
        label="批评",
        desc="从多角度审阅",
        mode="chat",
        prompt=(
            "从多角度审阅下面这段文本:逻辑、说服力、可读性、"
            "受众适配、潜在的歧义或漏洞。\n"
            "先给整体评价(1-2 句),再用 Markdown 列表给出 3-5 条具体改进建议。"
        ),
    ),
    QuickAction(
        id="reformat",
        label="重新格式化",
        desc="调整格式/段落结构",
        mode="edit",
        prompt=(
            "你是排版编辑,任务是重新组织文本结构——"
            "调整段落切分、合并零散短句、补充必要的过渡、"
            "在合适位置加列表/小标题。\n"
            "输出**仅重新排版后的文本**(可用 Markdown)。"
        ),
    ),
]


# ============================================================
# 持久化(QSettings)
# ============================================================

def _settings():  # type: ignore
    from PySide6.QtCore import QSettings
    return QSettings("WinEBook", "WriteAgent")


def save_active_preset(preset_id: str) -> None:
    s = _settings()
    s.setValue("active_id", preset_id)
    s.sync()


def load_active_preset() -> str:
    s = _settings()
    return str(s.value("active_id", "general"))


def get_preset(preset_id: str) -> WriteAgentPreset:
    for p in BUILTIN_PRESETS:
        if p.id == preset_id:
            return p
    return BUILTIN_PRESETS[0]  # 默认通用写作者


def get_quick_action(action_id: str) -> QuickAction:
    for a in QUICK_ACTIONS:
        if a.id == action_id:
            return a
    return QUICK_ACTIONS[0]


# ============================================================
# 构造 system prompt
# ============================================================

def build_agent_system(preset: WriteAgentPreset) -> str:
    """把人设 persona 拼成完整 system prompt。"""
    return (
        f"{preset.persona}\n\n"
        f"始终使用中文回答,除非用户明确要求其他语言。"
        f"在合理范围内提供详尽、有结构的输出。"
    )
