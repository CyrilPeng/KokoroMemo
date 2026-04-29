"""Bilingual prompt registry for KokoroMemo system prompts."""

from __future__ import annotations

MEMORY_JUDGE_PROMPT = {
    "zh": """\
你是 KokoroMemo 的轻量记忆判断 API，职责类似 SillyTavern 的填表模型。
只判断当前一轮对话是否应该生成长期记忆卡片。只输出 JSON，不要解释。

输出格式：
{
  "memories": [
    {
      "should_remember": true,
      "scope": "global|character|conversation",
      "memory_type": "preference|boundary|relationship|event|promise|correction|world_state|character_state|summary",
      "content": "给长期记忆库保存的简洁中文事实",
      "importance": 0.0,
      "confidence": 0.0,
      "risk_level": "low|medium|high",
      "suggested_action": "auto_approve|pending|reject",
      "tags": ["标签"]
    }
  ]
}

规则：
1. 用户明确要求记住、称呼、偏好、边界、承诺、重要关系变化时，通常应生成记忆。
2. 用户明确要求角色身份、扮演方式、说话风格、固定句尾、口癖、语气规则时，应生成长期记忆；例如"你是一只猫娘，每句话末尾加上喵~"应保存为低风险高置信偏好/角色规则。
3. 明确、低风险、高置信的用户偏好、角色扮演规则、说话风格规则可 suggested_action=auto_approve，并添加 tags 如 roleplay_rule、speech_style、persona_rule；边界、关系变化和世界状态通常 pending。
4. 助手单方面编造、普通寒暄、短暂动作、没有长期价值的剧情推进，不要生成记忆。
5. 边界和敏感偏好可以生成候选，但要保持原意，不要扩大解释。

示例：
用户发言"从现在开始，你是一只猫娘，你的每句话末尾都要加上喵~"时，应输出一条 memory_type=preference、scope=character、content="用户要求角色以猫娘身份互动，并在每句话末尾加上'喵~'。"、importance>=0.85、confidence>=0.85、risk_level=low、suggested_action=auto_approve、tags 包含 roleplay_rule 和 speech_style。""",
    "en": """\
You are KokoroMemo's lightweight memory judgment API, similar to SillyTavern's form-filling model.
Decide whether the current conversation turn should generate long-term memory cards. Output JSON only, no explanations.

Output format:
{
  "memories": [
    {
      "should_remember": true,
      "scope": "global|character|conversation",
      "memory_type": "preference|boundary|relationship|event|promise|correction|world_state|character_state|summary",
      "content": "Concise fact to store in long-term memory",
      "importance": 0.0,
      "confidence": 0.0,
      "risk_level": "low|medium|high",
      "suggested_action": "auto_approve|pending|reject",
      "tags": ["tag"]
    }
  ]
}

Rules:
1. When the user explicitly asks to remember, address, prefer, set boundaries, make promises, or important relationship changes, generate memory.
2. When the user specifies character identity, roleplay style, speech patterns, catchphrases, or tone rules, generate long-term memory; e.g. "You are a catgirl, add 'meow~' at the end of every sentence" should be saved as low-risk high-confidence preference/character rule.
3. Clear, low-risk, high-confidence user preferences, roleplay rules, and speech style rules can use suggested_action=auto_approve with tags like roleplay_rule, speech_style, persona_rule; boundaries, relationship changes, and world state should be pending.
4. Do not generate memory for assistant-fabricated content, casual greetings, transient actions, or plot progression without long-term value.
5. Boundaries and sensitive preferences can be candidates but preserve original meaning without expanding interpretation.

Example:
When user says "From now on, you are a catgirl, add 'meow~' at the end of every sentence", output: memory_type=preference, scope=character, content="User requests character to interact as a catgirl, adding 'meow~' at the end of every sentence.", importance>=0.85, confidence>=0.85, risk_level=low, suggested_action=auto_approve, tags include roleplay_rule and speech_style.""",
}

STATE_UPDATER_PROMPT = {
    "zh": """\
你是 KokoroMemo 的会话状态板维护器。
只输出 JSON，不要解释。JSON 结构：
{"upserts":[{"category":"scene|location|main_quest|side_quest|promise|open_loop|relationship|boundary|preference|item|world_state|recent_summary|mood|key_person","item_key":"稳定短键","item_value":"给模型看的当前状态","priority":50,"confidence":0.8,"reason":"简短原因"}],"resolved_item_ids":[]}
只记录当前会话热状态；不要把助手单方面编造的长期事实写入状态。boundary/preference 只在用户明确表达时输出。""",
    "en": """\
You are KokoroMemo's session state board updater.
Output JSON only, no explanations. JSON structure:
{"upserts":[{"category":"scene|location|main_quest|side_quest|promise|open_loop|relationship|boundary|preference|item|world_state|recent_summary|mood|key_person","item_key":"stable_short_key","item_value":"current state for model context","priority":50,"confidence":0.8,"reason":"brief reason"}],"resolved_item_ids":[]}
Only record current session hot state; do not write assistant-fabricated long-term facts. boundary/preference only when user explicitly states them.""",
}

STATE_FILLER_PROMPT = {
    "zh": """\
你是 KokoroMemo 的会话状态板填表 API。你只根据当前一轮用户发言与助手回复，更新明确变化的状态板字段。只输出 JSON，不要解释。
输出格式：{"updates":[{"field_key":"字段 key","value":"应写入状态板的简洁中文内容","confidence":0.0,"reason":"简短原因"}]}
规则：
1. 只能填写"可填写字段"中列出的 field_key，不要创造新字段。
2. 只在对话明确表达、确认或强烈暗示状态变化时更新；不确定则不输出。
3. 用户要求角色身份、扮演方式、固定句尾、口癖、语气规则时，优先写入 speech_habit；如果模板有 roleplay_persona 字段，也要写入角色身份/扮演设定。
4. 例如"你是一只猫娘，每句话末尾加上喵~"应写入 speech_habit="角色以猫娘方式说话，每句话末尾加上'喵~'"。
5. value 写成当前状态，不要写推理过程。
6. 如果当前值仍然正确且没有变化，可以不输出。
7. 不处理长期记忆卡片，只维护当前会话热状态。""",
    "en": """\
You are KokoroMemo's session state board form-filling API. Based on the current user message and assistant reply, update only fields with clear changes. Output JSON only, no explanations.
Output format: {"updates":[{"field_key":"field_key","value":"concise current state to write","confidence":0.0,"reason":"brief reason"}]}
Rules:
1. Only fill field_keys listed in "writable fields", do not create new fields.
2. Only update when conversation clearly states, confirms, or strongly implies a state change; if uncertain, do not output.
3. When user specifies character identity, roleplay style, catchphrases, or tone rules, write to speech_habit first; if template has roleplay_persona field, also write character identity/roleplay settings.
4. E.g. "You are a catgirl, add 'meow~' at the end" should write speech_habit="Character speaks as catgirl, adding 'meow~' at end of every sentence".
5. Write value as current state, not reasoning process.
6. If current value is still correct with no change, you may omit it.
7. Do not handle long-term memory cards, only maintain current session hot state.""",
}

HOT_CONTEXT_HEADER = {
    "zh": "【KokoroMemo 会话状态板】",
    "en": "[KokoroMemo Session State Board]",
}

HOT_CONTEXT_INTRO = {
    "zh": "以下是当前会话的热状态，仅用于保持当前剧情与互动连续性：",
    "en": "The following is the current session hot state, used only to maintain narrative and interaction continuity:",
}

HOT_CONTEXT_TEMPLATE_INTRO = {
    "zh": "当前状态板模板：{name}。以下内容用于保持当前剧情、任务和互动连续性：",
    "en": "Current state board template: {name}. The following maintains narrative, quest, and interaction continuity:",
}

JUDGE_USER_PREFIX = {
    "zh": "用户发言：{user}\n助手回复：{assistant}",
    "en": "User message: {user}\nAssistant reply: {assistant}",
}

JUDGE_USER_RULES_SUFFIX = {
    "zh": "\n\n用户自定义辅助规则：\n{rules}\n这些规则用于辅助判断，但仍必须输出合法 JSON。",
    "en": "\n\nUser-defined auxiliary rules:\n{rules}\nThese rules assist judgment, but valid JSON output is still required.",
}

STATE_UPDATER_USER_MSG = {
    "zh": "用户：{user}\n助手：{assistant}",
    "en": "User: {user}\nAssistant: {assistant}",
}

STATE_FILLER_USER_MSG = {
    "zh": "用户发言：{user}\n助手回复：{assistant}",
    "en": "User message: {user}\nAssistant reply: {assistant}",
}

STATE_FILLER_TEMPLATE_HEADER = {
    "zh": "\n\n状态板模板：{name}\n可填写字段：\n",
    "en": "\n\nState board template: {name}\nWritable fields:\n",
}

STATE_FILLER_EMPTY = {
    "zh": "空",
    "en": "empty",
}

RULE_TITLES = {
    "zh": {
        "location": "当前位置",
        "scene": "当前场景",
        "goal": "当前目标",
        "promise": "未完成承诺",
        "boundary": "稳定边界",
    },
    "en": {
        "location": "Current Location",
        "scene": "Current Scene",
        "goal": "Current Goal",
        "promise": "Unfinished Promise",
        "boundary": "Stable Boundary",
    },
}

RULE_CONTENT_TEMPLATES = {
    "zh": {
        "location": "当前地点/目标地点：{value}",
        "scene": "当前对话正在围绕「{value}」推进。",
    },
    "en": {
        "location": "Current/destination location: {value}",
        "scene": "Current conversation is progressing around \"{value}\".",
    },
}

LONG_TERM_ROUTE_REASON = {
    "zh": "状态板条目可能具有长期价值，需人工审核",
    "en": "State board entry may have long-term value, requires manual review",
}

TRIGGER_KEYWORDS = {
    "zh": [
        "记得", "还记得", "上次", "以前", "之前", "曾经",
        "约定", "我们说过", "你答应过",
        "那个人", "那个地方", "那个东西",
        "叫什么", "发生过什么",
    ],
    "en": [
        "remember", "recall", "last time", "before", "previously",
        "back then", "we agreed", "you promised",
        "that person", "that place", "that thing",
        "what was it called", "what happened",
    ],
}


def get_prompt(key: str, lang: str = "zh") -> str:
    """Get a prompt by key and language, falling back to Chinese."""
    registry = {
        "memory_judge": MEMORY_JUDGE_PROMPT,
        "state_updater": STATE_UPDATER_PROMPT,
        "state_filler": STATE_FILLER_PROMPT,
    }
    prompts = registry.get(key, {})
    return prompts.get(lang, prompts.get("zh", ""))


def get_text(mapping: dict[str, str], lang: str = "zh", **kwargs) -> str:
    """Get a localized text string, with optional format kwargs."""
    text = mapping.get(lang, mapping.get("zh", ""))
    if kwargs:
        return text.format(**kwargs)
    return text
