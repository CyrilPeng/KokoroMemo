# Changelog

## v0.1.0 (2026-04-27)

首个公开版本。

### 核心功能

- **OpenAI-compatible 代理** — 支持流式/非流式请求转发，AIRP 客户端只需配置本地地址即可使用
- **多 LLM Provider** — 支持 OpenAI-compatible、OpenAI Responses、Anthropic Claude、Google Gemini 四种云端大模型
- **转发模式** — 覆盖模式（本项目配置优先）/ 透传模式（使用客户端传来的 Key 和模型）
- **记忆卡片系统** — 基于 SQLite 的结构化记忆存储，支持 memory_cards / memory_inbox / memory_edges / memory_summaries
- **半自动审核** — 新提炼记忆经 review_policy 判定：自动通过 / 待审核 / 拒绝
- **多路召回** — 向量检索 + pinned/boundary 卡片 + 近期重要卡片 + 图扩展（placeholder）
- **分层注入** — 记忆按类型分层注入（稳定边界 / 用户偏好 / 关系状态 / 当前剧情 / 未完成承诺）
- **模板变量** — 支持 12 个 `{{变量}}` 占位符（时间/身份/系统状态），自动替换
- **相对时间标签** — 注入的记忆卡片自动附带"昨天"/"3天前"等时间锚点
- **向量索引重建** — 从 SQLite approved cards 重建 LanceDB，支持切换 Embedding 模型
- **降级机制** — 记忆系统任何环节失败不影响聊天

### GUI (Tauri + Vue 3 + Naive UI)

- **仪表盘** — 服务状态、模型信息一览
- **记忆管理** — 查看/编辑/删除记忆卡片，支持作用域筛选和分页
- **设置页面** — 完整配置 GUI，含 Provider 选择、API Key、模型拉取、转发模式等
- **Tooltip 帮助** — 关键配置项旁有 `?` 图标说明
- **文件夹选择器** — 数据存储路径支持系统原生文件夹选择（Tauri 环境）
- **自动重启** — 修改端口或存储目录后服务自动重启
- **暗色主题** — 现代深色 UI

### 技术栈

- 后端：Python 3.11+ / FastAPI / SQLite (WAL) / LanceDB / httpx
- 前端：Vue 3 / Naive UI / Vite / TypeScript
- 桌面：Tauri 2
- CI/CD：GitHub Actions (Nuitka + Tauri 三平台打包)

### 默认模型

- Embedding：模力方舟 Qwen3-Embedding-8B（需自行注册 ai.gitee.com 获取 API Key）
- Rerank：模力方舟 Qwen3-Reranker-8B（默认关闭）
