<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
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
import { apiFetch, friendlyError } from '../api'
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
import { useTableManagement } from '../composables/useTableManagement'
import { useBoardEditing } from '../composables/useBoardEditing'
import { useStateFiller } from '../composables/useStateFiller'

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
const historyEvents = ref<any[]>([])
const historyLoading = ref(false)
const config = ref<ConversationConfig | null>(null)
const defaultConfig = ref<ConversationConfig | null>(null)
const profiles = ref<any[]>([])
const tableTemplates = ref<any[]>([])
const mountPresets = ref<any[]>([])
const memoryLibraries = ref<any[]>([])
const retrievalProfiles = ref<any[]>([])
const mountedLibraryIds = ref<string[]>([])
const writeLibraryId = ref<string | null>(null)
const activeTableKey = ref(localStorage.getItem(STATE_ACTIVE_TABLE_STORAGE_KEY) || '')
const preview = ref({ preview: '', char_count: 0, max_chars: 0, item_count: 0, summary: null as any })
const retrievalTraces = ref<any[]>([])
const retrievalTraceDetail = ref<any | null>(null)
const showHelpModal = ref(false)
const showRenameModal = ref(false)
const showDefaultDrawer = ref(false)
const renameForm = ref({ title: '' })

// ── Composables ──────────────────────────────────────────
const tableMgmt = useTableManagement({
  template,
  config,
  adminToken,
  saving,
  activeTableKey,
  mountedLibraryIds,
  writeLibraryId,
  fetchOptions: fetchOptionsFn,
  saveConfig: saveConfigFn,
  fetchBoard: fetchBoardFn,
})
const {
  showAddTabModal, showEditTabModal, tabForm,
  openAddTab, openEditTab, saveNewTab, saveEditTab, deleteTab,
  showAddColumnModal, showEditColumnModal, columnForm,
  openAddColumn, openEditColumn, saveNewColumn, saveEditColumn,
  showRenameTemplateModal, renameTemplateForm,
  cloneCurrentTemplate, openRenameTemplate, renameTemplate, deleteTemplate,
  showPresetModal, presetForm, openPresetModal, savePreset, deletePreset,
  showProfileModal, profileForm, openProfileModal, saveProfile, deleteProfile,
} = tableMgmt

const boardEdit = useBoardEditing({
  conversationId,
  adminToken,
  saving,
  fetchBoard: fetchBoardFn,
})
const {
  showEditModal, editingTable, editingRow, editValues, editMeta,
  checkedRowKeys, batchPriority,
  openCreate, openEdit, duplicateRow, saveRow, deleteRow,
  batchAction, onCellSaved,
} = boardEdit

const filler = useStateFiller({
  conversationId,
  adminToken,
  saving,
  fetchBoard: fetchBoardFn,
})
const {
  showFillPreviewModal, fillPreviewOps, showUndoAlert, lastFillEventIds,
  fillForm, runFillPreview, runFillConfirm, revertLastFill,
} = filler

// ── Computed ─────────────────────────────────────────────
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
const retrievalProfileOptions = computed(() => retrievalProfiles.value.map((item) => ({
  label: item.name,
  value: item.profile_id,
})))
const conversationOptions = computed(() => conversations.value.map((item) => {
  const name = conversationDisplayName(item)
  const char = item.character_display_name || item.character_id || '-'
  const turns = item.turn_count || 0
  const lastMsg = item.last_user_message?.slice(0, 40) || ''
  const turnsLabel = t('state.toolbar.turns', { n: turns })
  const label = turns > 0
    ? `[${char}] ${name}  ·  ${turnsLabel}${lastMsg ? `  ·  ${t('state.toolbar.lastMsg')}: ${lastMsg}` : ''}`
    : `[${char}] ${name}`
  return { label, value: item.conversation_id }
}))
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
const continuityCards = computed(() => {
  const specs = [
    {
      key: 'scene',
      title: t('state.continuity.scene'),
      tableKeys: ['current_scene', 'current_interaction', 'colony_overview'],
      fields: ['scene', 'location', 'topic', 'name', 'situation', 'focus', 'next_step', 'risk'],
    },
    {
      key: 'relationship',
      title: t('state.continuity.relationship'),
      tableKeys: ['relationship_state', 'pawn_relationships'],
      fields: ['subject', 'object', 'relationship', 'attitude', 'recent_change', 'change'],
    },
    {
      key: 'rules',
      title: t('state.continuity.rules'),
      tableKeys: ['roleplay_rules'],
      fields: ['rule', 'scope', 'source'],
    },
    {
      key: 'tasks',
      title: t('state.continuity.tasks'),
      tableKeys: ['promises_tasks', 'quests_clues', 'threats_events', 'story_flags'],
      fields: ['task', 'item', 'event', 'flag', 'status', 'owner', 'due', 'note', 'impact', 'response'],
    },
  ]

  return specs.map((spec) => {
    const tableKey = spec.tableKeys.find((key) => (rowsByTable.value[key] || []).length)
      || spec.tableKeys.find((key) => tables.value.some((table) => table.table_key === key))
      || spec.tableKeys[0]
    const tableRows = (rowsByTable.value[tableKey] || [])
      .slice()
      .sort((a, b) => (b.priority || 0) - (a.priority || 0))
      .slice(0, 2)
    const table = tables.value.find((item) => item.table_key === tableKey)
    return {
      ...spec,
      tableKey,
      tableName: table?.name || '',
      count: rowsByTable.value[tableKey]?.length || 0,
      lines: tableRows.map((row) => summarizeRow(row, spec.fields)),
      updatedAt: tableRows[0]?.updated_at || '',
    }
  })
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

// ── Core helpers ─────────────────────────────────────────
function conversationDisplayName(item: any) {
  return item?.title?.trim() || item?.conversation_id || '未命名会话'
}

function summarizeRow(row: StateRow, preferredKeys: string[]) {
  const values = row.values || {}
  const selected = preferredKeys
    .map((key) => values[key])
    .filter((value) => value && String(value).trim())
    .slice(0, 3)
  const fallback = Object.values(values)
    .filter((value) => value && String(value).trim())
    .slice(0, 3)
  const parts = (selected.length ? selected : fallback).map((value) => String(value).trim())
  return parts.join(' · ') || t('state.continuity.emptyLine')
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

// ── Data fetching ────────────────────────────────────────
async function fetchBoardFn() {
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
    message.error(friendlyError(error.message || '', 'state.loadBoard'))
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
    message.error(friendlyError(error.message || '', 'state.loadTraces'))
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
    message.error(friendlyError(error.message || '', 'state.loadTraceDetail'))
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

async function fetchOptionsFn() {
  try {
    const [profilesResp, retrievalProfilesResp, tableResp, presetResp, libResp] = await Promise.all([
      apiFetch('/admin/conversation-profiles', { headers: authHeaders() }),
      apiFetch('/admin/retrieval-profiles', { headers: authHeaders() }),
      apiFetch('/admin/state/table-templates', { headers: authHeaders() }),
      apiFetch('/admin/memory-mount-presets', { headers: authHeaders() }),
      apiFetch('/admin/memory-libraries', { headers: authHeaders() }),
    ])
    if (profilesResp.ok) profiles.value = (await profilesResp.json()).items || []
    if (retrievalProfilesResp.ok) retrievalProfiles.value = (await retrievalProfilesResp.json()).items || []
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
    message.error(friendlyError(error.message || '', 'state.saveMounts'))
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
    if (conversationId.value) await fetchBoardFn()
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
    retrieval_profile_id: profile.retrieval_profile_id || 'balanced',
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
    retrieval_profile_id: profile.retrieval_profile_id || 'balanced',
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

async function saveConfigFn() {
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
    await fetchBoardFn()
  } catch (error: any) {
    message.error(error.message || '保存会话策略失败')
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
      if (targetId === conversationId.value.trim()) await fetchBoardFn()
    } catch (error: any) {
      message.error(error.message || t('state.messages.importFailed'))
    }
  }
  input.click()
}

function onWsEvent(e: any) {
  const data = e.detail
  if (data?.event === 'state_fill_complete' && data?.conversation_id === conversationId.value.trim()) {
    fetchBoardFn()
  }
}

onMounted(async () => {
  window.addEventListener('kokoromemo:event', onWsEvent)
  fetchOptionsFn()
  fetchDefaultConfig()
  await fetchConversations()
  if (conversationId.value.trim()) {
    await fetchBoardFn()
  } else if (conversations.value.length > 0) {
    const first = conversations.value[0]
    conversationId.value = first.conversation_id
    persistInputs()
    await fetchBoardFn()
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
        @load="fetchBoardFn"
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
        :retrieval-profile-options="retrievalProfileOptions"
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
        @update-retrieval-profile="patchCurrentConfig('retrieval_profile_id', $event)"
        @open-profile-modal="openProfileModal"
        @delete-profile="deleteProfile"
        @clone-template="cloneCurrentTemplate"
        @open-rename-template="openRenameTemplate"
        @delete-template="deleteTemplate"
        @open-preset-modal="openPresetModal"
        @delete-preset="deletePreset"
        @reload="fetchBoardFn"
        @save-config="saveConfigFn"
      />

      <NCard class="continuity-overview-card">
        <template #header>
          <div class="continuity-header">
            <span>{{ $t('state.continuity.title') }}</span>
            <NTag size="small" round>{{ rows.length }} {{ $t('state.continuity.rows') }}</NTag>
          </div>
        </template>
        <div class="continuity-grid">
          <div v-for="card in continuityCards" :key="card.key" class="continuity-card">
            <div class="continuity-card__top">
              <div>
                <div class="continuity-card__title">{{ card.title }}</div>
                <div class="continuity-card__table">{{ card.tableName || card.tableKey }}</div>
              </div>
              <NTag size="small" :type="card.count ? 'success' : 'default'" round>
                {{ card.count }}
              </NTag>
            </div>
            <div v-if="card.lines.length" class="continuity-card__lines">
              <div v-for="(line, idx) in card.lines" :key="idx" class="continuity-card__line">{{ line }}</div>
            </div>
            <div v-else class="continuity-card__empty">{{ $t('state.continuity.empty') }}</div>
            <div class="continuity-card__footer">
              <span>{{ card.updatedAt || $t('state.continuity.noUpdate') }}</span>
              <NButton size="tiny" quaternary @click="updateActiveTable(card.tableKey)">
                {{ $t('state.continuity.openTable') }}
              </NButton>
            </div>
          </div>
        </div>
      </NCard>

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
      :retrieval-profile-options="retrievalProfileOptions"
      @update-profile="applyProfileToDefault"
      @update-table-template="patchDefaultConfig('table_template_id', $event)"
      @update-mount-preset="patchDefaultConfig('mount_preset_id', $event)"
      @update-memory-write-policy="patchDefaultConfig('memory_write_policy', $event)"
      @update-state-update-policy="patchDefaultConfig('state_update_policy', $event)"
      @update-injection-policy="patchDefaultConfig('injection_policy', $event)"
      @update-retrieval-profile="patchDefaultConfig('retrieval_profile_id', $event)"
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

.continuity-overview-card {
  background: #18181b;
  border: 1px solid #27272a;
}

.continuity-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  color: #e4e4e7;
  font-size: 15px;
  font-weight: 600;
}

.continuity-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.continuity-card {
  min-height: 176px;
  padding: 12px;
  border: 1px solid #27272a;
  border-radius: 8px;
  background: #111113;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.continuity-card__top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.continuity-card__title {
  color: #f4f4f5;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
}

.continuity-card__table,
.continuity-card__footer,
.continuity-card__empty {
  color: #71717a;
  font-size: 12px;
  line-height: 1.5;
}

.continuity-card__lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.continuity-card__line {
  color: #e4e4e7;
  font-size: 13px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.continuity-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border-top: 1px solid #27272a;
  padding-top: 8px;
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

  .continuity-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (min-width: 769px) and (max-width: 1180px) {
  .continuity-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.state-data-table :deep(.row-inserted td) {
  border-left: 3px solid #18a058;
}

.state-data-table :deep(.row-updated td) {
  border-left: 3px solid #2080f0;
}
</style>
