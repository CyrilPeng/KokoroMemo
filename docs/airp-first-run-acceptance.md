# 首次 AIRP 成功路径验收清单

这份清单用于验证 KokoroMemo 的核心体验是否跑通：用户能把一个 AIRP 客户端接入本地代理，并看到角色连续性真的发生。

目标不是覆盖全部功能，而是确认最小可用闭环：

```text
接入客户端 -> 产生对话 -> 形成候选记忆/状态 -> 审核或确认 -> 下一轮召回/注入 -> 用户能解释发生了什么
```

## 验收前准备

- 后端或桌面版能正常启动。
- GUI 首页能显示服务可用。
- 设置页已配置聊天模型 Provider、Base URL、API Key 和模型名。
- 记忆判断模型和状态板填表模型能连接；如果暂未配置，至少确认聊天代理链路可用。
- AIRP 客户端使用 OpenAI-compatible 接入，并填写 GUI 显示的 `OpenAI Base URL`。

建议客户端请求带上：

```text
X-User-Id: default
X-Character-Id: first_run_character
X-Conversation-Id: first_run_conversation
```

## 路径 1：接入代理成功

操作：

1. 打开“设置 -> 接入向导”。
2. 选择“普通角色扮演”。
3. 复制 `OpenAI Base URL` 到 AIRP 客户端。
4. 在客户端发送一句普通问候，例如“你好，今天我们从咖啡馆开始。”。

通过标准：

- 客户端能收到模型回复。
- KokoroMemo “总览”能看到最近会话或服务请求变化。
- 没有要求用户理解内部端口、数据库或向量索引细节。

失败排查：

- 客户端连接失败：优先确认 GUI 显示的实际端口，而不是固定假设 `14514`。
- 模型无响应：先在设置页测试聊天模型连接。
- 多轮会话混乱：确认客户端是否稳定传入同一个 `X-Conversation-Id`。

## 路径 2：角色记住稳定信息

操作：

1. 用户对角色说：“以后请叫我小凛，我喜欢安静一点的叙事节奏。”。
2. 继续聊 2-3 轮无关内容。
3. 打开“记忆审核”，查看是否出现称呼或偏好候选。
4. 批准合理候选，拒绝临时玩笑或误解。
5. 用户问：“你还记得该怎么称呼我吗？”。

通过标准：

- 候选记忆能进入审核流程。
- 用户能看懂候选为什么应该被批准或拒绝。
- 下一轮对话能召回称呼或偏好。
- “AIRP 召回解释”或“注入来源”能看到相关记忆卡片和选中原因。

失败排查：

- 没有候选：检查记忆判断模型配置和后台日志。
- 候选质量差：检查本轮是否只是临时玩笑，或 prompt 是否没有明确稳定信息。
- 召回失败：检查候选是否已批准、作用域是否匹配、Embedding 是否可用。

## 路径 3：多角色不串记忆

操作：

1. 使用 `first_run_character_a` 开始会话，并告诉角色 A 一个只属于它的信息。
2. 切换到 `first_run_character_b`，保持同一用户但更换 `X-Character-Id`。
3. 向角色 B 询问类似话题。
4. 打开“总览 -> AIRP 召回解释”或状态板右侧“注入来源”。

通过标准：

- 角色 A 的角色级记忆不会进入角色 B 的最终注入。
- 如果使用不同记忆库，未挂载库中的记忆不会出现在当前注入里。
- 用户能从“召回解释”判断为什么没有串记忆。

失败排查：

- 角色 ID 相同：检查客户端是否真的传入不同 `X-Character-Id`。
- 会话归属错误：在“会话管理”里修正角色归属。
- 记忆库污染：检查当前会话挂载库和写入库。

## 路径 4：状态板维护当前剧情

操作：

1. 在“状态板”中为当前会话选择“普通角色扮演”或“跑团 / 剧情模拟”。
2. 在对话里推进场景，例如“我们从咖啡馆转移到旧图书馆，目标是找失踪档案。”。
3. 回到“状态板”，查看连续性摘要和表格行。
4. 打开“注入预览”，确认当前场景和任务进入 prompt。

通过标准：

- 当前地点、任务或下一步能体现在状态板里。
- 临时剧情不会被误当成长期稳定记忆自动批准。
- 用户能区分“长期记忆”和“当前状态”。

失败排查：

- 状态板为空：检查状态板填表模型配置。
- 旧地点混入：确认会话 ID 是否复用错误，或是否把旧状态复制到了新会话。
- 长期记忆污染：在“记忆审核”拒绝临时剧情候选。

## 最小通过标准

一次首次体验验收至少需要满足：

- 10 分钟内完成客户端接入并收到回复。
- 至少产生 1 条可解释的候选记忆。
- 至少批准 1 条稳定记忆，并在后续对话中召回。
- 至少确认 1 次“AIRP 召回解释”或“注入来源”能解释召回内容。
- 至少确认 1 次状态板记录当前场景或任务。
- 多角色或多会话测试中没有明显串记忆。

## 官方验收接口

仪表盘中的“AIRP 首次成功验收”面板使用后端接口作为唯一判定来源：

```http
GET /admin/airp-first-run-status
```

这个接口用于把首次成功路径转成稳定契约，供 GUI、测试、CLI 或发布检查复用。它属于 admin API；如果已配置 `admin_token`，请求需要携带对应鉴权信息。返回字段：

- `ready`：核心 6 步是否全部完成。
- `progress`：核心步骤完成数、总数和百分比。
- `steps`：每一步的状态、入口和计数。
- `next_step`：第一项未完成的核心步骤；全部完成时为 `null`。
- `summary`：便于排查的原始计数，例如角色数、活跃会话数、候选记忆数、已批准记忆数和状态行数。

核心步骤含义：

| key | done 判定 | 入口 |
| --- | --- | --- |
| `config` | `config-status.health_score >= 100` | `/settings` |
| `role` | 已识别角色，或最近活跃会话带有 `character_id` | `/characters` |
| `conversation` | 至少存在 1 个活跃会话 | `/conversations` 或 `/settings` |
| `candidate` | 已有待审核候选，或已有批准记忆 | `/inbox` |
| `approved` | 至少已有 1 条已批准长期记忆 | `/inbox` 或 `/memories` |
| `state` | 最近活跃会话至少有 1 行 active 状态表格行 | `/state` |

`benchmark` 是发布检查步骤，不计入核心完成数。只有核心 6 步全部完成时，`benchmark.done` 才会为 `true`，并返回建议命令：

```bash
python benchmarks/run_airp_benchmark.py --smoke --enforce-thresholds --report-dir benchmarks/reports/first-run
```

响应片段示例：

```json
{
  "status": "ok",
  "ready": false,
  "progress": { "done": 3, "total": 6, "percentage": 50 },
  "next_step": {
    "key": "candidate",
    "done": false,
    "optional": false,
    "target": "/inbox",
    "action_key": "openInbox",
    "count": 0
  }
}
```

## 官方召回解释接口

仪表盘中的“AIRP 召回解释”面板使用后端接口汇总最近会话的 retrieval trace、最终注入记忆和隔离排除原因：

```http
GET /admin/airp-recall-explanation
GET /admin/airp-recall-explanation?conversation_id=<conversation_id>
GET /admin/airp-recall-explanation?trace_id=<trace_id>
```

这个接口用于回答“本轮为什么记得、为什么没有串、为什么某些记忆没有进入注入”。它不会启动真实召回，也不依赖外部模型；它读取已记录的 retrieval trace 和本地 SQLite 记忆卡片，生成可审计解释。返回字段包括：

- `selected_memories`：最终进入注入的记忆、召回路径、分数和选中原因。
- `excluded_memories`：被角色隔离、会话隔离、记忆库挂载、作用域或审核状态排除的记忆。
- `isolation`：最终选中的记忆是否通过角色/会话/记忆库隔离检查。
- `summary`：仪表盘和发布门禁使用的计数摘要。

更完整的契约说明见 [airp-recall-explanation.md](airp-recall-explanation.md)。

## 对应自动检查

首次体验验收后，建议运行：

```bash
python benchmarks/run_airp_benchmark.py --smoke --enforce-thresholds --report-dir benchmarks/reports/first-run
```

发布前运行完整基准：

```bash
python benchmarks/run_airp_benchmark.py --enforce-thresholds --report-dir benchmarks/reports/release
```

自动门禁会要求 `failed_cases <= 0`、`recall_accuracy >= 1.0`、`false_positive_rate <= 0.0`。如果 `character_isolation`、`library_isolation` 或 `conversation_isolation` 失败，不建议发布。

## 产品精简判断

后续清理功能时优先保留直接支撑这条路径的入口：

- 设置接入向导
- 总览里的角色连续性状态
- 记忆审核
- 状态板连续性摘要
- AIRP 召回解释和注入来源解释
- 会话管理中的角色归属修正

不直接服务首次成功路径的高级功能，应默认收纳到高级设置、帮助弹窗或二级入口。
