# KokoroMemo 热记忆层与按需召回改造 TODO

> 目标读者：Codex / AI Agent / 项目维护者  
> 适用项目：KokoroMemo / 心忆  
> 目标方案：在现有“SQLite 记忆卡片库 + LanceDB 语义索引 + 图结构关系索引 + 层级摘要”的基础上，加入“会话状态板 Hot Memory + Retrieval Gate 按需召回门控”  
> 核心目标：减少每轮向量库调用，让当前剧情、人物、任务、承诺、关系状态以轻量结构常驻上下文；只有需要具体历史细节时才调用 LanceDB / 图扩展 / Rerank。  

---

## 0. 给 Codex 的总指令

请基于当前 KokoroMemo 项目进行增量施工，不要推翻已有架构，不要重写代理主流程。

本次目标是在现有长期记忆体系之上新增一层 **Hot Memory / 会话状态板**，并引入 **Retrieval Gate / 按需召回门控**。

最终记忆架构应形成四层：

```text
第 1 层：Raw Log 原始对话层
- chat.sqlite
- 保存完整对话
- 用于回溯、导出、溯源、重新提炼

第 2 层：Hot State 会话状态板
- conversation_state_items
- 每轮默认注入
- 记录当前场景、关键人物、主线任务、支线任务、未完成承诺、开放伏笔、关系状态和边界

第 3 层：Card Graph 记忆卡片图谱
- memory_cards
- memory_edges
- memory_tags
- memory_summaries
- 保存 approved 长期记忆、结构关系和层级摘要

第 4 层：Semantic Index 语义索引
- LanceDB
- 只索引 approved cards / summaries
- 仅在需要具体历史细节时调用
```

请严格遵守以下原则：

1. 保留现有 OpenAI-compatible 代理、流式转发、SQLite 对话落盘、Embedding Provider、LanceDBStore、记忆卡片、记忆收件箱、图结构关系和层级摘要能力。
2. 新增会话状态板，不替代长期记忆卡片。
3. 会话状态板负责“当前正在发生什么”，默认每轮注入。
4. 记忆卡片负责“长期应该记住什么”，仍走审核流程。
5. LanceDB 负责“需要时检索具体历史细节”，不要每轮强制调用。
6. 状态板可以更自动，因为它主要影响当前会话。
7. 长期记忆仍保持半自动审核，不能因为状态板存在而绕过 memory_inbox。
8. 如果状态板生成或注入失败，聊天必须继续。
9. 如果 Retrieval Gate 判断无需召回，必须跳过 Embedding / LanceDB / Rerank，以降低延迟和 API 调用。
10. 所有新增表必须支持迁移、测试和降级。

---

## 1. 背景与动机

当前 KokoroMemo 的长期记忆体系已经具备：

```text
SQLite 完整对话落盘
记忆卡片 memory_cards
记忆收件箱 memory_inbox
图结构关系 memory_edges
层级摘要 memory_summaries
LanceDB approved 语义索引
可选 Rerank
多作用域隔离
```

但如果每轮聊天都执行完整召回链路：

```text
构造 query
→ Embedding
→ LanceDB 向量召回
→ 标签 / FTS
→ 图扩展
→ 层级摘要
→ 可选 Rerank
→ 注入
```

会带来以下问题：

```text
每轮远程 Embedding 调用增加延迟
每轮动态注入长期记忆可能导致 prompt 前缀频繁变化
普通剧情推进不一定需要查历史向量库
当前任务、地点、人物、承诺这类热状态不适合每轮从向量库找
长期记忆系统显得过重
```

本次方案引入：

```text
会话状态板 = 每轮常驻的热记忆
Retrieval Gate = 决定本轮是否需要调用向量库
```

最终目标：

```text
默认每轮注入：会话状态板 + 少量固定边界
按需召回：长期记忆卡片 + LanceDB 语义索引 + 图扩展 + Rerank
后台维护：状态更新 + 候选记忆审核 + 层级摘要
```

---

## 2. 目标与非目标

### 2.1 目标

- 新增会话状态板数据模型。
- 新增 State Updater，每轮或每 N 轮维护当前会话状态。
- 新增 Hot Context Injector，将状态板常驻注入 prompt。
- 新增 Retrieval Gate，决定是否调用长期记忆检索。
- 改造现有 Retrieval Orchestrator，使其可以被 Gate 跳过。
- 明确状态板与记忆卡片的边界。
- 支持状态板与长期卡片互相链接。
- 支持状态板 UI / Admin API 的基础读写。
- 增加测试，确保跳过向量检索时代理正常工作。
- 增加配置项控制状态板和召回门控。
- 将本 TODO 完成后合并进项目设计文档。

### 2.2 非目标

本阶段不要做：

- 复杂可视化任务看板。
- 完整图形化编辑器。
- 多人协同状态板。
- 外部插件市场。
- 复杂自动剧情规划器。
- 对所有 SillyTavern 插件做兼容。
- 把状态板直接写入 LanceDB。
- 让状态板绕过长期记忆审核机制。
- 用状态板取代 memory_cards / memory_edges / memory_summaries。

---

## 3. 核心概念

### 3.1 Hot Memory / 会话状态板

用于记录当前会话热状态，默认每轮注入。

适合记录：

```text
当前场景
当前地点
当前时间
当前氛围
关键人物
当前主线任务
支线任务
未完成承诺
开放伏笔
当前关系状态
临时世界状态
当前物品 / 线索
稳定边界摘要
最近剧情摘要
```

不适合记录：

```text
长期用户偏好
跨会话关系变化
长期边界
重要人生事实
长期世界观设定
需要用户确认的重大剧情事实
```

### 3.2 Retrieval Gate / 按需召回门控

用于判断当前请求是否调用长期记忆检索。

应调用向量库的情况：

```text
用户问“记得吗”“还记得吗”
用户提到“上次”“以前”“之前”“约定”“我们说过”
用户提到状态板里没有的人名、地点、物品、事件
新会话开始，需要加载角色长期背景
当前状态板置信度不足
用户明确询问历史细节
每隔 N 轮进行一次轻量刷新
状态板与当前用户输入存在明显缺口
```

可以跳过向量库的情况：

```text
普通寒暄
当前剧情自然推进
短句互动
情绪回应
状态板已经包含足够上下文
用户发言只依赖当前场景
```

### 3.3 State Updater / 状态板维护器

负责从每轮对话中提取当前会话状态变化。

它不同于 Memory Extractor：

```text
State Updater：维护当前会话状态，可以更自动、更轻量
Memory Extractor：提炼长期记忆卡片，需要审核、更谨慎
```

---

## 4. 数据库 TODO

### 4.1 新增表：conversation_state_items

位置：`memory.sqlite` 或每个会话的 `chat.sqlite`

推荐：放入 `memory.sqlite`，通过 `conversation_id` 绑定会话。  
原因：便于统一 Admin API、跨模块查询、与 memory_cards 建立链接。

SQL：

```sql
CREATE TABLE IF NOT EXISTS conversation_state_items (
  item_id TEXT PRIMARY KEY,

  user_id TEXT NOT NULL,
  character_id TEXT,
  conversation_id TEXT NOT NULL,
  world_id TEXT,

  category TEXT NOT NULL,
  item_key TEXT NOT NULL,
  item_value TEXT NOT NULL,

  status TEXT NOT NULL DEFAULT 'active',
  priority INTEGER NOT NULL DEFAULT 50,
  confidence REAL NOT NULL DEFAULT 0.8,

  source_turn_ids_json TEXT,
  source_message_ids_json TEXT,
  linked_card_ids_json TEXT,
  linked_summary_ids_json TEXT,

  created_by TEXT NOT NULL DEFAULT 'state_updater',

  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_injected_at TEXT,
  expires_at TEXT
);
```

索引：

```sql
CREATE INDEX IF NOT EXISTS idx_state_items_conversation
ON conversation_state_items(user_id, character_id, conversation_id, world_id, status);

CREATE INDEX IF NOT EXISTS idx_state_items_category
ON conversation_state_items(conversation_id, category, status, priority);

CREATE INDEX IF NOT EXISTS idx_state_items_updated
ON conversation_state_items(conversation_id, updated_at);
```

唯一约束建议：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_state_items_unique_key
ON conversation_state_items(conversation_id, category, item_key)
WHERE status = 'active';
```

说明：

- `category` 表示状态类型。
- `item_key` 表示该类别下的条目键。
- `item_value` 是给模型看的文本值。
- `priority` 控制注入优先级。
- `confidence` 控制是否触发向量召回补充。
- `expires_at` 用于临时状态过期。

### 4.2 新增表：conversation_state_events

用于记录状态板变更历史，便于调试和回滚。

```sql
CREATE TABLE IF NOT EXISTS conversation_state_events (
  event_id TEXT PRIMARY KEY,
  item_id TEXT,
  conversation_id TEXT NOT NULL,

  event_type TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT,
  payload_json TEXT,

  created_at TEXT NOT NULL
);
```

事件类型：

```text
created
updated
resolved
expired
deleted
linked_card
linked_summary
injected
state_updater_failed
manual_edit
```

### 4.3 新增表：retrieval_decisions

用于记录每轮是否调用长期召回，方便排查性能和召回质量。

```sql
CREATE TABLE IF NOT EXISTS retrieval_decisions (
  decision_id TEXT PRIMARY KEY,

  request_id TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  character_id TEXT,
  world_id TEXT,

  should_retrieve INTEGER NOT NULL,
  reasons_json TEXT,
  skipped_routes_json TEXT,
  triggered_routes_json TEXT,

  state_confidence REAL,
  latest_user_text TEXT,

  created_at TEXT NOT NULL
);
```

注意：

- `latest_user_text` 可配置是否保存。
- 如果日志隐私策略不允许，应只保存摘要或 hash。

---

## 5. 状态板分类 TODO

新增状态类别枚举。

建议位置：

```text
app/memory/state_schema.py
```

分类：

```python
STATE_CATEGORIES = {
    "scene": "当前场景",
    "key_person": "关键人物",
    "main_quest": "主线任务",
    "side_quest": "支线任务",
    "promise": "未完成承诺",
    "open_loop": "开放伏笔",
    "relationship": "当前关系状态",
    "boundary": "稳定边界",
    "preference": "当前相关偏好",
    "location": "地点状态",
    "item": "重要物品 / 线索",
    "world_state": "当前世界状态",
    "recent_summary": "近期剧情摘要",
    "mood": "当前氛围 / 情绪基调"
}
```

状态条目示例：

```json
{
  "category": "scene",
  "item_key": "current_location",
  "item_value": "Yuki 的房间",
  "priority": 95,
  "confidence": 0.9
}
```

```json
{
  "category": "main_quest",
  "item_key": "烟火大会计划",
  "item_value": "玩家和 Yuki 正在计划周末一起去看烟火大会，下一步需要确认集合时间和地点。",
  "priority": 90,
  "confidence": 0.86
}
```

```json
{
  "category": "boundary",
  "item_key": "avoid_yandere_threats",
  "item_value": "玩家不喜欢威胁、自伤或过度病态表达。",
  "priority": 100,
  "confidence": 0.95,
  "linked_card_ids_json": "[\"card_xxx\"]"
}
```

---

## 6. 配置 TODO

在 `config.example.yaml` 中新增：

```yaml
memory:
  hot_context:
    enabled: true
    inject_always: true
    max_chars: 1200

    include_sections:
      scene: true
      key_people: true
      main_quest: true
      side_quests: true
      promises: true
      open_loops: true
      relationship: true
      boundaries: true
      preferences: true
      recent_summary: true

    section_order:
      - boundary
      - scene
      - key_person
      - relationship
      - main_quest
      - side_quest
      - promise
      - open_loop
      - item
      - world_state
      - recent_summary
      - mood

    max_items_per_section:
      boundary: 5
      scene: 6
      key_person: 8
      relationship: 4
      main_quest: 5
      side_quest: 5
      promise: 6
      open_loop: 6
      item: 6
      world_state: 5
      recent_summary: 3
      mood: 3

  state_updater:
    enabled: true
    mode: "rule_then_llm"  # rule_only | llm_only | rule_then_llm
    update_after_each_turn: true
    update_every_n_turns: 1
    min_confidence: 0.55
    auto_expire_resolved_items: true
    max_state_items_per_conversation: 200

  retrieval_gate:
    enabled: true
    mode: "auto"  # always | never | auto
    vector_search_on_new_session: true
    vector_search_every_n_turns: 6
    vector_search_when_state_confidence_below: 0.65

    trigger_keywords:
      - "记得"
      - "还记得"
      - "上次"
      - "以前"
      - "之前"
      - "曾经"
      - "约定"
      - "我们说过"
      - "你答应过"
      - "那个人"
      - "那个地方"
      - "那个东西"
      - "叫什么"
      - "发生过什么"

    skip_when_latest_user_text_chars_below: 4
    skip_when_state_is_sufficient: true
```

配置含义：

- `hot_context.enabled`：是否启用状态板。
- `hot_context.inject_always`：是否每轮注入。
- `state_updater.enabled`：是否后台维护状态板。
- `retrieval_gate.enabled`：是否让门控决定是否调用向量库。
- `mode = always`：每轮都调用长期召回，兼容旧行为。
- `mode = never`：不调用长期召回，只用状态板。
- `mode = auto`：按规则判断。

---

## 7. 新增模块 TODO

### 7.1 新增 `app/memory/state_schema.py`

职责：

- 定义状态类别枚举。
- 定义状态 item dataclass / Pydantic model。
- 定义 StateUpdateResult。
- 定义 StateRenderOptions。

建议模型：

```python
from pydantic import BaseModel, Field
from typing import Literal

StateCategory = Literal[
    "scene",
    "key_person",
    "main_quest",
    "side_quest",
    "promise",
    "open_loop",
    "relationship",
    "boundary",
    "preference",
    "location",
    "item",
    "world_state",
    "recent_summary",
    "mood",
]

class ConversationStateItem(BaseModel):
    item_id: str
    user_id: str
    character_id: str | None = None
    conversation_id: str
    world_id: str | None = None
    category: StateCategory
    item_key: str
    item_value: str
    status: str = "active"
    priority: int = 50
    confidence: float = 0.8
    linked_card_ids: list[str] = Field(default_factory=list)
    linked_summary_ids: list[str] = Field(default_factory=list)

class StateUpdate(BaseModel):
    category: StateCategory
    item_key: str
    item_value: str
    status: str = "active"
    priority: int = 50
    confidence: float = 0.8
    reason: str | None = None

class StateUpdateResult(BaseModel):
    upserts: list[StateUpdate] = Field(default_factory=list)
    resolved_item_ids: list[str] = Field(default_factory=list)
    deleted_item_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
```

### 7.2 新增 `app/storage/sqlite_state.py`

职责：

- 初始化 `conversation_state_items`。
- 初始化 `conversation_state_events`。
- 初始化 `retrieval_decisions`。
- CRUD 状态条目。
- 查询 active 状态。
- 批量 upsert 状态条目。
- 标记 resolved / expired。
- 记录注入事件。

需要实现：

```python
class SQLiteStateStore:
    async def init_schema(self) -> None: ...
    async def list_active_items(self, conversation_id: str, categories: list[str] | None = None) -> list[ConversationStateItem]: ...
    async def upsert_item(self, item: ConversationStateItem) -> None: ...
    async def upsert_many(self, items: list[ConversationStateItem]) -> None: ...
    async def resolve_item(self, item_id: str, reason: str | None = None) -> None: ...
    async def expire_old_items(self, conversation_id: str) -> int: ...
    async def record_state_event(self, ...) -> None: ...
    async def record_retrieval_decision(self, ...) -> None: ...
```

### 7.3 新增 `app/memory/state_renderer.py`

职责：

- 把状态板渲染为 prompt 文本。
- 控制 section 顺序。
- 控制最大字数。
- 控制每类最多条数。
- 避免输出过长表格。
- 优先注入 boundary、scene、relationship、main_quest。

输出模板：

```text
【KokoroMemo 会话状态板】
以下是当前会话的简要状态，用于保持剧情连续性。若与用户最新发言冲突，以用户最新发言为准。

[稳定边界 / 禁忌]
- ...

[当前场景]
- 地点：...
- 时间：...
- 氛围：...
- 当前目标：...

[关键人物]
- Yuki：...
- 玩家：...

[关系状态]
- ...

[主线任务]
- ...

[支线任务]
- ...

[未完成事项]
- ...

[开放伏笔]
- ...
```

注意：

- 不要强行每个 section 都输出。
- 没有内容的 section 省略。
- 最终文本不能超过 `memory.hot_context.max_chars`。
- 如果超长，按 priority 降序保留。
- 不要输出“数据库”“检索结果”等暴露实现的说法。

### 7.4 新增 `app/memory/state_injector.py`

职责：

- 在原始 system prompt 后、用户最新消息前注入状态板。
- 与现有 `memory.injector` 协调。
- 支持状态板和长期记忆同时注入。
- 记录 injected state item IDs。

建议顺序：

```text
原始 System Prompt
→ KokoroMemo 会话状态板
→ KokoroMemo 长期记忆召回结果
→ 最近上下文
→ 最新用户输入
```

如果当前已有 memory injector，可将状态板注入逻辑合并，但建议单独模块，避免职责混乱。

### 7.5 新增 `app/memory/state_updater.py`

职责：

- 根据当前 turn 和最近上下文生成状态更新。
- 先做 rule-based 轻量更新。
- 如配置允许，再调用 LLM 生成结构化 JSON。
- 输出 StateUpdateResult。
- 写入 SQLiteStateStore。

输入：

```python
@dataclass
class StateUpdateInput:
    ctx: RequestContext
    latest_user_message: str
    latest_assistant_message: str
    recent_messages: list[dict]
    current_state_items: list[ConversationStateItem]
    injected_memory_cards: list[str]
```

输出 JSON：

```json
{
  "upserts": [
    {
      "category": "scene",
      "item_key": "current_location",
      "item_value": "前往车站途中",
      "status": "active",
      "priority": 90,
      "confidence": 0.88,
      "reason": "用户表示现在出发去车站。"
    }
  ],
  "resolved_item_ids": [
    "state_old_location_001"
  ],
  "notes": []
}
```

规则提取建议：

```text
用户说“现在去/我们去/到了/回到” → 更新 scene/location
用户说“以后/记得/你答应” → 生成 promise 或 preference 候选；长期记忆另走 Memory Extractor
用户说“任务完成/已经做完” → resolve 相关 quest/promise
用户说“不要/不喜欢/别再” → boundary 状态项 + 长期记忆候选
用户说“接下来/下一步” → main_quest 或 side_quest
```

注意：

- State Updater 不直接创建 approved memory_cards。
- 如果发现长期价值内容，应通过 memory_extract_job 生成候选卡片。
- Assistant-only 的状态更新只影响当前会话，不自动成为长期记忆。

### 7.6 新增 `app/memory/retrieval_gate.py`

职责：

- 判断本轮是否调用长期记忆检索。
- 返回 decision 和 reasons。
- 记录到 `retrieval_decisions`。

输入：

```python
@dataclass
class RetrievalGateInput:
    ctx: RequestContext
    latest_user_text: str
    recent_messages: list[dict]
    current_state_items: list[ConversationStateItem]
    turn_index: int
    is_new_session: bool
```

输出：

```python
@dataclass
class RetrievalGateDecision:
    should_retrieve: bool
    reasons: list[str]
    triggered_routes: list[str]
    skipped_routes: list[str]
    state_confidence: float | None
```

规则：

```python
def should_retrieve(input):
    if config.memory.retrieval_gate.mode == "always":
        return True

    if config.memory.retrieval_gate.mode == "never":
        return False

    if input.is_new_session and config.vector_search_on_new_session:
        return True

    if contains_trigger_keyword(input.latest_user_text):
        return True

    if mentions_unknown_entity(input.latest_user_text, input.current_state_items):
        return True

    if input.turn_index % config.vector_search_every_n_turns == 0:
        return True

    if average_state_confidence(input.current_state_items) < threshold:
        return True

    return False
```

关键词初始列表使用配置项。

### 7.7 改造 `retrieval_orchestrator.py`

当前行为可能默认每轮召回。需要变为：

```text
1. 先读取会话状态板
2. 调用 Retrieval Gate
3. 如果 should_retrieve = false：
   - 跳过 Embedding / LanceDB / Rerank
   - 只返回 empty long_memory_candidates
4. 如果 should_retrieve = true：
   - 执行原有长期召回链路
5. 无论是否长期召回，状态板仍可注入
```

伪代码：

```python
state_items = await state_store.list_active_items(ctx.conversation_id)

state_block = await state_renderer.render(state_items)

decision = await retrieval_gate.decide(ctx, latest_user_text, state_items)

if decision.should_retrieve:
    long_memory_candidates = await long_memory_retriever.retrieve(ctx, query)
else:
    long_memory_candidates = []

messages = state_injector.inject(messages, state_block)
messages = memory_injector.inject(messages, long_memory_candidates)
```

### 7.8 改造 `injector.py`

需要支持两类注入：

```text
Hot Context：每轮状态板
Long Memory：按需召回的长期记忆
```

注入内容建议拆成两条 system 消息，便于调试：

```text
【KokoroMemo 会话状态板】
...

【KokoroMemo 长期记忆】
...
```

也可以合并为一条 system 消息，但内部必须分区。

要求：

- 原 system prompt 不得被覆盖。
- 最新用户输入不得被移到状态板之前。
- 超过字数预算时优先保留状态板的 boundary、scene、main_quest。
- 长期记忆预算独立于状态板预算。

---

## 8. Pipeline TODO

### 8.1 非流式流程

目标流程：

```text
1. 接收请求
2. 保存 raw request
3. 解析 messages
4. 解析 user_id / character_id / conversation_id / world_id
5. 读取当前 conversation_state_items
6. 渲染会话状态板
7. 调用 Retrieval Gate
8. 如果需要长期召回：
   - 构造 retrieval query
   - Embedding
   - LanceDB / Tag / FTS / Summary / Graph
   - 可选 Rerank
9. 注入会话状态板
10. 注入长期记忆候选
11. 转发到真实 LLM
12. 接收响应
13. 保存 raw response 和 messages
14. 后台执行 State Updater
15. 后台执行 Memory Extractor
16. 后台执行长期卡片审核 / 向量同步
```

### 8.2 流式流程

目标流程：

```text
1. 接收请求
2. 保存 raw request
3. 读取并注入状态板
4. Retrieval Gate 决定是否长期召回
5. 转发真实 LLM stream
6. SSE chunk 原样返回客户端
7. 同时收集 assistant delta
8. stream 结束后保存完整回复
9. 后台执行 State Updater
10. 后台执行 Memory Extractor
```

注意：

- State Updater 必须在完整 assistant 回复可用后执行。
- 如果流式中断，应记录 partial response，并允许 State Updater 跳过。
- 不要为了更新状态板阻塞流式返回。

---

## 9. Admin API TODO

新增只读接口：

```text
GET /admin/conversations/{conversation_id}/state
GET /admin/conversations/{conversation_id}/state/events
GET /admin/conversations/{conversation_id}/retrieval-decisions
```

新增写接口：

```text
POST /admin/conversations/{conversation_id}/state
PATCH /admin/state/{item_id}
POST /admin/state/{item_id}/resolve
DELETE /admin/state/{item_id}
POST /admin/conversations/{conversation_id}/state/rebuild
```

请求示例：

```json
{
  "category": "main_quest",
  "item_key": "烟火大会计划",
  "item_value": "玩家和 Yuki 正在计划周末去看烟火大会。",
  "priority": 90,
  "confidence": 0.9
}
```

必须鉴权：

```http
Authorization: Bearer {ADMIN_TOKEN}
```

---

## 10. 前端 UI TODO

如果当前 GUI 已有管理界面，新增“会话状态板”页签。

### 10.1 会话状态板页面

显示：

```text
当前场景
关键人物
主线任务
支线任务
未完成承诺
开放伏笔
关系状态
边界 / 偏好
最近摘要
```

每个条目显示：

```text
category
item_key
item_value
status
priority
confidence
updated_at
linked_cards
操作按钮
```

操作：

```text
编辑
标记完成 / resolved
删除
链接到记忆卡片
提升优先级
降低优先级
```

### 10.2 Retrieval Gate 调试页

显示最近请求：

```text
request_id
latest_user_text / hash
should_retrieve
reasons
triggered_routes
skipped_routes
state_confidence
created_at
```

这对调试“为什么没想起来”非常重要。

---

## 11. 测试 TODO

### 11.1 单元测试

新增：

```text
test_state_schema_validation
test_state_store_create_item
test_state_store_upsert_same_key
test_state_store_resolve_item
test_state_renderer_empty
test_state_renderer_budget_limit
test_state_renderer_section_order
test_retrieval_gate_keyword_trigger
test_retrieval_gate_new_session
test_retrieval_gate_skip_short_current_context
test_retrieval_gate_low_confidence_trigger
test_state_injector_preserves_original_system_prompt
test_state_updater_rule_location
test_state_updater_rule_promise
```

### 11.2 集成测试

新增：

```text
非流式请求能注入会话状态板
流式请求能注入会话状态板
普通短句不触发向量召回
“你还记得...”触发向量召回
新会话首次请求触发长期召回
状态板 confidence 低时触发长期召回
Embedding 失败时仍注入状态板并继续聊天
State Updater 失败不影响聊天
状态板条目 resolved 后不再注入
```

### 11.3 回归测试

确保现有能力不退化：

```text
/v1/models 正常
/v1/chat/completions 非流式正常
/v1/chat/completions stream=true 正常
raw request / response 正常落盘
memory_cards approved 后仍可同步 LanceDB
memory_inbox 审核流程不受影响
deprecated / superseded 卡片默认不注入
```

---

## 12. 验收标准

### 12.1 功能验收

1. 启动服务后，`/health` 正常。
2. 非流式聊天正常。
3. 流式聊天正常。
4. 每轮对话保存到 `chat.sqlite`。
5. 每轮对话结束后生成或维护 `conversation_state_items`。
6. 下一轮请求默认注入会话状态板。
7. 普通剧情推进不触发 Embedding / LanceDB。
8. 用户说“你还记得之前的约定吗？”时触发长期记忆召回。
9. 当 Retrieval Gate 跳过长期召回时，日志和 `retrieval_decisions` 能看到原因。
10. State Updater 失败时，聊天不失败。
11. Embedding 失败时，状态板仍可注入，聊天不失败。
12. 状态板条目可以通过 Admin API 编辑、删除、resolve。
13. 状态板不绕过 memory_inbox，不直接创建 approved 长期记忆。
14. 长期记忆卡片仍按 approved 状态进入 LanceDB。

### 12.2 性能验收

在普通连续剧情对话中：

```text
不应每轮调用 Embedding
不应每轮调用 LanceDB
不应每轮调用 Rerank
状态板读取和渲染应在低毫秒级完成
状态板注入文本默认不超过 1200 字符
```

### 12.3 体验验收

示例流程：

第一轮：

```text
用户：我们现在去车站吧，烟火大会快开始了。
```

后台生成状态项：

```text
scene.current_location = 前往车站途中
main_quest.烟火大会计划 = 玩家和 Yuki 正在前往车站，准备参加烟火大会。
```

第二轮：

```text
用户：嗯，那走吧。
```

期望：

```text
不调用向量库
注入状态板
角色知道当前在前往车站
```

第三轮：

```text
用户：你还记得我之前说过喜欢什么颜色吗？
```

期望：

```text
Retrieval Gate 触发长期召回
调用 Embedding / LanceDB
召回相关 approved 记忆卡片
```

---

## 13. 分阶段施工计划

### Phase 0：准备与保护现有能力

- [ ] 跑通现有测试。
- [ ] 记录当前 `/health`、`/v1/models`、非流式、流式行为。
- [ ] 确认当前数据库 migration 机制。
- [ ] 确认 memory injector 和 retrieval orchestrator 的调用点。
- [ ] 新增 feature flags，默认启用状态板，但保留可关闭开关。

交付：

```text
无业务行为变化
新增配置项可读取
测试仍通过
```

### Phase 1：数据库与 Store

- [ ] 新增 `conversation_state_items` migration。
- [ ] 新增 `conversation_state_events` migration。
- [ ] 新增 `retrieval_decisions` migration。
- [ ] 新增 `SQLiteStateStore`。
- [ ] 写单元测试覆盖 CRUD。
- [ ] 确保 WAL / busy_timeout / foreign_keys 行为与现有 SQLite 一致。

交付：

```text
可以创建、读取、更新、resolve 状态项
可以记录 retrieval decision
```

### Phase 2：状态板渲染与注入

- [ ] 新增 `state_schema.py`。
- [ ] 新增 `state_renderer.py`。
- [ ] 新增 `state_injector.py`。
- [ ] 将状态板注入 pipeline，但先不做 State Updater。
- [ ] 允许手动插入状态项后，在下一轮请求注入。

交付：

```text
手动写入状态项后，聊天请求中出现 KokoroMemo 会话状态板
```

### Phase 3：Retrieval Gate

- [ ] 新增 `retrieval_gate.py`。
- [ ] 在 pipeline 中读取状态板后调用 Gate。
- [ ] Gate 决定是否调用长期召回。
- [ ] 将 decision 写入 `retrieval_decisions`。
- [ ] 支持 `always / never / auto` 三种模式。
- [ ] 补充关键词触发和新会话触发规则。

交付：

```text
普通短句可跳过 LanceDB
“还记得 / 上次 / 之前 / 约定”可触发 LanceDB
```

### Phase 4：State Updater 规则版

- [ ] 新增 `state_updater.py`。
- [ ] 实现 rule-based 初版。
- [ ] 支持 scene/location/main_quest/promise/boundary 的基础提取。
- [ ] 在非流式和流式完成后入队执行。
- [ ] 失败写入 jobs / events，不影响聊天。

交付：

```text
用户说“我们去车站吧”后，状态板出现当前地点 / 当前任务
```

### Phase 5：State Updater LLM 版

- [ ] 设计 LLM prompt。
- [ ] 要求输出严格 JSON。
- [ ] 做 JSON schema 校验。
- [ ] 做低置信过滤。
- [ ] 与 rule-based 合并。
- [ ] 防止 assistant-only 内容变成长期记忆。

交付：

```text
复杂剧情变化可自动进入状态板
```

### Phase 6：Admin API

- [ ] 新增状态板只读接口。
- [ ] 新增状态板写接口。
- [ ] 新增 retrieval decision 只读接口。
- [ ] 添加鉴权。
- [ ] 添加测试。

交付：

```text
可通过 API 查看、编辑、resolve 状态项
```

### Phase 7：GUI 支持

- [ ] 新增“会话状态板”页面。
- [ ] 显示状态项分组。
- [ ] 支持编辑 / resolve / 删除。
- [ ] 新增 Retrieval Gate 调试面板。
- [ ] 与 Admin API 对接。

交付：

```text
首次使用者可以在界面中看懂当前剧情状态
```

### Phase 8：与记忆卡片联动

- [ ] 支持状态项链接 `memory_cards`。
- [ ] approved boundary / preference 卡片可投影为状态板条目。
- [ ] 状态项中的长期价值内容仍进入 memory_inbox。
- [ ] 状态项 resolved 不应删除长期 memory_cards。

交付：

```text
长期边界可常驻状态板；临时状态不会污染长期卡片
```

### Phase 9：项目设计文档合并

- [ ] 将本 TODO 的核心内容合并进项目设计。
- [ ] 在项目设计中新增“Hot Memory / 会话状态板”章节。
- [ ] 在架构图中加入 Conversation State Board。
- [ ] 在数据库设计中加入 `conversation_state_items` 等表。
- [ ] 在请求流程中加入 State Renderer、Retrieval Gate、State Updater。
- [ ] 在配置章节中加入 `hot_context`、`state_updater`、`retrieval_gate`。
- [ ] 在 MVP 和阶段计划中将状态板提前到 P0 / Phase 2。
- [ ] 在测试计划中加入状态板与 Gate 测试。
- [ ] 在 README 中加入“热记忆 / 温记忆 / 冷记忆”说明。

交付：

```text
项目设计与实现一致
README 与用户认知一致
Codex 后续施工有统一依据
```

---

## 14. 项目设计合并稿草案

完成代码后，将以下内容合并进项目设计文档。

### 14.1 新增章节：分层记忆架构

```text
KokoroMemo 使用四层记忆架构：

1. Raw Log 原始对话层
保存完整对话，用于溯源、导出、重新提炼。

2. Hot State 会话状态板
保存当前会话的热状态，包括当前场景、关键人物、主线任务、支线任务、未完成承诺、开放伏笔、关系状态和稳定边界。状态板默认每轮注入上下文。

3. Card Graph 记忆卡片图谱
保存经过审核的长期记忆卡片、标签、关系边和层级摘要。它负责跨会话长期稳定记忆。

4. Semantic Index 语义索引
使用 LanceDB 对 approved 卡片和摘要建立向量索引。该索引用于按需召回具体历史细节，可从 SQLite 重建。
```

### 14.2 新增章节：会话状态板

```text
会话状态板负责维护“当前正在发生什么”。它不是长期记忆库，而是当前会话的热状态缓存。状态板可以更自动地维护，因为它只影响当前会话；长期记忆仍必须通过 memory_inbox 和审核策略。

状态板默认每轮注入，用于减少不必要的向量检索，并提升当前剧情连续性。
```

### 14.3 新增章节：按需召回门控

```text
Retrieval Gate 用于判断当前请求是否需要调用长期记忆检索。普通剧情推进和短句互动可只依赖会话状态板；当用户提到“记得、上次、之前、约定”等历史触发词，或状态板置信度不足时，系统再调用 LanceDB、图扩展和可选 Rerank。
```

### 14.4 请求流程替换为

```text
1. 接收请求
2. 保存 raw request
3. 解析 user / character / conversation
4. 读取会话状态板
5. 渲染并准备注入 Hot Context
6. Retrieval Gate 判断是否长期召回
7. 必要时执行长期记忆召回
8. 注入状态板与长期记忆
9. 转发真实 LLM
10. 返回响应
11. 后台保存消息
12. 后台 State Updater 维护状态板
13. 后台 Memory Extractor 生成候选长期记忆
```

---

## 15. Codex 执行提示词

可以直接把下面这段给 Codex：

```text
请根据《KokoroMemo 热记忆层与按需召回改造 TODO》进行增量施工。

本次目标是在现有 KokoroMemo 记忆卡片与 LanceDB 语义索引架构上，加入会话状态板和按需召回门控。不要重写项目，不要破坏现有代理、流式转发、SQLite 对话落盘、memory_cards、memory_inbox、memory_edges、memory_summaries 和 LanceDB approved 索引能力。

请先完成 Phase 0 到 Phase 3：
1. 新增配置项 hot_context、state_updater、retrieval_gate；
2. 新增 SQLite 表 conversation_state_items、conversation_state_events、retrieval_decisions；
3. 新增 SQLiteStateStore；
4. 新增 state_schema、state_renderer、state_injector；
5. 新增 retrieval_gate；
6. 在 chat pipeline 中注入会话状态板；
7. 让 Retrieval Gate 可以决定是否跳过长期召回；
8. 补充对应测试。

完成后请输出：
- 改动文件列表
- 数据库 migration 说明
- 新增配置说明
- 测试结果
- 下一阶段建议

不要直接做 GUI 和复杂 LLM State Updater，先保证状态板能手动写入、自动注入、Gate 能跳过向量检索。
```

---

## 16. 最终一句话

本次改造的目标是让 KokoroMemo 形成更轻、更适合 AIRP 的记忆调用策略：

```text
状态板负责当前剧情连续性；
卡片图谱负责长期记忆稳定性；
向量索引负责按需历史细节召回。
```
