<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  NCard, NForm, NFormItem, NInput, NSwitch, NInputNumber,
  NButton, NSpace, NDivider, NAlert, NSelect, NTag, NTooltip, useMessage,
} from 'naive-ui'
import { apiFetch, getServerUrl, setServerUrl } from '../api'

const message = useMessage()
const backendUrl = ref(getServerUrl())
const loading = ref(true)

const llmModels = ref<{label: string, value: string}[]>([])
const embeddingModels = ref<{label: string, value: string}[]>([])
const rerankModels = ref<{label: string, value: string}[]>([])
const judgeModels = ref<{label: string, value: string}[]>([])
const fetchingLlm = ref(false)
const fetchingEmbedding = ref(false)
const fetchingRerank = ref(false)
const fetchingJudge = ref(false)

async function fetchModelList(baseUrl: string, apiKey: string, target: 'llm' | 'embedding' | 'rerank' | 'judge') {
  if (!baseUrl) {
    message.warning('请先填写 Base URL')
    return
  }
  if (!apiKey) {
    message.warning('请先填写 API Key，否则无法从远端获取模型列表')
    return
  }
  const flagRef = target === 'llm' ? fetchingLlm : target === 'embedding' ? fetchingEmbedding : target === 'rerank' ? fetchingRerank : fetchingJudge
  flagRef.value = true
  try {
    const resp = await apiFetch('/admin/fetch-models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url: baseUrl, api_key: apiKey }),
    })
    const data = await resp.json()
    if (data.status === 'ok' && data.models.length > 0) {
      const options = data.models.map((m: string) => ({ label: m, value: m }))
      if (target === 'llm') llmModels.value = options
      else if (target === 'embedding') embeddingModels.value = options
      else if (target === 'rerank') rerankModels.value = options
      else judgeModels.value = options
      message.success(`获取到 ${data.models.length} 个模型`)
    } else {
      message.error(data.message || '未获取到模型列表')
    }
  } catch (e) {
    message.error('请求失败，请检查后端是否运行')
  }
  flagRef.value = false
}

const config = ref({
  server_port: 14514,
  storage_root_dir: './data',
  llm_forward_mode: 'override',
  llm_provider: 'openai_compatible',
  llm_base_url: '',
  llm_api_key: '',
  llm_model: '',
  embedding_enabled: true,
  embedding_provider: 'modelark',
  embedding_base_url: '',
  embedding_api_key: '',
  embedding_model: 'qwen3-embedding-8b',
  embedding_dimension: 4096,
  rerank_enabled: false,
  rerank_provider: 'modelark',
  rerank_base_url: '',
  rerank_api_key: '',
  rerank_model: 'qwen3-reranker-8b',
  rerank_max_docs: 20,
  memory_enabled: true,
  max_injected_chars: 1500,
  final_top_k: 6,
  judge_enabled: false,
  judge_provider: 'openai_compatible',
  judge_base_url: '',
  judge_api_key: '',
  judge_model: '',
  judge_timeout_seconds: 30,
  judge_temperature: 0,
  judge_mode: 'model_only',
  judge_user_rules: '',
  judge_prompt: '',
})

const forwardModeOptions = [
  { label: '覆盖模式（使用下方配置，AIRP 客户端 Key 可随意填写）', value: 'override' },
  { label: '透传模式（使用 AIRP 客户端传来的 Key 和模型）', value: 'passthrough' },
]

const providerOptions = [
  { label: 'OpenAI 兼容 (DeepSeek/Grok/中转站等)', value: 'openai_compatible' },
  { label: 'OpenAI Responses API', value: 'openai_responses' },
  { label: 'Anthropic Claude', value: 'anthropic' },
  { label: 'Google Gemini', value: 'gemini' },
]

const judgeModeOptions = [
  { label: '仅模型判断（推荐）', value: 'model_only' },
  { label: '模型 + 用户辅助规则', value: 'model_with_user_rules' },
]

const providerUrlPlaceholder = computed(() => {
  const map: Record<string, string> = {
    openai_compatible: 'https://api.openai.com/v1',
    openai_responses: 'https://api.openai.com/v1',
    anthropic: 'https://api.anthropic.com/v1',
    gemini: 'https://generativelanguage.googleapis.com/v1beta',
  }
  return map[config.value.llm_provider] || ''
})

const providerModelPlaceholder = computed(() => {
  const map: Record<string, string> = {
    openai_compatible: 'gpt-4o / deepseek-chat',
    openai_responses: 'gpt-4o',
    anthropic: 'claude-sonnet-4-20250514',
    gemini: 'gemini-2.5-flash',
  }
  return map[config.value.llm_provider] || ''
})

async function pickFolder() {
  try {
    const { isTauri } = await import('@tauri-apps/api/core')
    if (!isTauri()) {
      message.info('当前是浏览器调试环境，请直接输入路径；桌面版可使用文件夹选择器')
      return
    }
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ directory: true, multiple: false, title: '选择数据存储目录' })
    if (selected) {
      config.value.storage_root_dir = selected as string
    }
  } catch (e: any) {
    message.error(`无法打开文件夹选择器：${e?.message || e || '请确认 Tauri dialog 权限已启用'}`)
  }
}

async function loadConfig() {
  loading.value = true
  try {
    const resp = await apiFetch('/admin/config')
    if (resp.ok) {
      const data = await resp.json()
      config.value.server_port = data.server?.port || 14514
      config.value.storage_root_dir = data.storage?.root_dir || './data'
      config.value.llm_forward_mode = data.llm?.forward_mode || 'override'
      config.value.llm_provider = data.llm?.provider || 'openai_compatible'
      config.value.llm_base_url = data.llm?.base_url || ''
      config.value.llm_api_key = data.llm?.api_key || ''
      config.value.llm_model = data.llm?.model || ''
      config.value.embedding_enabled = data.embedding?.enabled ?? true
      config.value.embedding_provider = data.embedding?.provider || 'modelark'
      config.value.embedding_base_url = data.embedding?.base_url || ''
      config.value.embedding_api_key = data.embedding?.api_key || ''
      config.value.embedding_model = data.embedding?.model || ''
      config.value.embedding_dimension = data.embedding?.dimension || 4096
      config.value.rerank_enabled = data.rerank?.enabled ?? false
      config.value.rerank_provider = data.rerank?.provider || 'modelark'
      config.value.rerank_base_url = data.rerank?.base_url || ''
      config.value.rerank_api_key = data.rerank?.api_key || ''
      config.value.rerank_model = data.rerank?.model || ''
      config.value.rerank_max_docs = data.rerank?.max_documents_per_request || 20
      config.value.memory_enabled = data.memory?.enabled ?? true
      config.value.max_injected_chars = data.memory?.max_injected_chars || 1500
      config.value.final_top_k = data.memory?.final_top_k || 6
      config.value.judge_enabled = data.memory?.judge?.enabled ?? false
      config.value.judge_provider = data.memory?.judge?.provider || 'openai_compatible'
      config.value.judge_base_url = data.memory?.judge?.base_url || ''
      config.value.judge_api_key = data.memory?.judge?.api_key || ''
      config.value.judge_model = data.memory?.judge?.model || ''
      config.value.judge_timeout_seconds = data.memory?.judge?.timeout_seconds || 30
      config.value.judge_temperature = data.memory?.judge?.temperature ?? 0
      config.value.judge_mode = normalizeJudgeMode(data.memory?.judge?.mode || 'model_only')
      config.value.judge_user_rules = (data.memory?.judge?.user_rules || []).join('\n')
      config.value.judge_prompt = data.memory?.judge?.prompt || ''
    }
  } catch (e) {
    // use defaults
  }
  loading.value = false
}

async function saveConfig() {
  try {
    setServerUrl(backendUrl.value)
    const payload: any = {
      server: { port: config.value.server_port },
      storage: { root_dir: config.value.storage_root_dir },
      llm: {
        forward_mode: config.value.llm_forward_mode,
        provider: config.value.llm_provider,
        base_url: config.value.llm_base_url,
        model: config.value.llm_model,
      },
      embedding: {
        enabled: config.value.embedding_enabled,
        base_url: config.value.embedding_base_url,
        model: config.value.embedding_model,
        dimension: config.value.embedding_dimension || 4096,
        ...(config.value.embedding_api_key ? { api_key: config.value.embedding_api_key } : {}),
      },
      rerank: {
        enabled: config.value.rerank_enabled,
        base_url: config.value.rerank_base_url,
        model: config.value.rerank_model,
        max_documents_per_request: config.value.rerank_max_docs,
        ...(config.value.rerank_api_key ? { api_key: config.value.rerank_api_key } : {}),
      },
      memory: {
        enabled: config.value.memory_enabled,
        max_injected_chars: config.value.max_injected_chars,
        final_top_k: config.value.final_top_k,
        judge: {
          enabled: config.value.judge_enabled,
          provider: config.value.judge_provider,
          base_url: config.value.judge_base_url,
          api_key: config.value.judge_api_key,
          model: config.value.judge_model,
          timeout_seconds: config.value.judge_timeout_seconds,
          temperature: config.value.judge_temperature,
          mode: config.value.judge_mode,
          user_rules: config.value.judge_user_rules.split('\n').map((line: string) => line.trim()).filter(Boolean),
          prompt: config.value.judge_prompt,
        },
      },
    }
    payload.llm.api_key = config.value.llm_api_key

    const resp = await apiFetch('/admin/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await resp.json()
    if (data.status === 'ok') {
      message.success(data.message || '配置已保存')
    } else {
      message.error(data.message || '保存失败')
    }
  } catch (e) {
    message.error('无法连接到后端服务')
  }
}

async function rebuildIndex() {
  try {
    const resp = await apiFetch('/admin/rebuild-vector-index', { method: 'POST' })
    const data = await resp.json()
    if (data.status === 'ok') {
      message.success(`索引重建完成：${data.rebuilt} 条记忆已索引`)
    } else {
      message.error(data.message || '重建失败')
    }
  } catch (e) {
    message.error('无法连接到后端服务')
  }
}

function normalizeJudgeMode(mode: string) {
  if (mode === 'model_with_user_rules' || mode === 'rule_then_llm' || mode === 'user_rules_then_model') return 'model_with_user_rules'
  return 'model_only'
}

onMounted(loadConfig)
</script>

<template>
  <div>
    <div style="margin-bottom: 28px;">
      <h1 style="font-size: 24px; font-weight: 600; color: #e4e4e7; margin-bottom: 4px;">设置</h1>
      <p style="color: #71717a; font-size: 14px;">配置 KokoroMemo 服务参数</p>
    </div>

    <NSpace vertical :size="16">
      <!-- 服务配置 -->
      <NCard title="服务配置" style="background: #18181b; border: 1px solid #27272a;">
        <NForm label-placement="left" label-width="160" :show-feedback="false" style="gap: 12px; display: flex; flex-direction: column;">
          <NFormItem>
            <template #label>
              GUI 后端地址
              <NTooltip trigger="hover">
                <template #trigger><span class="help-icon">?</span></template>
                GUI 用这个地址访问 KokoroMemo 后端。如果你改了后端端口，请同步改成对应地址。
              </NTooltip>
            </template>
            <NInput v-model:value="backendUrl" placeholder="http://127.0.0.1:14514" style="width: 320px;" />
          </NFormItem>
          <NFormItem>
            <template #label>
              本地监听端口
              <NTooltip trigger="hover">
                <template #trigger><span class="help-icon">?</span></template>
                AIRP 客户端填写的 OpenAI Base URL 端口。例如客户端填 http://127.0.0.1:14514/v1
              </NTooltip>
            </template>
            <NInputNumber v-model:value="config.server_port" :min="1024" :max="65535" style="width: 200px;" />
          </NFormItem>
          <NFormItem>
            <template #label>
              数据存储目录
              <NTooltip trigger="hover">
                <template #trigger><span class="help-icon">?</span></template>
                所有数据库文件的根目录。留空使用默认值 ./data。修改后服务会自动重启
              </NTooltip>
            </template>
            <div style="display: flex; gap: 8px; flex: 1;">
              <NInput v-model:value="config.storage_root_dir" placeholder="./data" style="flex: 1;" />
              <NButton size="small" @click="pickFolder" title="选择文件夹">
                📁
              </NButton>
            </div>
          </NFormItem>
        </NForm>
      </NCard>

      <!-- LLM 配置 -->
      <NCard title="对话大模型配置" style="background: #18181b; border: 1px solid #27272a;">
        <template #header-extra>
          <NTooltip trigger="hover">
            <template #trigger><NTag size="small" round type="info" style="cursor: help;">请求将转发到此模型</NTag></template>
            你的 AIRP 客户端请求到本地后，KokoroMemo 会将对话转发到这里配置的云端大模型
          </NTooltip>
        </template>
        <NForm label-placement="left" label-width="160" :show-feedback="false" style="gap: 12px; display: flex; flex-direction: column;">
          <NFormItem>
            <template #label>
              转发模式
              <NTooltip trigger="hover">
                <template #trigger><span class="help-icon">?</span></template>
                覆盖模式：使用下方配置的 Key 和模型，AIRP 客户端可填任意 Key。透传模式：直接使用 AIRP 客户端传来的 Key 和模型名
              </NTooltip>
            </template>
            <NSelect
              v-model:value="config.llm_forward_mode"
              :options="forwardModeOptions"
              style="width: 280px;"
            />
          </NFormItem>
          <NFormItem>
            <template #label>
              Provider
              <NTooltip trigger="hover">
                <template #trigger><span class="help-icon">?</span></template>
                选择你的大模型服务商。大多数中转站选"OpenAI 兼容"即可
              </NTooltip>
            </template>
            <NSelect
              v-model:value="config.llm_provider"
              :options="providerOptions"
              style="width: 280px;"
            />
          </NFormItem>
          <NFormItem>
            <template #label>
              Base URL
              <NTooltip trigger="hover">
                <template #trigger><span class="help-icon">?</span></template>
                模型服务商提供的 API 地址，不需要加 /chat/completions 后缀
              </NTooltip>
            </template>
            <NInput v-model:value="config.llm_base_url" :placeholder="providerUrlPlaceholder" />
          </NFormItem>
          <NFormItem>
            <template #label>
              API Key
              <NTooltip trigger="hover">
                <template #trigger><span class="help-icon">?</span></template>
                从模型服务商后台获取的密钥，保存后写入本地 config.yaml，不会上传
              </NTooltip>
            </template>
            <NInput v-model:value="config.llm_api_key" type="password" show-password-on="click" placeholder="sk-..." />
          </NFormItem>
          <NFormItem>
            <template #label>
              模型名称
              <NTooltip trigger="hover">
                <template #trigger><span class="help-icon">?</span></template>
                你想使用的模型 ID，如 deepseek-chat、gpt-4o、claude-sonnet-4-20250514
              </NTooltip>
            </template>
            <div style="display: flex; gap: 8px; flex: 1;">
              <NSelect
                v-if="llmModels.length > 0"
                v-model:value="config.llm_model"
                :options="llmModels"
                filterable
                tag
                :placeholder="providerModelPlaceholder"
                style="flex: 1;"
              />
              <NInput v-else v-model:value="config.llm_model" :placeholder="providerModelPlaceholder" style="flex: 1;" />
              <NButton size="small" :loading="fetchingLlm" @click="fetchModelList(config.llm_base_url, config.llm_api_key, 'llm')">
                拉取
              </NButton>
            </div>
          </NFormItem>
        </NForm>
      </NCard>

      <!-- Embedding 配置 -->
      <NCard style="background: #18181b; border: 1px solid #27272a;">
        <template #header>
          Embedding 配置
          <NTooltip trigger="hover">
            <template #trigger><span class="help-icon">?</span></template>
            Embedding 将文本转为向量用于语义检索。默认使用模力方舟 Qwen3-Embedding-8B，需自行注册获取 API Key
          </NTooltip>
        </template>
        <NForm label-placement="left" label-width="160" :show-feedback="false" style="gap: 12px; display: flex; flex-direction: column;">
          <NFormItem label="启用 Embedding">
            <NSwitch v-model:value="config.embedding_enabled" />
          </NFormItem>
          <template v-if="config.embedding_enabled">
            <NFormItem label="Base URL">
              <NInput v-model:value="config.embedding_base_url" placeholder="https://ai.gitee.com/v1" />
            </NFormItem>
            <NFormItem label="API Key">
              <NInput v-model:value="config.embedding_api_key" type="password" show-password-on="click" placeholder="填写 Embedding 服务的 API Key" />
            </NFormItem>
            <NFormItem label="模型名称">
              <div style="display: flex; gap: 8px; flex: 1;">
                <NSelect
                  v-if="embeddingModels.length > 0"
                  v-model:value="config.embedding_model"
                  :options="embeddingModels"
                  filterable
                  tag
                  placeholder="qwen3-embedding-8b"
                  style="flex: 1;"
                />
                <NInput v-else v-model:value="config.embedding_model" placeholder="qwen3-embedding-8b" style="flex: 1;" />
                <NButton size="small" :loading="fetchingEmbedding" @click="fetchModelList(config.embedding_base_url, config.embedding_api_key, 'embedding')">
                  拉取
                </NButton>
              </div>
            </NFormItem>
            <NFormItem>
              <template #label>
                向量维度
                <NTooltip trigger="hover">
                  <template #trigger><span class="help-icon">?</span></template>
                  必须与模型实际输出维度一致；切换模型或维度后需要重建索引
                </NTooltip>
              </template>
              <NInputNumber v-model:value="config.embedding_dimension" :min="1" :max="8192" style="width: 200px;" placeholder="4096" />
            </NFormItem>
          </template>
        </NForm>
      </NCard>

      <!-- Rerank 配置 -->
      <NCard style="background: #18181b; border: 1px solid #27272a;">
        <template #header>
          Rerank 配置
          <NTooltip trigger="hover">
            <template #trigger><span class="help-icon">?</span></template>
            Rerank 对召回的记忆重新排序以提高准确度。默认关闭，记忆较多时建议开启。默认使用模力方舟 Qwen3-Reranker-8B，需自行注册获取 API Key
          </NTooltip>
        </template>
        <NForm label-placement="left" label-width="160" :show-feedback="false" style="gap: 12px; display: flex; flex-direction: column;">
          <NFormItem label="启用 Rerank">
            <NSwitch v-model:value="config.rerank_enabled" />
          </NFormItem>
          <template v-if="config.rerank_enabled">
            <NFormItem label="Base URL">
              <NInput v-model:value="config.rerank_base_url" placeholder="https://ai.gitee.com/v1" />
            </NFormItem>
            <NFormItem label="API Key">
              <NInput v-model:value="config.rerank_api_key" type="password" show-password-on="click" placeholder="填写 Rerank 服务的 API Key" />
            </NFormItem>
            <NFormItem label="模型名称">
              <div style="display: flex; gap: 8px; flex: 1;">
                <NSelect
                  v-if="rerankModels.length > 0"
                  v-model:value="config.rerank_model"
                  :options="rerankModels"
                  filterable
                  tag
                  placeholder="qwen3-reranker-8b"
                  style="flex: 1;"
                />
                <NInput v-else v-model:value="config.rerank_model" placeholder="qwen3-reranker-8b" style="flex: 1;" />
                <NButton size="small" :loading="fetchingRerank" @click="fetchModelList(config.rerank_base_url, config.rerank_api_key, 'rerank')">
                  拉取
                </NButton>
              </div>
            </NFormItem>
            <NFormItem>
              <template #label>
                每批最大文本数
                <NTooltip trigger="hover">
                  <template #trigger><span class="help-icon">?</span></template>
                  高级设置。每次 Rerank 请求最多发送多少条候选文本，默认 20。过大可能超时
                </NTooltip>
              </template>
              <NInputNumber v-model:value="config.rerank_max_docs" :min="5" :max="100" style="width: 200px;" />
            </NFormItem>
          </template>
        </NForm>
      </NCard>

      <!-- 记忆配置 -->
      <NCard style="background: #18181b; border: 1px solid #27272a;">
        <template #header>
          记忆配置
          <NTooltip trigger="hover">
            <template #trigger><span class="help-icon">?</span></template>
            控制 AI 角色的长期记忆行为。记忆会在对话中自动提炼并注入
          </NTooltip>
        </template>
        <NForm label-placement="left" label-width="160" :show-feedback="false" style="gap: 12px; display: flex; flex-direction: column;">
          <NFormItem label="启用记忆系统">
            <NSwitch v-model:value="config.memory_enabled" />
          </NFormItem>
          <NFormItem>
            <template #label>
              注入最大字数
              <NTooltip trigger="hover">
                <template #trigger><span class="help-icon">?</span></template>
                每次对话时注入的记忆总字数上限。过大可能占用上下文窗口
              </NTooltip>
            </template>
            <NInputNumber v-model:value="config.max_injected_chars" :min="500" :max="5000" style="width: 200px;" />
          </NFormItem>
          <NFormItem label="最大召回条数">
            <NInputNumber v-model:value="config.final_top_k" :min="1" :max="20" style="width: 200px;" />
          </NFormItem>
          <NDivider style="margin: 8px 0;" />
          <NFormItem>
            <template #label>
              记忆判断模型
              <NTooltip trigger="hover">
                <template #trigger><span class="help-icon">?</span></template>
                类似 SillyTavern 填表 API，使用更便宜更快的模型判断一轮对话是否应写入长期记忆。关闭后不再自动填表，只保留原始对话落盘、状态板和手动记忆管理。
              </NTooltip>
            </template>
            <NSwitch v-model:value="config.judge_enabled" />
          </NFormItem>
          <template v-if="config.judge_enabled">
            <NFormItem label="判断模式">
              <div style="display: flex; align-items: center; gap: 8px;">
                <NSelect v-model:value="config.judge_mode" :options="judgeModeOptions" style="width: 240px;" />
                <NTooltip trigger="hover">
                  <template #trigger><span class="help-icon">?</span></template>
                  “仅模型判断”完全交给记忆判断模型；“模型 + 用户辅助规则”会把下方规则附加进 Prompt，由模型参考执行，不再使用内置硬编码正则。
                </NTooltip>
              </div>
            </NFormItem>
            <NFormItem label="Provider">
              <NSelect v-model:value="config.judge_provider" :options="providerOptions" style="width: 280px;" />
            </NFormItem>
            <NFormItem label="Base URL">
              <NInput v-model:value="config.judge_base_url" placeholder="留空则复用对话大模型 Base URL" />
            </NFormItem>
            <NFormItem label="API Key">
              <NInput v-model:value="config.judge_api_key" type="password" show-password-on="click" placeholder="留空则复用对话大模型 Key" />
            </NFormItem>
            <NFormItem label="模型名称">
              <div style="display: flex; gap: 8px; flex: 1;">
                <NSelect
                  v-if="judgeModels.length > 0"
                  v-model:value="config.judge_model"
                  :options="judgeModels"
                  filterable
                  tag
                  placeholder="例如便宜快速的小模型"
                  style="flex: 1;"
                />
                <NInput v-else v-model:value="config.judge_model" placeholder="留空则复用对话大模型" style="flex: 1;" />
                <NButton size="small" :loading="fetchingJudge" @click="fetchModelList(config.judge_base_url || config.llm_base_url, config.judge_api_key || config.llm_api_key, 'judge')">
                  拉取
                </NButton>
              </div>
            </NFormItem>
            <NFormItem label="超时时间">
              <NInputNumber v-model:value="config.judge_timeout_seconds" :min="5" :max="120" style="width: 200px;" />
            </NFormItem>
            <NFormItem label="Temperature">
              <NInputNumber v-model:value="config.judge_temperature" :min="0" :max="1" :step="0.05" style="width: 200px;" />
            </NFormItem>
            <NFormItem>
              <template #label>
                用户辅助规则
                <NTooltip trigger="hover">
                  <template #trigger><span class="help-icon">?</span></template>
                  每行一条规则，仅在“模型 + 用户辅助规则”模式下生效。例如：用户要求改变称呼时生成 preference，tags 包含 addressing。
                </NTooltip>
              </template>
              <NInput v-model:value="config.judge_user_rules" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="每行一条辅助规则，留空则不附加" />
            </NFormItem>
            <NFormItem label="自定义 Prompt">
              <NInput v-model:value="config.judge_prompt" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="留空使用内置记忆判断 Prompt" />
            </NFormItem>
          </template>
        </NForm>

        <NDivider style="margin: 16px 0;" />

        <NSpace>
          <NButton type="warning" size="small" @click="rebuildIndex">
            重建向量索引
          </NButton>
        </NSpace>
      </NCard>

      <!-- 保存 -->
      <NAlert type="info" style="background: rgba(167, 139, 250, 0.05); border-color: #27272a;">
        保存后配置将写入 config.yaml 并立即生效。端口或存储目录变更时服务会自动重启。
      </NAlert>

      <div style="text-align: right;">
        <NButton type="primary" @click="saveConfig">保存配置</NButton>
      </div>
    </NSpace>
  </div>
</template>

<style scoped>
.help-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #3f3f46;
  color: #a1a1aa;
  font-size: 11px;
  font-weight: 600;
  cursor: help;
  margin-left: 6px;
  vertical-align: middle;
}
.help-icon:hover {
  background: #52525b;
  color: #e4e4e7;
}
</style>
