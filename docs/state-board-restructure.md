# 会话状态板重构说明

## 目标

- 降低 `ConversationState.vue` 单文件复杂度
- 明确“会话选择 → 策略配置 → 状态维护 → 历史追踪”的信息架构
- 为后续高级交互（批量编辑、上下文菜单、拖拽排序）保留稳定组件边界

## 组件边界

- `StateSessionToolbar.vue`：会话选择、导入导出、默认配置入口
- `StateDiagnosticsPanel.vue`：健康诊断与基础提示
- `StatePolicyCard.vue`：当前会话策略、模板/方案/挂载配置
- `StateDefaultConfigDrawer.vue`：新会话默认配置
- `EditableCell.vue`：单元格编辑与历史回滚

## 后续建议

1. 将状态表格工作区进一步拆为 `StateBoardWorkspace.vue`
2. 将注入预览、AI 填表、历史时间线整合为右侧 `StateInspector.vue`
3. 在工作区内增加批量优先级、状态切换、右键快捷操作
