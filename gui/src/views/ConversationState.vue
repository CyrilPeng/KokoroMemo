<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NForm,
  NFormItem,
  NGrid,
  NGridItem,
  NInput,
  NInputNumber,
  NModal,
  NPopconfirm,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { apiFetch } from '../api'
import { saveJsonExport } from '../export'
import HelpModal from '../components/HelpModal.vue'
import PageHeader from '../components/PageHeader.vue'
import StateDefaultConfigDrawer from '../components/state/StateDefaultConfigDrawer.vue'
import StateBoardSidePanel from '../components/state/StateBoardSidePanel.vue'
import StateDiagnosticsPanel from '../components/state/StateDiagnosticsPanel.vue'
import StatePolicyCard from '../components/state/StatePolicyCard.vue'
import StateSessionToolbar from '../components/state/StateSessionToolbar.vue'
import StateTableWorkspace from '../components/state/StateTableWorkspace.vue'
import type { ConversationConfig, StateRow, StateTable } from '../components/state/types'

const stateHelpSections = [
  { title: '这是什么', body: '状态板用于追踪当前会话的"热信息"——场景、角色情绪、规则、关系等会随对话演变的内容。它会和长期记忆一起注入到 AI 的 system prompt，帮助 AI 维持连续性。' },
  { title: '会话方案与策略', body: '「会话方案」是一组预设组合，选中后会自动套用对应的模板/写入/注入策略。也可以单独调整每一项。改完记得点「保存会话策略」。' },
  { title: '新会话默认配置（右上⚙）', body: '仅影响之后第一次出现的新 conversation_id；已有会话不会被自动覆盖。建议在开始 RimTalk、跑团或新角色之前先设好默认方案。' },
  { title: '状态行与 AI 填充', body: '每一行是一条独立状态。AI 会尽量更新已有行而非堆砌新行。若注入预览显示空，说明当前还没有任何状态行。' },
  { title: '常见误解', bullets: [
    'RimTalk / 殖民地模拟：建议「不写入长期记忆」+「只注入状态板」，避免资源/小人状态污染长期记忆',
    '普通助手：用「长期记忆助手」方案，不维护状态板',
    '注入预览有内容但状态表格为空：可能是旧版字段兼容兜底，编辑后会迁移到新表格',
  ] },
]

const STATE_CONVERSATION_STORAGE_KEY = 'kokoromemo.stateConversationId'
const STATE_ACTIVE_TABLE_STORAGE_KEY = 'kokoromemo.stateActiveTableKey'
const message = useMessage()
const { t } = useI18n()
const loading = ref(false)
const saving = ref(false)
const previewLoading = ref(false)
const retrievalLoading = ref(false)
const conversationId = ref(localStorage.getItem(STATE_CONVERSATION_STORAGE_KEY) || '')
const adminToken = ref(localStorage.getItem('kokoromemo.adminToken') || '')
const conversations = ref<any[]>([])
const template = ref<any | null>(null)
const rows = ref<StateRow[]>([])
const recentEvents = ref<any[]>([])
const checkedRowKeys = ref<string[]>([])
const batchPriority = ref<number | null>(80)
const historyEvents = ref<any[]>([])
const historyLoading = ref(false)
const config = ref<ConversationConfig | null>(null)
const defaultConfig = ref<ConversationConfig | null>(null)
const profiles = ref<any[]>([])
const tableTemplates = ref<any[]>([])
const mountPresets = ref<any[]>([])
const memoryLibraries = ref<any[]>([])
const mountedLibraryIds = ref<string[]>([])
const writeLibraryId = ref<string | null>(null)
const activeTableKey = ref(localStorage.getItem(STATE_ACTIVE_TABLE_STORAGE_KEY) || '')
const preview = ref({ preview: '', char_count: 0, max_chars: 0, item_count: 0, summary: null as any })
const retrievalTraces = ref<any[]>([])
const retrievalTraceDetail = ref<any | null>(null)
const showEditModal = ref(false)
const showFillModal = ref(false)
const showHelpModal = ref(false)
const showRenameModal = ref(false)
const showDefaultDrawer = ref(false)
const showAddTabModal = ref(false)
const showEditTabModal = ref(false)
const showAddColumnModal = ref(false)
const showEditColumnModal = ref(false)
const showPresetModal = ref(false)
const showProfileModal = ref(false)
const showRenameTemplateModal = ref(false)
const showFillPreviewModal = ref(false)
const fillPreviewOps = ref<any[]>([])
const lastFillEventIds = ref<string[]>([])
const showUndoAlert = ref(false)
const editingTable = ref<StateTable | null>(null)
const editingRow = ref<StateRow | null>(null)
const editValues = ref<Record<string, string>>({})
const editMeta = ref({ priority: 80, confidence: 0.9 })
const fillForm = ref({ user_message: '', assistant_message: '' })
const renameForm = ref({ title: '' })
const tabForm = ref({ table_key: '', name: '', description: '' })
const columnForm = ref({ table_key: '', column_key: '', name: '', description: '', max_chars: 240, required: 0 })
const editingTabKey = ref('')
const editingColumnKey = ref('')
const presetForm = ref({ preset_id: '', name: '', description: '' })
const profileForm = ref({ profile_id: '', name: '', description: '' })
const renameTemplateForm = ref({ template_id: '', name: '' })

const profileOptions = computed(() => profiles.value.map((item) => ({
  label: item.name,
  value: item.profile_id,
  is_builtin: item.is_builtin,
})))
const profileRenderLabel = (option: any) => {
  if (option.is_builtin === false) {
    return h('span', {}, [option.label, ' ', h(NTag, { size: 'tiny', type: 'info', bordered: false, style: 'vertical-align: middle' }, () => t('state.template.customMark'))])
  }
  return option.label
}
const tableTemplateOptions = computed(() => [
  { label: t('state.template.noTemplate'), value: null },
  ...tableTemplates.value.map((item) => ({ label: item.name, value: item.template_id, is_builtin: item.is_builtin })),
])
const templateRenderLabel = (option: any) => {
  if (option.is_builtin === false) {
    return h('span', {}, [option.label, ' ', h(NTag, { size: 'tiny', type: 'info', bordered: false, style: 'vertical-align: middle' }, () => t('state.template.customMark'))])
  }
  return option.label
}
const mountPresetOptions = computed(() => [
  { label: '不套用挂载预设', value: null },
  ...mountPresets.value.map((item) => ({ label: item.name, value: item.preset_id })),
])
const memoryLibraryOptions = computed(() => memoryLibraries.value.map((item) => ({
  label: item.name + (item.card_count != null ? ` (${item.card_count})` : ''),
  value: item.library_id,
})))
const writeLibraryOptions = computed(() => mountedLibraryIds.value.map((id) => {
  const lib = memoryLibraries.value.find((item) => item.library_id === id)
  return { label: lib?.name || id, value: id }
}))
const conversationOptions = computed(() => conversations.value.map((item) => ({
  label: `${conversationDisplayName(item)} · ${item.character_display_name || item.character_id || '未知角色'} · ${item.last_seen_at || item.conversation_id}`,
  value: item.conversation_id,
})))
const selectedConversation = computed(() => conversations.value.find((item) => item.conversation_id === conversationId.value.trim()) || null)
const activeProfile = computed(() => profiles.value.find((item) => item.profile_id === config.value?.profile_id) || null)
const activeTemplate = computed(() => tableTemplates.value.find((item) => item.template_id === config.value?.table_template_id) || null)
const activePreset = computed(() => mountPresets.value.find((item) => item.preset_id === config.value?.mount_preset_id) || null)
const memoryPolicyOptions = [
  { label: '不写入长期记忆', value: 'disabled' },
  { label: '抽取候选，需我审核', value: 'candidate' },
  { label: '仅稳定设定自动入库（需配置记忆判断模型）', value: 'stable_only' },
  { label: '由判断模型自动决定（需配置记忆判断模型）', value: 'auto' },
]
const statePolicyOptions = [
  { label: '不维护状态板', value: 'disabled' },
  { label: '仅手动维护', value: 'manual' },
  { label: '每轮自动更新状态板', value: 'auto' },
]
const injectionPolicyOptions = [
  { label: '不注入任何上下文（仅做代理）', value: 'none' },
  { label: '只注入长期记忆', value: 'memory_only' },
  { label: '只注入状态板（适合模拟类）', value: 'state_only' },
  { label: '状态板优先 + 长期记忆补充', value: 'state_first' },
  { label: '混合注入：长期记忆 + 状态板', value: 'mixed' },
]

const tables = computed<StateTable[]>(() => template.value?.tables || [])
const rowsByTable = computed(() => {
  const result: Record<string, StateRow[]> = {}
  for (const row of rows.value) {
    if (!result[row.table_key]) result[row.table_key] = []
    result[row.table_key].push(row)
  }
  return result
})
const boardDiagnostics = computed(() => {
  const issues: { label: string, type: 'default' | 'info' | 'success' | 'warning' | 'error' }[] = []
  if (!conversationId.value.trim()) issues.push({ label: '未选择会话', type: 'warning' })
  if (!config.value) issues.push({ label: '未加载策略', type: 'warning' })
  if (config.value && !config.value.table_template_id) issues.push({ label: '未绑定表格模板', type: 'error' })
  if (config.value?.injection_policy === 'state_only' && rows.value.length === 0) issues.push({ label: '仅状态板但暂无状态行', type: 'warning' })
  if (config.value?.memory_write_policy !== 'disabled' && config.value?.profile_id === 'rimtalk_colony') issues.push({ label: 'RimTalk 建议关闭长期记忆写入', type: 'error' })
  if (template.value && rows.value.length === 0) issues.push({ label: '模板已就绪但暂无状态', type: 'info' })
  if (!issues.length) issues.push({ label: '状态板健康', type: 'success' })
  return issues
})
function conversationDisplayName(item: any) {
  return item?.title?.trim() || item?.conversation_id || '未命名会话'
}

function authHeaders(json = false) {
  const headers: Record<string, string> = {}
  if (json) headers['Content-Type'] = 'application/json'
  if (adminToken.value.trim()) headers.Authorization = `Bearer ${adminToken.value.trim()}`
  return headers
}

function persistInputs() {
  localStorage.setItem(STATE_CONVERSATION_STORAGE_KEY, conversationId.value.trim())
  localStorage.setItem('kokoromemo.adminToken', adminToken.value.trim())
}

function updateConversationId(value: string) {
  conversationId.value = value
  persistInputs()
}

function updateAdminToken(value: string) {
  adminToken.value = value
  persistInputs()
}

function persistActiveTable() {
  localStorage.setItem(STATE_ACTIVE_TABLE_STORAGE_KEY, activeTableKey.value)
}

function updateActiveTable(value: string) {
  activeTableKey.value = value
  persistActiveTable()
}

function reconcileActiveTable() {
  if (!tables.value.length) {
    activeTableKey.value = ''
    persistActiveTable()
    return
  }
  const exists = tables.value.some((table) => table.table_key === activeTableKey.value)
  if (!activeTableKey.value || !exists) activeTableKey.value = tables.value[0].table_key
  persistActiveTable()
}

async function fetchBoard() {
  if (!conversationId.value.trim()) {
    message.warning('请输入会话 ID')
    return
  }
  persistInputs()
  loading.value = true
  try {
    await fetchConfig()
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/state/tables`, {
      headers: authHeaders(),
    })
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || data.message || '加载失败')
    template.value = data.template
    rows.value = data.rows || []
    recentEvents.value = data.recent_events || []
    reconcileActiveTable()
    await fetchPreview()
    await fetchMounts()
    await fetchRetrievalTraces()
  } catch (error: any) {
    message.error(error.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function fetchRetrievalTraces() {
  if (!conversationId.value.trim()) {
    retrievalTraces.value = []
    retrievalTraceDetail.value = null
    return
  }
  retrievalLoading.value = true
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/retrieval-traces?limit=10`, {
      headers: authHeaders(),
    })
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || data.message || '加载检索解释失败')
    retrievalTraces.value = data.items || []
    if (!retrievalTraces.value.length) {
      retrievalTraceDetail.value = null
    } else if (!retrievalTraceDetail.value || !retrievalTraces.value.some((item) => item.trace_id === retrievalTraceDetail.value?.trace_id)) {
      await fetchRetrievalTraceDetail(retrievalTraces.value[0].trace_id)
    }
  } catch (error: any) {
    message.error(error.message || '加载检索解释失败')
  } finally {
    retrievalLoading.value = false
  }
}

async function fetchRetrievalTraceDetail(traceId: string) {
  if (!traceId) return
  retrievalLoading.value = true
  try {
    const resp = await apiFetch(`/admin/retrieval-traces/${encodeURIComponent(traceId)}`, {
      headers: authHeaders(),
    })
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || data.message || '加载检索详情失败')
    retrievalTraceDetail.value = data
  } catch (error: any) {
    message.error(error.message || '加载检索详情失败')
  } finally {
    retrievalLoading.value = false
  }
}

async function fetchConfig() {
  if (!conversationId.value.trim()) return
  const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/config`, {
    headers: authHeaders(),
  })
  const data = await resp.json()
  if (!resp.ok) throw new Error(data.detail || data.message || '加载会话策略失败')
  config.value = data
}

async function fetchOptions() {
  try {
    const [profilesResp, tableResp, presetResp, libResp] = await Promise.all([
      apiFetch('/admin/conversation-profiles', { headers: authHeaders() }),
      apiFetch('/admin/state/table-templates', { headers: authHeaders() }),
      apiFetch('/admin/memory-mount-presets', { headers: authHeaders() }),
      apiFetch('/admin/memory-libraries', { headers: authHeaders() }),
    ])
    if (profilesResp.ok) profiles.value = (await profilesResp.json()).items || []
    if (tableResp.ok) tableTemplates.value = (await tableResp.json()).items || []
    if (presetResp.ok) mountPresets.value = (await presetResp.json()).items || []
    if (libResp.ok) memoryLibraries.value = (await libResp.json()).items || []
  } catch (error) {
    console.warn('加载状态板配置选项失败', error)
  }
}

async function fetchMounts() {
  if (!conversationId.value.trim()) {
    mountedLibraryIds.value = []
    writeLibraryId.value = null
    return
  }
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/memory-mounts`, {
      headers: authHeaders(),
    })
    if (!resp.ok) return
    const data = await resp.json()
    const items = data.items || []
    mountedLibraryIds.value = items.map((item: any) => item.library_id)
    const writeItem = items.find((item: any) => item.is_write_target) || items[0]
    writeLibraryId.value = writeItem?.library_id || null
  } catch (error) {
    console.warn('加载挂载库失败', error)
  }
}

async function saveMounts() {
  if (!conversationId.value.trim()) return
  if (!mountedLibraryIds.value.length) {
    message.warning('请至少挂载一个长期记忆库')
    return
  }
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/memory-mounts`, {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({
        library_ids: mountedLibraryIds.value,
        write_library_id: writeLibraryId.value || mountedLibraryIds.value[0],
      }),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '保存挂载失败')
    await fetchMounts()
  } catch (error: any) {
    message.error(error.message || '保存挂载失败')
  } finally {
    saving.value = false
  }
}

async function onMountedLibrariesChange(ids: string[]) {
  mountedLibraryIds.value = ids
  if (writeLibraryId.value && !ids.includes(writeLibraryId.value)) {
    writeLibraryId.value = ids[0] || null
  } else if (!writeLibraryId.value && ids.length) {
    writeLibraryId.value = ids[0]
  }
  await saveMounts()
}

async function onWriteLibraryChange(id: string | null) {
  writeLibraryId.value = id
  await saveMounts()
}

async function fetchConversations() {
  try {
    const resp = await apiFetch('/admin/conversations?limit=200', { headers: authHeaders() })
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || data.message || '加载会话列表失败')
    conversations.value = data.items || []
    if (!conversationId.value.trim() && conversations.value.length) {
      conversationId.value = conversations.value[0].conversation_id
      persistInputs()
    }
  } catch (error: any) {
    message.error(error.message || '加载会话列表失败')
  }
}

async function deleteSelectedConversation() {
  const target = conversationId.value.trim()
  if (!target) {
    message.warning('请先选择会话')
    return
  }
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(target)}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '删除会话失败')
    message.success('会话已删除')
    conversations.value = conversations.value.filter((item) => item.conversation_id !== target)
    conversationId.value = conversations.value[0]?.conversation_id || ''
    template.value = null
    rows.value = []
    config.value = null
    preview.value = { preview: '', char_count: 0, max_chars: 0, item_count: 0, summary: null }
    persistInputs()
    if (conversationId.value) await fetchBoard()
    else persistActiveTable()
  } catch (error: any) {
    message.error(error.message || '删除会话失败')
  } finally {
    saving.value = false
  }
}

function openRenameConversation() {
  const current = selectedConversation.value
  if (!current) {
    message.warning('请先选择会话')
    return
  }
  renameForm.value = { title: current.title || '' }
  showRenameModal.value = true
}

async function saveConversationTitle() {
  const target = conversationId.value.trim()
  if (!target) return
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(target)}`, {
      method: 'PATCH',
      headers: authHeaders(true),
      body: JSON.stringify({ title: renameForm.value.title }),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '保存会话名称失败')
    const index = conversations.value.findIndex((item) => item.conversation_id === target)
    if (index >= 0) conversations.value[index] = { ...conversations.value[index], ...data.item }
    message.success('会话名称已保存')
    showRenameModal.value = false
  } catch (error: any) {
    message.error(error.message || '保存会话名称失败')
  } finally {
    saving.value = false
  }
}

async function fetchDefaultConfig() {
  try {
    const resp = await apiFetch('/admin/conversation-defaults', { headers: authHeaders() })
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || data.message || '加载新会话默认配置失败')
    defaultConfig.value = data
  } catch (error: any) {
    message.error(error.message || '加载新会话默认配置失败')
  }
}

function applyProfileToConfig(profileId: string) {
  if (!config.value) return
  const profile = profiles.value.find((item) => item.profile_id === profileId)
  if (!profile) return
  config.value = {
    ...config.value,
    profile_id: profile.profile_id,
    table_template_id: profile.table_template_id,
    mount_preset_id: profile.mount_preset_id,
    memory_write_policy: profile.memory_write_policy,
    state_update_policy: profile.state_update_policy,
    injection_policy: profile.injection_policy,
  }
}

function applyProfileToDefault(profileId: string) {
  if (!defaultConfig.value) return
  const profile = profiles.value.find((item) => item.profile_id === profileId)
  if (!profile) return
  defaultConfig.value = {
    ...defaultConfig.value,
    profile_id: profile.profile_id,
    table_template_id: profile.table_template_id,
    mount_preset_id: profile.mount_preset_id,
    memory_write_policy: profile.memory_write_policy,
    state_update_policy: profile.state_update_policy,
    injection_policy: profile.injection_policy,
  }
}

function patchCurrentConfig<K extends keyof ConversationConfig>(key: K, value: ConversationConfig[K]) {
  if (!config.value) return
  config.value = { ...config.value, [key]: value }
}

function patchDefaultConfig<K extends keyof ConversationConfig>(key: K, value: ConversationConfig[K]) {
  if (!defaultConfig.value) return
  defaultConfig.value = { ...defaultConfig.value, [key]: value }
}

async function saveDefaultConfig() {
  if (!defaultConfig.value) return
  saving.value = true
  try {
    const resp = await apiFetch('/admin/conversation-defaults', {
      method: 'PUT',
      headers: authHeaders(true),
      body: JSON.stringify(defaultConfig.value),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '保存新会话默认配置失败')
    defaultConfig.value = data.config
    message.success('新会话默认配置已保存')
  } catch (error: any) {
    message.error(error.message || '保存新会话默认配置失败')
  } finally {
    saving.value = false
  }
}

async function saveConfig() {
  if (!config.value || !conversationId.value.trim()) return
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/config`, {
      method: 'PUT',
      headers: authHeaders(true),
      body: JSON.stringify({
        ...config.value,
        mounted_library_ids: mountedLibraryIds.value,
        library_ids: mountedLibraryIds.value,
        write_library_id: writeLibraryId.value || mountedLibraryIds.value[0],
      }),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '保存会话策略失败')
    config.value = data.config
    mountedLibraryIds.value = data.config.mounted_library_ids || []
    writeLibraryId.value = data.config.write_library_id || mountedLibraryIds.value[0] || null
    message.success('会话策略已保存')
    await fetchBoard()
  } catch (error: any) {
    message.error(error.message || '保存会话策略失败')
  } finally {
    saving.value = false
  }
}


async function applyTemplateUpdate(updatedTemplate: any) {
  template.value = updatedTemplate
  await fetchOptions()
  if (config.value && updatedTemplate?.template_id) {
    config.value.table_template_id = updatedTemplate.template_id
    await saveConfig()
  } else {
    await fetchBoard()
  }
}

function openAddTab() {
  tabForm.value = { table_key: '', name: '', description: '' }
  showAddTabModal.value = true
}

function openEditTab(table: StateTable) {
  editingTabKey.value = table.table_key
  tabForm.value = { table_key: table.table_key, name: table.name, description: table.description || '' }
  showEditTabModal.value = true
}

function openAddColumn(table: StateTable) {
  columnForm.value = { table_key: table.table_key, column_key: '', name: '', description: '', max_chars: 240, required: 0 }
  showAddColumnModal.value = true
}

function openEditColumn(table: StateTable, column: any) {
  editingColumnKey.value = column.column_key
  columnForm.value = {
    table_key: table.table_key,
    column_key: column.column_key,
    name: column.name,
    description: column.description || '',
    max_chars: column.max_chars || 240,
    required: column.required ? 1 : 0,
  }
  showEditColumnModal.value = true
}

async function cloneCurrentTemplate() {
  if (!template.value?.template_id) return
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/state/table-templates/${encodeURIComponent(template.value.template_id)}/clone`, {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({ name: `${template.value.name || t('state.template.fallbackName')} ${t('state.template.customSuffix')}` }),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || 'Clone template failed')
    message.success(t('state.messages.templateCloned'))
    await applyTemplateUpdate(data.template)
  } catch (error: any) {
    message.error(error.message || 'Clone template failed')
  } finally {
    saving.value = false
  }
}

async function saveNewTab() {
  if (!template.value?.template_id || !tabForm.value.name.trim()) return
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/state/table-templates/${encodeURIComponent(template.value.template_id)}/tables`, {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify(tabForm.value),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || t('state.messages.addTabFailed'))
    showAddTabModal.value = false
    activeTableKey.value = data.template.tables?.at(-1)?.table_key || activeTableKey.value
    persistActiveTable()
    message.success(t('state.messages.tabAdded'))
    await applyTemplateUpdate(data.template)
  } catch (error: any) {
    message.error(error.message || t('state.messages.addTabFailed'))
  } finally {
    saving.value = false
  }
}

async function saveEditTab() {
  if (!template.value?.template_id || !editingTabKey.value || !tabForm.value.name.trim()) return
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/state/table-templates/${encodeURIComponent(template.value.template_id)}/tables/${encodeURIComponent(editingTabKey.value)}`, {
      method: 'PATCH',
      headers: authHeaders(true),
      body: JSON.stringify({ name: tabForm.value.name, description: tabForm.value.description }),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '保存标签页失败')
    showEditTabModal.value = false
    message.success('标签页已更新')
    await applyTemplateUpdate(data.template)
  } catch (error: any) {
    message.error(error.message || '保存标签页失败')
  } finally {
    saving.value = false
  }
}

async function deleteTab(table: StateTable) {
  if (!template.value?.template_id) return
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/state/table-templates/${encodeURIComponent(template.value.template_id)}/tables/${encodeURIComponent(table.table_key)}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '删除标签页失败')
    if (activeTableKey.value === table.table_key) {
      activeTableKey.value = data.template.tables?.[0]?.table_key || ''
      persistActiveTable()
    }
    message.success('标签页已删除')
    await applyTemplateUpdate(data.template)
  } catch (error: any) {
    message.error(error.message || '删除标签页失败')
  } finally {
    saving.value = false
  }
}

async function saveNewColumn() {
  if (!template.value?.template_id || !columnForm.value.table_key || !columnForm.value.name.trim()) return
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/state/table-templates/${encodeURIComponent(template.value.template_id)}/tables/${encodeURIComponent(columnForm.value.table_key)}/columns`, {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify(columnForm.value),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || t('state.messages.addColumnFailed'))
    showAddColumnModal.value = false
    message.success(t('state.messages.columnAdded'))
    await applyTemplateUpdate(data.template)
  } catch (error: any) {
    message.error(error.message || t('state.messages.addColumnFailed'))
  } finally {
    saving.value = false
  }
}

async function saveEditColumn() {
  if (!template.value?.template_id || !columnForm.value.table_key || !editingColumnKey.value || !columnForm.value.name.trim()) return
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/state/table-templates/${encodeURIComponent(template.value.template_id)}/tables/${encodeURIComponent(columnForm.value.table_key)}/columns/${encodeURIComponent(editingColumnKey.value)}`, {
      method: 'PATCH',
      headers: authHeaders(true),
      body: JSON.stringify(columnForm.value),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '保存列失败')
    showEditColumnModal.value = false
    message.success('列标题已更新')
    await applyTemplateUpdate(data.template)
  } catch (error: any) {
    message.error(error.message || '保存列失败')
  } finally {
    saving.value = false
  }
}

function openPresetModal(preset?: any) {
  presetForm.value = {
    preset_id: preset?.preset_id || '',
    name: preset?.name || '',
    description: preset?.description || '',
  }
  showPresetModal.value = true
}

async function savePreset() {
  if (!presetForm.value.name.trim() || !mountedLibraryIds.value.length) return
  saving.value = true
  try {
    const isEdit = Boolean(presetForm.value.preset_id)
    const resp = await apiFetch(isEdit ? `/admin/memory-mount-presets/${encodeURIComponent(presetForm.value.preset_id)}` : '/admin/memory-mount-presets', {
      method: isEdit ? 'PUT' : 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({
        name: presetForm.value.name,
        description: presetForm.value.description,
        library_ids: mountedLibraryIds.value,
        write_library_id: writeLibraryId.value || mountedLibraryIds.value[0],
      }),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || t('state.messages.savePresetFailed'))
    showPresetModal.value = false
    message.success(t('state.messages.presetSaved'))
    await fetchOptions()
  } catch (error: any) {
    message.error(error.message || t('state.messages.savePresetFailed'))
  } finally {
    saving.value = false
  }
}

async function deletePreset(preset: any) {
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/memory-mount-presets/${encodeURIComponent(preset.preset_id)}`, { method: 'DELETE', headers: authHeaders() })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || t('state.messages.deletePresetFailed'))
    message.success(t('state.messages.presetDeleted'))
    await fetchOptions()
  } catch (error: any) {
    message.error(error.message || t('state.messages.deletePresetFailed'))
  } finally {
    saving.value = false
  }
}

function openProfileModal(profile?: any) {
  profileForm.value = {
    profile_id: profile?.is_builtin === false ? profile.profile_id : '',
    name: profile?.is_builtin === false ? profile.name : '',
    description: profile?.is_builtin === false ? profile.description || '' : '',
  }
  showProfileModal.value = true
}

async function saveProfile() {
  if (!profileForm.value.name.trim() || !config.value) return
  saving.value = true
  try {
    const isEdit = Boolean(profileForm.value.profile_id)
    const resp = await apiFetch(isEdit ? `/admin/conversation-profiles/${encodeURIComponent(profileForm.value.profile_id)}` : '/admin/conversation-profiles', {
      method: isEdit ? 'PUT' : 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({
        ...config.value,
        profile_id: profileForm.value.profile_id || undefined,
        name: profileForm.value.name,
        description: profileForm.value.description,
        table_template_id: config.value.table_template_id,
        mount_preset_id: config.value.mount_preset_id,
      }),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || t('state.messages.saveProfileFailed'))
    showProfileModal.value = false
    message.success(t('state.messages.profileSaved'))
    await fetchOptions()
    if (data.profile?.profile_id) config.value.profile_id = data.profile.profile_id
  } catch (error: any) {
    message.error(error.message || t('state.messages.saveProfileFailed'))
  } finally {
    saving.value = false
  }
}

async function deleteProfile(profile: any) {
  if (profile?.is_builtin !== false) return
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/conversation-profiles/${encodeURIComponent(profile.profile_id)}`, { method: 'DELETE', headers: authHeaders() })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || t('state.messages.deleteProfileFailed'))
    message.success(t('state.messages.profileDeleted'))
    await fetchOptions()
  } catch (error: any) {
    message.error(error.message || t('state.messages.deleteProfileFailed'))
  } finally {
    saving.value = false
  }
}

function openRenameTemplate(tmpl: any) {
  renameTemplateForm.value = { template_id: tmpl.template_id, name: tmpl.name }
  showRenameTemplateModal.value = true
}

async function renameTemplate() {
  if (!renameTemplateForm.value.name.trim()) return
  saving.value = true
  try {
    const full = await apiFetch(`/admin/state/table-templates/${encodeURIComponent(renameTemplateForm.value.template_id)}`, { headers: authHeaders() })
    const fullData = await full.json()
    if (!full.ok) throw new Error(fullData.detail || 'Load failed')
    fullData.name = renameTemplateForm.value.name.trim()
    const resp = await apiFetch(`/admin/state/table-templates/${encodeURIComponent(renameTemplateForm.value.template_id)}`, {
      method: 'PUT',
      headers: authHeaders(true),
      body: JSON.stringify(fullData),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || t('state.messages.templateRenameFailed'))
    showRenameTemplateModal.value = false
    message.success(t('state.messages.templateRenamed'))
    await fetchOptions()
  } catch (error: any) {
    message.error(error.message || t('state.messages.templateRenameFailed'))
  } finally {
    saving.value = false
  }
}

async function deleteTemplate(tmpl: any) {
  if (tmpl?.is_builtin !== false) return
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/state/table-templates/${encodeURIComponent(tmpl.template_id)}`, { method: 'DELETE', headers: authHeaders() })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || t('state.messages.templateDeleteFailed'))
    message.success(t('state.messages.templateDeleted'))
    await fetchOptions()
    const currentConfig = config.value
    if (currentConfig && currentConfig.table_template_id === tmpl.template_id) {
      currentConfig.table_template_id = null
    }
  } catch (error: any) {
    message.error(error.message || t('state.messages.templateDeleteFailed'))
  } finally {
    saving.value = false
  }
}

async function fetchPreview() {
  if (!conversationId.value.trim()) return
  previewLoading.value = true
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/state/preview`, {
      headers: authHeaders(),
    })
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || data.message || '预览失败')
    preview.value = data
  } catch (error: any) {
    message.error(error.message || '预览失败')
  } finally {
    previewLoading.value = false
  }
}

function openCreate(table: StateTable) {
  editingTable.value = table
  editingRow.value = null
  editValues.value = Object.fromEntries(table.columns.map((column) => [column.column_key, '']))
  editMeta.value = { priority: table.prompt_priority || 80, confidence: 0.9 }
  showEditModal.value = true
}

function openEdit(table: StateTable, row: StateRow) {
  editingTable.value = table
  editingRow.value = row
  editValues.value = Object.fromEntries(table.columns.map((column) => [column.column_key, row.values?.[column.column_key] || '']))
  editMeta.value = { priority: row.priority ?? table.prompt_priority ?? 80, confidence: row.confidence ?? 0.9 }
  showEditModal.value = true
}

function duplicateRow(table: StateTable, row: StateRow) {
  editingTable.value = table
  editingRow.value = null
  editValues.value = Object.fromEntries(table.columns.map((column) => [column.column_key, row.values?.[column.column_key] || '']))
  editMeta.value = { priority: row.priority ?? table.prompt_priority ?? 80, confidence: row.confidence ?? 0.9 }
  showEditModal.value = true
}

async function saveRow() {
  if (!editingTable.value) return
  saving.value = true
  try {
    const resp = await apiFetch(
      `/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/state/tables/${editingTable.value.table_key}/rows`,
      {
        method: 'POST',
        headers: authHeaders(true),
        body: JSON.stringify({
          row_id: editingRow.value?.row_id,
          values: editValues.value,
          priority: editMeta.value.priority,
          confidence: editMeta.value.confidence,
        }),
      },
    )
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '保存失败')
    message.success('状态行已保存')
    showEditModal.value = false
    await fetchBoard()
  } catch (error: any) {
    message.error(error.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function deleteRow(row: StateRow) {
  try {
    const resp = await apiFetch(`/admin/state/table-rows/${row.row_id}`, { method: 'DELETE', headers: authHeaders() })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '删除失败')
    message.success('状态行已删除')
    await fetchBoard()
  } catch (error: any) {
    message.error(error.message || '删除失败')
  }
}

async function runFillPreview() {
  if (!conversationId.value.trim()) return
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/state/fill`, {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({ ...fillForm.value, table_only: true, preview: true }),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || t('state.messages.fillFailed'))
    fillPreviewOps.value = data.operations || []
    if (!fillPreviewOps.value.length) {
      message.info(t('state.messages.fillNoChanges'))
    } else {
      showFillPreviewModal.value = true
    }
  } catch (error: any) {
    message.error(error.message || t('state.messages.fillFailed'))
  } finally {
    saving.value = false
  }
}

async function runFillConfirm() {
  if (!conversationId.value.trim()) return
  saving.value = true
  showFillPreviewModal.value = false
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/state/fill`, {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({ ...fillForm.value, table_only: true, operations: fillPreviewOps.value }),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || t('state.messages.fillFailed'))
    message.success(t('state.messages.fillDone', { applied: data.applied, skipped: data.skipped }))
    showFillModal.value = false
    await fetchBoard()
    const eventsResp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/state/events?limit=20`, { headers: authHeaders() })
    const eventsData = await eventsResp.json()
    const recentIds = (eventsData.items || [])
      .filter((e: any) => e.event_type !== 'revert')
      .slice(0, data.applied)
      .map((e: any) => e.event_id)
    if (recentIds.length) {
      lastFillEventIds.value = recentIds
      showUndoAlert.value = true
    }
  } catch (error: any) {
    message.error(error.message || t('state.messages.fillFailed'))
  } finally {
    saving.value = false
  }
}

async function revertLastFill() {
  if (!lastFillEventIds.value.length || !conversationId.value.trim()) return
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/state/revert`, {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({ event_ids: lastFillEventIds.value }),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message)
    message.success(t('state.messages.reverted', { count: data.reverted }))
    showUndoAlert.value = false
    lastFillEventIds.value = []
    await fetchBoard()
  } catch (error: any) {
    message.error(error.message || t('state.messages.revertFailed'))
  } finally {
    saving.value = false
  }
}

async function fetchHistory() {
  if (!conversationId.value.trim()) return
  historyLoading.value = true
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/state/events?limit=100`, { headers: authHeaders() })
    const data = await resp.json()
    historyEvents.value = data.items || []
  } catch { /* silent */ }
  historyLoading.value = false
}

async function exportBoard() {
  if (!template.value) return
  const payload = { conversation_id: conversationId.value.trim(), config: config.value, template: template.value, rows: rows.value }
  const savedPath = await saveJsonExport(`state_board_${conversationId.value.trim()}.json`, payload)
  message.success(savedPath ? `已导出到 ${savedPath}` : '已导出')
}

async function importBoard() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const targetId = conversationId.value.trim() || data.conversation_id
      if (!targetId) { message.error(t('state.messages.inputId')); return }
      const resp = await apiFetch('/admin/conversations/import', {
        method: 'POST',
        headers: authHeaders(true),
        body: JSON.stringify({
          target_conversation_id: targetId,
          config: data.config || {},
          table_rows: (data.rows || data.table_rows || []).map((r: any) => ({
            table_key: r.table_key,
            values: r.values || r.cells || {},
            priority: r.priority,
            confidence: r.confidence,
          })),
        }),
      })
      const result = await resp.json()
      if (!resp.ok || result.status !== 'ok') throw new Error(result.detail || result.message)
      message.success(t('state.messages.importDone', { count: result.imported_rows || 0 }))
      if (targetId === conversationId.value.trim()) await fetchBoard()
    } catch (error: any) {
      message.error(error.message || t('state.messages.importFailed'))
    }
  }
  input.click()
}

async function batchAction(action: string, value?: any) {
  if (!checkedRowKeys.value.length) return
  saving.value = true
  try {
    const resp = await apiFetch('/admin/state/table-rows/batch', {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({ action, row_ids: checkedRowKeys.value, value }),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message)
    message.success(t('state.batch.done', { count: data.affected }))
    checkedRowKeys.value = []
    await fetchBoard()
  } catch (error: any) {
    message.error(error.message || t('state.batch.failed'))
  } finally {
    saving.value = false
  }
}

function onCellSaved(row: StateRow, columnKey: string, value: string) {
  if (row.values) row.values[columnKey] = value
}

function onWsEvent(e: any) {
  const data = e.detail
  if (data?.event === 'state_fill_complete' && data?.conversation_id === conversationId.value.trim()) {
    fetchBoard()
  }
}

onMounted(async () => {
  window.addEventListener('kokoromemo:event', onWsEvent)
  fetchOptions()
  fetchDefaultConfig()
  await fetchConversations()
  if (conversationId.value.trim()) {
    await fetchBoard()
  } else {
    showDefaultDrawer.value = true
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('kokoromemo:event', onWsEvent)
})
</script>

<template>
  <div class="state-page">
    <PageHeader :title="$t('state.title')" :subtitle="$t('state.subtitle')" show-help @help="showHelpModal = true" />
    <NSpace vertical size="large">
      <StateSessionToolbar
        :conversation-id="conversationId"
        :admin-token="adminToken"
        :conversation-options="conversationOptions"
        :template-name="template?.name || ''"
        :row-count="rows.length"
        :loading="loading"
        :saving="saving"
        :has-template="Boolean(template)"
        :can-rename-conversation="Boolean(selectedConversation)"
        @update:conversation-id="updateConversationId"
        @update:admin-token="updateAdminToken"
        @load="fetchBoard"
        @export="exportBoard"
        @import="importBoard"
        @rename="openRenameConversation"
        @delete="deleteSelectedConversation"
        @open-defaults="showDefaultDrawer = true"
      />

      <StateDiagnosticsPanel
        :issues="boardDiagnostics"
        :row-count="rows.length"
        :preview-chars="preview.char_count || 0"
      />

      <StatePolicyCard
        v-if="config"
        :config="config"
        :loading="loading"
        :saving="saving"
        :profile-options="profileOptions"
        :profile-render-label="profileRenderLabel"
        :table-template-options="tableTemplateOptions"
        :template-render-label="templateRenderLabel"
        :mount-preset-options="mountPresetOptions"
        :memory-library-options="memoryLibraryOptions"
        :write-library-options="writeLibraryOptions"
        :mounted-library-ids="mountedLibraryIds"
        :write-library-id="writeLibraryId"
        :memory-policy-options="memoryPolicyOptions"
        :state-policy-options="statePolicyOptions"
        :injection-policy-options="injectionPolicyOptions"
        :active-profile="activeProfile"
        :active-template="activeTemplate"
        :active-preset="activePreset"
        @update-profile="applyProfileToConfig"
        @update-table-template="patchCurrentConfig('table_template_id', $event)"
        @update-mount-preset="patchCurrentConfig('mount_preset_id', $event)"
        @update-mounted-libraries="onMountedLibrariesChange"
        @update-write-library-id="onWriteLibraryChange"
        @update-memory-write-policy="patchCurrentConfig('memory_write_policy', $event)"
        @update-state-update-policy="patchCurrentConfig('state_update_policy', $event)"
        @update-injection-policy="patchCurrentConfig('injection_policy', $event)"
        @open-profile-modal="openProfileModal"
        @delete-profile="deleteProfile"
        @clone-template="cloneCurrentTemplate"
        @open-rename-template="openRenameTemplate"
        @delete-template="deleteTemplate"
        @open-preset-modal="openPresetModal"
        @delete-preset="deletePreset"
        @reload="fetchBoard"
        @save-config="saveConfig"
      />

      <NAlert v-if="showUndoAlert" type="success" closable style="margin-bottom: 12px;" @close="showUndoAlert = false">
        {{ $t('state.fill.undoHint', { count: lastFillEventIds.length }) }}
        <NButton size="tiny" type="warning" style="margin-left: 12px;" :loading="saving" @click="revertLastFill">{{ $t('state.fill.undoBtn') }}</NButton>
      </NAlert>

      <NSpin :show="loading">
        <NGrid :cols="24" :x-gap="16" :y-gap="16">
          <NGridItem :span="16">
            <StateTableWorkspace
              v-model:active-table-key="activeTableKey"
              v-model:checked-row-keys="checkedRowKeys"
              v-model:batch-priority="batchPriority"
              :template="template"
              :tables="tables"
              :rows-by-table="rowsByTable"
              :recent-events="recentEvents"
              :admin-token="adminToken"
              @add-tab="openAddTab"
              @edit-tab="openEditTab"
              @delete-tab="deleteTab"
              @add-row="openCreate"
              @add-column="openAddColumn"
              @edit-column="openEditColumn"
              @refresh-preview="fetchPreview"
              @batch-action="batchAction"
              @edit-row="openEdit"
              @duplicate-row="duplicateRow"
              @delete-row="deleteRow"
              @cell-saved="onCellSaved"
              @update:active-table-key="updateActiveTable"
            />
          </NGridItem>

          <NGridItem :span="8">
            <StateBoardSidePanel
              v-model:fill-form="fillForm"
              :preview="preview"
              :preview-loading="previewLoading"
              :retrieval-traces="retrievalTraces"
              :retrieval-trace-detail="retrievalTraceDetail"
              :retrieval-loading="retrievalLoading"
              :tables="tables"
              :rows-by-table="rowsByTable"
              :saving="saving"
              :can-fill="!!conversationId.trim()"
              :show-history="!!conversationId.trim()"
              :history-events="historyEvents"
              :history-loading="historyLoading"
              @refresh-preview="fetchPreview"
              @refresh-retrieval-traces="fetchRetrievalTraces"
              @select-retrieval-trace="fetchRetrievalTraceDetail"
              @preview-fill="runFillPreview"
              @direct-fill="runFillConfirm"
              @refresh-history="fetchHistory"
            />
          </NGridItem>
        </NGrid>
      </NSpin>

    </NSpace>

    <StateDefaultConfigDrawer
      v-model:show="showDefaultDrawer"
      :saving="saving"
      :default-config="defaultConfig"
      :profile-options="profileOptions"
      :profile-render-label="profileRenderLabel"
      :table-template-options="tableTemplateOptions"
      :template-render-label="templateRenderLabel"
      :mount-preset-options="mountPresetOptions"
      :memory-policy-options="memoryPolicyOptions"
      :state-policy-options="statePolicyOptions"
      :injection-policy-options="injectionPolicyOptions"
      @update-profile="applyProfileToDefault"
      @update-table-template="patchDefaultConfig('table_template_id', $event)"
      @update-mount-preset="patchDefaultConfig('mount_preset_id', $event)"
      @update-memory-write-policy="patchDefaultConfig('memory_write_policy', $event)"
      @update-state-update-policy="patchDefaultConfig('state_update_policy', $event)"
      @update-injection-policy="patchDefaultConfig('injection_policy', $event)"
      @save="saveDefaultConfig"
    />

    <NModal v-model:show="showRenameModal" preset="card" title="重命名会话" style="width: min(520px, 96vw)">
      <NSpace vertical>
        <NAlert type="info" :show-icon="false">
          会话名称仅用于界面辨认，不会改变原始会话 ID。
        </NAlert>
        <NForm label-placement="top">
          <NFormItem label="会话名称">
            <NInput v-model:value="renameForm.title" placeholder="例如：芙莉莲主线第 3 章" clearable />
          </NFormItem>
          <NFormItem label="原始会话 ID">
            <NInput :value="conversationId" readonly />
          </NFormItem>
        </NForm>
      </NSpace>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showRenameModal = false">取消</NButton>
          <NButton type="primary" :loading="saving" @click="saveConversationTitle">保存</NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal v-model:show="showEditModal" preset="card" style="width: min(720px, 96vw)" :title="editingRow ? '编辑状态行' : '新增状态行'">
      <NForm v-if="editingTable" label-placement="top">
        <NFormItem v-for="column in editingTable.columns" :key="column.column_key" :label="`${column.name}${column.required ? ' *' : ''}`">
          <NInput v-model:value="editValues[column.column_key]" type="textarea" :maxlength="column.max_chars || undefined" show-count :placeholder="column.description || column.name" :autosize="{ minRows: 2, maxRows: 5 }" />
        </NFormItem>
        <NGrid :cols="2" :x-gap="12">
          <NGridItem><NFormItem label="优先级"><NInputNumber v-model:value="editMeta.priority" :min="0" :max="100" /></NFormItem></NGridItem>
          <NGridItem><NFormItem label="置信度"><NInputNumber v-model:value="editMeta.confidence" :min="0" :max="1" :step="0.05" /></NFormItem></NGridItem>
        </NGrid>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showEditModal = false">取消</NButton>
          <NButton type="primary" :loading="saving" @click="saveRow">保存</NButton>
        </NSpace>
      </template>
    </NModal>


    <NModal v-model:show="showAddTabModal" preset="card" :title="$t('state.template.addTabTitle')" style="width: min(560px, 96vw)">
      <NForm label-placement="top">
        <NFormItem :label="$t('state.template.tabName')"><NInput v-model:value="tabForm.name" :placeholder="$t('state.template.tabNamePlaceholder')" /></NFormItem>
        <NFormItem :label="$t('state.template.key')"><NInput v-model:value="tabForm.table_key" placeholder="quests" /></NFormItem>
        <NFormItem :label="$t('state.template.description')"><NInput v-model:value="tabForm.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" /></NFormItem>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showAddTabModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" :loading="saving" @click="saveNewTab">{{ $t('common.save') }}</NButton></NSpace></template>
    </NModal>

    <NModal v-model:show="showEditTabModal" preset="card" title="编辑标签页" style="width: min(560px, 96vw)">
      <NForm label-placement="top">
        <NFormItem label="标签页名称"><NInput v-model:value="tabForm.name" /></NFormItem>
        <NFormItem :label="$t('state.template.description')"><NInput v-model:value="tabForm.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" /></NFormItem>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showEditTabModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" :loading="saving" @click="saveEditTab">{{ $t('common.save') }}</NButton></NSpace></template>
    </NModal>

    <NModal v-model:show="showAddColumnModal" preset="card" :title="$t('state.template.addColumnTitle')" style="width: min(560px, 96vw)">
      <NForm label-placement="top">
        <NFormItem :label="$t('state.template.columnName')"><NInput v-model:value="columnForm.name" :placeholder="$t('state.template.columnNamePlaceholder')" /></NFormItem>
        <NFormItem :label="$t('state.template.key')"><NInput v-model:value="columnForm.column_key" placeholder="owner" /></NFormItem>
        <NFormItem :label="$t('state.template.description')"><NInput v-model:value="columnForm.description" /></NFormItem>
        <NGrid :cols="2" :x-gap="12">
          <NGridItem><NFormItem :label="$t('state.template.maxChars')"><NInputNumber v-model:value="columnForm.max_chars" :min="20" :max="2000" /></NFormItem></NGridItem>
          <NGridItem><NFormItem :label="$t('state.template.required')"><NSelect v-model:value="columnForm.required" :options="[{ label: $t('common.no'), value: 0 }, { label: $t('common.yes'), value: 1 }]" /></NFormItem></NGridItem>
        </NGrid>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showAddColumnModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" :loading="saving" @click="saveNewColumn">{{ $t('common.save') }}</NButton></NSpace></template>
    </NModal>

    <NModal v-model:show="showEditColumnModal" preset="card" title="编辑列" style="width: min(560px, 96vw)">
      <NForm label-placement="top">
        <NFormItem label="列标题"><NInput v-model:value="columnForm.name" /></NFormItem>
        <NFormItem :label="$t('state.template.description')"><NInput v-model:value="columnForm.description" /></NFormItem>
        <NGrid :cols="2" :x-gap="12">
          <NGridItem><NFormItem :label="$t('state.template.maxChars')"><NInputNumber v-model:value="columnForm.max_chars" :min="20" :max="2000" /></NFormItem></NGridItem>
          <NGridItem><NFormItem :label="$t('state.template.required')"><NSelect v-model:value="columnForm.required" :options="[{ label: $t('common.no'), value: 0 }, { label: $t('common.yes'), value: 1 }]" /></NFormItem></NGridItem>
        </NGrid>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showEditColumnModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" :loading="saving" @click="saveEditColumn">{{ $t('common.save') }}</NButton></NSpace></template>
    </NModal>

    <NModal v-model:show="showPresetModal" preset="card" :title="$t('state.preset.manageTitle')" style="width: min(560px, 96vw)">
      <NForm label-placement="top">
        <NFormItem :label="$t('state.preset.name')"><NInput v-model:value="presetForm.name" :placeholder="$t('state.preset.namePlaceholder')" /></NFormItem>
        <NFormItem :label="$t('state.template.description')"><NInput v-model:value="presetForm.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" /></NFormItem>
        <NAlert type="info" :show-icon="false">{{ $t('state.preset.saveCurrentHelp') }}</NAlert>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showPresetModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" :loading="saving" @click="savePreset">{{ $t('common.save') }}</NButton></NSpace></template>
    </NModal>

    <NModal v-model:show="showProfileModal" preset="card" :title="$t('state.profile.manageTitle')" style="width: min(560px, 96vw)">
      <NForm label-placement="top">
        <NFormItem :label="$t('state.profile.name')"><NInput v-model:value="profileForm.name" :placeholder="$t('state.profile.namePlaceholder')" /></NFormItem>
        <NFormItem :label="$t('state.template.description')"><NInput v-model:value="profileForm.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" /></NFormItem>
        <NAlert type="info" :show-icon="false">{{ $t('state.profile.saveCurrentHelp') }}</NAlert>
      </NForm>
      <template #footer>
        <NSpace justify="space-between" style="width: 100%;">
          <NPopconfirm v-if="profileForm.profile_id" @positive-click="deleteProfile(profiles.find((item) => item.profile_id === profileForm.profile_id))">
            <template #trigger><NButton type="error" quaternary>{{ $t('state.profile.delete') }}</NButton></template>
            {{ $t('state.messages.confirmDeleteCurrentProfile') }}
          </NPopconfirm>
          <span v-else></span>
          <NSpace><NButton @click="showProfileModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" :loading="saving" @click="saveProfile">{{ $t('common.save') }}</NButton></NSpace>
        </NSpace>
      </template>
    </NModal>
    <NModal v-model:show="showRenameTemplateModal" preset="card" :title="$t('state.template.renameTitle')" style="width: min(420px, 96vw)">
      <NForm label-placement="top">
        <NFormItem :label="$t('state.template.newName')"><NInput v-model:value="renameTemplateForm.name" /></NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showRenameTemplateModal = false">{{ $t('common.cancel') }}</NButton>
          <NButton type="primary" :loading="saving" @click="renameTemplate">{{ $t('common.save') }}</NButton>
        </NSpace>
      </template>
    </NModal>
    <NModal v-model:show="showFillPreviewModal" preset="card" :title="$t('state.fill.previewTitle')" style="width: min(700px, 96vw)">
      <div v-if="fillPreviewOps.length" style="max-height: 400px; overflow-y: auto;">
        <div v-for="(op, idx) in fillPreviewOps" :key="idx" style="margin-bottom: 12px; padding: 8px; border-radius: 4px; background: #1a1a2e;">
          <NSpace align="center" size="small">
            <NTag :type="op.op.includes('insert') ? 'success' : op.op.includes('delete') || op.op.includes('resolve') ? 'error' : 'warning'" size="small">
              {{ op.op === 'insert_row' ? '+' : op.op.includes('delete') || op.op.includes('resolve') ? '×' : '~' }} {{ op.op }}
            </NTag>
            <span style="color: #a1a1aa; font-size: 12px;">{{ op.table_key }}</span>
            <span v-if="op.reason" style="color: #888; font-size: 12px;">— {{ op.reason }}</span>
          </NSpace>
          <div v-if="op.after" style="margin-top: 6px; font-size: 12px; color: #e0e0e0;">
            <div v-for="(val, key) in op.after" :key="key" style="margin-left: 12px;">
              <span style="color: #63e2b7;">{{ key }}</span>: {{ val }}
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showFillPreviewModal = false">{{ $t('common.cancel') }}</NButton>
          <NButton type="primary" :loading="saving" @click="runFillConfirm">{{ $t('state.fill.confirmBtn') }}</NButton>
        </NSpace>
      </template>
    </NModal>
    <HelpModal v-model:show="showHelpModal" title="会话状态板帮助" :sections="stateHelpSections" />
  </div>
</template>

<style scoped>
.state-page {
  padding: 20px;
}

.state-data-table {
  width: 100%;
}

.state-data-table :deep(.n-data-table-base-table-body) {
  overflow-x: auto;
}

.hint-text {
  color: #a1a1aa;
  font-size: 12px;
  line-height: 1.6;
  margin: 4px 0 0 0;
}

@media (max-width: 768px) {
  .state-page {
    padding: 0;
  }

  .state-page :deep(.n-card__content),
  .state-page :deep(.n-card-header) {
    padding: 12px;
  }

  .state-page :deep(.n-grid) {
    grid-template-columns: minmax(0, 1fr) !important;
  }

  .state-page :deep(.n-grid-item) {
    grid-column: span 1 / span 1 !important;
  }
}

.state-data-table :deep(.row-inserted td) {
  border-left: 3px solid #18a058;
}

.state-data-table :deep(.row-updated td) {
  border-left: 3px solid #2080f0;
}
</style>
