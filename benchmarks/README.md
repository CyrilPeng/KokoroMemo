# AIRP Benchmark

KokoroMemo 的 benchmark 用来证明一件具体的事：在 AIRP 场景里，角色记忆应该 **召回该召回的内容**，同时 **过滤不该进入当前角色 / 当前会话 / 当前记忆库的内容**。

这不是通用 RAG 评测。它服务于 KokoroMemo 的产品承诺：

- **不忘**：称呼、偏好、边界、关系阶段、任务目标等稳定信息能被召回。
- **不串**：角色 A、会话 A、世界观 A 的记忆不会污染当前角色或当前世界。
- **不乱记**：状态/剧情类信息应按作用域和预算控制，不把旧场景或无关卡片塞进 prompt。

## 快速运行

Smoke case：

```bash
python benchmarks/run_airp_benchmark.py --smoke --enforce-thresholds --report-dir benchmarks/reports/smoke
```

完整 case：

```bash
python benchmarks/run_airp_benchmark.py --enforce-thresholds --report-dir benchmarks/reports/full
```

与上一份报告对比：

```bash
python benchmarks/run_airp_benchmark.py --report-dir benchmarks/reports/release --compare-to benchmarks/reports/previous
```

在脚本或发布门禁中阻止退化：

```bash
python benchmarks/run_airp_benchmark.py --enforce-thresholds --report-dir benchmarks/reports/release --compare-to benchmarks/reports/previous --fail-on-regression
```

报告会生成：

- `airp_benchmark.json`：机器可读结果。
- `airp_benchmark.md`：发布和人工审查用摘要。

`--enforce-thresholds` 会把发布阈值写入 JSON / Markdown 报告，并在任一阈值不满足时返回非零退出码。默认阈值是 `failed_cases <= 0`、`recall_accuracy >= 1.0`、`false_positive_rate <= 0.0`；如需临时放宽，可显式传入 `--max-failed-cases`、`--min-recall-accuracy` 或 `--max-false-positive-rate`，但发布前应在变更说明里解释原因。

`--compare-to` 可以指向旧的 `airp_benchmark.json`，也可以指向包含该文件的报告目录。Markdown 报告会列出关键指标 delta、退化 case、改善 case、新增 case 和移除 case。加上 `--fail-on-regression` 后，如果失败数上升、召回率下降、误召回率上升，或原本通过的 case 变失败，命令会返回非零退出码。

## 当前覆盖

| Case | 证明点 |
|---|---|
| `nickname_memory` | 用户称呼偏好应被召回。 |
| `character_isolation` | 角色 A 的角色级记忆不能污染角色 B。 |
| `library_isolation` | 未挂载记忆库中的世界观记忆不能进入当前会话。 |
| `preference_memory` | 用户偏好应被召回。 |
| `boundary_memory` | 用户边界和禁忌应被召回。 |
| `conversation_isolation` | 其他会话的会话级记忆不能污染当前会话。 |
| `scene_location_continuity` | 当前场景地点应保持连续，旧会话地点不能混入。 |
| `relationship_stage` | 关系阶段应被召回。 |
| `quest_objective` | 未完成任务目标应被召回。 |
| `token_budget_priority` | 字符预算有限时，高优先级卡片应保留，低优先级噪音应排除。 |

## 指标解释

- `passed_cases`：没有漏召回，也没有 forbidden 卡片泄漏的 case 数。
- `recall_accuracy`：应召回卡片中实际进入注入结果的比例。
- `false_positive_rate`：禁止召回卡片中实际泄漏进注入结果的比例。
- `avg_injected_tokens`：本轮注入文本的粗略 token 估算，用于观察上下文成本。
- `comparison`：使用 `--compare-to` 时生成，展示当前报告相对上一份报告的变化。
- `quality_regression`：使用 `--compare-to` 时生成；可配合 `--fail-on-regression` 做自动门禁。
- `quality_gate`：使用 `--enforce-thresholds` 时生成，记录发布阈值、是否通过和具体违规指标。

发布前建议：

- `failed_cases` 必须为 `0`。
- `recall_accuracy` 应保持 `1.0`，除非 case 本身被重新定义。
- `false_positive_rate` 必须保持 `0.0`。
- `avg_injected_tokens` 大幅上升时，应检查是否引入了过度召回或预算回退。

## 发布前检查清单

发布前至少运行：

```bash
python benchmarks/run_airp_benchmark.py --enforce-thresholds --report-dir benchmarks/reports/release
```

检查：

- `quality_gate.passed` 为 `true`。
- `character_isolation` 没有 leaked card。
- `library_isolation` 没有 leaked card。
- `conversation_isolation` 没有 leaked card。
- `scene_location_continuity` 没有召回旧地点。
- `token_budget_priority` 没有把低优先级噪音挤进最终注入。

如果任一隔离类 case 失败，不建议发布。AIRP 用户最敏感的问题不是“少想起一条”，而是“把另一个角色或世界观的记忆说出来”。

## 与 Demo 的关系

`examples/airp-demo` 是面向用户的演示流程；`benchmarks/airp_cases` 是同一价值主张的确定性验证。

建议展示顺序：

1. 用 `examples/airp-demo` 解释 KokoroMemo 为什么不是通用长期记忆助手。
2. 用 `benchmarks/run_airp_benchmark.py` 证明核心召回和隔离行为没有退化。
3. 用 GUI 的“状态板 / 记忆审核 / 注入来源”展示用户能看懂并控制这套记忆系统。
