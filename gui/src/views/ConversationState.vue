<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NCollapse,
  NCollapseItem,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NGrid,
  NGridItem,
  NIcon,
  NInput,
  NInputNumber,
  NModal,
  NPopconfirm,
  NSelect,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  useMessage,
} from 'naive-ui'
import { AddOutline, CreateOutline, RefreshOutline, SettingsOutline, TrashOutline } from '@vicons/ionicons5'
import { useI18n } from 'vue-i18n'
import { apiFetch } from '../api'
import { saveJsonExport } from '../export'
import HelpModal from '../components/HelpModal.vue'
import PageHeader from '../components/PageHeader.vue'
import EditableCell from '../components/state/EditableCell.vue'

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

type StateColumn = {
  column_id: string
  column_key: string
  name: string
  description?: string
  required?: boolean
  max_chars?: number
}

type StateTable = {
  table_id: string
  table_key: string
  name: string
  description?: string
  max_prompt_rows: number
  prompt_priority: number
  columns: StateColumn[]
}

type StateRow = {
  row_id: string
  table_key: string
  values: Record<string, string>
  priority: number
  confidence: number
  source: string
  updated_at?: string
}

type ConversationConfig = {
  conversation_id: string
  profile_id: string
  table_template_id?: string | null
  mount_preset_id?: string | null
  memory_write_policy: string
  state_update_policy: string
  injection_policy: string
  created_from_default?: boolean
}

const STATE_CONVERSATION_STORAGE_KEY = 'kokoromemo.stateConversationId'
const STATE_ACTIVE_TABLE_STORAGE_KEY = 'kokoromemo.stateActiveTableKey'
const message = useMessage()
const { t } = useI18n()
const loading = ref(false)
const saving = ref(false)
const previewLoading = ref(false)
const conversationId = ref(localStorage.getItem(STATE_CONVERSATION_STORAGE_KEY) || '')
const adminToken = ref(localStorage.getItem('kokoromemo.adminToken') || '')
const conversations = ref<any[]>([])
const template = ref<any | null>(null)
const rows = ref<StateRow[]>([])
const recentEvents = ref<any[]>([])
const checkedRowKeys = ref<string[]>([])
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
const preview = ref({ preview: '', char_count: 0, max_chars: 0, item_count: 0 })
const showEditModal = ref(false)
const showFillModal = ref(false)
const showHelpModal = ref(false)
const showRenameModal = ref(false)
const showDefaultDrawer = ref(false)
const showAddTabModal = ref(false)
const showAddColumnModal = ref(false)
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
const presetForm = ref({ preset_id: '', name: '', description: '' })
const profileForm = ref({ profile_id: '', name: '', description: '' })
const renameTemplateForm = ref({ template_id: '', name: '' })

const profileDescriptions: Record<string, string> = {
  airp_roleplay: '日常角色扮演与陪伴聊天，AI 抽取的记忆候选会进入待审核',
  rimtalk_colony: '殖民地/模拟类游戏，仅维护状态板，避免污染长期记忆',
  ttrpg_story: '跑团与长线剧情，状态板优先，仅稳定设定进入长期记忆',
  memory_only: '普通助手或偏好记录，只用长期记忆，不维护状态板',
  proxy_only: '纯透传代理，不注入、不写入、不维护任何状态',
}
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
const selectedProfileHint = computed(() => {
  const id = config.value?.profile_id || ''
  return profileDescriptions[id] || profiles.value.find((item) => item.profile_id === id)?.description || ''
})
const selectedDefaultProfileHint = computed(() => {
  const id = defaultConfig.value?.profile_id || ''
  return profileDescriptions[id] || profiles.value.find((item) => item.profile_id === id)?.description || ''
})
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

function persistActiveTable() {
  localStorage.setItem(STATE_ACTIVE_TABLE_STORAGE_KEY, activeTableKey.value)
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
  } catch (error: any) {
    message.error(error.message || '加载失败')
  } finally {
    loading.value = false
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
    message.success('挂载已保存')
    await fetchMounts()
  } catch (error: any) {
    message.error(error.message || '保存挂载失败')
  } finally {
    saving.value = false
  }
}

function onMountedLibrariesChange(ids: string[]) {
  mountedLibraryIds.value = ids
  if (writeLibraryId.value && !ids.includes(writeLibraryId.value)) {
    writeLibraryId.value = ids[0] || null
  } else if (!writeLibraryId.value && ids.length) {
    writeLibraryId.value = ids[0]
  }
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
    preview.value = { preview: '', char_count: 0, max_chars: 0, item_count: 0 }
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

function openAddColumn(table: StateTable) {
  columnForm.value = { table_key: table.table_key, column_key: '', name: '', description: '', max_chars: 240, required: 0 }
  showAddColumnModal.value = true
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
    if (config.value?.table_template_id === tmpl.template_id) {
      config.value.table_template_id = null
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
  const payload = { conversation_id: conversationId.value.trim(), template: template.value, rows: rows.value }
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

function tableScrollX(table: StateTable) {
  return Math.max(760, table.columns.length * 180 + 430)
}

function columnsFor(table: StateTable) {
  const valueColumns = table.columns.map((column) => ({
    title: column.name,
    key: column.column_key,
    minWidth: 140,
    render: (row: StateRow) => h(EditableCell, {
      value: row.values?.[column.column_key] || '',
      rowId: row.row_id,
      columnKey: column.column_key,
      maxChars: column.max_chars || 360,
      adminToken: adminToken.value,
      onSaved: (_key: string, newValue: string) => {
        if (row.values) row.values[column.column_key] = newValue
      },
    }),
  }))
  return [
    { type: 'selection', width: 48 },
    ...valueColumns,
    { title: '来源', key: 'source', width: 110, render: (row: StateRow) => h(NTag, { size: 'small' }, { default: () => row.source || 'manual' }) },
    { title: '更新时间', key: 'updated_at', width: 170, render: (row: StateRow) => row.updated_at || '-' },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (row: StateRow) => h(NSpace, { size: 6 }, {
        default: () => [
          h(NButton, { size: 'tiny', onClick: () => openEdit(table, row) }, { default: () => '编辑' }),
          h(NPopconfirm, { onPositiveClick: () => deleteRow(row) }, {
            trigger: () => h(NButton, { size: 'tiny', type: 'error', quaternary: true }, { default: () => '删除' }),
            default: () => '删除该状态行？',
          }),
        ],
      }),
    },
  ]
}

function rowClassName(row: StateRow) {
  const evt = recentEvents.value.find((e: any) => e.row_id === row.row_id)
  if (!evt) return ''
  if (evt.event_type === 'insert_row') return 'row-inserted'
  if (evt.event_type === 'update_row' || evt.event_type === 'manual_cell_edit' || evt.event_type === 'manual_upsert_row') return 'row-updated'
  return ''
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
      <NCard>
        <template #header>
          <NSpace align="center" justify="space-between" style="width:100%">
            <NSpace align="center">
              <span>当前会话</span>
              <NTag v-if="template" size="small" type="info">模板：{{ template.name }}</NTag>
              <NTag v-if="rows.length" size="small">{{ rows.length }} 条状态</NTag>
            </NSpace>
            <NSpace align="center">
              <NButton size="small" @click="showDefaultDrawer = true">
                <template #icon><NIcon :component="SettingsOutline" /></template>
                新会话默认配置
              </NButton>
            </NSpace>
          </NSpace>
        </template>
        <NGrid :cols="24" :x-gap="12" :y-gap="12">
          <NGridItem :span="10">
            <NSelect
              v-model:value="conversationId"
              filterable
              clearable
              :options="conversationOptions"
              :placeholder="conversationOptions.length ? '选择会话' : '无数据'"
              :disabled="!conversationOptions.length"
              @update:value="persistInputs"
            />
          </NGridItem>
          <NGridItem :span="8">
            <NInput v-model:value="adminToken" type="password" show-password-on="click" placeholder="Admin Token（可选）" />
          </NGridItem>
          <NGridItem :span="6">
            <NSpace>
              <NButton type="primary" :loading="loading" @click="fetchBoard">
                <template #icon><NIcon :component="RefreshOutline" /></template>
                加载
              </NButton>
              <NButton :disabled="!template" @click="exportBoard">导出</NButton>
              <NButton @click="importBoard">导入</NButton>
              <NButton :disabled="!selectedConversation" @click="openRenameConversation">重命名</NButton>
              <NPopconfirm
                :disabled="!conversationId.trim()"
                positive-text="删除"
                negative-text="取消"
                @positive-click="deleteSelectedConversation"
              >
                <template #trigger>
                  <NButton type="error" quaternary :disabled="!conversationId.trim()" :loading="saving">删除会话</NButton>
                </template>
                删除当前会话记录？此操作会从会话列表移除该 ID，但不会删除磁盘上的聊天文件。
              </NPopconfirm>
            </NSpace>
          </NGridItem>
        </NGrid>
      </NCard>

      <NCollapse>
        <NCollapseItem title="健康诊断" name="diag">
          <NSpace align="center" :wrap="true">
            <NTag v-for="item in boardDiagnostics" :key="item.label" :type="item.type">{{ item.label }}</NTag>
            <span style="color: #a1a1aa; font-size: 13px;">当前状态行 {{ rows.length }} 条，注入预览 {{ preview.char_count || 0 }} 字符。</span>
          </NSpace>
        </NCollapseItem>
      </NCollapse>

      <NCard v-if="config" title="当前会话策略">
        <NForm label-placement="top">
          <NGrid :cols="24" :x-gap="12" :y-gap="12">
            <NGridItem :span="8">
              <NFormItem label="会话方案">
                <NSelect v-model:value="config.profile_id" :options="profileOptions" :render-label="profileRenderLabel" @update:value="applyProfileToConfig" />
              </NFormItem>
              <div v-if="selectedProfileHint" class="hint-text">{{ selectedProfileHint }}</div>
              <NSpace style="margin-top: 6px;">
                <NButton size="tiny" @click="openProfileModal()">
                  <template #icon><NIcon :component="AddOutline" size="14" /></template>
                  {{ $t('state.profile.createNew') }}
                </NButton>
                <NButton v-if="profiles.find((item) => item.profile_id === config?.profile_id)?.is_builtin === false" size="tiny" @click="openProfileModal(profiles.find((item) => item.profile_id === config?.profile_id))">
                  <template #icon><NIcon :component="CreateOutline" size="14" /></template>
                  {{ $t('state.profile.rename') }}
                </NButton>
                <NPopconfirm v-if="profiles.find((item) => item.profile_id === config?.profile_id)?.is_builtin === false" @positive-click="deleteProfile(profiles.find((item) => item.profile_id === config?.profile_id))">
                  <template #trigger>
                    <NButton size="tiny" type="error" quaternary>
                      <template #icon><NIcon :component="TrashOutline" size="14" /></template>
                      {{ $t('state.actions.delete') }}
                    </NButton>
                  </template>
                  {{ $t('state.profile.deleteConfirm') }}
                </NPopconfirm>
              </NSpace>
            </NGridItem>
            <NGridItem :span="8">
              <NFormItem label="状态板表格模板">
                <NSelect v-model:value="config.table_template_id" filterable :options="tableTemplateOptions" :render-label="templateRenderLabel" />
              </NFormItem>
              <NSpace style="margin-top: 6px;">
                <NButton size="tiny" @click="cloneCurrentTemplate" :disabled="!config.table_template_id">
                  <template #icon><NIcon :component="AddOutline" size="14" /></template>
                  {{ $t('state.template.createNew') }}
                </NButton>
                <NButton v-if="tableTemplates.find((item) => item.template_id === config?.table_template_id)?.is_builtin === false" size="tiny" @click="openRenameTemplate(tableTemplates.find((item) => item.template_id === config?.table_template_id))">
                  <template #icon><NIcon :component="CreateOutline" size="14" /></template>
                  {{ $t('state.template.rename') }}
                </NButton>
                <NPopconfirm v-if="tableTemplates.find((item) => item.template_id === config?.table_template_id)?.is_builtin === false" @positive-click="deleteTemplate(tableTemplates.find((item) => item.template_id === config?.table_template_id))">
                  <template #trigger>
                    <NButton size="tiny" type="error" quaternary>
                      <template #icon><NIcon :component="TrashOutline" size="14" /></template>
                      {{ $t('state.actions.delete') }}
                    </NButton>
                  </template>
                  {{ $t('state.template.deleteConfirm') }}
                </NPopconfirm>
              </NSpace>
            </NGridItem>
            <NGridItem :span="8">
              <NFormItem label="挂载组合预设">
                <NSelect v-model:value="config.mount_preset_id" filterable :options="mountPresetOptions" />
              </NFormItem>
              <NSpace>
                <NButton size="tiny" @click="openPresetModal(mountPresets.find((item) => item.preset_id === config?.mount_preset_id))" :disabled="!config.mount_preset_id">{{ $t('state.actions.edit') }}</NButton>
                <NPopconfirm v-if="config.mount_preset_id" @positive-click="deletePreset(mountPresets.find((item) => item.preset_id === config?.mount_preset_id))">
                  <template #trigger><NButton size="tiny" type="error" quaternary>{{ $t('state.actions.delete') }}</NButton></template>
                  {{ $t('state.messages.confirmDeleteCurrentPreset') }}
                </NPopconfirm>
              </NSpace>
            </NGridItem>
            <NGridItem :span="16">
              <NFormItem label="挂载的长期记忆库">
                <NSelect
                  multiple
                  filterable
                  :value="mountedLibraryIds"
                  :options="memoryLibraryOptions"
                  placeholder="选择一个或多个记忆库"
                  @update:value="onMountedLibrariesChange"
                />
              </NFormItem>
              <div class="hint-text">挂载库决定本会话能召回哪些长期记忆，可用于隔离不同角色或世界观。</div>
            </NGridItem>
            <NGridItem :span="8">
              <NFormItem label="新记忆写入到">
                <NSelect
                  v-model:value="writeLibraryId"
                  :options="writeLibraryOptions"
                  :disabled="!mountedLibraryIds.length"
                  placeholder="必须是已挂载的库"
                />
              </NFormItem>
              <NButton size="tiny" :loading="saving" :disabled="!mountedLibraryIds.length" @click="saveMounts">保存挂载</NButton>
            </NGridItem>
            <NGridItem :span="8">
              <NFormItem label="长期记忆写入">
                <NSelect v-model:value="config.memory_write_policy" :options="memoryPolicyOptions" />
              </NFormItem>
            </NGridItem>
            <NGridItem :span="8">
              <NFormItem label="状态板更新">
                <NSelect v-model:value="config.state_update_policy" :options="statePolicyOptions" />
              </NFormItem>
            </NGridItem>
            <NGridItem :span="8">
              <NFormItem label="注入策略">
                <NSelect v-model:value="config.injection_policy" :options="injectionPolicyOptions" />
              </NFormItem>
            </NGridItem>
          </NGrid>
          <NSpace justify="end">
            <NButton :loading="loading" @click="fetchBoard">重新加载</NButton>
            <NButton type="primary" :loading="saving" @click="saveConfig">保存会话策略</NButton>
          </NSpace>
        </NForm>
      </NCard>

      <NAlert v-if="showUndoAlert" type="success" closable style="margin-bottom: 12px;" @close="showUndoAlert = false">
        {{ $t('state.fill.undoHint', { count: lastFillEventIds.length }) }}
        <NButton size="tiny" type="warning" style="margin-left: 12px;" :loading="saving" @click="revertLastFill">{{ $t('state.fill.undoBtn') }}</NButton>
      </NAlert>

      <NSpin :show="loading">
        <NGrid :cols="24" :x-gap="16" :y-gap="16">
          <NGridItem :span="16">
            <NCard title="状态表格">
              <template #header-extra>
                <NSpace>
                  <NButton size="tiny" type="primary" :disabled="!template" @click="openAddTab">{{ $t('state.template.addTab') }}</NButton>
                </NSpace>
              </template>
              <NTabs v-if="tables.length" v-model:value="activeTableKey" type="line" animated @update:value="persistActiveTable">
                <NTabPane v-for="table in tables" :key="table.table_key" :name="table.table_key" :tab="`${table.name} (${(rowsByTable[table.table_key] || []).length})`">
                  <NSpace vertical size="medium">
                    <div v-if="table.description" class="hint-text">{{ table.description }}</div>
                    <NSpace align="center">
                      <NButton type="primary" size="small" @click="openCreate(table)">
                        <template #icon><NIcon :component="AddOutline" /></template>
                        新增状态行
                      </NButton>
                      <NButton size="small" @click="openAddColumn(table)">{{ $t('state.template.addColumn') }}</NButton>
                      <NButton size="small" @click="fetchPreview">刷新注入预览</NButton>
                    </NSpace>
                    <NSpace v-if="checkedRowKeys.length" align="center" size="small" style="padding: 6px 10px; background: #1a1a2e; border-radius: 4px;">
                      <span style="font-size: 12px; color: #a1a1aa;">{{ $t('state.batch.selected', { count: checkedRowKeys.length }) }}</span>
                      <NPopconfirm @positive-click="batchAction('delete')">
                        <template #trigger><NButton size="tiny" type="error" quaternary>{{ $t('state.batch.deleteSelected') }}</NButton></template>
                        {{ $t('state.batch.deleteConfirm', { count: checkedRowKeys.length }) }}
                      </NPopconfirm>
                      <NButton size="tiny" quaternary @click="checkedRowKeys = []">{{ $t('state.batch.clearSelection') }}</NButton>
                    </NSpace>
                    </NSpace>
                    <NDataTable class="state-data-table" :columns="columnsFor(table)" :data="rowsByTable[table.table_key] || []" :pagination="{ pageSize: 8 }" :scroll-x="tableScrollX(table)" :row-class-name="rowClassName" row-key="row_id" v-model:checked-row-keys="checkedRowKeys" />
                  </NSpace>
                </NTabPane>
              </NTabs>
              <NAlert v-else type="warning">暂无表格模板，请先确认后端数据库初始化正常。</NAlert>
            </NCard>
          </NGridItem>

          <NGridItem :span="8">
            <NSpace vertical size="medium">
              <NCard title="注入预览">
                <template #header-extra>
                  <NButton size="tiny" :loading="previewLoading" @click="fetchPreview">刷新</NButton>
                </template>
                <NSpace vertical>
                  <NTag size="small">{{ preview.char_count }} / {{ preview.max_chars }} 字符，{{ preview.item_count }} 行，≈{{ Math.ceil(preview.char_count / 2.5) }} tokens</NTag>
                  <NInput :value="preview.preview" type="textarea" readonly :autosize="{ minRows: 12, maxRows: 24 }" placeholder="加载后显示注入到模型的状态板文本" />
                  <div v-if="tables.length" style="font-size: 12px; color: #a1a1aa;">
                    <div v-for="table in tables" :key="table.table_key">
                      {{ table.name }}: {{ (rowsByTable[table.table_key] || []).length }} 行
                    </div>
                  </div>
                </NSpace>
              </NCard>

              <NCard title="AI 填充调试">
                <NSpace vertical>
                  <NInput v-model:value="fillForm.user_message" type="textarea" placeholder="用户消息" :autosize="{ minRows: 3, maxRows: 6 }" />
                  <NInput v-model:value="fillForm.assistant_message" type="textarea" placeholder="助手回复" :autosize="{ minRows: 3, maxRows: 8 }" />
                  <NSpace>
                    <NButton type="primary" :loading="saving" :disabled="!conversationId.trim()" @click="runFillPreview">{{ $t('state.fill.previewBtn') }}</NButton>
                    <NButton :loading="saving" :disabled="!conversationId.trim()" @click="runFillConfirm">{{ $t('state.fill.directBtn') }}</NButton>
                  </NSpace>
                </NSpace>
              </NCard>
            </NSpace>
          </NGridItem>
        </NGrid>
      </NSpin>

      <NCard v-if="conversationId.trim()" :title="$t('state.history.title')" style="margin-top: 16px;">
        <template #header-extra>
          <NButton size="tiny" :loading="historyLoading" @click="fetchHistory">{{ $t('common.refresh') }}</NButton>
        </template>
        <div v-if="!historyEvents.length" class="hint-text">{{ $t('state.history.empty') }}</div>
        <div v-else style="max-height: 400px; overflow-y: auto;">
          <div v-for="evt in historyEvents" :key="evt.event_id" style="padding: 6px 0; border-bottom: 1px solid #333; font-size: 12px;">
            <NSpace align="center" size="small">
              <NTag size="tiny" :type="evt.event_type.includes('insert') ? 'success' : evt.event_type.includes('delete') || evt.event_type.includes('resolve') ? 'error' : evt.event_type === 'revert' ? 'warning' : 'info'">
                {{ evt.event_type }}
              </NTag>
              <span style="color: #a1a1aa;">{{ evt.table_key || '-' }}</span>
              <span style="color: #666;">{{ evt.created_at }}</span>
            </NSpace>
            <div v-if="evt.reason" style="margin-top: 2px; color: #888;">{{ evt.reason }}</div>
            <div v-if="evt.after && Object.keys(evt.after).length" style="margin-top: 2px; color: #63e2b7;">
              <span v-for="(val, key) in evt.after" :key="key" style="margin-right: 8px;">{{ key }}={{ val }}</span>
            </div>
          </div>
        </div>
      </NCard>
    </NSpace>

    <NDrawer v-model:show="showDefaultDrawer" width="min(560px, 96vw)" placement="right">
      <NDrawerContent title="新会话默认配置" closable>
        <p class="hint-text" style="margin-bottom: 16px;">
          这里设置的是<b>未来新出现的会话</b>使用的初始配置（识别到新的 conversation_id 时自动应用）。已有会话不会被覆盖；要修改当前会话请使用页面上的"当前会话策略"。
        </p>
        <NForm v-if="defaultConfig" label-placement="top">
          <NFormItem label="默认会话方案">
            <NSelect v-model:value="defaultConfig.profile_id" :options="profileOptions" :render-label="profileRenderLabel" @update:value="applyProfileToDefault" />
          </NFormItem>
          <div v-if="selectedDefaultProfileHint" class="hint-text" style="margin-bottom: 12px;">{{ selectedDefaultProfileHint }}</div>
          <NFormItem label="默认表格模板">
            <NSelect v-model:value="defaultConfig.table_template_id" filterable :options="tableTemplateOptions" :render-label="templateRenderLabel" />
          </NFormItem>
          <NFormItem label="默认挂载组合预设">
            <NSelect v-model:value="defaultConfig.mount_preset_id" filterable :options="mountPresetOptions" />
          </NFormItem>
          <NFormItem label="默认长期记忆写入">
            <NSelect v-model:value="defaultConfig.memory_write_policy" :options="memoryPolicyOptions" />
          </NFormItem>
          <NFormItem label="默认状态板更新">
            <NSelect v-model:value="defaultConfig.state_update_policy" :options="statePolicyOptions" />
          </NFormItem>
          <NFormItem label="默认注入策略">
            <NSelect v-model:value="defaultConfig.injection_policy" :options="injectionPolicyOptions" />
          </NFormItem>
        </NForm>
        <template #footer>
          <NSpace justify="end">
            <NButton @click="showDefaultDrawer = false">关闭</NButton>
            <NButton type="primary" :loading="saving" @click="saveDefaultConfig">保存</NButton>
          </NSpace>
        </template>
      </NDrawerContent>
    </NDrawer>

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
