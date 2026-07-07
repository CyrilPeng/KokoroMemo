# AIRP 记忆隔离门禁

AIRP 记忆隔离门禁用于证明 KokoroMemo 的“不串”不是只在界面上提示，而是在 CI 和发布前被自动验证。

## 验证范围

- 当前角色只能注入当前角色、当前会话或全局作用域允许的记忆。
- 其他角色的角色级记忆会出现在召回解释的隔离排除列表里，而不是进入最终注入。
- 其他会话的会话级记忆会被 `conversation_isolation` 排除。
- 未挂载记忆库中的记忆会被 `library_not_mounted` 排除。
- 如果 retrieval trace 记录了跨角色记忆被选中，接口会把 `isolation.passed` 标记为 `false`，并给出 `review_isolation_risk` 下一步。
- AIRP 记忆账本只展示当前角色/会话相关的记忆、候选和拒绝记录。

## 本地命令

```bash
uv run pytest tests/test_ux_api.py -q -k "airp_isolation"
```

该门禁使用 ASGI 测试客户端和临时 SQLite 数据库，不依赖真实 AIRP 客户端、外部 Embedding 或外部模型。
