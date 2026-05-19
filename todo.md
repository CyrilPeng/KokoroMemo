# KokoroMemo 优化计划：SDK 抽象、检索解释与 Benchmark 体系

> 目标：借鉴 `su-memory-sdk` 的 SDK 抽象、检索解释与 benchmark 体系，但保持 KokoroMemo 的核心定位：面向 AIRP / AI 角色扮演的本地长期记忆代理、状态板与审核控制系统。

## 一、总体目标

### 1. 产品目标

- 降低“GUI 设置完成但后端实际未生效”的配置链路风险。
- 提升记忆召回、状态板注入与记忆库挂载的可解释性。
- 建立面向 AIRP 场景的质量评估体系，发布前能量化检查记忆能力是否退化。
- 为未来插件、脚本、外部客户端或轻量 SDK 接入打基础。

### 2. 技术目标

- 将记忆库挂载、记忆检索、状态板更新、注入构建等核心逻辑从 API / GUI 编排中抽出，形成内部服务层。
- 为每次检索与注入生成结构化 trace，记录触发原因、候选、过滤、排序和最终注入结果。
- 建立可重复运行的 benchmark 数据集和指标，覆盖角色连续性、记忆污染、状态板更新和 token 成本。
- 保持现有用户功能稳定，不做一次性大重构。

## 二、设计原则

- **先内部抽象，后对外 SDK**：先让后端内部调用统一服务层，稳定后再考虑暴露外部 SDK。
- **先观测，后调参**：先记录检索解释与质量指标，再做召回策略优化。
- **场景优先**：benchmark 优先覆盖 KokoroMemo 的 AIRP 核心场景，而不是照搬通用 RAG 数据集。
- **最小迁移**：尽量复用现有 SQLite 表、API 和 GUI 页面，避免破坏用户已有数据。
- **可回滚**：每个阶段保持独立提交，出现问题可以单独回退。

## 三、Phase A：内部 SDK / Engine 抽象

### 目标

把目前分散在 `app/api`、`app/pipeline`、`app/memory`、`app/storage` 中的核心业务逻辑收敛为稳定的内部服务层，降低重复实现和配置不一致风险。

### 建议新增模块

- `app/services/memory_engine.py`
- `app/services/mount_resolver.py`
- `app/services/retrieval_engine.py`
- `app/services/state_board_engine.py`
- `app/services/injection_engine.py`
- `app/services/types.py`

### 子任务

- [x] 新增 `MountResolver`：统一解析显式记忆库、挂载预设、角色默认配置、会话配置和默认配置。
- [ ] 新增 `MemoryEngine`：封装记忆写入、候选创建、审核状态转换、写入库选择。
- [ ] 新增 `RetrievalEngine`：封装 retrieval gate、query build、card retrieval、rerank、过滤和结果归一化。
- [ ] 新增 `StateBoardEngine`：封装状态板模板解析、表格读取、AI 填表、手动更新和注入渲染。
- [ ] 新增 `InjectionEngine`：统一构建最终注入上下文，包括长期记忆、状态板、策略说明和 token 预算。
- [ ] 将 `/admin/conversations/{id}/config`、聊天管线和角色默认配置逐步迁移到服务层。
- [ ] 为每个服务层对象增加 focused unit tests，避免只通过 API 测试覆盖。

### 验收标准

- [ ] GUI 保存会话策略、角色默认配置、新会话默认配置都使用同一套挂载解析逻辑。
- [ ] 聊天管线写入记忆时不直接手写写入库解析逻辑。
- [ ] 现有后端测试全部通过。
- [ ] 新增服务层测试覆盖挂载预设、写入库、默认配置继承和显式覆盖。

### 风险

- 迁移过程可能改变现有边界行为。
- 服务层抽象过早过大可能导致“新壳套旧逻辑”。

### 控制方式

- 每次只迁移一条链路，例如先迁移挂载解析，再迁移检索，再迁移状态板。
- 保持旧 API 响应结构不变。

## 四、Phase B：检索解释 Trace 体系

### 目标

让用户和开发者知道：为什么触发检索、为什么召回这些记忆、哪些记忆被过滤、最终注入了什么。

当前状态：已实现 `retrieval_decisions` 门控决策日志和查询 API，可查看每轮是否触发检索及原因；尚未实现候选、过滤、排序和最终注入结果级别的完整 trace。

### 建议新增数据结构

- `RetrievalTrace`
- `RetrievalCandidateTrace`
- `InjectionTrace`
- `StateBoardTrace`

### 建议新增字段

每条候选记忆至少记录：

- `card_id`
- `library_id`
- `source_conversation_id`
- `source_character_id`
- `query_text`
- `vector_score`
- `keyword_score`
- `recency_score`
- `rerank_score`
- `final_score`
- `selected`
- `filtered_reason`
- `injection_reason`

### 建议新增存储

- 可先使用 SQLite 表：`retrieval_traces`、`retrieval_trace_candidates`。
- 或先以 JSON 存入现有注入日志，稳定后再拆表。

### 子任务

- [ ] 在 `RetrievalEngine` 中生成 trace，不改变现有召回结果。
- [ ] 为 retrieval gate 记录触发决策：是否检索、触发关键词、判断依据。
- [ ] 为候选记忆记录来源库、分数、过滤原因和最终是否注入。
- [ ] 为状态板注入记录模板、标签页、行数、token 估算和渲染摘要。
- [x] 新增管理 API：按会话查询最近注入 trace。
- [ ] GUI 增加“检索解释 / 注入来源”面板。
- [ ] 在注入预览中支持点击某条记忆查看来源和入选原因。

### GUI 建议

新增侧栏或抽屉：

| 区块 | 内容 |
|---|---|
| 检索触发 | 本轮是否触发长期记忆检索，为什么触发 |
| 查询构造 | 原始用户输入、改写后的检索 query、关键词 |
| 候选列表 | 候选记忆、分数、来源库、过滤状态 |
| 最终注入 | 实际进入 prompt 的记忆和状态板片段 |
| 问题诊断 | 未召回、跨角色过滤、库未挂载等原因提示 |

### 验收标准

- [x] 每次聊天后可以查询本轮记忆注入 trace。
- [x] 用户能看到每条注入记忆来自哪个记忆库。
- [ ] 用户能看到某条记忆没有被注入的原因，例如库未挂载、角色不匹配、分数过低。
- [ ] trace 记录失败不影响主聊天流程。

## 五、Phase C：AIRP 场景 Benchmark 体系

### 目标

建立 KokoroMemo 自己的质量评估，而不是只依赖人工试用。重点评估角色连续性、世界观隔离、记忆污染、状态板更新和 token 成本。

### 建议目录

- `benchmarks/airp_cases/`
- `benchmarks/fixtures/`
- `benchmarks/run_airp_benchmark.py`
- `benchmarks/metrics.py`
- `benchmarks/reports/`

### Benchmark 类型

| 类型 | 评估目标 | 样例 |
|---|---|---|
| 称呼记忆 | 是否能记住用户希望的称呼 | 用户要求角色称呼自己“小凛”，隔多轮后是否召回 |
| 偏好记忆 | 是否能保存和召回用户偏好 | 用户不喜欢咖啡，之后角色是否避免推荐咖啡 |
| 边界记忆 | 是否能记住禁忌和边界 | 用户要求不要提某话题，后续是否避免 |
| 多角色隔离 | A 角色记忆是否不会污染 B 角色 | 与角色 A 的秘密不会被角色 B 召回 |
| 世界观隔离 | 不同记忆库挂载是否隔离 | 赛博世界观记忆不会进入奇幻世界观 |
| 状态板连续性 | 场景、地点、任务、关系是否正确更新 | 剧情地点从图书馆转移到车站后状态板同步更新 |
| 误记忆审核 | 不确定内容是否进入待审核而非直接写入 | 玩笑、假设、梦境不应稳定入库 |
| token 成本 | 注入内容是否足够精简 | 正确召回前提下 token 数不过高 |

### 指标设计

- `recall_accuracy`：应召回记忆中实际召回的比例。
- `false_positive_rate`：不应召回但被注入的比例。
- `cross_character_leak_rate`：跨角色污染率。
- `cross_library_leak_rate`：跨记忆库污染率。
- `state_update_accuracy`：状态板更新正确率。
- `review_precision`：应进入审核的候选是否正确进入审核。
- `avg_injected_tokens`：平均注入 token 数。
- `latency_ms`：检索和注入构建耗时。

### 子任务

- [x] 设计 benchmark case JSON 格式。
- [ ] 编写 10 个最小 AIRP case，覆盖称呼、偏好、多角色隔离和状态板。
- [x] 编写 benchmark runner，支持使用 fake LLM / mock embedding 保证可重复。
- [x] 输出 markdown 报告和 JSON 报告。
- [x] 在 CI 中加入轻量 benchmark smoke test。
- [ ] 发布前手动运行完整 benchmark，记录版本间变化。

### 验收标准

- [x] 本地可以一条命令运行 benchmark。
- [x] benchmark 不依赖真实外部 API 即可跑 smoke test。
- [ ] 报告能显示本次版本相对上次版本的指标变化。
- [ ] 当跨角色污染率或挂载库污染率升高时，测试能失败或给出警告。

## 六、Phase D：策略可解释与用户可调

### 目标

在已有 trace 和 benchmark 基础上，把检索策略产品化，让用户能选择更适合自己的行为模式。

### 建议新增策略

| 策略 | 行为 |
|---|---|
| 保守召回 | 更少注入，降低污染，适合严格角色扮演 |
| 平衡召回 | 默认策略，兼顾连续性和污染控制 |
| 高召回 | 尽量补充上下文，适合资料库问答或长剧情回顾 |
| 状态板优先 | 优先注入状态板，长期记忆只补充关键事实 |
| 记忆优先 | 优先长期记忆，状态板作为摘要补充 |

### 子任务

- [ ] 新增 retrieval profile 配置。
- [ ] 将分数阈值、时间衰减、库过滤、角色过滤、token 预算参数化。
- [ ] GUI 增加策略选择，不暴露过多底层参数。
- [ ] 高级设置中允许查看和微调参数。
- [ ] benchmark 按策略输出对比报告。

### 验收标准

- [ ] 用户可以在会话策略中选择召回策略。
- [ ] 每种策略在 trace 中显示实际使用的阈值和 token 预算。
- [ ] benchmark 能比较不同策略的召回准确率、污染率和 token 成本。

## 七、Phase E：对外 SDK / 插件化准备

### 目标

在内部服务层稳定后，考虑暴露轻量 SDK 或插件接口，让外部脚本、客户端、第三方前端能复用 KokoroMemo 的记忆能力。

### 可能形式

- Python 内部 SDK：`kokoromemo_sdk`
- HTTP SDK：基于现有管理 API 封装客户端
- 插件 API：允许扩展 embedding、rerank、memory judge、state filler
- MCP / Tool 接口：让其他 Agent 工具调用记忆查询和写入

### 子任务

- [ ] 明确哪些能力可以对外开放，哪些只保留内部使用。
- [ ] 为 `MemoryEngine` 和 `RetrievalEngine` 定义稳定接口。
- [ ] 编写最小 Python client 示例。
- [ ] 编写 HTTP API 文档。
- [ ] 增加权限和鉴权说明，避免本地管理接口被误暴露。

### 验收标准

- [ ] 外部脚本可以查询某会话可见记忆。
- [ ] 外部脚本可以提交候选记忆到审核箱。
- [ ] 外部脚本可以获取检索解释 trace。
- [ ] 不破坏现有 GUI 和代理使用方式。

## 八、推荐优先级

### P0：必须优先

- [x] `MountResolver` 内部抽象。
- [ ] 会话配置、角色默认配置、新会话默认配置统一使用挂载解析。
- [x] 检索 trace 最小闭环：记录最终注入记忆来源库、来源会话、入选原因。
- [x] AIRP benchmark 最小样例：多角色隔离、记忆库隔离、称呼记忆。

### P1：强烈建议

- [ ] GUI 检索解释面板。
- [ ] 状态板 trace。
- [x] benchmark markdown 报告。
- [ ] 召回策略 profile。

### P2：后续增强

- [ ] 对外 Python SDK。
- [ ] 插件系统。
- [ ] 多策略自动 A/B benchmark。
- [ ] 可视化检索路径图。

## 九、阶段提交建议

每个阶段建议独立中文 commit：

1. `抽象记忆库挂载解析服务`
2. `统一会话与角色默认挂载生效链路`
3. `记录记忆检索与注入解释信息`
4. `新增检索解释管理接口`
5. `增加状态板注入来源面板`
6. `建立 AIRP 记忆场景基准测试`
7. `增加召回策略配置与基准报告`

## 十、完成后的预期收益

- 配置链路更稳定：GUI、API、聊天管线不会各自解析挂载库。
- 用户信任更高：能看到每条记忆为什么被注入。
- 调试效率更高：出现错召回、漏召回、跨角色污染时能快速定位。
- 发布质量更高：benchmark 能在发布前发现记忆能力退化。
- 架构更可扩展：未来可以做插件、SDK、外部客户端接入，而不需要重写核心逻辑。

## 十一、暂不建议做的事情

- 暂不照搬 su-memory-sdk 的大而全插件/商业/支付体系。
- 暂不把项目定位改成通用 RAG SDK。
- 暂不引入过重的默认依赖，例如强制 FAISS 或 sentence-transformers。
- 暂不在 GUI 暴露过多检索参数，避免普通用户困惑。
- 暂不一次性重构整个状态板，应先抽象后迁移。
