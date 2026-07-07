# AIRP 记忆账本

AIRP 记忆账本用于回答用户最常问的五件事：

- 这个角色现在记住了什么。
- 这些内容为什么进入长期记忆。
- 哪些候选还在等审核。
- 哪些内容被拒绝，为什么不会进入召回池。
- 当前剧情状态在状态板的哪里。

它和 [AIRP 召回解释](airp-recall-explanation.md) 的分工不同：记忆账本看“角色当前记忆池和审核结果”，召回解释看“某一轮请求为什么注入了这些记忆”。

## 官方接口

```http
GET /admin/airp-memory-audit
GET /admin/airp-memory-audit?conversation_id=<conversation_id>
```

接口属于 admin API；如果启用了 `admin_token`，需要携带管理鉴权。未传参数时，接口会选择最近活跃会话。

返回字段：

- `ready`：当前会话存在，且至少有长期记忆、候选、拒绝记录或状态板行。
- `conversation`：账本对应的会话。
- `current_role`：当前角色 ID 和显示名。
- `remembered_memories`：当前角色可用的已批准长期记忆，包含类型、作用域、证据和“为什么记住”。
- `pending_candidates`：待审核候选，说明为什么还不能直接写入长期记忆。
- `rejected_memories`：已拒绝或丢弃的候选，说明为什么不会进入召回池。
- `deprecated_memories`：已废弃的记忆卡片。
- `current_state`：当前会话状态板 active 行，提供“当前剧情状态在哪里”的入口。
- `summary`：仪表盘和自动化使用的计数摘要。
- `next_actions`：当前最需要用户处理的入口。

仪表盘会直接展示最多两条 `current_state.rows` 快照，用户无需先进入状态板，也能看见当前剧情停在哪张状态表、关键字段是什么。

## 发布门禁

CI 和 Release workflow 都会运行：

```bash
uv run pytest tests/test_ux_api.py -q -k "airp_memory_audit"
```

该测试通过 ASGI 客户端和本地临时 SQLite 数据库完成，不依赖真实后端服务、真实 Embedding 或外部模型。
