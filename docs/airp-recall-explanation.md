# AIRP 召回解释闭环

KokoroMemo 的召回解释不是通用 RAG 调试器，而是 AIRP 角色连续性的验收面板：用户需要知道这轮为什么记得、为什么没有串到别的角色、为什么某些记忆没有进入注入。

## 官方接口

```http
GET /admin/airp-recall-explanation
GET /admin/airp-recall-explanation?conversation_id=<conversation_id>
GET /admin/airp-recall-explanation?trace_id=<trace_id>
```

接口属于 admin API；如果启用了 `admin_token`，需要携带管理鉴权。未传参数时，接口会选择最近活跃会话和该会话最新 retrieval trace。

返回字段：

- `ready`：当前会话存在、已有 retrieval trace，且最终选中的记忆没有隔离风险。
- `conversation`：当前解释对应的会话、用户和角色。
- `current_role`：当前角色 ID 和显示名。
- `trace`：本轮查询、触发原因、召回策略、挂载库、允许作用域和最终注入数量。
- `selected_memories`：最终进入注入的记忆卡片，包含路径、分数、来源角色/会话和选中原因。
- `excluded_memories`：被隔离或过滤的记忆卡片，包含 `character_isolation`、`conversation_isolation`、`library_not_mounted`、`scope_disabled` 或 `not_approved`。
- `rejected_candidates`：trace 中出现但未进入最终注入的候选，供后续扩展精排或冲突解释。
- `isolation`：本轮最终注入是否通过角色、会话和记忆库隔离检查。
- `summary`：仪表盘和自动化使用的计数摘要。
- `next_actions`：当前还缺哪一步，给 GUI 提供跳转入口。

## 验收重点

召回解释至少要能回答三件事：

1. **不忘**：`selected_memories` 能说明哪些批准记忆进入了本轮注入，以及通过哪条召回路径命中。
2. **不串**：`isolation.passed` 为 `true` 时，最终选中的角色级/会话级记忆不得来自其他角色或其他会话。
3. **不乱记**：`excluded_memories` 要能显示尚未批准、未挂载库、关闭作用域或隔离规则导致的排除原因。

## 发布门禁

CI 和 Release workflow 都会运行：

```bash
uv run pytest tests/test_ux_api.py -q -k "airp_recall_explanation"
```

该测试通过 ASGI 客户端和本地临时 SQLite 数据库完成，不依赖真实后端服务、真实 Embedding 或外部模型。
