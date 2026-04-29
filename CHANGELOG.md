# Changelog

## v0.2.3 (2026-04-29)

### 新增

- **状态板注入预览** — 新增"注入预览"标签页，实时展示 AI 实际收到的状态板注入文本及字符预算占比
- **Dashboard 统计面板** — 仪表盘新增已批准记忆数、待审核数、检索门控统计、7 日增长趋势和类型分布
- **多语言 Prompt 支持** — 新建双语 prompt 注册表 (`app/core/prompts.py`)；新增 `language` 配置项（zh/en），切换所有系统 prompt 和触发关键词语言
- **角色级自动配置** — 新增 `character_defaults` 表；角色可绑定默认模板和记忆库；新会话自动应用角色默认配置
- **智能会话自动识别** — 新增 `conversation` 配置节；支持时间间隔和消息数量启发式检测新会话（默认关闭）
- **记忆语义去重** — 记忆提取后增加向量相似度检查（阈值 0.92），自动跳过近似重复卡片
- **Embedding 热切换框架** — 更换 embedding 模型后可后台异步重建索引，不中断服务；新增 `GET /admin/index-migration-status`
- **WebSocket 实时推送** — 新增 `/ws` 端点和事件总线；记忆提取后自动推送 `card_approved` / `inbox_new` 事件
- **SillyTavern 对话导入** — 新增 `POST /admin/import/sillytavern` 和 `POST /admin/import/{id}/extract-memories`；支持批量导入聊天并提取记忆
- **记忆图谱数据接口** — 新增 `GET /admin/memory-graph` 返回卡片节点和关系边，供前端图谱可视化使用

### 改进

- Admin API 新增角色管理端点 (`GET /admin/characters`, `GET/POST /admin/characters/{id}/defaults`)
- 前端 `api.ts` 新增 `createWebSocket` 工具函数
- 检索门控触发关键词自动合并多语言列表

### 修复

- 修复 CI 发布工作流中 Windows Portable 目录未清理导致 `gh release upload` 失败

## v0.2.1 (2026-04-28)

### 新增

- **桌面端自动启动后端** — 发行版启动时会自动拉起后端，避免 GUI 无法连接 `14514` 端口
- **关闭后最小化到托盘** — 设置页新增开关，默认启用；关闭窗口时隐藏到系统托盘，托盘菜单可显示窗口或退出应用
- **更新检测** — 设置页自动对比 GitHub 最新发行版，支持手动检查和打开发行页

### 改进

- **发行版命名** — GitHub Actions 产物统一命名为 `KokoroMemo-版本号-系统-CPU架构`
- **Windows 单 exe 打包** — Windows 便携版和 MSI 安装版均改为前端主程序内嵌后端，不再分离携带后端 sidecar
- **Windows 便携版** — Windows 发行版改为 `Portable.zip`，解压后得到仅包含 `KokoroMemo.exe` 的独立文件夹
- **Release 发布流程** — 构建产物先重命名归档，再统一发布到 GitHub Release

### 修复

- 修复打包发行版未启动后端导致前端无法连接的问题
- 修复 Windows 发行版前端和后端分离，导致便携版和 MSI 未满足单 exe 分发预期的问题
- 修复关闭窗口即退出应用导致托盘行为缺失的问题

## v0.2.0 (2026-04-28)

### 新增

- **长期记忆库** — 支持创建、编辑、删除多个记忆库；默认内置 `lib_default`；可从已有记忆库另存为新预设
- **会话记忆挂载** — 每个 conversation_id 可挂载多个记忆库；支持指定"写入目标"库；召回时仅检索挂载的库，避免跨世界串台
- **挂载组合预设** — 将当前挂载组合保存为命名预设；支持一键应用、删除、导出/导入
- **模板化多标签状态板** — 内置"通用角色扮演"和"跑团/剧情推进"两套模板；每个模板可自定义标签页和字段
- **模型驱动记忆判断** — 独立记忆判断模型配置；完全取代旧的硬编码正则抽取规则；低风险角色扮演规则（口癖、身份设定等）现可正常写入长期记忆
- **模型驱动状态板填表** — 独立状态填表模型配置；支持"模板字段填表"和"旧规则填表"两种模式；锁定字段不会被 AI 覆盖
- **会话配置汇总接口** — `GET/POST /admin/conversations/{id}/config` 一次性获取/保存挂载、写入目标和模板
- **会话配置面板** — GUI 顶部整合会话 ID、模板选择、记忆挂载、写入目标、状态摘要
- **新会话初始化向导** — 检测新会话时弹出 Modal 引导选择记忆库、写入目标和模板
- **状态板操作** — 清空当前会话状态板；重置为空状态（保留模板绑定）；复制状态板到新会话（可选复制挂载配置）
- **导入导出** — 记忆库、状态板模板、挂载组合预设均支持 JSON 导出/导入
- **多语言支持 (i18n)** — 新增中文/English 语言包；首次启动根据系统语言自动选择；设置页可手动切换
- **时区配置** — 新增 `server.timezone` 配置项（IANA 时区名）；统一所有时间戳生成使用系统本地时间

### 修复

- 修复旧数据库升级时新增列索引迁移顺序问题
- 修复角色扮演规则未写入长期记忆和状态板
- 修复时间戳统一使用系统本地时间（新增 `app/core/time_util.py` 集中管理时区）
- 修复 GUI 后端连接配置
- 修复桌面端文件夹选择权限
- 修复设置页 API Key 回显
- 修复称呼偏好记忆自动入库

### 改进

- GUI 会话状态板页面重构为统一会话配置面板
- 挂载预设交互改为下拉菜单（应用/导出/删除）
- Embedding 和 Rerank 配置移到记忆判断模型同一区域
- 状态板填表模型可配置更便宜更快的独立模型
- 会话状态板模板支持自定义 JSON 创建

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
