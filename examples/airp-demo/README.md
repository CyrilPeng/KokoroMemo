# KokoroMemo AIRP Demo

这个目录用于展示 KokoroMemo 的核心价值：让 AI 角色在长线互动中 **不忘、不串、不乱记**。

Demo 不是通用 RAG 问答演示，而是围绕 AIRP 用户最容易遇到的问题设计：

- 角色是否记得用户称呼、偏好、边界和关系进展。
- 不同角色、不同会话、不同世界观是否互相污染。
- 当前剧情、任务、场景和游戏状态是否由状态板维护，而不是全部写进长期记忆。

## Demo 1：角色不忘

目标：证明 KokoroMemo 能让角色跨轮次记住稳定关系信息。

建议流程：

1. 在“设置 → 接入向导”选择“普通角色扮演”。
2. 在客户端中使用同一个 `X-Character-Id` 和 `X-Conversation-Id` 开始聊天。
3. 用户明确告诉角色：“以后请叫我小凛。”
4. 继续进行几轮无关闲聊。
5. 用户问：“你还记得应该怎么称呼我吗？”
6. 回到 KokoroMemo 的“注入来源”面板，确认称呼记忆被召回。
7. 在“记忆审核”中确认该候选属于角色连续性或偏好类记忆。

对应 benchmark：

```bash
python benchmarks/run_airp_benchmark.py --smoke --report-dir benchmarks/reports/demo
```

重点观察：

- `nickname_memory` 应通过。
- 召回内容应包含“用户希望被称呼为小凛”。
- 没有无关旧剧情被注入。

## Demo 2：多角色不串

目标：证明角色 A 的秘密不会泄漏给角色 B。

建议流程：

1. 使用角色 A 开启一段会话，告诉角色 A 一个只属于该角色的信息。
2. 切换到角色 B，确保客户端传入不同的 `X-Character-Id`。
3. 用户向角色 B 询问类似话题。
4. 回到 KokoroMemo 的“注入来源”面板。
5. 确认角色 A 的角色级记忆没有进入最终注入。

对应 benchmark：

```bash
python benchmarks/run_airp_benchmark.py --report-dir benchmarks/reports/demo
```

重点观察：

- `character_isolation` 应通过。
- `library_isolation` 应通过。
- `conversation_isolation` 应通过。

这些 case 分别覆盖角色隔离、记忆库隔离和会话隔离，是 KokoroMemo 与通用长期记忆助手拉开差异的关键证明。

## Demo 3：状态板维护当前剧情

目标：证明临时剧情状态由状态板维护，不必全部污染长期记忆库。

建议流程：

1. 在“设置 → 接入向导”选择“跑团 / 长篇剧情”或“RimTalk / 殖民地模拟”。
2. 开始一段剧情：地点从图书馆移动到中央车站，并产生一个未完成任务。
3. 回到“状态板”，查看“连续性摘要”。
4. 确认当前场景、关系变化、扮演规则、承诺与任务已更新。
5. 打开“注入预览”，确认状态板内容进入 prompt。
6. 如果是 RimTalk / 殖民地模拟，确认长期记忆写入策略为“不写长期记忆”。

对应 benchmark：

```bash
python benchmarks/run_airp_benchmark.py --report-dir benchmarks/reports/demo
```

重点观察：

- `scene_location_continuity` 应召回当前场景，不召回旧会话地点。
- `quest_objective` 应保留当前任务目标。
- 状态板适合保存“当前正在发生什么”，长期记忆只保存稳定设定。

## 演示话术

可以用下面这段作为项目展示开场：

> KokoroMemo 不是把聊天记录全塞进向量库。它把 AIRP 里的信息分成两类：长期稳定记忆和当前会话状态。称呼、边界、关系进展会进入可审核的长期记忆；地点、任务、物品、殖民地资源这类临时状态优先放进状态板。这样角色能记住该记住的东西，也不会把临时剧情到处串。

## 验收标准

- 用户能在 10 分钟内完成“接入向导 → 客户端配置 → 一小段聊天 → 查看状态板/记忆审核/注入来源”。
- 至少能演示一个“角色记得”的成功案例。
- 至少能演示一个“角色没有串记忆”的成功案例。
- 至少能演示一个“状态板维护当前剧情”的成功案例。
- benchmark 报告中隔离类 case 不应出现 leaked card。

