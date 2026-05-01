<script setup lang="ts">
import { h, ref, computed, onMounted } from 'vue'
import {
  NCard, NForm, NFormItem, NInput, NSwitch, NInputNumber,
  NButton, NSpace, NDivider, NAlert, NSelect,
  NTabs, NTabPane, NModal,
  NDynamicTags, NSlider, NProgress, NTag, NPopconfirm,
  NMenu, NDataTable,
  useMessage,
} from 'naive-ui'
import { apiFetch, getServerUrl, setServerUrl, resolveBackendUrl } from '../api'
import { useI18n } from 'vue-i18n'
import { setLanguage, getLanguage } from '../i18n'
import { invoke } from '@tauri-apps/api/core'
import { getVersion } from '@tauri-apps/api/app'

const message = useMessage()
const { t } = useI18n()
const backendUrl = ref(getServerUrl())
const loading = ref(true)

const llmModels = ref<{label: string, value: string}[]>([])
const embeddingModels = ref<{label: string, value: string}[]>([])
const rerankModels = ref<{label: string, value: string}[]>([])
const judgeModels = ref<{label: string, value: string}[]>([])
const stateFillerModels = ref<{label: string, value: string}[]>([])
const fetchingLlm = ref(false)
const fetchingEmbedding = ref(false)
const fetchingRerank = ref(false)
const fetchingJudge = ref(false)
const fetchingStateFiller = ref(false)
const updateChecking = ref(false)
const updateInfo = ref<{
  checked: boolean
  hasUpdate: boolean
  currentVersion: string
  latestVersion: string
  releaseUrl: string
  error: string
}>({
  checked: false,
  hasUpdate: false,
  currentVersion: '',
  latestVersion: '',
  releaseUrl: '',
  error: '',
})
const GITHUB_LATEST_RELEASE_API = 'https://api.github.com/repos/CyrilPeng/KokoroMemo/releases/latest'
const CURRENT_VERSION_FALLBACK = '0.1.0'

function normalizeVersion(version: string) {
  return version.trim().replace(/^v/i, '').split(/[+-]/)[0]
}

function compareVersions(a: string, b: string) {
  const left = normalizeVersion(a).split('.').map((part) => Number.parseInt(part, 10) || 0)
  const right = normalizeVersion(b).split('.').map((part) => Number.parseInt(part, 10) || 0)
  const length = Math.max(left.length, right.length)
  for (let i = 0; i < length; i += 1) {
    const diff = (left[i] || 0) - (right[i] || 0)
    if (diff !== 0) return diff > 0 ? 1 : -1
  }
  return 0
}

async function getCurrentAppVersion() {
  try {
    return await getVersion()
  } catch (e) {
    return CURRENT_VERSION_FALLBACK
  }
}

async function checkForUpdates(silent = false) {
  updateChecking.value = true
  try {
    const currentVersion = await getCurrentAppVersion()
    const resp = await fetch(GITHUB_LATEST_RELEASE_API, {
      headers: { Accept: 'application/vnd.github+json' },
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const data = await resp.json()
    const latestVersion = data.tag_name || data.name || ''
    const releaseUrl = data.html_url || 'https://github.com/CyrilPeng/KokoroMemo/releases/latest'
    const hasUpdate = latestVersion ? compareVersions(latestVersion, currentVersion) > 0 : false
    updateInfo.value = {
      checked: true,
      hasUpdate,
      currentVersion,
      latestVersion,
      releaseUrl,
      error: '',
    }
    if (!silent) {
      message[hasUpdate ? 'success' : 'info'](
        hasUpdate ? t('settings.updateAvailable') : t('settings.noUpdateAvailable'),
      )
    }
  } catch (e) {
    updateInfo.value = {
      ...updateInfo.value,
      checked: true,
      error: e instanceof Error ? e.message : String(e),
    }
    if (!silent) message.error(t('settings.updateCheckFailed'))
  } finally {
    updateChecking.value = false
  }
}

function openReleasePage() {
  if (updateInfo.value.releaseUrl) {
    window.open(updateInfo.value.releaseUrl, '_blank', 'noopener,noreferrer')
  }
}


const language = ref(getLanguage())
const closeToTray = ref(localStorage.getItem('kokoromemo.closeToTray') !== 'false')
const languageOptions = [
  { label: '中文', value: 'zh-CN' },
  { label: 'English', value: 'en-US' },
]
function handleLanguageChange(val: string) {
  setLanguage(val)
  language.value = val
}

async function handleCloseToTrayChange(enabled: boolean) {
  closeToTray.value = enabled
  localStorage.setItem('kokoromemo.closeToTray', enabled ? 'true' : 'false')
  try {
    await invoke('set_close_to_tray', { enabled })
  } catch (e) {
    // Browser dev mode or older desktop builds without this command.
  }
}

async function syncCloseToTraySetting() {
  try {
    await invoke('set_close_to_tray', { enabled: closeToTray.value })
  } catch (e) {
    // Browser dev mode or older desktop builds without this command.
  }
}
const timezone = ref('')

async function fetchModelList(baseUrl: string, apiKey: string, target: 'llm' | 'embedding' | 'rerank' | 'judge' | 'state_filler') {
  if (!baseUrl) {
    message.warning(t('settings.inputBaseUrl'))
    return
  }
  if (!apiKey) {
    message.warning(t('settings.inputApiKey'))
    return
  }
  const flagRef = target === 'llm' ? fetchingLlm : target === 'embedding' ? fetchingEmbedding : target === 'rerank' ? fetchingRerank : target === 'judge' ? fetchingJudge : fetchingStateFiller
  flagRef.value = true
  const provider = target === 'llm' ? config.value.llm_provider : undefined
  try {
    const resp = await apiFetch('/admin/fetch-models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url: baseUrl, api_key: apiKey, provider }),
    })
    const data = await resp.json()
    if (data.status === 'ok' && data.models.length > 0) {
      const options = data.models.map((m: string) => ({ label: m, value: m }))
      if (target === 'llm') llmModels.value = options
      else if (target === 'embedding') embeddingModels.value = options
      else if (target === 'rerank') rerankModels.value = options
      else if (target === 'judge') judgeModels.value = options
      else stateFillerModels.value = options
      message.success(t('settings.fetchModelsSuccess', { count: data.models.length }))
    } else {
      message.error(data.message || t('settings.fetchModelsEmpty'))
    }
  } catch (e) {
    message.error(t('settings.fetchModelsFailed'))
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
  embedding_model: 'Qwen3-Embedding-8B',
  embedding_dimension: 4096,
  rerank_enabled: false,
  rerank_provider: 'modelark',
  rerank_base_url: '',
  rerank_api_key: '',
  rerank_model: 'Qwen3-Reranker-8B',
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
  state_filler_enabled: true,
  state_filler_mode: 'model_template',
  state_filler_provider: 'openai_compatible',
  state_filler_base_url: '',
  state_filler_api_key: '',
  state_filler_model: '',
  state_filler_timeout_seconds: 30,
  state_filler_temperature: 0,
  state_filler_min_confidence: 0.55,
  state_filler_prompt: '',
  // Advanced — conversation auto-detection
  conv_auto_gap: 0,
  conv_detect_prompt_change: false,
  conv_detect_count_reset: false,
  // Advanced — memory top-level
  inject_enabled: true,
  extraction_enabled: true,
  max_recent_turns_for_query: 6,
  vector_top_k: 30,
  // Advanced — scopes
  scope_global: true,
  scope_character: true,
  scope_conversation: true,
  // Advanced — extraction
  ext_min_importance: 0.45,
  ext_min_confidence: 0.55,
  ext_after_each_turn: true,
  ext_fallback_rule_based: true,
  // Advanced — scoring weights
  score_vector: 0.55,
  score_importance: 0.20,
  score_recency: 0.10,
  score_scope: 0.10,
  score_confidence: 0.05,
  // Advanced — retrieval gate
  rg_enabled: true,
  rg_mode: 'auto',
  rg_on_new_session: true,
  rg_every_n_turns: 6,
  rg_state_conf_below: 0.65,
  rg_trigger_keywords: [] as string[],
  rg_skip_chars_below: 4,
  rg_skip_when_state_sufficient: true,
  // Advanced — hot context
  hc_enabled: true,
  hc_inject_always: true,
  hc_max_chars: 1200,
  hc_include_sections: {} as Record<string, boolean>,
  hc_section_order: [] as string[],
  hc_max_items: {} as Record<string, number>,
})

const forwardModeOptions = computed(() => [
  { label: t('settings.overrideMode'), value: 'override' },
  { label: t('settings.passthroughMode'), value: 'passthrough' },
])

const providerOptions = computed(() => [
  { label: t('settings.openaiCompatible'), value: 'openai_compatible' },
  { label: 'OpenAI Responses API', value: 'openai_responses' },
  { label: 'Anthropic Claude', value: 'anthropic' },
  { label: 'Google Gemini', value: 'gemini' },
])

const HOT_CONTEXT_SECTION_KEYS = [
  'boundary', 'scene', 'location', 'key_person', 'relationship',
  'main_quest', 'side_quest', 'promise', 'open_loop', 'item',
  'world_state', 'recent_summary', 'mood', 'preference',
]

const retrievalGateModes = computed(() => [
  { label: t('settings.adv.gateModeAuto'), value: 'auto' },
  { label: t('settings.adv.gateModeAlways'), value: 'always' },
  { label: t('settings.adv.gateModeNever'), value: 'never' },
  { label: t('settings.adv.gateModeKeyword'), value: 'keyword_only' },
])

const scoringTotal = computed(() => {
  return (config.value.score_vector || 0)
    + (config.value.score_importance || 0)
    + (config.value.score_recency || 0)
    + (config.value.score_scope || 0)
    + (config.value.score_confidence || 0)
})

const advancedSection = ref('memoryTop')
const advancedMenuOptions = computed(() => [
  { label: t('settings.adv.memoryTop'), key: 'memoryTop' },
  { label: t('settings.adv.conversation'), key: 'conversation' },
  { label: t('settings.adv.scopes'), key: 'scopes' },
  { label: t('settings.adv.extraction'), key: 'extraction' },
  { label: t('settings.adv.scoring'), key: 'scoring' },
  { label: t('settings.adv.retrievalGate'), key: 'gate' },
  { label: t('settings.adv.hotContext'), key: 'hotContext' },
])

const hotContextRows = computed(() =>
  HOT_CONTEXT_SECTION_KEYS.map((key) => ({
    key,
    label: t(`settings.adv.section.${key}`),
    enabled: config.value.hc_include_sections[key] !== false,
    max: config.value.hc_max_items[key] ?? 5,
  }))
)

const hotContextColumns = computed(() => [
  {
    title: t('settings.adv.hcColEnabled'),
    key: 'enabled',
    width: 80,
    render: (row: any) => h(NSwitch, {
      size: 'small',
      value: row.enabled,
      'onUpdate:value': (v: boolean) => { config.value.hc_include_sections[row.key] = v },
    }),
  },
  { title: t('settings.adv.hcColSection'), key: 'label', minWidth: 140 },
  {
    title: t('settings.adv.hcColMax'),
    key: 'max',
    width: 130,
    render: (row: any) => h(NInputNumber, {
      size: 'small',
      value: row.max,
      min: 0,
      max: 50,
      style: 'width: 100%;',
      'onUpdate:value': (v: number | null) => { config.value.hc_max_items[row.key] = v ?? 5 },
    }),
  },
])

const judgeModeOptions = computed(() => [
  { label: t('settings.judgeModeModel'), value: 'model_only' },
  { label: t('settings.judgeModeModelRules'), value: 'model_with_user_rules' },
])

const helpModal = ref('')

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
      message.info(t('settings.browserEnv'))
      return
    }
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ directory: true, multiple: false, title: t('settings.folderDialog') })
    if (selected) {
      config.value.storage_root_dir = selected as string
    }
  } catch (e: any) {
    message.error(t('settings.folderError', { error: e?.message || e || t('settings.folderPermission') }))
  }
}

async function loadConfig() {
  loading.value = true
  try {
    const resp = await apiFetch('/admin/config')
    if (resp.ok) {
      const data = await resp.json()
      config.value.server_port = data.server?.port || 14514
      timezone.value = data.server?.timezone || ''
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
      config.value.judge_mode = data.memory?.judge?.mode || 'model_only'
      config.value.judge_user_rules = (data.memory?.judge?.user_rules || []).join('\n')
      config.value.judge_prompt = data.memory?.judge?.prompt || ''
      config.value.state_filler_enabled = data.memory?.state_updater?.enabled ?? true
      config.value.state_filler_mode = data.memory?.state_updater?.mode || 'model_template'
      config.value.state_filler_provider = data.memory?.state_updater?.provider || 'openai_compatible'
      config.value.state_filler_base_url = data.memory?.state_updater?.base_url || ''
      config.value.state_filler_api_key = data.memory?.state_updater?.api_key || ''
      config.value.state_filler_model = data.memory?.state_updater?.model || ''
      config.value.state_filler_timeout_seconds = data.memory?.state_updater?.timeout_seconds || 30
      config.value.state_filler_temperature = data.memory?.state_updater?.temperature ?? 0
      config.value.state_filler_min_confidence = data.memory?.state_updater?.min_confidence ?? 0.55
      config.value.state_filler_prompt = data.memory?.state_updater?.prompt || ''
      // Advanced
      config.value.conv_auto_gap = data.conversation?.auto_new_session_gap_minutes ?? 0
      config.value.conv_detect_prompt_change = data.conversation?.detect_system_prompt_change ?? false
      config.value.conv_detect_count_reset = data.conversation?.detect_message_count_reset ?? false
      config.value.inject_enabled = data.memory?.inject_enabled ?? true
      config.value.extraction_enabled = data.memory?.extraction_enabled ?? true
      config.value.max_recent_turns_for_query = data.memory?.max_recent_turns_for_query ?? 6
      config.value.vector_top_k = data.memory?.vector_top_k ?? 30
      const scopes = data.memory?.scopes || {}
      config.value.scope_global = scopes.include_global ?? true
      config.value.scope_character = scopes.include_character ?? true
      config.value.scope_conversation = scopes.include_conversation ?? true
      const ext = data.memory?.extraction || {}
      config.value.ext_min_importance = ext.min_importance ?? 0.45
      config.value.ext_min_confidence = ext.min_confidence ?? 0.55
      config.value.ext_after_each_turn = ext.extract_after_each_turn ?? true
      config.value.ext_fallback_rule_based = ext.fallback_rule_based ?? true
      const sc = data.memory?.scoring || {}
      config.value.score_vector = sc.vector_weight ?? 0.55
      config.value.score_importance = sc.importance_weight ?? 0.20
      config.value.score_recency = sc.recency_weight ?? 0.10
      config.value.score_scope = sc.scope_weight ?? 0.10
      config.value.score_confidence = sc.confidence_weight ?? 0.05
      const rg = data.memory?.retrieval_gate || {}
      config.value.rg_enabled = rg.enabled ?? true
      config.value.rg_mode = rg.mode || 'auto'
      config.value.rg_on_new_session = rg.vector_search_on_new_session ?? true
      config.value.rg_every_n_turns = rg.vector_search_every_n_turns ?? 6
      config.value.rg_state_conf_below = rg.vector_search_when_state_confidence_below ?? 0.65
      config.value.rg_trigger_keywords = Array.isArray(rg.trigger_keywords) ? [...rg.trigger_keywords] : []
      config.value.rg_skip_chars_below = rg.skip_when_latest_user_text_chars_below ?? 4
      config.value.rg_skip_when_state_sufficient = rg.skip_when_state_is_sufficient ?? true
      const hc = data.memory?.hot_context || {}
      config.value.hc_enabled = hc.enabled ?? true
      config.value.hc_inject_always = hc.inject_always ?? true
      config.value.hc_max_chars = hc.max_chars ?? 1200
      config.value.hc_include_sections = { ...(hc.include_sections || {}) }
      config.value.hc_section_order = Array.isArray(hc.section_order) ? [...hc.section_order] : []
      config.value.hc_max_items = { ...(hc.max_items_per_section || {}) }
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
      server: { port: config.value.server_port, timezone: timezone.value || undefined },
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
        inject_enabled: config.value.inject_enabled,
        extraction_enabled: config.value.extraction_enabled,
        max_recent_turns_for_query: config.value.max_recent_turns_for_query,
        vector_top_k: config.value.vector_top_k,
        max_injected_chars: config.value.max_injected_chars,
        final_top_k: config.value.final_top_k,
        scopes: {
          include_global: config.value.scope_global,
          include_character: config.value.scope_character,
          include_conversation: config.value.scope_conversation,
        },
        scoring: {
          vector_weight: config.value.score_vector,
          importance_weight: config.value.score_importance,
          recency_weight: config.value.score_recency,
          scope_weight: config.value.score_scope,
          confidence_weight: config.value.score_confidence,
        },
        extraction: {
          min_importance: config.value.ext_min_importance,
          min_confidence: config.value.ext_min_confidence,
          extract_after_each_turn: config.value.ext_after_each_turn,
          fallback_rule_based: config.value.ext_fallback_rule_based,
        },
        retrieval_gate: {
          enabled: config.value.rg_enabled,
          mode: config.value.rg_mode,
          vector_search_on_new_session: config.value.rg_on_new_session,
          vector_search_every_n_turns: config.value.rg_every_n_turns,
          vector_search_when_state_confidence_below: config.value.rg_state_conf_below,
          trigger_keywords: config.value.rg_trigger_keywords,
          skip_when_latest_user_text_chars_below: config.value.rg_skip_chars_below,
          skip_when_state_is_sufficient: config.value.rg_skip_when_state_sufficient,
        },
        hot_context: {
          enabled: config.value.hc_enabled,
          inject_always: config.value.hc_inject_always,
          max_chars: config.value.hc_max_chars,
          include_sections: config.value.hc_include_sections,
          section_order: config.value.hc_section_order,
          max_items_per_section: config.value.hc_max_items,
        },
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
        state_updater: {
          enabled: config.value.state_filler_enabled,
          mode: config.value.state_filler_mode,
          update_after_each_turn: true,
          update_every_n_turns: 1,
          min_confidence: config.value.state_filler_min_confidence,
          provider: config.value.state_filler_provider,
          base_url: config.value.state_filler_base_url,
          api_key: config.value.state_filler_api_key,
          model: config.value.state_filler_model,
          timeout_seconds: config.value.state_filler_timeout_seconds,
          temperature: config.value.state_filler_temperature,
          prompt: config.value.state_filler_prompt,
        },
      },
    }
    payload.llm.api_key = config.value.llm_api_key
    payload.conversation = {
      auto_new_session_gap_minutes: config.value.conv_auto_gap,
      detect_system_prompt_change: config.value.conv_detect_prompt_change,
      detect_message_count_reset: config.value.conv_detect_count_reset,
    }

    const resp = await apiFetch('/admin/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await resp.json()
    if (data.status === 'ok') {
      message.success(data.message || t('settings.configSaved'))
    } else if (data.status === 'restart_required') {
      message.success(data.message || '配置已保存，正在重启服务...')
      try {
        await invoke('restart_backend')
        // Re-resolve port — it may have changed after restart
        const newUrl = await resolveBackendUrl()
        backendUrl.value = newUrl
        message.success('服务已重启')
      } catch (e) {
        message.warning('自动重启失败，请手动重启服务')
      }
    } else {
      message.error(data.message || t('common.saveFailed'))
    }
  } catch (e) {
    message.error(t('common.backendConnectionFailed'))
  }
}

async function rebuildIndex() {
  try {
    const resp = await apiFetch('/admin/rebuild-vector-index', { method: 'POST' })
    const data = await resp.json()
    if (data.status === 'ok') {
      message.success(t('settings.indexRebuilt', { count: data.rebuilt }))
    } else {
      message.error(data.message || t('settings.rebuildFailed'))
    }
  } catch (e) {
    message.error(t('common.backendConnectionFailed'))
  }
}

const migrationStatus = ref<any>({ status: 'idle' })
let migrationPollTimer: number | null = null

async function fetchMigrationStatus() {
  try {
    const resp = await apiFetch('/admin/index-migration-status')
    if (resp.ok) migrationStatus.value = await resp.json()
  } catch {}
}

async function startMigration() {
  try {
    const resp = await apiFetch('/admin/start-index-migration', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    const data = await resp.json()
    if (data.status === 'ok') {
      message.success(t('settings.migrationStarted'))
      pollMigration()
    } else {
      message.error(data.message || t('settings.migrationFailed'))
    }
  } catch {
    message.error(t('common.backendConnectionFailed'))
  }
}

function pollMigration() {
  if (migrationPollTimer) clearInterval(migrationPollTimer)
  migrationPollTimer = window.setInterval(async () => {
    await fetchMigrationStatus()
    const s = migrationStatus.value?.status
    if (s !== 'running') {
      if (migrationPollTimer) {
        clearInterval(migrationPollTimer)
        migrationPollTimer = null
      }
    }
  }, 2000)
}

const migrationProgressPercent = computed(() => {
  const total = migrationStatus.value?.total || 0
  const progress = migrationStatus.value?.progress || 0
  if (!total) return 0
  return Math.min(100, Math.round((progress / total) * 100))
})

async function retryVectorSync() {
  try {
    const resp = await apiFetch('/admin/jobs/retry-vector-sync?limit=50', { method: 'POST' })
    const data = await resp.json()
    if (data.status === 'ok') {
      message.success(t('settings.vectorSyncDone', { total: data.total, success: data.success, failed: data.failed }))
    } else {
      message.error(data.message || t('settings.vectorSyncFailed'))
    }
  } catch {
    message.error(t('common.backendConnectionFailed'))
  }
}

onMounted(() => {
  loadConfig()
  syncCloseToTraySetting()
})
</script>

<template>
  <div>
    <div style="margin-bottom: 28px;">
      <h1 style="font-size: 24px; font-weight: 600; color: #e4e4e7; margin-bottom: 4px;">{{ $t('settings.title') }}</h1>
      <p style="color: #71717a; font-size: 14px;">{{ $t('settings.subtitle') }}</p>
    </div>

    <NTabs type="line" animated>
      <!-- Tab 1: 模型配置 -->
      <NTabPane name="model" :tab="$t('settings.tabModel')">
        <NSpace vertical :size="16">
          <!-- LLM Config -->
          <NCard style="background: #18181b; border: 1px solid #27272a;">
            <template #header>
              <NSpace align="center">
                <span>{{ $t('settings.llmConfig') }}</span>
                <NButton quaternary size="tiny" @click="helpModal = 'llm'"><span class="help-icon">?</span></NButton>
              </NSpace>
            </template>
            <NForm label-placement="left" label-width="160" :show-feedback="false" style="gap: 12px; display: flex; flex-direction: column;">
              <NFormItem :label="$t('settings.forwardMode')">
                <NSelect v-model:value="config.llm_forward_mode" :options="forwardModeOptions" style="width: 280px;" />
              </NFormItem>
              <NFormItem :label="$t('settings.provider')">
                <NSelect v-model:value="config.llm_provider" :options="providerOptions" style="width: 280px;" />
              </NFormItem>
              <NFormItem label="Base URL">
                <NInput v-model:value="config.llm_base_url" :placeholder="providerUrlPlaceholder" />
              </NFormItem>
              <NFormItem label="API Key">
                <NInput v-model:value="config.llm_api_key" type="password" show-password-on="click" placeholder="sk-..." />
              </NFormItem>
              <NFormItem :label="$t('settings.modelName')">
                <div style="display: flex; gap: 8px; flex: 1;">
                  <NSelect v-if="llmModels.length > 0" v-model:value="config.llm_model" :options="llmModels" filterable tag :placeholder="providerModelPlaceholder" style="flex: 1;" />
                  <NInput v-else v-model:value="config.llm_model" :placeholder="providerModelPlaceholder" style="flex: 1;" />
                  <NButton size="small" :loading="fetchingLlm" @click="fetchModelList(config.llm_base_url, config.llm_api_key, 'llm')">{{ $t('common.fetch') }}</NButton>
                </div>
              </NFormItem>
            </NForm>
          </NCard>

          <!-- Embedding Config -->
          <NCard style="background: #18181b; border: 1px solid #27272a;">
            <template #header>
              <NSpace align="center">
                <span>{{ $t('settings.embeddingConfig') }}</span>
                <NButton quaternary size="tiny" @click="helpModal = 'embedding'"><span class="help-icon">?</span></NButton>
              </NSpace>
            </template>
            <NForm label-placement="left" label-width="160" :show-feedback="false" style="gap: 12px; display: flex; flex-direction: column;">
              <NFormItem :label="$t('settings.enableEmbedding')">
                <NSwitch v-model:value="config.embedding_enabled" />
              </NFormItem>
              <template v-if="config.embedding_enabled">
                <NFormItem label="Base URL">
                  <NInput v-model:value="config.embedding_base_url" placeholder="https://ai.gitee.com/v1" />
                </NFormItem>
                <NFormItem label="API Key">
                  <NInput v-model:value="config.embedding_api_key" type="password" show-password-on="click" :placeholder="$t('settings.embeddingApiKeyPlaceholder')" />
                </NFormItem>
                <NFormItem :label="$t('settings.modelName')">
                  <div style="display: flex; gap: 8px; flex: 1;">
                    <NSelect v-if="embeddingModels.length > 0" v-model:value="config.embedding_model" :options="embeddingModels" filterable tag placeholder="Qwen3-Embedding-8B" style="flex: 1;" />
                    <NInput v-else v-model:value="config.embedding_model" placeholder="Qwen3-Embedding-8B" style="flex: 1;" />
                    <NButton size="small" :loading="fetchingEmbedding" @click="fetchModelList(config.embedding_base_url, config.embedding_api_key, 'embedding')">{{ $t('common.fetch') }}</NButton>
                  </div>
                </NFormItem>
                <NFormItem :label="$t('settings.dimension')">
                  <NInputNumber v-model:value="config.embedding_dimension" :min="1" :max="8192" style="width: 200px;" placeholder="4096" />
                </NFormItem>
              </template>
            </NForm>
          </NCard>

          <!-- Rerank Config -->
          <NCard style="background: #18181b; border: 1px solid #27272a;">
            <template #header>
              <NSpace align="center">
                <span>{{ $t('settings.rerankConfig') }}</span>
                <NButton quaternary size="tiny" @click="helpModal = 'rerank'"><span class="help-icon">?</span></NButton>
              </NSpace>
            </template>
            <NForm label-placement="left" label-width="160" :show-feedback="false" style="gap: 12px; display: flex; flex-direction: column;">
              <NFormItem :label="$t('settings.enableRerank')">
                <NSwitch v-model:value="config.rerank_enabled" />
              </NFormItem>
              <template v-if="config.rerank_enabled">
                <NFormItem label="Base URL">
                  <NInput v-model:value="config.rerank_base_url" placeholder="https://ai.gitee.com/v1" />
                </NFormItem>
                <NFormItem label="API Key">
                  <NInput v-model:value="config.rerank_api_key" type="password" show-password-on="click" :placeholder="$t('settings.rerankApiKeyPlaceholder')" />
                </NFormItem>
                <NFormItem :label="$t('settings.modelName')">
                  <div style="display: flex; gap: 8px; flex: 1;">
                    <NSelect v-if="rerankModels.length > 0" v-model:value="config.rerank_model" :options="rerankModels" filterable tag placeholder="Qwen3-Reranker-8B" style="flex: 1;" />
                    <NInput v-else v-model:value="config.rerank_model" placeholder="Qwen3-Reranker-8B" style="flex: 1;" />
                    <NButton size="small" :loading="fetchingRerank" @click="fetchModelList(config.rerank_base_url, config.rerank_api_key, 'rerank')">{{ $t('common.fetch') }}</NButton>
                  </div>
                </NFormItem>
                <NFormItem :label="$t('settings.maxDocsPerBatch')">
                  <NInputNumber v-model:value="config.rerank_max_docs" :min="5" :max="100" style="width: 200px;" />
                </NFormItem>
              </template>
            </NForm>
          </NCard>
        </NSpace>
      </NTabPane>

      <!-- Tab 2: 记忆配置 -->
      <NTabPane name="memory" :tab="$t('settings.tabMemory')">
        <NSpace vertical :size="16">
          <NCard style="background: #18181b; border: 1px solid #27272a;">
            <template #header>
              <NSpace align="center">
                <span>{{ $t('settings.memoryConfig') }}</span>
                <NButton quaternary size="tiny" @click="helpModal = 'memory'"><span class="help-icon">?</span></NButton>
              </NSpace>
            </template>
            <NForm label-placement="left" label-width="160" :show-feedback="false" style="gap: 12px; display: flex; flex-direction: column;">
              <NFormItem :label="$t('settings.enableMemory')">
                <NSwitch v-model:value="config.memory_enabled" />
              </NFormItem>
              <NFormItem :label="$t('settings.maxInjectChars')">
                <NInputNumber v-model:value="config.max_injected_chars" :min="500" :max="5000" style="width: 200px;" />
              </NFormItem>
              <NFormItem :label="$t('settings.maxRecall')">
                <NInputNumber v-model:value="config.final_top_k" :min="1" :max="20" style="width: 200px;" />
              </NFormItem>
              <NDivider style="margin: 8px 0;" />
              <NFormItem :label="$t('settings.memoryJudge')">
                <NSwitch v-model:value="config.judge_enabled" />
              </NFormItem>
              <template v-if="config.judge_enabled">
                <NFormItem :label="$t('settings.judgeMode')">
                  <NSelect v-model:value="config.judge_mode" :options="judgeModeOptions" style="width: 240px;" />
                </NFormItem>
                <NFormItem label="Provider">
                  <NSelect v-model:value="config.judge_provider" :options="providerOptions" style="width: 280px;" />
                </NFormItem>
                <NFormItem label="Base URL">
                  <NInput v-model:value="config.judge_base_url" :placeholder="$t('settings.reuseLlmBaseUrl')" />
                </NFormItem>
                <NFormItem label="API Key">
                  <NInput v-model:value="config.judge_api_key" type="password" show-password-on="click" :placeholder="$t('settings.reuseLlmApiKey')" />
                </NFormItem>
                <NFormItem :label="$t('settings.modelName')">
                  <div style="display: flex; gap: 8px; flex: 1;">
                    <NSelect v-if="judgeModels.length > 0" v-model:value="config.judge_model" :options="judgeModels" filterable tag :placeholder="$t('settings.cheapModelPlaceholder')" style="flex: 1;" />
                    <NInput v-else v-model:value="config.judge_model" :placeholder="$t('settings.reuseLlmModel')" style="flex: 1;" />
                    <NButton size="small" :loading="fetchingJudge" @click="fetchModelList(config.judge_base_url || config.llm_base_url, config.judge_api_key || config.llm_api_key, 'judge')">{{ $t('common.fetch') }}</NButton>
                  </div>
                </NFormItem>
                <NFormItem :label="$t('settings.timeout')">
                  <NInputNumber v-model:value="config.judge_timeout_seconds" :min="5" :max="120" style="width: 200px;" />
                </NFormItem>
                <NFormItem label="Temperature">
                  <NInputNumber v-model:value="config.judge_temperature" :min="0" :max="1" :step="0.05" style="width: 200px;" />
                </NFormItem>
                <NFormItem :label="$t('settings.userRules')">
                  <NInput v-model:value="config.judge_user_rules" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :placeholder="$t('settings.userRulesPlaceholder')" />
                </NFormItem>
                <NFormItem :label="$t('settings.customPrompt')">
                  <NInput v-model:value="config.judge_prompt" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :placeholder="$t('settings.judgePromptPlaceholder')" />
                </NFormItem>
              </template>
            </NForm>

            <NDivider style="margin: 16px 0;" />
            <div class="vector-actions">
              <h4 class="vector-actions-title">
                {{ $t('settings.vectorMaintenance') }}
                <NButton quaternary size="tiny" @click="helpModal = 'vectorMaintenance'"><span class="help-icon">?</span></NButton>
              </h4>
              <div class="vector-action-row">
                <div class="vector-action-info">
                  <div class="vector-action-name">{{ $t('settings.rebuildIndex') }}</div>
                  <div class="vector-action-desc">{{ $t('settings.rebuildIndexDesc') }}</div>
                </div>
                <NPopconfirm :positive-text="$t('common.confirm')" :negative-text="$t('common.cancel')" @positive-click="rebuildIndex">
                  <template #trigger><NButton type="warning" size="small">{{ $t('common.execute') }}</NButton></template>
                  {{ $t('settings.rebuildIndexConfirm') }}
                </NPopconfirm>
              </div>
              <div class="vector-action-row">
                <div class="vector-action-info">
                  <div class="vector-action-name">{{ $t('settings.startMigration') }}</div>
                  <div class="vector-action-desc">{{ $t('settings.startMigrationDesc') }}</div>
                </div>
                <NPopconfirm :positive-text="$t('common.confirm')" :negative-text="$t('common.cancel')" @positive-click="startMigration" :disabled="migrationStatus?.status === 'running'">
                  <template #trigger><NButton size="small" :disabled="migrationStatus?.status === 'running'">{{ $t('common.execute') }}</NButton></template>
                  {{ $t('settings.startMigrationConfirm') }}
                </NPopconfirm>
              </div>
              <div class="vector-action-row">
                <div class="vector-action-info">
                  <div class="vector-action-name">{{ $t('settings.retryVectorSync') }}</div>
                  <div class="vector-action-desc">{{ $t('settings.retryVectorSyncDesc') }}</div>
                </div>
                <NButton size="small" @click="retryVectorSync">{{ $t('common.execute') }}</NButton>
              </div>
            </div>
            <div v-if="migrationStatus?.status && migrationStatus.status !== 'idle'" style="margin-top: 12px;">
              <NSpace align="center" :size="8">
                <NTag size="small" :type="migrationStatus.status === 'running' ? 'info' : migrationStatus.status === 'completed' ? 'success' : 'error'">
                  {{ migrationStatus.status }}
                </NTag>
                <span v-if="migrationStatus.error" style="color: #ef4444; font-size: 12px;">{{ migrationStatus.error }}</span>
                <span v-else-if="migrationStatus.status === 'running'" style="color: #a1a1aa; font-size: 12px;">
                  {{ migrationStatus.progress || 0 }} / {{ migrationStatus.total || 0 }}
                </span>
              </NSpace>
              <NProgress
                v-if="migrationStatus.status === 'running'"
                :percentage="migrationProgressPercent"
                :show-indicator="false"
                style="margin-top: 6px;"
              />
            </div>
          </NCard>
        </NSpace>
      </NTabPane>

      <!-- Tab 3: 状态板填表 -->
      <NTabPane name="stateFiller" :tab="$t('settings.tabStateFiller')">
        <NSpace vertical :size="16">
          <NCard style="background: #18181b; border: 1px solid #27272a;">
            <template #header>
              <NSpace align="center">
                <span>{{ $t('settings.stateFillerConfig') }}</span>
                <NButton quaternary size="tiny" @click="helpModal = 'stateFiller'"><span class="help-icon">?</span></NButton>
              </NSpace>
            </template>
            <NForm label-placement="left" label-width="160" :show-feedback="false" style="gap: 12px; display: flex; flex-direction: column;">
              <NFormItem :label="$t('common.enabled')">
                <NSwitch v-model:value="config.state_filler_enabled" />
              </NFormItem>
              <template v-if="config.state_filler_enabled">
                <NFormItem label="Provider">
                  <NSelect v-model:value="config.state_filler_provider" :options="providerOptions" style="width: 280px;" />
                </NFormItem>
                <NFormItem label="Base URL">
                  <NInput v-model:value="config.state_filler_base_url" :placeholder="$t('settings.reuseBaseUrlPlaceholder')" />
                </NFormItem>
                <NFormItem label="API Key">
                  <NInput v-model:value="config.state_filler_api_key" type="password" show-password-on="click" :placeholder="$t('settings.reuseApiKeyPlaceholder')" />
                </NFormItem>
                <NFormItem :label="$t('settings.modelName')">
                  <div style="display: flex; gap: 8px; flex: 1;">
                    <NSelect v-if="stateFillerModels.length > 0" v-model:value="config.state_filler_model" :options="stateFillerModels" filterable tag :placeholder="$t('settings.cheapModelPlaceholder')" style="flex: 1;" />
                    <NInput v-else v-model:value="config.state_filler_model" :placeholder="$t('settings.reuseModelPlaceholder')" style="flex: 1;" />
                    <NButton size="small" :loading="fetchingStateFiller" @click="fetchModelList(config.state_filler_base_url || config.judge_base_url || config.llm_base_url, config.state_filler_api_key || config.judge_api_key || config.llm_api_key, 'state_filler')">{{ $t('common.fetch') }}</NButton>
                  </div>
                </NFormItem>
                <NFormItem :label="$t('settings.minConfidence')">
                  <NInputNumber v-model:value="config.state_filler_min_confidence" :min="0" :max="1" :step="0.05" style="width: 200px;" />
                </NFormItem>
                <NFormItem :label="$t('settings.timeout')">
                  <NInputNumber v-model:value="config.state_filler_timeout_seconds" :min="5" :max="120" style="width: 200px;" />
                </NFormItem>
                <NFormItem label="Temperature">
                  <NInputNumber v-model:value="config.state_filler_temperature" :min="0" :max="1" :step="0.05" style="width: 200px;" />
                </NFormItem>
                <NFormItem :label="$t('settings.customPrompt')">
                  <NInput v-model:value="config.state_filler_prompt" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :placeholder="$t('settings.stateFillerPromptPlaceholder')" />
                </NFormItem>
              </template>
            </NForm>
          </NCard>
        </NSpace>
      </NTabPane>

      <!-- Tab 4: 服务配置 -->
      <NTabPane name="server" :tab="$t('settings.tabServer')">
        <NSpace vertical :size="16">
          <NCard style="background: #18181b; border: 1px solid #27272a;">
            <template #header>
              <NSpace align="center">
                <span>{{ $t('settings.serverConfig') }}</span>
                <NButton quaternary size="tiny" @click="helpModal = 'server'"><span class="help-icon">?</span></NButton>
              </NSpace>
            </template>
            <NForm label-placement="left" label-width="160" :show-feedback="false" style="gap: 12px; display: flex; flex-direction: column;">
              <NFormItem :label="$t('settings.guiBackendUrl')">
                <NInput v-model:value="backendUrl" placeholder="http://127.0.0.1:14514" style="width: 320px;" />
              </NFormItem>
              <NFormItem :label="$t('settings.localPort')">
                <NInputNumber v-model:value="config.server_port" :min="1024" :max="65535" style="width: 200px;" />
              </NFormItem>
              <NFormItem :label="$t('settings.storageDir')">
                <div style="display: flex; gap: 8px; flex: 1;">
                  <NInput v-model:value="config.storage_root_dir" placeholder="./data" style="flex: 1;" />
                  <NButton size="small" @click="pickFolder" :title="$t('settings.selectFolder')">📁</NButton>
                </div>
              </NFormItem>
              <NFormItem :label="$t('settings.timezone')">
                <NInput v-model:value="timezone" :placeholder="$t('settings.timezonePlaceholder')" style="width: 280px;" />
              </NFormItem>
              <NFormItem :label="$t('settings.language')">
                <NSelect v-model:value="language" :options="languageOptions" style="width: 200px;" @update:value="handleLanguageChange" />
              </NFormItem>
              <NFormItem :label="$t('settings.closeToTray')">
                <NSwitch v-model:value="closeToTray" @update:value="handleCloseToTrayChange" />
              </NFormItem>
              <NFormItem :label="$t('settings.updateCheck')">
                <div style="display: flex; flex-direction: column; gap: 8px; flex: 1;">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <NButton size="small" :loading="updateChecking" @click="checkForUpdates(false)">{{ $t('settings.checkNow') }}</NButton>
                    <NButton v-if="updateInfo.releaseUrl && updateInfo.checked" size="small" secondary @click="openReleasePage">{{ $t('settings.openReleasePage') }}</NButton>
                  </div>
                  <NAlert v-if="updateInfo.checked" :type="updateInfo.error ? 'error' : updateInfo.hasUpdate ? 'warning' : 'success'" :show-icon="false">
                    <template v-if="updateInfo.error">{{ $t('settings.updateCheckFailed') }}: {{ updateInfo.error }}</template>
                    <template v-else-if="updateInfo.hasUpdate">{{ $t('settings.updateAvailableDetail', { current: updateInfo.currentVersion, latest: updateInfo.latestVersion }) }}</template>
                    <template v-else>{{ $t('settings.noUpdateDetail', { current: updateInfo.currentVersion, latest: updateInfo.latestVersion }) }}</template>
                  </NAlert>
                </div>
              </NFormItem>
            </NForm>
          </NCard>
        </NSpace>
      </NTabPane>

      <NTabPane name="advanced" :tab="$t('settings.tabAdvanced')">
        <NCard style="background: #18181b; border: 1px solid #27272a;">
          <template #header>
            <NSpace align="center">
              <span>{{ $t('settings.adv.title') }}</span>
              <NButton quaternary size="tiny" @click="helpModal = 'advanced'"><span class="help-icon">?</span></NButton>
            </NSpace>
          </template>
          <p style="color: #71717a; font-size: 13px; margin: 0 0 14px;">{{ $t('settings.adv.subtitle') }}</p>

          <div class="adv-layout">
            <div class="adv-sidebar">
              <NMenu
                :options="advancedMenuOptions"
                :value="advancedSection"
                @update:value="(v: string) => { advancedSection = v }"
                :indent="14"
              />
            </div>
            <div class="adv-content">
              <div v-if="advancedSection === 'memoryTop'">
                <h3 class="adv-section-title">{{ $t('settings.adv.memoryTop') }}</h3>
                <NForm label-placement="left" label-width="200" :show-feedback="false" class="adv-form">
                  <NFormItem :label="$t('settings.adv.injectEnabled')"><NSwitch v-model:value="config.inject_enabled" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.extractionEnabled')"><NSwitch v-model:value="config.extraction_enabled" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.maxRecentTurns')"><NInputNumber v-model:value="config.max_recent_turns_for_query" :min="1" :max="50" style="width: 200px;" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.vectorTopK')"><NInputNumber v-model:value="config.vector_top_k" :min="1" :max="200" style="width: 200px;" /></NFormItem>
                </NForm>
              </div>

              <div v-else-if="advancedSection === 'conversation'">
                <h3 class="adv-section-title">{{ $t('settings.adv.conversation') }}</h3>
                <NForm label-placement="left" label-width="200" :show-feedback="false" class="adv-form">
                  <NFormItem :label="$t('settings.adv.convAutoGap')">
                    <NInputNumber v-model:value="config.conv_auto_gap" :min="0" :max="1440" style="width: 160px;" />
                    <span style="color: #71717a; font-size: 12px; margin-left: 12px;">{{ $t('settings.adv.convAutoGapHint') }}</span>
                  </NFormItem>
                  <NFormItem :label="$t('settings.adv.convDetectPrompt')"><NSwitch v-model:value="config.conv_detect_prompt_change" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.convDetectCount')"><NSwitch v-model:value="config.conv_detect_count_reset" /></NFormItem>
                </NForm>
              </div>

              <div v-else-if="advancedSection === 'scopes'">
                <h3 class="adv-section-title">{{ $t('settings.adv.scopes') }}</h3>
                <NForm label-placement="left" label-width="200" :show-feedback="false" class="adv-form">
                  <NFormItem :label="$t('settings.adv.scopeGlobal')"><NSwitch v-model:value="config.scope_global" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.scopeCharacter')"><NSwitch v-model:value="config.scope_character" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.scopeConversation')"><NSwitch v-model:value="config.scope_conversation" /></NFormItem>
                </NForm>
              </div>

              <div v-else-if="advancedSection === 'extraction'">
                <h3 class="adv-section-title">{{ $t('settings.adv.extraction') }}</h3>
                <NForm label-placement="left" label-width="200" :show-feedback="false" class="adv-form">
                  <NFormItem :label="$t('settings.adv.extMinImportance')">
                    <NSlider v-model:value="config.ext_min_importance" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 360px;" />
                  </NFormItem>
                  <NFormItem :label="$t('settings.adv.extMinConfidence')">
                    <NSlider v-model:value="config.ext_min_confidence" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 360px;" />
                  </NFormItem>
                  <NFormItem :label="$t('settings.adv.extAfterEachTurn')"><NSwitch v-model:value="config.ext_after_each_turn" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.extFallbackRules')"><NSwitch v-model:value="config.ext_fallback_rule_based" /></NFormItem>
                </NForm>
              </div>

              <div v-else-if="advancedSection === 'scoring'">
                <h3 class="adv-section-title">{{ $t('settings.adv.scoring') }}</h3>
                <p class="adv-hint">{{ $t('settings.adv.scoringHint', { total: scoringTotal.toFixed(2) }) }}</p>
                <NForm label-placement="left" label-width="200" :show-feedback="false" class="adv-form">
                  <NFormItem :label="$t('settings.adv.scoreVector')"><NSlider v-model:value="config.score_vector" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 420px;" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.scoreImportance')"><NSlider v-model:value="config.score_importance" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 420px;" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.scoreRecency')"><NSlider v-model:value="config.score_recency" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 420px;" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.scoreScope')"><NSlider v-model:value="config.score_scope" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 420px;" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.scoreConfidence')"><NSlider v-model:value="config.score_confidence" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 420px;" /></NFormItem>
                </NForm>
              </div>

              <div v-else-if="advancedSection === 'gate'">
                <h3 class="adv-section-title">{{ $t('settings.adv.retrievalGate') }}</h3>
                <NForm label-placement="left" label-width="220" :show-feedback="false" class="adv-form">
                  <NFormItem :label="$t('settings.adv.gateEnabled')"><NSwitch v-model:value="config.rg_enabled" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.gateMode')"><NSelect v-model:value="config.rg_mode" :options="retrievalGateModes" style="width: 220px;" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.gateOnNewSession')"><NSwitch v-model:value="config.rg_on_new_session" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.gateEveryNTurns')"><NInputNumber v-model:value="config.rg_every_n_turns" :min="0" :max="50" style="width: 160px;" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.gateStateConfBelow')"><NSlider v-model:value="config.rg_state_conf_below" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 360px;" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.gateTriggerKeywords')"><NDynamicTags v-model:value="config.rg_trigger_keywords" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.gateSkipCharsBelow')"><NInputNumber v-model:value="config.rg_skip_chars_below" :min="0" :max="200" style="width: 160px;" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.gateSkipWhenSufficient')"><NSwitch v-model:value="config.rg_skip_when_state_sufficient" /></NFormItem>
                </NForm>
              </div>

              <div v-else-if="advancedSection === 'hotContext'">
                <h3 class="adv-section-title">{{ $t('settings.adv.hotContext') }}</h3>
                <NForm label-placement="left" label-width="200" :show-feedback="false" class="adv-form">
                  <NFormItem :label="$t('settings.adv.hcEnabled')"><NSwitch v-model:value="config.hc_enabled" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.hcInjectAlways')"><NSwitch v-model:value="config.hc_inject_always" /></NFormItem>
                  <NFormItem :label="$t('settings.adv.hcMaxChars')"><NInputNumber v-model:value="config.hc_max_chars" :min="100" :max="10000" :step="100" style="width: 200px;" /></NFormItem>
                </NForm>
                <div style="margin-top: 12px;">
                  <p class="adv-hint" style="margin-bottom: 8px;">{{ $t('settings.adv.hcSections') }}</p>
                  <NDataTable :columns="hotContextColumns" :data="hotContextRows" :pagination="false" :bordered="false" size="small" />
                </div>
              </div>
            </div>
          </div>
        </NCard>
      </NTabPane>
    </NTabs>

    <!-- Save -->
    <div style="margin-top: 16px;">
      <NAlert type="info" style="background: rgba(167, 139, 250, 0.05); border-color: #27272a; margin-bottom: 12px;">
        {{ $t('settings.saveHint') }}
      </NAlert>
      <div style="text-align: right;">
        <NButton type="primary" @click="saveConfig">{{ $t('settings.saveConfig') }}</NButton>
      </div>
    </div>

    <!-- Help Modals -->
    <NModal :show="!!helpModal" preset="card" :title="$t('settings.helpTitle')" style="width: 600px; background: #18181b;" :mask-closable="true" @update:show="(v: boolean) => { if (!v) helpModal = '' }">
      <div v-if="helpModal === 'llm'" class="help-content">
        <p><strong>{{ $t('settings.forwardMode') }}</strong>: {{ $t('settings.forwardModeHelp') }}</p>
        <p><strong>{{ $t('settings.provider') }}</strong>: {{ $t('settings.providerHelp') }}</p>
        <p><strong>Base URL</strong>: {{ $t('settings.baseUrlHelp') }}</p>
        <p><strong>API Key</strong>: {{ $t('settings.apiKeyHelp') }}</p>
        <p><strong>{{ $t('settings.modelName') }}</strong>: {{ $t('settings.modelNameHelp') }}</p>
      </div>
      <div v-else-if="helpModal === 'embedding'" class="help-content">
        <p>{{ $t('settings.embeddingHelp') }}</p>
        <p><strong>{{ $t('settings.dimension') }}</strong>: {{ $t('settings.dimensionHelp') }}</p>
      </div>
      <div v-else-if="helpModal === 'rerank'" class="help-content">
        <p>{{ $t('settings.rerankHelp') }}</p>
        <p><strong>{{ $t('settings.maxDocsPerBatch') }}</strong>: {{ $t('settings.maxDocsHelp') }}</p>
      </div>
      <div v-else-if="helpModal === 'stateFiller'" class="help-content">
        <p>{{ $t('settings.stateFillerHelp') }}</p>
        <p><strong>{{ $t('settings.fillMode') }}</strong>: {{ $t('settings.fillModeHelp') }}</p>
        <p><strong>{{ $t('settings.minConfidence') }}</strong>: {{ $t('settings.minConfidenceHelp') }}</p>
        <p><strong>{{ $t('settings.timeout') }}</strong>: {{ $t('settings.timeoutHelp') }}</p>
        <p><strong>{{ $t('settings.temperature') }}</strong>: {{ $t('settings.temperatureHelp') }}</p>
        <p><strong>{{ $t('settings.customPrompt') }}</strong>: {{ $t('settings.customPromptHelp') }}</p>
      </div>
      <div v-else-if="helpModal === 'memory'" class="help-content">
        <p>{{ $t('settings.memoryHelp') }}</p>
        <p><strong>{{ $t('settings.maxInjectChars') }}</strong>: {{ $t('settings.maxInjectCharsHelp') }}</p>
        <p><strong>{{ $t('settings.memoryJudge') }}</strong>: {{ $t('settings.memoryJudgeHelp') }}</p>
        <p><strong>{{ $t('settings.judgeMode') }}</strong>: {{ $t('settings.judgeModeHelp') }}</p>
        <p><strong>{{ $t('settings.userRules') }}</strong>: {{ $t('settings.userRulesHelp') }}</p>
      </div>
      <div v-else-if="helpModal === 'server'" class="help-content">
        <p><strong>{{ $t('settings.guiBackendUrl') }}</strong>: {{ $t('settings.guiBackendUrlHelp') }}</p>
        <p><strong>{{ $t('settings.localPort') }}</strong>: {{ $t('settings.localPortHelp') }}</p>
        <p><strong>{{ $t('settings.storageDir') }}</strong>: {{ $t('settings.storageDirHelp') }}</p>
        <p><strong>{{ $t('settings.timezone') }}</strong>: {{ $t('settings.timezoneHelp') }}</p>
        <p><strong>{{ $t('settings.language') }}</strong>: {{ $t('settings.languageHelp') }}</p>
        <p><strong>{{ $t('settings.closeToTray') }}</strong>: {{ $t('settings.closeToTrayHelp') }}</p>
        <p><strong>{{ $t('settings.updateCheck') }}</strong>: {{ $t('settings.updateCheckHelp') }}</p>
      </div>
      <div v-else-if="helpModal === 'advanced'" class="help-content">
        <p>{{ $t('settings.adv.help.intro') }}</p>
        <p><strong>{{ $t('settings.adv.conversation') }}</strong>: {{ $t('settings.adv.help.conversation') }}</p>
        <p><strong>{{ $t('settings.adv.memoryTop') }}</strong>: {{ $t('settings.adv.help.memoryTop') }}</p>
        <p><strong>{{ $t('settings.adv.scopes') }}</strong>: {{ $t('settings.adv.help.scopes') }}</p>
        <p><strong>{{ $t('settings.adv.extraction') }}</strong>: {{ $t('settings.adv.help.extraction') }}</p>
        <p><strong>{{ $t('settings.adv.scoring') }}</strong>: {{ $t('settings.adv.help.scoring') }}</p>
        <p><strong>{{ $t('settings.adv.retrievalGate') }}</strong>: {{ $t('settings.adv.help.retrievalGate') }}</p>
        <p><strong>{{ $t('settings.adv.hotContext') }}</strong>: {{ $t('settings.adv.help.hotContext') }}</p>
      </div>
      <div v-else-if="helpModal === 'vectorMaintenance'" class="help-content">
        <p>{{ $t('settings.vectorHelp.intro') }}</p>
        <p><strong>{{ $t('settings.rebuildIndex') }}</strong>: {{ $t('settings.vectorHelp.rebuild') }}</p>
        <p><strong>{{ $t('settings.startMigration') }}</strong>: {{ $t('settings.vectorHelp.migration') }}</p>
        <p><strong>{{ $t('settings.retryVectorSync') }}</strong>: {{ $t('settings.vectorHelp.retry') }}</p>
      </div>
    </NModal>
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
.help-content p {
  color: #d4d4d8;
  font-size: 15px;
  line-height: 1.85;
  margin: 10px 0;
}
.help-content p strong {
  color: #ffffff;
  font-weight: 600;
}
.adv-layout {
  display: flex;
  gap: 20px;
  min-height: 480px;
}
.adv-sidebar {
  flex: 0 0 200px;
  border-right: 1px solid #27272a;
  padding-right: 8px;
}
.adv-content {
  flex: 1;
  min-width: 0;
  padding: 4px 4px 4px 8px;
}
.adv-section-title {
  font-size: 16px;
  font-weight: 600;
  color: #e4e4e7;
  margin: 0 0 16px;
}
.adv-hint {
  color: #71717a;
  font-size: 12px;
  margin: 0 0 14px;
}
.adv-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
@media (max-width: 720px) {
  .adv-layout {
    flex-direction: column;
  }
  .adv-sidebar {
    flex: 0 0 auto;
    border-right: none;
    border-bottom: 1px solid #27272a;
    padding-right: 0;
    padding-bottom: 8px;
  }
}
.vector-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.vector-actions-title {
  font-size: 14px;
  font-weight: 600;
  color: #d4d4d8;
  margin: 0 0 4px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.vector-action-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 14px;
  background: #09090b;
  border: 1px solid #27272a;
  border-radius: 6px;
}
.vector-action-info {
  flex: 1;
  min-width: 0;
}
.vector-action-name {
  color: #e4e4e7;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 2px;
}
.vector-action-desc {
  color: #71717a;
  font-size: 12px;
  line-height: 1.5;
}
</style>
