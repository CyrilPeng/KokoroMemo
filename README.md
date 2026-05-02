<p align="center">
  <img src="gui/src/assets/logo.svg" width="180" alt="KokoroMemo Logo" />
</p>

<h1 align="center">KokoroMemo / 心忆</h1>

<p align="center">
  <em>让 AI 角色不只回应你，也记得你。</em>
</p>

<p align="center">
  <a href="https://github.com/CyrilPeng/KokoroMemo">GitHub</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#接入客户端">接入客户端</a> ·
  <a href="#gui-功能概览">GUI 功能</a> ·
  <a href="#常见问题">常见问题</a> ·
  <a href="DESIGN.md">设计文档</a>
</p>

---

## KokoroMemo 是什么？

**KokoroMemo（心忆）** 是一个面向 **AI 角色扮演（AIRP）**、AI 游戏、AI 桌宠、SillyTavern 类前端与其他 OpenAI-compatible 客户端的 **本地长期记忆核心**。

它作为一个运行在本机的 OpenAI-compatible 代理，位于你的 AI 客户端与真实大模型 API 之间。客户端仍然像往常一样请求聊天模型，KokoroMemo 会在中间负责保存对话、维护会话状态、检索长期记忆，并把必要的上下文注入给模型。

KokoroMemo 的目标不是简单地把聊天记录塞进向量库，而是用可审阅的记忆卡片、会话状态板、按需召回和本地语义索引，让 AI 角色跨会话记住你的称呼、偏好、边界、关系进展、重要约定、剧情状态与共同经历。

```text
你的客户端 → KokoroMemo 本地代理 → 大模型 API
              ↓
        本地记忆、状态板与审核
```

适合希望角色能长期保持连续性，又不想让自动记忆污染角色设定或把全部聊天记录直接塞进上下文的用户。

---

## 主要功能

- **OpenAI-compatible 代理**：客户端只需要填写 KokoroMemo 的 Base URL，就能继续使用原来的聊天模型。
- **本地长期记忆**：对话、记忆卡片、审核记录和状态板默认保存在本机 SQLite 数据库中。
- **记忆审核**：新提炼出的记忆会进入收件箱，可自动通过、人工审核或拒绝。
- **会话状态板**：记录“当前正在发生什么”，例如场景、角色状态、关系、规则、任务、事件和物品。
- **按需召回**：通过 Retrieval Gate 判断是否需要检索长期记忆，减少不必要的向量搜索和上下文污染。
- **多模型支持**：聊天模型、记忆判断模型、状态板填充模型、Embedding、Rerank 可分别配置。
- **桌面 GUI / Web UI**：提供仪表盘、设置、记忆管理、收件箱、会话状态板和导入导出功能。
- **降级可用**：LanceDB 不可用时可回退到 SQLite + numpy 向量检索，适合轻量环境。

---
## 快速开始

### 方式一：下载发行版

前往 GitHub Releases 下载对应系统的桌面版本。启动后在设置页填写模型服务商的 Base URL、API Key 和模型名。

如果配置端口 `14514` 不可用，后端会自动切换到可用端口。请以 GUI 中显示的 `OpenAI Base URL` 为准。

### 方式二：从源码运行

环境要求：

- Python 3.11+
- Node.js 20+
- Rust/Tauri 环境（仅桌面开发需要）

```bash
git clone https://github.com/CyrilPeng/KokoroMemo.git
cd KokoroMemo

python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

pip install -e .
cd gui
npm install
```

准备配置：

```bash
copy config.example.yaml config.yaml  # Windows
# cp config.example.yaml config.yaml  # Linux/macOS
```

启动后端：

```bash
python -m app.main
```

启动前端：

```bash
cd gui
npm run dev
```

桌面开发模式：

```bash
cd gui
npm run tauri dev
```

---

## 接入客户端

在 AIRP、SillyTavern 或其他 OpenAI-compatible 客户端中填写：

```text
Base URL: http://127.0.0.1:14514/v1
API Key: 任意非空值，或按你的上游服务商要求填写
Model:   你的聊天模型名
```

如果 GUI 显示的 OpenAI Base URL 不是 `14514`，请复制 GUI 中的实际地址。例如：

```text
http://127.0.0.1:33238/v1
```

推荐为请求添加以下 Header，帮助 KokoroMemo 区分用户、角色和会话：

```text
X-User-Id: default
X-Character-Id: character_name
X-Conversation-Id: conversation_id
```

没有这些 Header 时，KokoroMemo 会使用默认值或从请求内容中推断，但多角色/多会话场景建议显式填写。

---

## 第一次使用建议

1. 打开 GUI 的“设置”页。
2. 填写聊天模型的 Provider、Base URL、API Key 和模型名。
3. 确认“OpenAI Base URL”，复制到你的客户端。
4. 先用普通聊天测试代理是否可用。
5. 打开“收件箱”，查看自动提炼出的候选记忆。
6. 打开“会话状态板”，确认当前会话状态是否被正确维护。

Embedding 默认使用模力方舟 `Qwen3-Embedding-8B`，需要自行配置 API Key。Rerank 默认关闭，不影响基本使用。

---

## GUI 功能概览

### 仪表盘

查看服务状态、实际监听端口、模型配置、记忆卡片数量和近期增长情况。

### 设置

配置聊天模型、Embedding、Rerank、记忆判断、状态板填充、存储目录、端口、语言和更新检查。

设置页中：

- **OpenAI Base URL**：客户端应该填写的真实地址。
- **本地监听端口**：后端当前实际监听端口，默认与 OpenAI Base URL 保持一致；点击“修改”可设置新端口，确认后会立即重启后端。

### 记忆管理

查看、编辑、删除、废弃和筛选正式记忆卡片。记忆卡片按作用域区分全局、角色、会话等范围。

### 收件箱

查看候选记忆，决定是否批准、拒绝或修改后保存。

### 会话状态板

状态板用于维护当前会话的短期连续性。v0.6.0 起，默认使用表格化状态板：

- 当前场景
- 角色状态
- 关系状态
- 扮演规则
- 承诺与任务
- 重要事件
- 重要物品

你可以按表查看、新增、编辑和删除状态行，也可以查看实际注入到模型的状态板预览。

状态板现在支持“会话方案”和“新会话默认配置”：

- **普通角色扮演**：长期记忆 + 状态板混合使用，适合陪伴聊天和角色关系维护。
- **RimTalk / 殖民地模拟**：默认关闭长期记忆写入，只用状态表格记录殖民地概况、小人状态、关系、资源、建筑、威胁和阵营，避免把临时游戏状态污染长期记忆库。
- **跑团 / 剧情模拟**：状态板优先，长期记忆只保留稳定设定，适合任务线索、NPC、地点、阵营和剧情旗标。
- **长期记忆助手 / 纯代理**：分别用于只管理长期记忆，或完全不写记忆与状态。

如果你准备开始 RimTalk 或跑团，建议先在“会话状态板”里设置“新会话默认配置”。这样第一次出现的新 `conversation_id` 就会使用正确模板和策略，而不是先落到通用 AIRP 模板。

### 导入导出

支持导出记忆库、会话配置、状态板数据和挂载预设。桌面端会弹出保存位置选择框，Web 端使用浏览器下载能力。

---

## 数据与隐私

默认数据目录：

```text
./data/
├─ conversations/   # 原始请求、回复和会话记录
├─ memory/          # SQLite 记忆数据库
└─ vector_indexes/  # LanceDB 向量索引（可重建）
```

KokoroMemo 默认本地运行，不会主动上传你的数据库。真正发送给上游模型的是原始聊天请求以及被注入的记忆/状态内容。请根据你使用的模型服务商隐私政策自行判断敏感信息风险。

备份时建议至少保存：

- `data/memory/memory.sqlite`
- `data/conversations/`
- `config.yaml`

向量索引目录通常可以从 SQLite 重新构建。

---

## 常见问题

### KokoroMemo 是聊天模型吗？

不是。KokoroMemo 是代理和记忆层，仍然需要你配置真实的大模型 API。

### 为什么端口不是 14514？

如果 `14514` 被其他程序监听、被系统保留或当前用户无权限监听，KokoroMemo 会自动切换到可用端口。请以 GUI 显示的 `OpenAI Base URL` 和“本地监听端口”为准。

排查端口可以使用：

```powershell
netstat -ano | findstr :14514
Get-NetTCPConnection -LocalPort 14514
```

`tasklist | findstr 14514` 查的是进程列表文本，不是端口占用。

### 为什么候选记忆没有立刻生效？

候选记忆需要通过审核策略。自动通过的会直接成为记忆卡片；待审核的需要在收件箱中批准。

### 为什么角色没有想起某件事？

常见原因包括：记忆尚未审核、作用域不匹配、Embedding 未配置、Retrieval Gate 判断当前请求不需要召回，或相关记忆分数不够高。

### Rerank 必须开启吗？

不必须。默认关闭即可使用。记忆数量变多后，开启 Rerank 可以改善最终注入质量，但会增加一次模型调用。

### 可以删除向量索引目录吗？

可以。向量索引是可重建缓存，正式记忆以 SQLite 为准。删除后需要在设置或维护功能中重建索引。

### 多角色会串记忆吗？

KokoroMemo 使用 `user_id`、`character_id`、`conversation_id` 和作用域隔离记忆。建议客户端显式传入对应 Header，尤其是多角色同时使用时。

---

## 更多文档

- [DESIGN.md](DESIGN.md)：架构、数据结构、状态板 v2、请求流程、检索门控和发布设计。
- [CHANGELOG.md](CHANGELOG.md)：版本更新记录。

---

## License

MIT License. 详见 [LICENSE](LICENSE) 文件。
