# KokoroMemo 项目设计文档

## 1. 总体架构

KokoroMemo 是一个本地化 AI 长期记忆代理，以 OpenAI-compatible 透明代理形式部署在用户的 AIRP 客户端和真实大模型之间。

```text
┌───────────────────┐      ┌──────────────────────────────────────────┐      ┌───────────────┐
│  AIRP 客户端       │─────▶│  KokoroMemo 本地代理                      │─────▶│  真实聊天模型   │
│  (SillyTavern等)  │◀─────│  127.0.0.1:14514                         │◀─────│  (Cloud LLM)  │
└───────────────────┘      └──────────────────────────────────────────┘      └───────────────┘
                                         │
                            ┌────────────┼────────────────┐
                            ▼            ▼                ▼
                       SQLite        LanceDB         填表/判断 LLM
                    (记忆本体)     (语义索引)        (便宜快速模型)
```

### 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+ / FastAPI / uvicorn / aiosqlite |
| 向量存储 | LanceDB + PyArrow（桌面端）/ SQLite + numpy（Termux 降级） |
| 前端 | Vue 3 / TypeScript / Naive UI / vue-i18n |
| 桌面 | Tauri 2 (Rust) |
| Web UI | 后端直接 serve Vue 静态文件（无需 Tauri） |
| 移动端 | Termux + proot-distro Ubuntu（安卓，避免 ARM 原生编译问题） |
| 发布 | Nuitka 编译 + GitHub Actions 三平台 CI |

### 端口

| 端口 | 用途 |
|---|---|
| `14514` | 主 API（OpenAI-compatible 代理 + Admin API + WebSocket + Web UI） |
| `5173` | 前端开发服务器（`npm run dev`） |

Web UI 模式下，后端同时服务 API 和 Vue 前端静态文件，统一监听 `14514`。适合 Termux / 无桌面环境部署。

---

## 2. 三层记忆架构

KokoroMemo 的核心设计决策是**分层记忆**，避免每轮都做昂贵的向量检索：

### 热记忆（Hot State）— 会话状态板

- **职责**：维护当前会话的实时上下文状态（场景、心情、任务、关系等）
- **存储**：SQLite `conversation_state_items` 表
- **注入时机**：每轮请求前，渲染为文本注入系统提示词
- **更新时机**：每轮对话后，由 State Filler 模型自动更新
- **数据结构**：模板 → 标签页 → 字段，14 种语义类别
- **生命周期**：当前会话临时状态，不跨会话

### 温记忆（Card Graph）— 记忆卡片图谱

- **职责**：存储经审核的跨会话长期记忆
- **存储**：SQLite `memory_cards` + `memory_edges` 表
- **注入时机**：由 Retrieval Gate 按需触发
- **数据结构**：记忆卡片（typed, scoped, tagged） + 关系边（supports, constrains, contradicts, supersedes, elaborates, belongs_to, continues, same_as）
- **生命周期**：永久，可编辑/废弃/替代

### 冷记忆（Semantic Index）— 向量索引

- **职责**：为温记忆提供语义相似度检索入口
- **存储**：LanceDB 本地文件（桌面端）或 SQLite + numpy（ARM/Termux 自动降级）
- **特点**：可从 SQLite 完全重建，是索引而非数据本体
- **调用条件**：仅在 Retrieval Gate 判定需要时调用
- **降级**：`services.py` 在 `import lancedb` 失败时自动使用 `SqliteVectorStore`，API 完全兼容，暴力余弦搜索在 <5000 卡片下性能足够

---

## 3. 请求处理流程

```text
[1] 接收 POST /v1/chat/completions
        │
[2] request_parser: 解析 X-User-Id / X-Character-Id / X-Conversation-Id
        │
[3] upsert_conversation: 注册/更新会话记录
        │
[4] state_renderer: 读取并渲染当前会话状态板
[5] state_injector: 注入状态板到消息数组（system 消息后）
        │
[6] retrieval_gate: 判断是否需要长期记忆检索
        │  ├─ 触发条件: 新会话 / 关键词 / 周期刷新 / 低置信度
        │  └─ 跳过条件: 文本过短 / 状态板已充分
        │
[7] card_retriever (条件触发):
        │  ├─ Route 1: Pinned/boundary 卡片 (SQLite 直接)
        │  ├─ Route 2: 向量检索 (Embedding + LanceDB)
        │  ├─ Route 3: 最近重要卡片 (SQLite)
        │  └─ Route 4: 图扩展 (关系边遍历)
        │
[8] 可选 Rerank 重排序
[9] card_injector: 注入召回的记忆卡片
        │
[10] llm_providers: 转发到真实 LLM（支持 4 种 Provider）
[11] 流式/非流式返回响应
        │
[12] 后台异步任务:
        ├─ state_filler: 更新会话状态板字段
        └─ judge + card_extractor: 提取候选记忆 → 审核策略 → 入库/待审/拒绝
```

### 时序图（聊天补全请求）

```mermaid
sequenceDiagram
    participant Client as 客户端（AIRP）
    participant Proxy as routes_openai
    participant App as app.sqlite
    participant Mem as memory.sqlite
    participant Gate as retrieval_gate
    participant Vec as LanceDB
    participant LLM as LLM Provider
    participant Judge as 判断模型
    participant WS as 事件总线

    Client->>Proxy: POST /v1/chat/completions
    Proxy->>App: upsert_conversation + upsert_character
    Proxy->>Mem: 读会话状态板 + 挂载库
    Proxy->>Gate: 决定是否检索
    alt 检索
        Proxy->>Vec: 向量召回 + 多路融合
        Vec-->>Proxy: top-k 候选卡片
    end
    Proxy->>Proxy: 注入热上下文 + 状态板 + 召回卡
    Proxy->>LLM: 转发请求（流式/非流式）
    LLM-->>Proxy: 响应
    Proxy-->>Client: 透传响应
    Note over Proxy: 后台异步抽取
    Proxy-)Judge: 候选记忆抽取
    Judge-->>Proxy: JSON {memories: [...]}
    Proxy->>Mem: 写入 cards / inbox
    Proxy->>Vec: 向量同步（失败入 jobs 队列）
    Proxy-)WS: emit card_approved / inbox_new
```

---

## 3.5 实时事件总线（WebSocket）

后端 `/ws` 端点 + `app/core/events.py` 内存级 pub/sub，将关键事件实时推送到前端，无需轮询。

### 已实现事件

| 事件 | 触发点 | Payload |
|---|---|---|
| `card_approved` | `card_extractor.py` 自动批准并写入卡片时 | `{card_id, content, memory_type, importance}` |
| `inbox_new` | `card_extractor.py` 候选送入审核队列时 | `{card_id, content, memory_type, importance}` |

### 前端消费

`gui/src/components/EventBridge.vue` 全局组件：
- 应用启动时自动连接 `/ws`，断线后 5s 重连
- 收到事件后：① 触发 toast 通知（`inbox_new` 提示去审核、`card_approved` 提示已自动批准）；② 通过 `window.dispatchEvent('kokoromemo:event')` 派发，相关页面（Inbox、Dashboard）订阅并刷新数据

设计目标：避免页面 setInterval 轮询，提供更即时的响应反馈。

---

## 4. 模型分工

KokoroMemo 使用 4 种模型，各司其职：

| 模型 | 配置位置 | 类型 | 调用时机 | 职责 |
|---|---|---|---|---|
| 对话大模型 | `llm.*` | Chat | 每次请求 | 生成 AI 角色的回复 |
| 记忆判断模型 | `memory.judge.*` | Chat (cheap) | 每轮结束后 | 判断哪些内容值得写入长期记忆 |
| 状态板填表模型 | `memory.state_updater.*` | Chat (cheap) | 每轮结束后 | 更新当前会话的状态板字段 |
| 向量化模型 | `embedding.*` | Embedding | 检索时 + 入库时 | 文本向量化，语义检索 |

**Fallback 链**：State Filler → Judge → 主 LLM。用户可只配一个模型让三者共用。

---

## 5. 记忆提取与审核流水线

```text
对话完成
    │
    ▼
[Judge LLM] 分析 user + assistant 消息
    │
    ▼ 输出: JSON { memories: [...] }
    │
[过滤] importance < 0.45 → 丢弃
[过滤] confidence < 0.55 → 丢弃
    │
    ▼
[语义去重] Embedding 相似度 > 0.92 → 跳过
    │
    ▼
[审核策略 review_policy]
    ├─ 低风险 + 高置信 → auto_approve → 直接入库 + 向量同步
    ├─ 关系/边界变化 → pending → 进入收件箱等待用户审核
    └─ 助手单方面编造 → reject → 丢弃
    │
    ▼ (入库)
[SQLite] memory_cards 表
[LanceDB] vector_sync 向量同步
[WebSocket] 推送 card_approved / inbox_new 事件
```

### 离线导入路径

除了实时对话抽取，也可以从历史聊天日志批量提取候选记忆：

- `POST /admin/import/sillytavern` — 接收 SillyTavern 原生 JSONL 或 OpenAI 格式 JSONL，落地为一个 `conv_import_*` 会话
- `POST /admin/import/{conversation_id}/extract-memories` — 对该会话的 user/assistant 配对批量调用 `extract_and_route`（与上述抽取流水线相同），结果同样进入 inbox 等待审核

GUI 入口：记忆库页"导入 SillyTavern"按钮，导入完成后弹窗确认是否立即提取。

---

## 6. 数据存储设计

### SQLite 数据库

| 数据库 | 路径 | 内容 |
|---|---|---|
| app.sqlite | `./data/app.sqlite` | 用户、角色（首次对话懒插入）、会话注册、角色默认配置 |
| memory.sqlite | `./data/memory/memory.sqlite` | 记忆卡片、卡片版本（memory_card_versions）、收件箱、关系边、摘要、记忆库、挂载、状态板、检索决策 |
| chat.sqlite | `./data/conversations/{id}/chat.sqlite` | 逐会话对话日志 |

### LanceDB / SQLite 向量存储

| 路径 | 内容 |
|---|---|
| `./data/vector_indexes/{model}_{dim}/lancedb/` | LanceDB 向量索引（桌面端） |
| `./data/vector_indexes/{model}_{dim}/lancedb/vectors.sqlite` | SQLite 向量存储（LanceDB 不可用时自动创建） |

### 设计原则

- **SQLite 是数据本体**，LanceDB 是可重建索引
- **WAL 模式** + busy_timeout 保证异步并发安全
- **UNIQUE 约束**确保同一会话、同一字段只有一个活跃状态项
- **软删除**（status 字段）保留审计追踪
- **卡片版本表**（`memory_card_versions`）保留每次内容修改的历史快照，支持基于 `supersedes_card_id` 的卡片合并/替换

---

## 7. 前端架构

### 页面结构

| 路由 | 页面 | 职责 |
|---|---|---|
| `/dashboard` | Dashboard.vue | 服务状态、记忆系统统计、待审核数点击直达 |
| `/memories` | Memories.vue | 记忆卡片 CRUD、记忆库管理、SillyTavern 导入 |
| `/inbox` | Inbox.vue | 待审核候选记忆批准/拒绝（带备注） |
| `/state` | ConversationState.vue | 会话状态板管理（模板、标签页、字段） |
| `/characters` | Characters.vue | 已发现角色的默认状态板模板/挂载库绑定 |
| `/memory-graph` | MemoryGraph.vue | 记忆卡片关系图谱可视化（力导向布局） |
| `/settings` | Settings.vue | 全局配置（5 标签页：模型 / 记忆 / 状态填表 / 服务 / 高级） |

### 全局组件

- `EventBridge.vue` — 全局 WebSocket 事件桥；连接 `/ws`、自动 5s 重连、把 `card_approved` / `inbox_new` 事件转为 toast 通知 + 通过 window CustomEvent 派发给各页面触发自动刷新

### UI 设计原则

- 暗色主题（#0f0f11 背景，#18181b 卡片）
- 紫色主色调（#a78bfa）
- Naive UI 组件库统一风格
- 分区卡片布局：每个卡片职责单一
- 下拉菜单收纳低频操作，减少视觉噪音
- 所有确认操作使用 NPopconfirm + i18n 按钮文本
- 中英双语（vue-i18n）

### 设置页 5 标签页

| 标签 | 内容 |
|---|---|
| 模型配置 | 对话大模型、记忆判断模型、Embedding、Rerank |
| 记忆配置 | 长期记忆系统基础参数、向量索引维护（重建 / 异步迁移 / sync 重试） |
| 状态板填表 | 填表模型独立配置 |
| 服务配置 | 端口、时区、语言、关闭到托盘、更新检测 |
| 高级 | 记忆系统内部参数（左菜单 + 右面板布局）：会话自动检测、记忆总开关、注入作用域、抽取阈值、评分权重、检索门控、热上下文 14 段 |

每个高级配置分组配独立帮助按钮，弹窗逐字段说明含义、推荐值与典型场景。

---

## 8. 会话状态板设计

### 模板系统

```text
StateBoardTemplate
  ├─ template_id, name, is_builtin
  ├─ StateBoardTab[]
  │    ├─ tab_id, label, sort_order
  │    └─ StateBoardField[]
  │         ├─ field_id, field_key, label, description
  │         ├─ ai_writable, include_in_prompt, user_locked
  │         └─ field_type, default_value, options
  └─ 绑定: conversation_state_boards(conversation_id → template_id)
```

### 填表流程

1. 每轮对话完成后，State Filler LLM 收到用户+AI 的对话文本
2. System Prompt 包含当前模板所有可写字段及其当前值
3. 模型返回 JSON `{ updates: [{field_key, value, confidence, reason}] }`
4. 低于 min_confidence 的更新被跳过
5. 被用户锁定的字段被跳过
6. 通过的更新 upsert 到 SQLite

### 注入渲染

- 按模板标签页 → 字段顺序渲染
- 格式: `【标签名】\n- 字段名：内容`
- 受 max_chars 预算限制（默认 1200）
- 超预算时截断最低优先级的项

---

## 9. 检索门控（Retrieval Gate）

Retrieval Gate 是 v0.2.0 引入的优化机制，避免每轮都执行昂贵的向量检索。

### 决策逻辑

支持 4 种模式：

```python
if mode == "always": return True
if mode == "never": return False
if mode == "keyword_only":
    return contains_trigger_keywords(user_text)  # 仅关键词匹配时检索
# mode == "auto":
if is_new_session: return True
if contains_trigger_keywords(user_text): return True
if turn_number % vector_search_every_n_turns == 0: return True
if state_board_avg_confidence < threshold: return True
if len(user_text) < 4: return False
if state_is_sufficient: return False
return False
```

### 触发后执行

1. query_builder 从最近 N 轮对话构建检索查询
2. Embedding 模型向量化查询文本
3. LanceDB cosine 相似度搜索 top-K
4. 图扩展（遍历关系边获取关联卡片）
5. 加权评分（vector 55% + importance 20% + recency 10% + scope 10% + confidence 5%）
6. 可选 Rerank 重排序
7. 取 final_top_k 条注入

---

## 10. 发布与分发

### CI/CD Pipeline（GitHub Actions）

```text
Tag v* → 触发 release.yml
  ├─ Job 1: Nuitka 编译 Python 后端
  │    ├─ Windows x86_64
  │    ├─ Linux x86_64
  │    └─ macOS aarch64
  ├─ Job 2: Tauri 打包桌面应用
  │    ├─ Windows: Portable ZIP + MSI
  │    ├─ Linux: AppImage
  │    └─ macOS: DMG
  └─ Job 3: 发布到 GitHub Release
```

### Windows 特殊处理

Windows 发行版将后端二进制内嵌到 `KokoroMemo.exe`（`kokoromemo_embedded_backend` cfg），确保 Portable 和 MSI 都是单 exe 分发。

---

## 10.5 错误处理与降级矩阵

KokoroMemo 强调"任何记忆系统失败都不影响聊天主链路"。下表列出关键失败场景及降级策略：

| 失败场景 | 触发位置 | 降级行为 | 用户可见影响 |
|---|---|---|---|
| LLM 上游超时 / 5xx | `proxy/llm_providers.py` | 直接把异常透传给客户端，不写记忆 | 客户端收到 502/超时；后续轮次正常 |
| 嵌入模型超时 / 失败 | `card_extractor` 抽取阶段 | 跳过本批向量同步，候选仍写入 SQLite，进入 `vector_sync` jobs 队列 | 候选可在审核页见到，召回时该卡暂不可用；可手动"重试失败的向量同步" |
| 嵌入模型超时 / 失败 | 召回查询阶段 | `card_retriever` 捕获异常并 `continue`，仅返回非向量路（pinned + recent + graph） | 召回质量下降但不中断 |
| Rerank 服务失败 | `card_retriever` 末尾 | 跳过 rerank，按打分排序直接取 `final_top_k` | 召回顺序略差 |
| 判断模型失败 | `card_extractor` 判断阶段 | 若开启 `extraction.fallback_rule_based` 则回退到正则规则；否则丢弃本轮候选 | 候选数减少 |
| LanceDB 索引损坏 / 维度不匹配 | `LanceDBStore.connect` | 启动时抛 `ValueError`，需要用户在设置页执行"重建向量索引" | 服务可启动但向量召回不可用 |
| 索引迁移中途失败 | `_run_index_migration` | 原子化策略：staging 表被 drop，老索引完整保留 | 用户在仪表盘看到 `failed` 状态，老索引继续工作 |
| 磁盘满 | SQLite 写操作 | aiosqlite 抛 `OperationalError`，调用方捕获并 log，候选丢失 | 服务降级；建议外部监控磁盘 |
| 数据库锁等待 | SQLite | `busy_timeout=5000` ms 后抛 `OperationalError`；上层捕获并 log | 偶发抖动 |
| WebSocket 连接断开 | 前端 `EventBridge.vue` | 5s 后自动重连；重连前页面回退到手动刷新 | 短暂无实时通知 |
| 配置文件损坏 | `load_config` | 启动失败，需要手动修复 YAML | 服务无法启动 |

设计原则：
- **静默降级**：能继续提供主功能就继续，不阻塞用户对话
- **可观察**：日志中必有 WARNING 或 ERROR 级别记录，方便排查
- **可恢复**：用户能在 GUI 内手动触发重试 / 重建（向量同步重试、索引重建等）

---

## 11. 设计决策记录

### 为什么用 SQLite 而不是 PostgreSQL？

- 本地优先：用户不需要安装额外数据库服务
- 零配置：WAL 模式 + aiosqlite 即可满足并发需求
- 便携：单文件数据库，方便备份和迁移
- 性能足够：AIRP 场景下并发量低，SQLite 绰绰有余

### 为什么用 LanceDB 而不是 Milvus/Pinecone？

- 本地文件存储，不需要额外服务
- 轻量级，适合桌面应用嵌入
- 支持 cosine similarity，满足语义检索需求
- 可从 SQLite 完全重建，不是数据本体

### 为什么记忆判断和状态板填表分开？

- **产出不同**：一个产出长期记忆卡片，一个产出临时会话状态
- **故障隔离**：一个出错不影响另一个
- **提示词精简**：各自 prompt 专注自己的任务
- **Fallback 链共享**：可以只配一个模型让两者共用

### 为什么不直接把聊天记录放进向量库？

- AIRP 对话包含大量临时剧情、玩笑、误会
- 全量入库会导致记忆污染
- 记忆卡片形式支持审核、编辑、废弃、关系结构
- 用户可控比全自动更重要
