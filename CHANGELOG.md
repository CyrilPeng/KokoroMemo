# Changelog

## Unreleased

### 修复

- **Termux 一键安装稳定性** - 一键安装脚本内置 Termux 镜像切换、短超时下载和 Python 下载兜底；首次安装默认使用内置稳定版本地址，不再请求 `latest.json`，降低国内网络环境下安装卡住或中断的概率。
- **Termux 依赖安装优化** - 首次安装不再执行 `pkg upgrade` 全量升级，只安装必要依赖；安装过程使用非交互 apt 参数，并补齐 `python-pip`、`python-ensurepip-wheels` 等组件，提升 venv 创建成功率。
- **Termux 原生依赖兼容** - Termux 端固定使用不依赖 `pydantic-core` 的 `pydantic v1` 兼容组合，并以 `pip --no-deps` 安装应用依赖和项目本体，避免在手机上源码编译 `pydantic-core` / Rust 扩展。

## v0.8.1 (2026-05-03)

### 新增

- **统一更新清单** - Release 工作流新增 `latest.json` 与 `SHA256SUMS.txt`，记录最新版本、各平台资产、下载镜像和校验值，供 PC 与 Android 共用。
- **Android 一键更新** - Android 单包新增 `update.sh`，支持检查最新版本、选择匹配运行环境的 aarch64 包、校验 SHA256、备份数据并替换程序文件。
- **Termux 一键安装** - `scripts/termux-setup.sh` 改为面向普通 Termux 用户的一键安装入口，自动安装依赖、下载当前稳定版 Android 单包、安装、启动并创建 `kokoromemo start/stop/update` 管理命令。

### 改进

- **多源更新回退** - 更新检测和 Android 更新脚本按 GitHub 直连、`https://gh-proxy.org/`、Gitee Release API 顺序回退，并移除无效的 Gitee `raw/main/latest.json` 地址，降低国内网络环境下无法检查或下载更新的问题。
- **GUI 更新入口** - 设置页改为读取统一更新清单，展示匹配安装包、更新来源，并提供下载更新包入口和 Android 一键更新命令提示。

### 修复

- **会话配置摘要兼容字段** - 修复 `GET /admin/conversations/{conversation_id}/config` 只返回新会话策略字段，导致旧 GUI / 测试读取 `mounted_library_ids`、`write_library_id`、`state_item_count` 等摘要字段失败的问题。

### 兼容

- **会话配置 API 合并** - 保留 `POST /admin/conversations/{conversation_id}/config` 作为 `PUT` 的兼容入口，并统一处理 `library_ids`、`mounted_library_ids` 和 `write_library_id`，避免新旧状态板配置接口返回结构不一致。

## v0.8.0 (2026-05-03)

### 新增

- **角色中心** - 将原“角色”展示页重构为角色档案、默认会话策略、记忆库绑定、相关会话和诊断工具一体化的角色中心。
- **角色默认策略** - 角色默认配置支持会话方案、旧字段模板、表格模板、挂载预设、长期记忆写入策略、状态板更新策略和注入策略。
- **角色会话管理** - 新增按角色查看相关会话、查看会话当前策略，并从角色中心跳转到会话状态板的能力。
- **角色配置导入导出** - 支持导出/导入角色档案与默认策略，便于复用角色预设。

### 改进

- **新会话策略优先级** - 新会话初始化时优先套用角色默认策略，其次才使用全局新会话默认配置，最后回退内置方案。
- **批量应用角色策略** - 支持将角色默认策略和默认挂载库批量应用到该角色已有会话，修复旧模板或错误记忆策略残留。
- **角色档案增强** - 角色支持显示名称、别名、备注和来源信息，降低只显示 `character_id` 的识别成本。
- **角色诊断提示** - 对 RimTalk / 殖民地模拟等场景提示长期记忆污染风险，引导使用状态板优先策略。

### 兼容

- **内测期角色数据重构** - 角色默认配置表扩展为新策略模型，旧页面逻辑已替换为角色中心工作流。

## v0.7.1 (2026-05-03)

### 新增

- **Android 单包部署** - Release 流程新增 `Android-Termux-aarch64` 与 `Android-ProotUbuntu-aarch64` 单包产物，用户按运行环境和 CPU 架构下载一个压缩包即可安装。
- **预构建 Web UI 支持** - 后端支持通过 `KOKOROMEMO_WEB_DIST` 指向包内 `webui/dist`，Android 端无需在手机上运行 `npm install` 或 `npm run build`。
- **Android 管理脚本** - 新增 `install.sh`、`start.sh`、`stop.sh`、`restart.sh`、`backup.sh` 和 `doctor.sh`，覆盖安装、启动、停止、诊断和数据备份。

### 改进

- **Android 轻量依赖** - 新增 Termux 与 Proot Ubuntu 专用 requirements，Android 默认避开桌面端重依赖，降低 numpy、PyArrow、LanceDB 等现场编译失败风险。
- **Release 资产整理** - Android Web UI、源码、脚本和预留 wheels 目录在 CI 内部组装为单包，避免普通用户在 Release 页面手动下载零散依赖。
- **Android 文档补充** - README 与 DESIGN 增加 Android 单包选择、安装命令、包结构、运行策略和 CI 打包流程说明。

## v0.7.0 (2026-05-03)

### 新增

- **会话策略配置** - 新增会话级 `profile_id`、状态板模板、表格模板、挂载预设、长期记忆写入策略、状态更新策略和注入策略配置。
- **新会话默认配置** - 支持在第一次对话前设置新 `conversation_id` 默认套用的会话方案、模板和策略，避免新会话首轮误用通用 AIRP 模板。
- **RimTalk / 殖民地模拟方案** - 新增状态板优先、关闭长期记忆写入的内置方案，适合记录殖民地概况、小人状态、关系、资源、建筑、威胁和阵营。
- **跑团 / 剧情模拟方案** - 新增剧情状态表方案，覆盖队伍成员、当前场景、任务线索、重要 NPC、地点阵营和剧情旗标。

### 改进

- **长期记忆与状态板分流** - OpenAI 请求链路按会话策略决定是否注入长期记忆、是否注入状态板、是否运行 State Filler、是否写入长期记忆候选。
- **空状态会话可配置** - 会话状态板即使没有任何状态行，也可以先修改当前会话模板、挂载预设和记忆/注入策略。
- **RimTalk 记忆污染防护** - `state_only` 与 `disabled` 写入策略可让殖民地、小人即时状态、资源变化等动态内容只进入状态表格，不污染长期记忆库。
- **状态板帮助与文档** - README 和 DESIGN 补充会话方案、新会话默认配置、会话策略表、专用模板和 API 说明。

### 兼容

- **旧状态板兼容保留** - 旧字段式状态板模板与 `conversation_state_items` 仍作为兼容兜底；已有会话不会被新会话默认配置自动覆盖。

## v0.6.1 (2026-05-02)

### 修复

- **收件箱拒绝报错** - 修复待审核条目点击拒绝时前端发送 `{ note }` 与后端字符串 Body 不匹配，导致弹出 `common.failed` 的问题。
- **重复批准生成重复记忆** - 批准待审核条目时先原子切换为 `approving`，并在前端禁用处理中按钮，避免延迟期间多次点击导致重复写入记忆库。
- **端口不可用误报占用** - 区分端口被监听、系统保留和权限不足等原因，避免统一提示为端口占用。
- **实际端口显示不一致** - 设置页和 OpenAI Base URL 统一使用后端实际监听端口，避免显示 `14514` 但实际运行在其他端口。

### 改进

- **监听端口修改交互** - 设置页只保留“本地监听端口”一个入口，点击修改后二次确认，保存后立即重启后端并刷新实际端口。
- **README 与 DESIGN 分工** - README 改为面向用户的项目介绍和快速使用文档，DESIGN 承接架构、状态板 v2、端口策略和内部流程说明，并恢复 README 的 logo 与 slogan。

## v0.6.0 (2026-05-02)

### 新增

- **会话状态板 v2 表格化存储** - 新增表格模板、表结构、列、行、单元格、事件和调试运行预留表，旧字段式状态板保留为兼容兜底。
- **RimTalk 角色扮演表格模板** - 新增 `tpl_rimtalk_roleplay_tables`，覆盖当前场景、角色状态、关系状态、扮演规则、承诺任务、重要事件和重要物品。
- **操作式 State Filler** - 状态板填充优先使用 `insert_row`、`update_row`、`upsert_row`、`resolve_row`、`delete_row` JSON 行级操作，减少大文本字段混杂。

### 改进

- **热上下文注入重构** - 会话注入优先渲染表格状态，并按表格优先级和最大行数压缩；表格为空时自动回退旧状态板渲染。
- **状态板 GUI 完整重做** - `/state` 改为表格工作台，支持按表查看、新增、编辑、删除状态行，刷新真实注入预览，并手动运行表格填充调试。
- **状态板文档补充** - README 和 DESIGN 增加表格化状态板 v2 的存储、填充、渲染和兼容策略说明。

### 兼容

- **旧状态板数据保留** - `conversation_state_items`、旧模板接口和旧渲染仍保留，确保已有会话可继续读取，并作为表格状态为空时的兜底。

## 未发布

## v0.5.7 (2026-05-02)

### 新增

- **会话状态板导入导出** - 新增会话状态包导出/导入能力，可保存模板快照、挂载记忆库、写入目标和状态项，并支持导入到指定会话 ID。
- **Gate 调试完整预览** - Gate 调试表格新增预览按钮，可在弹窗中查看完整请求、原因、触发/跳过路由和置信度等调试内容。

### 改进

- **会话状态板管理体验重构** - 明确区分会话配置、状态板内容、模板管理、导入导出和调试能力；状态板模板改为显式应用并增加确认说明。
- **模板与预设管理增强** - 自定义模板支持删除；内置模板保持只读并通过克隆保护；挂载组合预设补充用途说明，明确只保存挂载库和写入目标。
- **导出保存位置选择** - 桌面端导出记忆库、会话配置、状态板模板和挂载预设时弹出另存为对话框，Web 端保留浏览器保存/下载兜底。
- **OpenAI Base URL 展示优化** - 设置页移除可编辑的 GUI 后端地址，改为直接展示 `OpenAI Base URL` 并提供一键复制，避免误改运行时地址。
- **状态板帮助与文档完善** - 完善会话状态板帮助弹窗，并更新 README/DESIGN 中状态板工作台、导入导出和模板管理说明。

### 修复

- **Gate 调试会话串扰** - Gate 调试和状态事件只展示当前选择会话 ID 的数据，并避免切换会话时旧请求结果覆盖新页面。
- **关闭窗口后端残留** - `关闭后最小化到托盘` 默认改为关闭；默认关闭窗口会退出 KokoroMemo 并停止后端，仍可在设置中手动启用托盘常驻。

## v0.5.6 (2026-05-02)

### 新增

- **SQLite + numpy 向量存储回退** - 新增 `SqliteVectorStore`，当 LanceDB/pyarrow 不可用时自动降级到 SQLite 向量检索，提升 Android Termux 等轻量环境可用性。
- **SQLite 向量库测试覆盖** - 新增向量 upsert/search/delete、where 过滤、staging promote、cosine 距离等测试，覆盖回退实现的核心行为。
- **Ubuntu 部署脚本** - 新增 `scripts/ubuntu-setup.sh`，用于 Ubuntu/proot-distro 环境的一键安装和运行。

### 改进

- **Termux 部署稳健性** - 安装脚本补充 `apt full-upgrade`、预编译 numpy、proot-distro Ubuntu 路径、原生 Termux 回退、克隆/下载/Gitee 多重回退，减少 ARM 设备依赖编译与网络失败。
- **向量服务自动降级** - `get_lancedb_store` 在 LanceDB 不可用时回退到 SQLite 向量存储，向量同步、重建和检索链路兼容回退存储。
- **Web/Tauri 地址解析** - Web UI 模式优先使用当前页面 origin，Tauri 模式兼容配置目录和工作目录中的 `.port` 文件。
- **版本同步** - 同步 Python、Tauri、前端包和锁文件版本到 `0.5.6`，并补充打包后端的构建期版本兜底。
- **文档补充** - 更新 README/DESIGN，补充 Termux、Ubuntu、SQLite 向量回退和运行环境说明。

### 修复

- **Release 版本号显示** - 为打包后端增加构建期版本兜底，并在 GitHub Release 工作流按 tag 写入版本，修复 GUI 左下角显示 `v0.0.0` 的问题。
- **开发模式配置路径** - 配置读取与保存改为解析实际 `config.yaml` 路径，避免 Tauri/后端工作目录不一致时误读 `config.example.yaml` 或覆盖错误文件。
- **实际监听端口统一** - 后端记录并通过 `/health`、`/admin/config` 返回实际监听端口，Dashboard、设置页和 GUI 后端地址统一展示动态端口。
- **状态板称呼误注入** - 明确称呼字段语义，禁止把字段默认值当作当前状态传入提示词，避免首轮对话错误注入测试值。
- **ARM/Termux 依赖安装失败** - 去掉 `uvicorn[standard]` extra，避免 uvloop/httptools 等依赖在 ARM/Termux 环境编译失败。

## v0.5.5 (2026-05-02)

### 新增

- **Web UI 模式** — 后端启动时自动检测 `gui/dist` 目录，存在则同时提供 Web 管理界面（手机浏览器访问 `http://127.0.0.1:14514` 即可使用完整 GUI）
- **Termux 一键部署** — 新增 `scripts/termux-setup.sh`，安卓手机通过 Termux 即可本地运行后端 + Web UI，自动从 GitHub Release 下载前端构建产物
- **Release 附带 WebUI-dist.zip** — GitHub Release 自动打包 `gui/dist/` 为独立 zip，供 Termux 或无 Node.js 环境使用

### 改进

- **Tauri API 版本锁定** — `@tauri-apps/api` 锁定为 `2.10.1`，消除与 Rust 端 tauri 2.10.3 的版本不匹配警告
- **CI 跨平台兼容** — 工作流 `npm ci` 改为 `npm install`，解决 `sharp` optional 依赖在 Linux/Windows 间的 lockfile 不一致

## v0.5.4 (2026-05-01)

### 新增

- **Web UI 模式** — 后端启动时自动检测 `gui/dist` 目录，存在则同时提供 Web 管理界面（手机浏览器访问 `http://127.0.0.1:14514` 即可使用完整 GUI）
- **Termux 一键部署** — 新增 `scripts/termux-setup.sh`，安卓手机通过 Termux 即可本地运行后端 + Web UI，AIRP 客户端指向 `http://127.0.0.1:14514/v1`

### 改进

- **版本号一处管理** — `pyproject.toml` 作为唯一版本来源，后端通过 `tomllib` 读取，前端通过 `/health` 接口动态获取；GUI 侧边栏版本号不再硬编码
- **i18n 模块化** — `zh-CN.ts` 和 `en-US.ts`（各 ~800 行）按功能域拆分为 8 个子模块（common / dashboard / memories / inbox / graph / characters / state / settings），顶层文件仅做聚合导出
- **Settings.vue 配置映射** — `loadConfig` 从 ~90 行手动赋值重构为声明式 `CONFIG_FIELDS` 映射表 + `applyConfigToForm` 循环，新增字段只需加一行映射

### 修复

- **`pyproject.toml` 版本滞后** — 之前版本停留在 `0.2.3`，与实际发布版本严重不同步

## v0.5.3 (2026-05-01)

### 修复

- **`memory.scopes` 过滤未生效** — 召回路径补全 `allowed_scopes` 参数，4 路（pinned/vector/recent/graph）均按设置页"高级 / 注入作用域"开关过滤
- **索引迁移调用签名 bug** — `_run_index_migration` 之前以错误参数调用 `rebuild_vector_index_v2`，运行时 TypeError；现在先 reset_services 再以正确签名调用
- **SillyTavern 导入两处 bug** — `save_turn_and_messages` 缺 4 个参数 + `get_all_messages` 函数缺失，之前任何上传都会 500
- **鉴权加固** — 未配置 admin_token 时拒绝远程客户端访问；启动告警

### 新增

- **CI 工作流** — push/PR 自动跑 pytest + 前端 vue-tsc/build，提前拦截 TS 错误
- **向量索引原子化重建** — staging 表 + atomic rename，迁移中途失败不会丢老索引
- **关键路径测试** — SillyTavern 导入、character_defaults、retrieval_gate keyword_only、事件总线、memory_graph 端点、scopes 过滤短路（共 7 个新测试）
- **前端类型定义** — `gui/src/types/memory.ts` 与 `state.ts`，Memories/Inbox 表格列函数类型化

### 改进

- **GUI 版本号动态获取** — 侧边栏版本号不再硬编码，改为启动时从 `/health` 接口读取后端实际版本
- **DESIGN.md 完善** — 新增聊天补全时序图（mermaid）+ 错误处理与降级矩阵（11 类失败场景）

## v0.5.2 (2026-05-01)

### 改进

- **高级配置页 UI 重构** — 改为左侧菜单 + 右侧面板布局，热上下文 14 段改为 NDataTable 三列表格，告别拥挤折叠面板
- **高级配置 label 精简** — 所有超过 13 字的 label 文案缩短，label-width 从 200 → 220px，避免在窄屏换行
- **高级配置每个分组独立帮助按钮** — 7 个分组（记忆总开关/会话检测/作用域/抽取/评分/门控/热上下文）各自有 ? 按钮，弹窗逐字段详解推荐值与典型场景
- **向量索引维护操作 UX** — 重建 / 异步迁移 / sync 重试三个按钮改为独立行卡片，每个带说明文字 + 二次确认弹窗，避免误操作
- **仪表盘、记忆库、待审核** 三个核心页面补齐帮助按钮（之前 7 个页面有 4 个有帮助）
- **GUI 中英文混用全面清理** — 帮助弹窗中混入的英文枚举（pending/approved/rejected、global/character/conversation、preference/boundary/...、low/medium/high）改为中文优先；technical 字段名（conversation_id/character_id/system prompt/ADMIN_TOKEN）在用户可见标签中改用通俗中文
- **表格枚举显示本地化** — 待审核页 card_type/scope 列、状态板"旧类别状态项" status 列、设置页迁移状态 Tag、仪表盘"按类型分布"、记忆图谱节点详情/图例 全部接入 i18n
- **状态板表格行内 NPopconfirm** — 重置/删除按钮的二次确认框补全 `positiveText`/`negativeText`，不再显示英文 Confirm/Cancel
- 设置页 3 条硬编码中文 toast 改用 i18n 键

### 修复

- 修复 i18n 中 `common.deleted` 误写为 "已 deleted" 的双语残留

## v0.5.1 (2026-05-01)

### 修复

- 修复 v0.5.0 CI 构建在 `vue-tsc -b` 严格模式下的 TypeScript 编译错误（NMessage 不支持 onClick、NInputNumber 回调签名、未使用的 svgRef/resolveItem/router import）
- 清理项目内残留的死代码与遗留兼容文件：旧 memories 数据流（sqlite_memory.py / rebuild.py / retriever.py / injector.py）、空 jobs 包、Vite 脚手架 HelloWorld.vue、`fetch_models_legacy` 兼容端点、graph.py 三个未使用的辅助函数
- 修复 `test_hot_context` 把双语 dict 当字符串使用导致的测试失败

## v0.5.0 (2026-05-01)

### 新增

- **角色默认绑定**（`/characters` 新页面）— 列出已发现的角色（从对话推断），可为每个角色绑定默认状态板模板、挂载库、写入库；新会话启动时自动应用
- **SillyTavern 导入**（记忆库页"导入 SillyTavern"按钮）— 选择本地 .jsonl/.json/.txt 聊天记录，导入后弹窗确认是否立即提取候选记忆，跳转待审核页查看
- **WebSocket 实时事件接通** — `card_approved` / `inbox_new` 事件通过全局 EventBridge 组件触发 toast 通知；Inbox/Dashboard 自动刷新数据，断线 5 秒重连
- **设置页"高级"标签页** — NCollapse 折叠展示 6 类记忆系统配置：会话自动检测、记忆总开关、注入作用域、抽取阈值、评分权重、检索门控、热上下文
- **记忆图谱可视化**（`/memory-graph` 新页面）— 力导向布局展示 memory_edges 网络，节点颜色按类型、半径按重要性，hover 显示详情
- **向量索引迁移进度** — 设置页新增"后台异步迁移"按钮，启动后实时显示 NProgress 进度条
- **重试失败的向量同步** — 设置页新增按钮一键重试 pending vector_sync 任务

### 改进

- 后端 `GET /admin/config` 返回完整的 conversation / memory.scopes / scoring / extraction / retrieval_gate / hot_context 字段
- 后端 `POST /admin/config` 改用深合并，正确处理 memory.* 嵌套字典
- 后端新增 `GET /admin/discovered-characters` 从 conversations 表推断已知角色
- 后端新增 `POST /admin/start-index-migration` 包装 `start_index_migration`

## v0.4.0 (2026-05-01)

### 新增

- **待审核记忆审核页面** — 新建独立 `/inbox` 页面，可在 GUI 中查看 pending 候选记忆并批准/拒绝（拒绝可填备注），不再只在 Dashboard 显示数字
- **状态板标签页自由管理** — 标签页可由用户自由添加（最右"+"按钮）、重命名、删除（每个标签旁的⋯菜单）；删除时关联状态项自动移入"旧类别状态项"
- **内置模板自动克隆保护** — 修改内置模板时自动克隆为自定义副本，避免覆盖内置模板
- **状态板帮助按钮** — 页面右上角"帮助"按钮 + 配置区帮助图标，弹窗讲解功能总览和配置项作用
- **自定义字段标识** — 自定义字段新增可选"字段标识"输入框，与字段名分离，避免主副标签重复显示

### 改进

- **会话状态板 UI 重构** — 顶部上下文条改为单行紧凑布局；会话配置改为 NCollapse 折叠（新会话自动展开）
- **危险操作收纳** — 复制到新会话/重置/清空收纳到"更多操作"下拉菜单，主操作行只剩保存/填表/投影
- **表格行操作改为图标按钮** — 编辑/重置/删除从紫色文字链接改为圆形 quaternary 图标按钮，hover 显示 tooltip；操作列宽度从 220px 缩到 140px
- **去除所有 emoji** — `➕ + ⋮ ?` 全替换为 `@vicons/ionicons5` 的图标
- **添加标签页按钮位置修复** — 改用 NTabs 原生 `addable` 方案，按钮紧贴最后一个标签页
- **帮助弹窗字体放大** — 状态板和设置页所有帮助弹窗字体从 13px → 15px、行高 1.85，正文颜色更亮，更易读
- **Dashboard 待审核卡片可点击** — 直接跳转到 /inbox 审核页面
- **标签页删除、挂载预设删除增加二次确认** — 防止误操作

### 修复

- 修复编辑自定义字段时模式回退为下拉框选择的问题，现在会自动恢复文本输入框并回填字段名
- 修复克隆内置模板后修改标签页时整个状态板被误删的问题（克隆后立即重新拉取完整模板）
- 修复 npm ci 缺失 `@emnapi/runtime` 和 `@emnapi/core` 入口导致 CI 构建失败

## v0.3.1 (2026-04-30)

### 新增

- **动态端口检测** — 后端启动时自动检测端口占用，切换到随机端口并写入 `.port` 文件；Tauri 读取 `.port` 获取实际端口，前端启动时自动连接正确地址
- **配置变更自动重启** — 修改存储目录或端口后，前端自动调用 Tauri `restart_backend` 重启后端，并重新解析端口
- **自定义状态字段** — 状态板新增 ➕ 按钮，支持用户输入自定义字段名创建词条，不再局限于模板预设字段
- **状态板操作二次确认** — 重置和删除按钮增加 NPopconfirm 确认弹窗，防止误操作

### 改进

- **CORS 补充 PATCH 方法** — 允许跨域 PATCH 请求，修复状态板保存时浏览器预检失败
- **仪表盘卡片高度统一** — 待审核统计卡片补充副标题行，与其他卡片保持一致
- **复制到新会话改为下拉框** — 目标会话 ID 从手动输入改为下拉选择器，支持搜索和手动输入
- **会话状态持久化** — 切换页面后自动恢复上次加载的会话数据，无需重新输入会话 ID
- **状态板"完成"改为"重置"** — 清空值但保留条目为 active 状态，更符合持续性字段的使用场景
- **状态板"删除"改为硬删除** — 从数据库彻底移除条目及关联事件
- **自定义词条归属标签页** — 用户新增的自定义字段显示在所属标签页内，不再归入"旧类别状态项"
- **配置子路径自动同步** — `root_dir` 变更时自动重算 SQLite/LanceDB 子路径

### 修复

- 修复 CORS 缺少 PATCH 导致状态板保存报 "Failed to fetch"
- 修复 `.port` 文件过期导致前端连接错误端口（启动前删除旧文件 + 端口可达性验证）
- 修复 `PurePosixPath` 在 Windows 路径下的兼容性问题

## v0.3.0 (2026-04-30)

### 新增

- **会话选择器** — 会话状态板的会话 ID 改为下拉选择器，自动列出最近会话，支持搜索和手动输入
- **会话删除** — 新增 `DELETE /admin/conversations/{id}` 接口，可从 UI 直接删除会话记录
- **侧边栏 GitHub 入口** — 左下角新增 GitHub 图标，使用 Tauri shell.open 跳转项目仓库

### 改进

- **会话状态板 UI 重构** — 配置面板拆为"会话选择"和"会话配置"两个独立卡片，布局更清晰
- **挂载预设下拉化** — 从平铺按钮列表改为下拉选择器 + 导出/删除同级按钮
- **模板操作收纳** — 创建/导出/导入收纳到"更多"下拉菜单，减少视觉噪音
- **设置页重构** — 状态板填表模型独立为单独标签页，与记忆配置并列
- **帮助文本全面改进** — 记忆配置说明三层架构、判断模式增加示例、Embedding 补充禁用影响、用户辅助规则补充多个示例
- **NPopconfirm 国际化** — 所有确认弹窗按钮文本改为 i18n 国际化
- **状态板填表帮助** — 帮助弹窗新增最小置信度、超时时间、Temperature、自定义 Prompt 的功能说明

### 修复

- 修复 Gemini 反代场景下 `x-goog-api-key` header 导致 401 认证失败
- 移除未使用的 `fillModeOptions` 变量，修复 TypeScript 构建报错

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
