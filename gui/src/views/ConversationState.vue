<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import {
  NButton,
  NCard,
  NCollapse,
  NCollapseItem,
  NDataTable,
  NDivider,
  NDropdown,
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
  NSwitch,
  NTabPane,
  NTabs,
  NTag,
  NTooltip,
  useDialog,
  useMessage,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { AddOutline, EllipsisHorizontal, HelpCircleOutline, CreateOutline, RefreshOutline, TrashOutline, AddCircleOutline } from '@vicons/ionicons5'
import { apiFetch } from '../api'
import { saveJsonExport } from '../export'

const { t } = useI18n()
const message = useMessage()
const dialog = useDialog()
const loading = ref(false)
const conversationId = ref('')
const adminToken = ref('')
const stateItems = ref<any[]>([])
const decisions = ref<any[]>([])
const events = ref<any[]>([])
const templates = ref<any[]>([])
const memoryLibraries = ref<any[]>([])
const memoryMounts = ref<any[]>([])
const currentTemplate = ref<any | null>(null)
const selectedTemplateId = ref('')
const mountedLibraryIds = ref<string[]>([])
const writeLibraryId = ref('')
const showEditModal = ref(false)
const showTemplateModal = ref(false)
const showFillModal = ref(false)
const editingItem = ref<any | null>(null)
const isCustomField = ref(false)
const customFieldName = ref('')
const customItemKey = ref('')
const currentTabId = ref('')
const editForm = ref({ field_id: '', item_value: '', priority: 70, confidence: 0.8, user_locked: false, linked_card_ids: '' })
const templateJson = ref('')
const fillForm = ref({ user_message: '', assistant_message: '' })
const configLoaded = ref(false)
const stateItemCount = ref(0)
const isNewSession = ref(false)
const recentConversations = ref<any[]>([])
const presets = ref<any[]>([])
const selectedPresetId = ref<string | null>(null)
const showPresetModal = ref(false)
const presetForm = ref({ name: '', description: '' })
const showCopyModal = ref(false)
const copyForm = ref({ target_conversation_id: '', copy_mounts: true })
const showConversationImportModal = ref(false)
const importForm = ref({ target_conversation_id: '', overwrite_state: false, import_template_snapshot: true })
const importJson = ref('')
const showInitWizard = ref(false)
const previewData = ref({ preview: '', char_count: 0, max_chars: 0, item_count: 0 })
const previewLoading = ref(false)
const wizardForm = ref({ library_ids: ['lib_default'] as string[], write_library_id: 'lib_default', template_id: 'tpl_roleplay_general' })
const showAddTabModal = ref(false)
const showRenameTabModal = ref(false)
const renamingTab = ref<any>(null)
const renameTabLabel = ref('')
const newTabLabel = ref('')
const helpModal = ref('')
const showGateDebugPreview = ref(false)
const gateDebugPreviewTitle = ref('')
const gateDebugPreviewContent = ref('')

const templateOptions = computed(() => templates.value.map((item) => ({ label: `${item.name}${item.is_builtin ? `(${t('common.builtin')})` : ''}`, value: item.template_id })))
const selectedTemplate = computed(() => templates.value.find((item) => item.template_id === selectedTemplateId.value) || null)
const memoryLibraryOptions = computed(() => memoryLibraries.value.map((item) => ({ label: `${item.name}${item.card_count ? `（${item.card_count}）` : ''}`, value: item.library_id })))
const conversationOptions = computed(() => recentConversations.value.map((item) => {
  const parts = [item.conversation_id]
  if (item.character_id) parts.push(item.character_id)
  if (item.client_name) parts.push(item.client_name)
  return { label: parts.join(' · '), value: item.conversation_id }
}))
const mountedLibraryNames = computed(() => memoryMounts.value.map((item) => item.name).join(' + ') || t('state.noMount'))
const fieldOptions = computed(() => (currentTemplate.value?.tabs || []).flatMap((tab: any) =>
  (tab.fields || []).map((field: any) => ({ label: `${tab.label} / ${field.label}`, value: field.field_id })),
))
const itemByField = computed(() => {
  const data: Record<string, any> = {}
  for (const item of stateItems.value) {
    if (item.field_id && item.status === 'active') data[item.field_id] = item
  }
  return data
})
const legacyItems = computed(() => stateItems.value.filter((item) => !item.field_id && !item.tab_id))
const presetOptions = computed(() => presets.value.map((item) => ({ label: item.name, value: item.preset_id })))
const templateMenuOptions = computed(() => [
  { label: t('state.create'), key: 'create' },
  { label: t('common.export'), key: 'export' },
  { label: t('common.import'), key: 'import' },
  { label: t('common.delete'), key: 'delete', disabled: !selectedTemplate.value || selectedTemplate.value.is_builtin },
])
const presetManageOptions = computed(() => [
  { label: t('state.importPreset'), key: 'import' },
  { label: t('state.exportAllPresets'), key: 'exportAll' },
])
const dangerActionOptions = computed(() => [
  { label: t('state.copyToNew'), key: 'copy' },
  { label: t('state.resetToEmpty'), key: 'reset' },
  { label: t('state.clearState'), key: 'clear' },
])
const currentConversationId = computed(() => conversationId.value.trim())
const scopedDecisions = computed(() => decisions.value.filter((item) => item.conversation_id === currentConversationId.value))
const scopedEvents = computed(() => events.value.filter((item) => item.conversation_id === currentConversationId.value))

function clearConversationScopedData() {
  stateItems.value = []
  decisions.value = []
  events.value = []
  currentTemplate.value = null
  selectedTemplateId.value = ''
  memoryMounts.value = []
  mountedLibraryIds.value = []
  writeLibraryId.value = ''
  stateItemCount.value = 0
  isNewSession.value = false
  configLoaded.value = false
  previewData.value = { preview: '', char_count: 0, max_chars: 0, item_count: 0 }
}

function parseDebugJson(value: unknown) {
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

function formatGateDebugRow(row: any) {
  return JSON.stringify({
    decision_id: row.decision_id,
    request_id: row.request_id,
    conversation_id: row.conversation_id,
    user_id: row.user_id,
    character_id: row.character_id,
    world_id: row.world_id,
    created_at: row.created_at,
    mode: row.mode,
    should_retrieve: !!row.should_retrieve,
    reason: row.reason,
    reasons: parseDebugJson(row.reasons_json),
    triggered_routes: parseDebugJson(row.triggered_routes_json),
    skipped_routes: parseDebugJson(row.skipped_routes_json),
    latest_user_text: row.latest_user_text,
    state_item_count: row.state_item_count,
    state_confidence: row.state_confidence,
    avg_state_confidence: row.avg_state_confidence,
    turn_index: row.turn_index,
  }, null, 2)
}

function openGateDebugPreview(row: any) {
  gateDebugPreviewTitle.value = `${t('state.gateDebugPreviewTitle')} · ${row.created_at || row.request_id || ''}`
  gateDebugPreviewContent.value = formatGateDebugRow(row)
  showGateDebugPreview.value = true
}

function ensureConversationId() {
  if (!conversationId.value.trim()) {
    message.warning(t('state.messages.inputId'))
    return false
  }
  return true
}

async function fetchTemplates() {
  const resp = await apiFetch('/admin/state/templates', { headers: authHeaders() })
  templates.value = (await resp.json()).items || []
}

async function fetchMemoryLibraries() {
  const resp = await apiFetch('/admin/memory-libraries', { headers: authHeaders() })
  memoryLibraries.value = (await resp.json()).items || []
}

async function fetchConversations() {
  const resp = await apiFetch('/admin/conversations?limit=100', { headers: authHeaders() })
  recentConversations.value = (await resp.json()).items || []
}

async function fetchConfig(targetConversationId = conversationId.value.trim()) {
  if (!targetConversationId) return
  const resp = await apiFetch(`/admin/conversations/${targetConversationId}/config`, { headers: authHeaders() })
  if (targetConversationId !== conversationId.value.trim()) return
  const data = await resp.json()
  stateItemCount.value = data.state_item_count || 0
  isNewSession.value = !!data.is_new_session
  if (data.mounts?.length) {
    memoryMounts.value = data.mounts
    mountedLibraryIds.value = data.mounted_library_ids || []
    writeLibraryId.value = data.write_library_id || ''
  }
  if (data.template_id) {
    selectedTemplateId.value = data.template_id
  }
  configLoaded.value = true
}

async function fetchPresets() {
  const resp = await apiFetch('/admin/memory-mount-presets', { headers: authHeaders() })
  presets.value = (await resp.json()).items || []
}

async function fetchAll() {
  if (!ensureConversationId()) return
  const targetConversationId = conversationId.value.trim()
  loading.value = true
  try {
    await Promise.all([fetchTemplates(), fetchMemoryLibraries(), fetchPresets()])
    const [templateResp, stateResp, decisionResp, eventResp] = await Promise.all([
      apiFetch(`/admin/conversations/${targetConversationId}/state/template`, { headers: authHeaders() }),
      apiFetch(`/admin/conversations/${targetConversationId}/state?limit=500`, { headers: authHeaders() }),
      apiFetch(`/admin/conversations/${targetConversationId}/retrieval-decisions?limit=100`, { headers: authHeaders() }),
      apiFetch(`/admin/conversations/${targetConversationId}/state/events?limit=100`, { headers: authHeaders() }),
    ])
    if (targetConversationId !== conversationId.value.trim()) return
    if (templateResp.ok) {
      currentTemplate.value = await templateResp.json()
      selectedTemplateId.value = currentTemplate.value?.template_id || ''
    }
    if (stateResp.ok) {
      stateItems.value = (await stateResp.json()).items || []
      stateItemCount.value = stateItems.value.filter((item) => item.status === 'active').length
    }
    if (decisionResp.ok) decisions.value = ((await decisionResp.json()).items || []).filter((item: any) => item.conversation_id === targetConversationId)
    if (eventResp.ok) events.value = ((await eventResp.json()).items || []).filter((item: any) => item.conversation_id === targetConversationId)
    await fetchConfig(targetConversationId)
    saveLocalInputs()
  } catch (e: any) {
    message.error(t('state.messages.loadFailed', { error: e.message || e }))
  } finally {
    if (targetConversationId === conversationId.value.trim()) loading.value = false
  }
}

watch(conversationId, () => {
  clearConversationScopedData()
})

async function deleteConversation() {
  if (!conversationId.value.trim()) return
  const resp = await apiFetch(`/admin/conversations/${conversationId.value}`, { method: 'DELETE', headers: authHeaders() })
  const data = await resp.json()
  if (data.status === 'ok') {
    message.success(t('state.messages.conversationDeleted'))
    conversationId.value = ''
    stateItems.value = []
    stateItemCount.value = 0
    configLoaded.value = false
    await fetchConversations()
  } else {
    message.error(data.message || t('common.deleteFailed'))
  }
}

async function fetchPreview() {
  if (!ensureConversationId()) return
  previewLoading.value = true
  try {
    const resp = await apiFetch(`/admin/conversations/${conversationId.value}/state/preview`, { headers: authHeaders() })
    previewData.value = await resp.json()
  } catch (e: any) {
    message.error(e.message || String(e))
  }
  previewLoading.value = false
}

async function saveFullConfig() {
  if (!ensureConversationId()) return
  if (!mountedLibraryIds.value.length) {
    message.warning(t('state.messages.mountRequired'))
    return
  }
  if (!mountedLibraryIds.value.includes(writeLibraryId.value)) {
    writeLibraryId.value = mountedLibraryIds.value[0]
  }
  try {
    const resp = await apiFetch(`/admin/conversations/${conversationId.value}/config`, {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({
        library_ids: mountedLibraryIds.value,
        write_library_id: writeLibraryId.value,
        template_id: selectedTemplateId.value || undefined,
      }),
    })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || t('common.saveFailed'))
    message.success(t('state.messages.configSaved'))
    isNewSession.value = false
    await fetchAll()
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

function handleMountedLibrariesChange(value: string[]) {
  mountedLibraryIds.value = value
  if (!value.includes(writeLibraryId.value)) {
    writeLibraryId.value = value[0] || ''
  }
}

async function changeTemplate() {
  if (!ensureConversationId() || !selectedTemplateId.value) return
  await apiFetch(`/admin/conversations/${conversationId.value}/state/template`, {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify({ template_id: selectedTemplateId.value }),
  })
  message.success(t('state.messages.templateSwitched'))
  fetchAll()
}

async function ensureCustomTemplate(): Promise<boolean> {
  if (!currentTemplate.value?.is_builtin) return true
  try {
    const resp = await apiFetch(`/admin/state/templates/${currentTemplate.value.template_id}/clone`, { method: 'POST', headers: authHeaders(true) })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message)
    const newId = data.template_id
    if (conversationId.value) {
      await apiFetch(`/admin/conversations/${conversationId.value}/state/template`, {
        method: 'POST', headers: authHeaders(true),
        body: JSON.stringify({ template_id: newId }),
      })
    }
    const tplResp = await apiFetch(`/admin/state/templates/${newId}`, { headers: authHeaders() })
    if (tplResp.ok) {
      currentTemplate.value = await tplResp.json()
      selectedTemplateId.value = newId
    }
    message.success(t('state.messages.clonedForEdit'))
    return true
  } catch (e: any) {
    message.error(e.message || String(e))
    return false
  }
}

async function saveTemplateFromCurrent(): Promise<string | null> {
  const tpl = currentTemplate.value
  if (!tpl) return null
  const payload = {
    template_id: tpl.template_id,
    name: tpl.name,
    description: tpl.description || '',
    is_builtin: false,
    tabs: (tpl.tabs || []).map((tab: any, index: number) => ({
      tab_id: tab.tab_id || undefined,
      tab_key: tab.tab_key || `tab_${Date.now()}_${index}`,
      label: tab.label,
      description: tab.description || '',
      sort_order: index,
      fields: (tab.fields || []).map((field: any, fi: number) => ({
        field_id: field.field_id || undefined,
        field_key: field.field_key,
        label: field.label,
        field_type: field.field_type || 'multiline',
        description: field.description || '',
        ai_writable: field.ai_writable ?? true,
        include_in_prompt: field.include_in_prompt ?? true,
        sort_order: fi,
        default_value: field.default_value || '',
        options: field.options || {},
        status: field.status || 'active',
      })),
    })),
  }
  const resp = await apiFetch('/admin/state/templates', { method: 'POST', headers: authHeaders(true), body: JSON.stringify(payload) })
  const data = await resp.json()
  if (data.status !== 'ok') throw new Error(data.message)
  return data.template_id
}

function onAddTabClick() {
  newTabLabel.value = ''
  showAddTabModal.value = true
}

async function addTab() {
  const label = newTabLabel.value.trim()
  if (!label) return
  if (!await ensureCustomTemplate()) return
  currentTemplate.value.tabs.push({
    tab_id: null,
    template_id: currentTemplate.value.template_id,
    tab_key: `tab_${Date.now()}`,
    label,
    description: '',
    sort_order: currentTemplate.value.tabs.length,
    fields: [],
  })
  try {
    const newId = await saveTemplateFromCurrent()
    if (newId) currentTemplate.value.template_id = newId
    showAddTabModal.value = false
    newTabLabel.value = ''
    message.success(t('state.messages.tabAdded'))
    await fetchAll()
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

function openRenameTab(tab: any) {
  renamingTab.value = tab
  renameTabLabel.value = tab.label
  showRenameTabModal.value = true
}

async function renameTab() {
  const label = renameTabLabel.value.trim()
  if (!label || !renamingTab.value) return
  if (!await ensureCustomTemplate()) return
  try {
    const tplId = currentTemplate.value.template_id
    const tabId = renamingTab.value.tab_id
    if (tabId) {
      const resp = await apiFetch(`/admin/state/templates/${tplId}/tabs/${tabId}`, {
        method: 'PATCH', headers: authHeaders(true),
        body: JSON.stringify({ label }),
      })
      const data = await resp.json()
      if (data.status !== 'ok') throw new Error(data.message)
    }
    showRenameTabModal.value = false
    renamingTab.value = null
    message.success(t('state.messages.tabRenamed'))
    await fetchAll()
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

async function deleteTab(tab: any) {
  const itemCount = tab.item_count || 0
  const content = itemCount > 0
    ? t('state.messages.confirmDeleteTab', { name: tab.label, count: itemCount })
    : t('state.messages.confirmDeleteTabEmpty', { name: tab.label })
  dialog.warning({
    title: t('state.deleteTab'),
    content,
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      if (!await ensureCustomTemplate()) return
      const idx = currentTemplate.value.tabs.findIndex((t: any) => t.tab_id === tab.tab_id)
      if (idx < 0) return
      currentTemplate.value.tabs.splice(idx, 1)
      try {
        const newId = await saveTemplateFromCurrent()
        if (newId) currentTemplate.value.template_id = newId
        message.success(t('state.messages.tabDeleted'))
        await fetchAll()
      } catch (e: any) {
        message.error(e.message || String(e))
      }
    },
  })
}

function handleTabAction(key: string, tab: any) {
  if (key === 'rename') openRenameTab(tab)
  else if (key === 'delete') deleteTab(tab)
}

function tabActionOptions(_tab: any) {
  return [
    { label: t('state.renameTab'), key: 'rename' },
    { label: t('state.deleteTab'), key: 'delete' },
  ]
}

function openCreateModal(field?: any) {
  editingItem.value = null
  isCustomField.value = false
  customFieldName.value = ''
  currentTabId.value = ''
  editForm.value = { field_id: field?.field_id || '', item_value: '', priority: 70, confidence: 0.8, user_locked: false, linked_card_ids: '' }
  showEditModal.value = true
}

function openCreateModalForTab(tab: any) {
  editingItem.value = null
  isCustomField.value = true
  customFieldName.value = ''
  customItemKey.value = ''
  currentTabId.value = tab.tab_id || ''
  editForm.value = { field_id: '', item_value: '', priority: 70, confidence: 0.8, user_locked: false, linked_card_ids: '' }
  showEditModal.value = true
}

function openEditModal(row: any, field?: any) {
  editingItem.value = row
  const fid = row.field_id || field?.field_id || ''
  isCustomField.value = !fid && !!row.item_key
  customFieldName.value = (!fid && !!row.item_key) ? (row.title || row.item_key || '') : ''
  customItemKey.value = (!fid && !!row.item_key && row.item_key !== row.title) ? row.item_key : ''
  editForm.value = {
    field_id: fid,
    item_value: row.item_value || row.content || '',
    priority: row.priority ?? 70,
    confidence: row.confidence ?? 0.8,
    user_locked: !!row.user_locked,
    linked_card_ids: (row.linked_card_ids || []).join(', '),
  }
  showEditModal.value = true
}

async function saveItem() {
  if (!ensureConversationId()) return
  const field = findField(editForm.value.field_id)
  const useCustom = isCustomField.value && !field
  const customName = customFieldName.value.trim()
  const customKey = customItemKey.value.trim()
  if (useCustom && !customName) {
    message.warning(t('state.messages.inputFieldName'))
    return
  }
  const body = JSON.stringify({
    template_id: currentTemplate.value?.template_id,
    tab_id: field?.tab_id || currentTabId.value || undefined,
    field_id: field?.field_id || undefined,
    field_key: field?.field_key || customKey || customName,
    category: useCustom ? 'custom' : categoryForField(field?.field_key),
    item_key: field?.field_key || customKey || customName,
    title: field?.label || customName,
    item_value: editForm.value.item_value,
    priority: editForm.value.priority,
    confidence: editForm.value.confidence,
    user_locked: editForm.value.user_locked,
    linked_card_ids: editForm.value.linked_card_ids
      ? editForm.value.linked_card_ids.split(',').map((s: string) => s.trim()).filter(Boolean)
      : [],
  })
  const isEdit = !!editingItem.value && !!editingItem.value.item_id
  const url = isEdit ? `/admin/state/${editingItem.value.item_id}` : `/admin/conversations/${conversationId.value}/state`
  const method = isEdit ? 'PATCH' : 'POST'
  try {
    const resp = await apiFetch(url, { method, headers: authHeaders(true), body })
    if (!resp.ok) {
      const errorText = await resp.text().catch(() => '')
      let errorMsg = `HTTP ${resp.status}`
      try { errorMsg = JSON.parse(errorText).detail || errorMsg } catch {}
      throw new Error(errorMsg)
    }
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || t('common.saveFailed'))
    showEditModal.value = false
    message.success(t('state.messages.stateItemSaved'))
    fetchAll().catch(() => {})
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

async function resetItem(row: any) {
  await apiFetch(`/admin/state/${row.item_id}`, { method: 'PATCH', headers: authHeaders(true), body: JSON.stringify({ item_value: '', content: '' }) })
  message.success(t('state.messages.stateItemSaved'))
  fetchAll()
}

async function deleteItem(row: any) {
  await apiFetch(`/admin/state/${row.item_id}`, { method: 'DELETE', headers: authHeaders() })
  message.success(t('state.messages.itemDeleted'))
  fetchAll()
}

async function rebuildFromCards() {
  if (!ensureConversationId()) return
  const resp = await apiFetch(`/admin/conversations/${conversationId.value}/state/rebuild`, { method: 'POST', headers: authHeaders(true), body: JSON.stringify({}) })
  const data = await resp.json()
  message.success(t('state.messages.projected', { count: data.projected || 0 }))
  fetchAll()
}

async function clearState() {
  if (!ensureConversationId()) return
  try {
    const resp = await apiFetch(`/admin/conversations/${conversationId.value}/state/clear`, {
      method: 'POST',
      headers: authHeaders(true),
    })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || t('state.messages.clearFailed'))
    message.success(t('state.messages.cleared', { count: data.cleared || 0 }))
    fetchAll()
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

async function resetState() {
  if (!ensureConversationId()) return
  try {
    const resp = await apiFetch(`/admin/conversations/${conversationId.value}/state/reset`, {
      method: 'POST',
      headers: authHeaders(true),
    })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || t('state.messages.resetFailed'))
    message.success(t('state.messages.resetDone', { count: data.cleared || 0 }))
    fetchAll()
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

function openCopyModal() {
  copyForm.value = { target_conversation_id: '', copy_mounts: true }
  showCopyModal.value = true
}

function handleDangerAction(key: string) {
  if (key === 'copy') openCopyModal()
  else if (key === 'reset') {
    dialog.warning({
      title: t('state.resetToEmpty'),
      content: t('state.resetConfirm'),
      positiveText: t('common.confirm'),
      negativeText: t('common.cancel'),
      onPositiveClick: () => { resetState() },
    })
  } else if (key === 'clear') {
    dialog.warning({
      title: t('state.clearState'),
      content: t('state.clearConfirm'),
      positiveText: t('common.confirm'),
      negativeText: t('common.cancel'),
      onPositiveClick: () => { clearState() },
    })
  }
}

async function confirmCopy() {
  if (!ensureConversationId()) return
  if (!copyForm.value.target_conversation_id.trim()) {
    message.warning(t('state.messages.inputTargetId'))
    return
  }
  try {
    const resp = await apiFetch(`/admin/conversations/${conversationId.value}/state/copy`, {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify(copyForm.value),
    })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || t('state.messages.copyFailed'))
    showCopyModal.value = false
    message.success(t('state.messages.copied', { items: data.copied_items || 0, mounts: data.copied_mounts ? ` and ${data.copied_mounts} mounts` : '' }))
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

function openInitWizard() {
  wizardForm.value = {
    library_ids: mountedLibraryIds.value.length ? [...mountedLibraryIds.value] : ['lib_default'],
    write_library_id: writeLibraryId.value || 'lib_default',
    template_id: selectedTemplateId.value || 'tpl_roleplay_general',
  }
  showInitWizard.value = true
}

function handleWizardLibrariesChange(value: string[]) {
  wizardForm.value.library_ids = value
  if (!value.includes(wizardForm.value.write_library_id)) {
    wizardForm.value.write_library_id = value[0] || 'lib_default'
  }
}

async function confirmInitWizard() {
  if (!ensureConversationId()) return
  if (!wizardForm.value.library_ids.length) {
    message.warning(t('state.messages.selectLibrary'))
    return
  }
  try {
    const resp = await apiFetch(`/admin/conversations/${conversationId.value}/config`, {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({
        library_ids: wizardForm.value.library_ids,
        write_library_id: wizardForm.value.write_library_id,
        template_id: wizardForm.value.template_id,
      }),
    })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || t('state.messages.initFailed'))
    showInitWizard.value = false
    message.success(t('state.messages.sessionInit'))
    await fetchAll()
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

function openTemplateModal() {
  templateJson.value = JSON.stringify({
    name: t('state.messages.defaultTemplate'),
    description: t('state.messages.defaultTemplateDesc'),
    tabs: [
      { tab_key: 'main', label: t('state.messages.defaultTabLabel'), fields: [{ field_key: 'current_goal', label: t('state.messages.defaultFieldLabel'), description: t('state.messages.defaultFieldDesc'), ai_writable: true, include_in_prompt: true }] },
    ],
  }, null, 2)
  showTemplateModal.value = true
}

async function saveTemplate() {
  try {
    const payload = JSON.parse(templateJson.value)
    const resp = await apiFetch('/admin/state/templates', { method: 'POST', headers: authHeaders(true), body: JSON.stringify(payload) })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || t('common.saveFailed'))
    showTemplateModal.value = false
    message.success(t('state.messages.templateSaved'))
    await fetchTemplates()
    selectedTemplateId.value = data.template_id
  } catch (e: any) {
    message.error(t('state.messages.templateSaveFailed', { error: e.message || e }))
  }
}

async function runStateFiller() {
  if (!ensureConversationId()) return
  const resp = await apiFetch(`/admin/conversations/${conversationId.value}/state/fill`, {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify(fillForm.value),
  })
  const data = await resp.json()
  if (data.status !== 'ok') {
    message.error(data.message || t('state.messages.fillFailed'))
    return
  }
  showFillModal.value = false
  message.success(t('state.messages.fillDone', { applied: data.applied || 0, skipped: data.skipped || 0 }))
  fetchAll()
}

function applyPreset(preset: any) {
  try {
    const libraryIds: string[] = JSON.parse(preset.library_ids_json || '[]')
    if (libraryIds.length) {
      mountedLibraryIds.value = libraryIds
      writeLibraryId.value = preset.write_library_id || libraryIds[0]
      message.success(t('state.messages.presetApplied', { name: preset.name }))
    }
  } catch {
    message.error(t('state.messages.presetParseFailed'))
  }
}

function applyPresetById(presetId: string) {
  selectedPresetId.value = presetId
  const preset = presets.value.find((item) => item.preset_id === presetId)
  if (preset) applyPreset(preset)
}

function handleTemplateMenuAction(key: string) {
  if (key === 'create') openTemplateModal()
  else if (key === 'export') exportTemplate()
  else if (key === 'import') triggerImportTemplate()
  else if (key === 'delete') confirmDeleteTemplate()
}

function handlePresetManageAction(key: string) {
  if (key === 'import') triggerImportPreset()
  else if (key === 'exportAll') exportAllPresets()
}

async function saveAsPreset() {
  if (!mountedLibraryIds.value.length) {
    message.warning(t('state.messages.presetSelectFirst'))
    return
  }
  showPresetModal.value = true
}

async function confirmSavePreset() {
  try {
    const resp = await apiFetch('/admin/memory-mount-presets', {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({
        name: presetForm.value.name || t('state.messages.unnamedPreset'),
        description: presetForm.value.description,
        library_ids: mountedLibraryIds.value,
        write_library_id: writeLibraryId.value,
      }),
    })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || t('common.saveFailed'))
    showPresetModal.value = false
    presetForm.value = { name: '', description: '' }
    message.success(t('state.messages.presetSaved'))
    await fetchPresets()
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

async function deletePreset(presetId: string) {
  const preset = presets.value.find((p) => p.preset_id === presetId)
  dialog.warning({
    title: t('common.delete'),
    content: t('state.messages.confirmDeletePreset', { name: preset?.name || presetId }),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      const resp = await apiFetch(`/admin/memory-mount-presets/${presetId}`, { method: 'DELETE', headers: authHeaders() })
      const data = await resp.json()
      if (data.status === 'ok') {
        if (selectedPresetId.value === presetId) selectedPresetId.value = null
        message.success(t('state.messages.presetDeleted'))
        await fetchPresets()
      }
    },
  })
}

async function exportSinglePreset(presetId: string) {
  try {
    const resp = await apiFetch(`/admin/memory-mount-presets/${presetId}/export`, { headers: authHeaders() })
    const data = await resp.json()
    const savedPath = await saveJsonExport(`mount_preset_${presetId}.json`, data)
    if (savedPath) message.success(t('state.messages.presetExported'))
  } catch (e: any) {
    message.error(e.message || t('common.exportFailed'))
  }
}

async function exportTemplate() {
  if (!selectedTemplateId.value) return
  try {
    const resp = await apiFetch(`/admin/state/templates/${selectedTemplateId.value}/export`, { headers: authHeaders() })
    const data = await resp.json()
    const savedPath = await saveJsonExport(`template_${selectedTemplateId.value}.json`, data)
    if (savedPath) message.success(t('state.messages.templateExported'))
  } catch (e: any) {
    message.error(e.message || t('common.exportFailed'))
  }
}

function confirmDeleteTemplate() {
  const template = selectedTemplate.value
  if (!template || template.is_builtin) return
  dialog.warning({
    title: t('state.deleteTemplate'),
    content: t('state.messages.confirmDeleteTemplate', { name: template.name }),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => deleteTemplate(template.template_id),
  })
}

async function deleteTemplate(templateId: string) {
  try {
    const resp = await apiFetch(`/admin/state/templates/${templateId}`, { method: 'DELETE', headers: authHeaders() })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || t('state.messages.templateDeleteFailed'))
    if (selectedTemplateId.value === templateId) selectedTemplateId.value = ''
    message.success(t('state.messages.templateDeleted'))
    await fetchTemplates()
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

async function exportConversationConfig() {
  if (!ensureConversationId()) return
  try {
    const resp = await apiFetch(`/admin/conversations/${conversationId.value}/export`, { headers: authHeaders() })
    const data = await resp.json()
    const savedPath = await saveJsonExport(`conversation_state_${conversationId.value}.json`, data)
    if (savedPath) message.success(t('state.messages.conversationExported'))
  } catch (e: any) {
    message.error(e.message || t('common.exportFailed'))
  }
}

function triggerConversationImport() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      importJson.value = await file.text()
      const data = JSON.parse(importJson.value)
      importForm.value = {
        target_conversation_id: data.conversation_id || conversationId.value || '',
        overwrite_state: false,
        import_template_snapshot: true,
      }
      showConversationImportModal.value = true
    } catch (e: any) {
      message.error(`${t('common.importFailed')}: ${e.message || e}`)
    }
  }
  input.click()
}

async function confirmConversationImport() {
  try {
    const payload = JSON.parse(importJson.value)
    const resp = await apiFetch('/admin/conversations/import', {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({
        ...payload,
        target_conversation_id: importForm.value.target_conversation_id,
        overwrite_state: importForm.value.overwrite_state,
        import_template_snapshot: importForm.value.import_template_snapshot,
      }),
    })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || t('common.importFailed'))
    showConversationImportModal.value = false
    conversationId.value = data.conversation_id
    message.success(t('state.messages.conversationImported', { count: data.imported_items || 0 }))
    await fetchConversations()
    await fetchAll()
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

function triggerImportTemplate() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const resp = await apiFetch('/admin/state/templates/import', {
        method: 'POST',
        headers: { ...authHeaders(true) },
        body: JSON.stringify(data),
      })
      const result = await resp.json()
      if (result.status === 'ok') {
        selectedTemplateId.value = result.template_id
        message.success(t('state.messages.templateImported'))
        await fetchTemplates()
      } else {
        message.error(result.message || t('common.importFailed'))
      }
    } catch (e: any) {
      message.error(`${t('common.importFailed')}: ${e.message || e}`)
    }
  }
  input.click()
}

function triggerImportPreset() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const resp = await apiFetch('/admin/memory-mount-presets/import', {
        method: 'POST',
        headers: { ...authHeaders(true) },
        body: JSON.stringify(data),
      })
      const result = await resp.json()
      if (result.status === 'ok') {
        message.success(t('state.messages.presetImported'))
        await fetchPresets()
      } else {
        message.error(result.message || t('common.importFailed'))
      }
    } catch (e: any) {
      message.error(`${t('common.importFailed')}: ${e.message || e}`)
    }
  }
  input.click()
}

async function exportAllPresets() {
  try {
    const exported: any[] = []
    for (const preset of presets.value) {
      const resp = await apiFetch(`/admin/memory-mount-presets/${preset.preset_id}/export`, { headers: authHeaders() })
      const data = await resp.json()
      exported.push(data)
    }
    const savedPath = await saveJsonExport('mount_presets.json', exported)
    if (savedPath) message.success(t('state.messages.presetsExported', { count: exported.length }))
  } catch (e: any) {
    message.error(e.message || t('common.exportFailed'))
  }
}

function findField(fieldId: string) {
  for (const tab of currentTemplate.value?.tabs || []) {
    const field = (tab.fields || []).find((item: any) => item.field_id === fieldId)
    if (field) return field
  }
  return null
}

function categoryForField(fieldKey?: string) {
  const map: Record<string, string> = { user_addressing: 'preference', current_mood: 'mood', current_task: 'main_quest', stable_boundary: 'boundary', current_location: 'location', main_quest: 'main_quest', world_state: 'world_state' }
  return map[fieldKey || ''] || 'scene'
}

const customItemsByTab = computed(() => {
  const map: Record<string, any[]> = {}
  for (const item of stateItems.value) {
    if (!item.field_id && item.status === 'active' && item.tab_id) {
      ;(map[item.tab_id] ??= []).push(item)
    }
  }
  return map
})

function fieldRows(tab: any) {
  const rows = (tab.fields || []).map((field: any) => ({ field, item: itemByField.value[field.field_id] || null }))
  for (const item of customItemsByTab.value[tab.tab_id] || []) {
    rows.push({ field: null, item })
  }
  return rows
}

function authHeaders(json = false) {
  const headers: Record<string, string> = {}
  if (json) headers['Content-Type'] = 'application/json'
  if (adminToken.value.trim()) headers.Authorization = `Bearer ${adminToken.value.trim()}`
  return headers
}

function saveLocalInputs() {
  localStorage.setItem('kokoromemo.lastConversationId', conversationId.value)
  localStorage.setItem('kokoromemo.adminToken', adminToken.value)
}

function actionIconBtn(icon: any, tooltip: string, onClick: () => void, type: 'default' | 'primary' | 'warning' | 'error' = 'default') {
  return h(NTooltip, { trigger: 'hover' }, {
    trigger: () => h(NButton, {
      circle: true, quaternary: true, size: 'tiny', type, onClick,
    }, { icon: () => h(NIcon, null, { default: () => h(icon) }) }),
    default: () => tooltip,
  })
}

const boardColumns = [
  { title: t('state.column.field'), key: 'label', width: 160, render: (row: any) => row.field
    ? h('div', [h('div', row.field.label), h('div', { class: 'km-muted' }, row.field.field_key)])
    : h('div', [h('div', row.item?.title || row.item?.item_key || '—'), row.item?.title && row.item?.title !== row.item?.item_key ? h('div', { class: 'km-muted' }, row.item?.item_key) : null]) },
  { title: t('state.column.value'), key: 'value', ellipsis: { tooltip: true }, render: (row: any) => row.item?.item_value || row.item?.content || '—' },
  { title: t('state.column.confidence'), key: 'confidence', width: 90, render: (row: any) => row.item ? Number(row.item.confidence).toFixed(2) : '—' },
  { title: t('state.column.priority'), key: 'priority', width: 80, render: (row: any) => row.item?.priority ?? '—' },
  { title: t('state.column.linkedCards'), key: 'linked_cards', width: 120, render: (row: any) => row.item?.linked_card_ids?.length ? h(NTag, { size: 'small', type: 'info' }, { default: () => `${row.item.linked_card_ids.length}` }) : '—' },
  { title: t('state.column.source'), key: 'source', width: 120, render: (row: any) => row.item?.source || '—' },
  { title: t('state.column.updatedAt'), key: 'updated_at', width: 170, render: (row: any) => row.item?.updated_at || '—' },
  { title: t('state.column.locked'), key: 'locked', width: 80, render: (row: any) => row.item?.user_locked ? h(NTag, { size: 'small', type: 'warning' }, { default: () => t('state.column.locked') }) : '—' },
  { title: t('state.column.actions'), key: 'actions', width: 140, render: (row: any) => row.item
    ? h(NSpace, { size: 4, align: 'center', wrap: false }, { default: () => [
        actionIconBtn(CreateOutline, t('state.actions.edit'), () => openEditModal(row.item, row.field)),
        h(NPopconfirm, { positiveText: t('common.confirm'), negativeText: t('common.cancel'), onPositiveClick: () => resetItem(row.item) }, {
          trigger: () => actionIconBtn(RefreshOutline, t('state.actions.reset'), () => {}, 'warning'),
          default: () => t('state.messages.confirmReset'),
        }),
        h(NPopconfirm, { positiveText: t('common.confirm'), negativeText: t('common.cancel'), onPositiveClick: () => deleteItem(row.item) }, {
          trigger: () => actionIconBtn(TrashOutline, t('state.actions.delete'), () => {}, 'error'),
          default: () => t('state.messages.confirmDelete'),
        }),
      ] })
    : h(NButton, { size: 'tiny', dashed: true, type: 'primary', onClick: () => openCreateModal(row.field) }, {
        icon: () => h(NIcon, null, { default: () => h(AddCircleOutline) }),
        default: () => t('state.actions.fill'),
      }) },
]

const legacyColumns = [
  { title: t('state.column.category'), key: 'category', width: 110 },
  { title: t('state.column.key'), key: 'item_key', width: 160 },
  { title: t('state.column.content'), key: 'item_value', ellipsis: { tooltip: true } },
  { title: t('state.column.priority'), key: 'priority', width: 80 },
  { title: t('state.column.status'), key: 'status', width: 90, render: (row: any) => {
    const labelKey = `state.statusLabels.${row.status}`
    const translated = t(labelKey)
    const label = translated === labelKey ? row.status : translated
    return h(NTag, { size: 'small', type: row.status === 'active' ? 'success' : row.status === 'resolved' ? 'warning' : 'default' }, { default: () => label })
  } },
  { title: t('state.column.source'), key: 'source', width: 120 },
  { title: t('state.column.actions'), key: 'actions', width: 140, render: (row: any) => h(NSpace, { size: 4, align: 'center', wrap: false }, { default: () => [
    actionIconBtn(CreateOutline, t('state.actions.edit'), () => openEditModal(row)),
    h(NPopconfirm, { positiveText: t('common.confirm'), negativeText: t('common.cancel'), onPositiveClick: () => resetItem(row) }, {
      trigger: () => actionIconBtn(RefreshOutline, t('state.actions.reset'), () => {}, 'warning'),
      default: () => t('state.messages.confirmReset'),
    }),
    h(NPopconfirm, { positiveText: t('common.confirm'), negativeText: t('common.cancel'), onPositiveClick: () => deleteItem(row) }, {
      trigger: () => actionIconBtn(TrashOutline, t('state.actions.delete'), () => {}, 'error'),
      default: () => t('state.messages.confirmDelete'),
    }),
  ] }) },
]

const decisionColumns = [
  { title: t('state.column.time'), key: 'created_at', width: 170 },
  { title: t('state.column.mode'), key: 'mode', width: 90 },
  { title: t('state.column.retrieve'), key: 'should_retrieve', width: 80, render: (row: any) => row.should_retrieve ? t('common.yes') : t('common.no') },
  { title: t('state.column.reason'), key: 'reason', ellipsis: { tooltip: true } },
  { title: t('state.column.latestInput'), key: 'latest_user_text', width: 120, ellipsis: { tooltip: true } },
  { title: t('state.column.requestId'), key: 'request_id', width: 160, ellipsis: { tooltip: true } },
  { title: t('state.column.triggeredRoutes'), key: 'triggered_routes_json', width: 140, ellipsis: { tooltip: true } },
  { title: t('state.column.skippedRoutes'), key: 'skipped_routes_json', width: 140, ellipsis: { tooltip: true } },
  { title: t('state.column.stateConfidence'), key: 'state_confidence', width: 110, render: (row: any) => row.state_confidence != null ? Number(row.state_confidence).toFixed(2) : '—' },
  { title: t('state.column.actions'), key: 'actions', width: 90, render: (row: any) => h(NButton, { size: 'tiny', secondary: true, onClick: () => openGateDebugPreview(row) }, { default: () => t('state.actions.preview') }) },
]

const eventColumns = [
  { title: t('state.column.time'), key: 'created_at', width: 170 },
  { title: t('state.column.event'), key: 'event_type', width: 160 },
  { title: t('state.column.item'), key: 'item_id', width: 180 },
  { title: t('state.column.oldValue'), key: 'old_value', ellipsis: { tooltip: true } },
  { title: t('state.column.newValue'), key: 'new_value', ellipsis: { tooltip: true } },
]

onMounted(async () => {
  const saved = localStorage.getItem('kokoromemo.lastConversationId')
  const savedToken = localStorage.getItem('kokoromemo.adminToken')
  if (saved) conversationId.value = saved
  if (savedToken) adminToken.value = savedToken
  await Promise.all([fetchTemplates(), fetchMemoryLibraries(), fetchPresets(), fetchConversations()]).catch(() => {})
  if (saved) fetchAll().catch(() => {})
})
</script>

<template>
  <div>
    <div style="margin-bottom: 28px; display: flex; justify-content: space-between; align-items: flex-start;">
      <div>
        <h1 style="font-size: 24px; font-weight: 600; color: #e4e4e7; margin-bottom: 4px;">{{ $t('state.title') }}</h1>
        <p style="color: #71717a; font-size: 14px; margin: 0;">{{ $t('state.subtitle') }}</p>
      </div>
      <NButton quaternary @click="helpModal = 'overview'">
        <template #icon><NIcon><HelpCircleOutline /></NIcon></template>
        {{ $t('state.helpButton') }}
      </NButton>
    </div>

    <!-- 顶部上下文条：会话选择 + Admin Token + 只读状态行 -->
    <NCard style="background: #18181b; border: 1px solid #27272a; margin-bottom: 16px;">
      <NSpace align="center" :wrap="true" style="row-gap: 12px;">
        <NSpace :wrap="false" align="center" :size="8">
          <span style="color: #a1a1aa; font-size: 13px;">{{ $t('state.conversationId') }}</span>
          <NSelect v-model:value="conversationId" :options="conversationOptions" filterable tag :placeholder="$t('state.selectConversation')" style="width: 280px;" size="small" @blur="saveLocalInputs" />
          <NButton type="primary" size="small" @click="fetchAll">{{ $t('common.load') }}</NButton>
          <NButton size="small" @click="exportConversationConfig" :disabled="!conversationId.trim()">{{ $t('state.exportConversation') }}</NButton>
          <NButton size="small" @click="triggerConversationImport">{{ $t('state.importConversation') }}</NButton>
          <NPopconfirm :positive-text="$t('common.confirm')" :negative-text="$t('common.cancel')" @positive-click="deleteConversation">
            <template #trigger><NButton type="error" quaternary size="small" :disabled="!conversationId.trim()">{{ $t('common.delete') }}</NButton></template>
            {{ $t('state.deleteConversationConfirm') }}
          </NPopconfirm>
        </NSpace>
        <NSpace :wrap="false" align="center" :size="8">
          <span style="color: #a1a1aa; font-size: 13px;">{{ $t('state.adminToken') }}</span>
          <NInput v-model:value="adminToken" type="password" :placeholder="$t('state.adminTokenPlaceholder')" style="width: 200px;" size="small" @blur="saveLocalInputs" />
        </NSpace>
      </NSpace>
      <NDivider style="margin: 12px 0 10px;" />
      <NSpace align="center" :size="10" :wrap="true">
        <NTag v-if="isNewSession" type="warning" size="small">{{ $t('state.newSession') }}</NTag>
        <NTag v-else type="success" size="small">{{ $t('state.configured') }}</NTag>
        <span style="color: #a1a1aa; font-size: 13px;">
          {{ $t('state.templateLabel') }}<strong style="color: #e4e4e7;">{{ currentTemplate?.name || $t('state.noTemplate') }}</strong>
          <span style="color: #3f3f46; margin: 0 8px;">·</span>
          {{ $t('state.mountLabel') }}<strong style="color: #e4e4e7;">{{ mountedLibraryNames }}</strong>
          <span style="color: #3f3f46; margin: 0 8px;">·</span>
          {{ $t('state.stateItems') }}<strong style="color: #e4e4e7;">{{ stateItemCount }}</strong>
        </span>
      </NSpace>
    </NCard>

    <!-- 配置区：NCollapse 折叠 -->
    <NCollapse :default-expanded-names="isNewSession ? ['config'] : []" style="margin-bottom: 16px;">
      <NCollapseItem :title="$t('state.configCard')" name="config">
        <NCard style="background: #18181b; border: 1px solid #27272a;">
      <NForm label-placement="left" label-width="120" :show-feedback="false" style="gap: 14px; display: flex; flex-direction: column;">
        <NFormItem :label="$t('state.stateTemplate')">
          <NSpace vertical :size="6" style="width: 100%;">
          <NSpace :wrap="false">
            <NSelect v-model:value="selectedTemplateId" :options="templateOptions" :placeholder="$t('state.selectTemplate')" style="width: 260px;" />
            <NPopconfirm :positive-text="$t('common.confirm')" :negative-text="$t('common.cancel')" @positive-click="changeTemplate">
              <template #trigger><NButton :disabled="!configLoaded || !selectedTemplateId">{{ $t('state.applyTemplate') }}</NButton></template>
              {{ $t('state.applyTemplateConfirm') }}
            </NPopconfirm>
            <NDropdown :options="templateMenuOptions" @select="handleTemplateMenuAction">
              <NButton>{{ $t('state.templateMore') }}</NButton>
            </NDropdown>
          </NSpace>
          <div class="km-muted">{{ $t('state.stateTemplateHelp') }}</div>
          </NSpace>
        </NFormItem>
        <NFormItem :label="$t('state.mountLibraries')">
          <NSpace vertical :size="6" style="width: 100%;">
          <NSelect
            :value="mountedLibraryIds"
            multiple
            filterable
            :options="memoryLibraryOptions"
            :placeholder="$t('state.mountLibrariesPlaceholder')"
            @update:value="handleMountedLibrariesChange"
          />
          <div class="km-muted">{{ $t('state.mountLibrariesHelp') }}</div>
          </NSpace>
        </NFormItem>
        <NFormItem :label="$t('state.writeTarget')">
          <NSpace vertical :size="6">
          <NSelect v-model:value="writeLibraryId" :options="memoryLibraryOptions.filter((item) => mountedLibraryIds.includes(item.value))" :placeholder="$t('state.writeTargetPlaceholder')" style="width: 260px;" />
          <div class="km-muted">{{ $t('state.writeTargetHelp') }}</div>
          </NSpace>
        </NFormItem>
        <NFormItem :label="$t('state.mountPresets')">
          <NSpace vertical :size="6" style="width: 100%;">
          <NSpace :wrap="false" style="width: 100%;">
            <NSelect v-model:value="selectedPresetId" :options="presetOptions" :placeholder="$t('state.presetPlaceholder')" style="flex: 1; min-width: 200px;" @update:value="applyPresetById" />
            <NButton size="small" @click="saveAsPreset" :disabled="!mountedLibraryIds.length">{{ $t('state.saveAsPreset') }}</NButton>
            <NButton size="small" @click="exportSinglePreset(selectedPresetId!)" :disabled="!selectedPresetId">{{ $t('common.export') }}</NButton>
            <NButton size="small" type="error" quaternary @click="deletePreset(selectedPresetId!)" :disabled="!selectedPresetId">{{ $t('common.delete') }}</NButton>
            <NDropdown :options="presetManageOptions" @select="handlePresetManageAction">
              <NButton size="small">{{ $t('state.managePresets') }}</NButton>
            </NDropdown>
          </NSpace>
          <div class="km-muted">{{ $t('state.mountPresetsHelp') }}</div>
          </NSpace>
        </NFormItem>
      </NForm>
      <NDivider style="margin: 14px 0;" />
      <NSpace align="center" justify="space-between" :wrap="true" style="width: 100%;">
        <NSpace align="center" :wrap="true">
          <NButton type="primary" @click="saveFullConfig" :disabled="!conversationId.trim()">{{ $t('state.saveConfig') }}</NButton>
          <NButton @click="showFillModal = true" :disabled="!configLoaded">{{ $t('state.manualFill') }}</NButton>
          <NButton @click="rebuildFromCards" :disabled="!configLoaded">{{ $t('state.projectFromMemory') }}</NButton>
          <NButton quaternary size="tiny" @click="helpModal = 'config'" style="padding: 0 6px;">
            <template #icon><NIcon><HelpCircleOutline /></NIcon></template>
          </NButton>
        </NSpace>
        <NDropdown :options="dangerActionOptions" @select="handleDangerAction" trigger="click">
          <NButton :disabled="!stateItemCount">
            {{ $t('state.moreActions') }}
            <template #icon><NIcon><EllipsisHorizontal /></NIcon></template>
          </NButton>
        </NDropdown>
      </NSpace>
        </NCard>
      </NCollapseItem>
    </NCollapse>

    <!-- 新会话初始化提示 -->
    <NCard v-if="configLoaded && isNewSession" style="background: rgba(167, 139, 250, 0.08); border: 1px solid #a78bfa; margin-bottom: 16px;">
      <NSpace align="center" justify="space-between">
        <div>
          <div style="color: #e4e4e7; font-weight: 600; margin-bottom: 4px;">{{ $t('state.isNewSession') }}</div>
          <div style="color: #a1a1aa; font-size: 13px;">{{ $t('state.newSessionHint') }}</div>
        </div>
        <NSpace>
          <NButton type="primary" @click="openInitWizard">{{ $t('state.initWizard') }}</NButton>
          <NButton @click="saveFullConfig">{{ $t('state.useCurrentConfig') }}</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NSpin :show="loading">
      <NTabs type="line" animated>
        <NTabPane name="board" :tab="$t('state.tabs.board')">
          <div v-if="currentTemplate">
            <NTabs type="card" animated addable @add="onAddTabClick">
              <NTabPane v-for="tab in currentTemplate.tabs" :key="tab.tab_id" :name="tab.tab_id">
                <template #tab>
                  <NSpace :size="6" align="center" :wrap="false">
                    <span>{{ tab.label }}</span>
                    <NDropdown :options="tabActionOptions(tab)" @select="(key: string) => handleTabAction(key, tab)" trigger="click" size="small">
                      <NButton text size="tiny" @click.stop>
                        <template #icon><NIcon><EllipsisHorizontal /></NIcon></template>
                      </NButton>
                    </NDropdown>
                  </NSpace>
                </template>
                <div style="padding: 4px 2px 0;">
                  <p v-if="tab.description" style="color: #71717a; margin: 0 0 12px;">{{ tab.description }}</p>
                  <NDataTable :columns="boardColumns" :data="fieldRows(tab)" :pagination="false" />
                  <div style="margin-top: 12px;">
                    <NButton dashed size="small" @click="openCreateModalForTab(tab)">
                      <template #icon><NIcon><AddOutline /></NIcon></template>
                      {{ $t('state.actions.addNew') }}
                    </NButton>
                  </div>
                </div>
              </NTabPane>
            </NTabs>
          </div>
          <NCollapse v-if="legacyItems.length" style="margin-top: 16px;">
            <NCollapseItem :title="`${$t('state.legacyItems')} (${legacyItems.length})`" name="legacy">
              <NDataTable :columns="legacyColumns" :data="legacyItems" :pagination="{ pageSize: 8 }" />
            </NCollapseItem>
          </NCollapse>
        </NTabPane>
        <NTabPane name="gate" :tab="$t('state.tabs.gate')"><NDataTable :columns="decisionColumns" :data="scopedDecisions" :pagination="{ pageSize: 12 }" /></NTabPane>
        <NTabPane name="events" :tab="$t('state.tabs.events')"><NDataTable :columns="eventColumns" :data="scopedEvents" :pagination="{ pageSize: 12 }" /></NTabPane>
        <NTabPane name="preview" :tab="$t('state.tabs.preview')">
          <NCard style="background: #18181b; border: 1px solid #27272a;">
            <template #header>
              <NSpace align="center" justify="space-between" style="width: 100%;">
                <span>{{ $t('state.previewTitle') }}</span>
                <NSpace align="center">
                  <NTag :type="previewData.char_count > previewData.max_chars * 0.9 ? 'warning' : 'success'" size="small">
                    {{ previewData.char_count }} / {{ previewData.max_chars }} chars
                  </NTag>
                  <NButton size="small" @click="fetchPreview" :loading="previewLoading">{{ $t('common.load') }}</NButton>
                </NSpace>
              </NSpace>
            </template>
            <div v-if="!previewData.preview && !previewLoading" style="color: #71717a; text-align: center; padding: 32px;">
              {{ $t('state.previewEmpty') }}
            </div>
            <pre v-else style="white-space: pre-wrap; word-break: break-word; font-size: 13px; line-height: 1.6; color: #e4e4e7; background: #09090b; padding: 16px; border-radius: 6px; max-height: 600px; overflow-y: auto; margin: 0;">{{ previewData.preview }}</pre>
          </NCard>
        </NTabPane>
      </NTabs>
    </NSpin>

    <!-- 编辑状态项 Modal -->
    <NModal v-model:show="showEditModal" preset="card" :title="isCustomField && !editForm.field_id ? $t('state.addStateItem') : $t('state.editStateItem')" style="width: 620px; background: #18181b;">
      <NForm label-placement="top">
        <NFormItem v-if="isCustomField && !editForm.field_id" :label="$t('state.fieldName')"><NInput v-model:value="customFieldName" :placeholder="$t('state.fieldNamePlaceholder')" /></NFormItem>
        <NFormItem v-if="isCustomField && !editForm.field_id" :label="$t('state.fieldKey')"><NInput v-model:value="customItemKey" :placeholder="$t('state.fieldKeyPlaceholder')" /></NFormItem>
        <NFormItem v-else :label="$t('state.fieldLabel')"><NSelect v-model:value="editForm.field_id" :options="fieldOptions" filterable /></NFormItem>
        <NFormItem :label="$t('state.content')"><NInput v-model:value="editForm.item_value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" /></NFormItem>
        <NGrid :cols="3" :x-gap="12">
          <NGridItem><NFormItem :label="$t('state.priority')"><NInputNumber v-model:value="editForm.priority" :min="0" :max="100" style="width: 100%;" /></NFormItem></NGridItem>
          <NGridItem><NFormItem :label="$t('state.confidence')"><NInputNumber v-model:value="editForm.confidence" :min="0" :max="1" :step="0.05" style="width: 100%;" /></NFormItem></NGridItem>
          <NGridItem><NFormItem :label="$t('state.locked')"><NSwitch v-model:value="editForm.user_locked" /></NFormItem></NGridItem>
        </NGrid>
        <NFormItem :label="$t('state.actions.linkCards')"><NInput v-model:value="editForm.linked_card_ids" placeholder="card_id1, card_id2" /></NFormItem>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showEditModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" @click="saveItem">{{ $t('common.save') }}</NButton></NSpace></template>
    </NModal>

    <!-- 新建模板 Modal -->
    <NModal v-model:show="showTemplateModal" preset="card" :title="$t('state.createTemplateTitle')" style="width: 760px; background: #18181b;">
      <NInput v-model:value="templateJson" type="textarea" :autosize="{ minRows: 18, maxRows: 28 }" />
      <template #footer><NSpace justify="end"><NButton @click="showTemplateModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" @click="saveTemplate">{{ $t('state.saveTemplate') }}</NButton></NSpace></template>
    </NModal>

    <!-- AI 填表 Modal -->
    <NModal v-model:show="showFillModal" preset="card" :title="$t('state.fillTitle')" style="width: 680px; background: #18181b;">
      <NForm label-placement="top">
        <NFormItem :label="$t('state.userMessage')"><NInput v-model:value="fillForm.user_message" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" /></NFormItem>
        <NFormItem :label="$t('state.assistantMessage')"><NInput v-model:value="fillForm.assistant_message" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" /></NFormItem>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showFillModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" @click="runStateFiller">{{ $t('state.run') }}</NButton></NSpace></template>
    </NModal>

    <!-- Gate 调试预览 Modal -->
    <NModal v-model:show="showGateDebugPreview" preset="card" :title="gateDebugPreviewTitle" style="width: min(920px, 92vw); background: #18181b;">
      <pre class="gate-debug-preview">{{ gateDebugPreviewContent }}</pre>
      <template #footer><NSpace justify="end"><NButton @click="showGateDebugPreview = false">{{ $t('common.close') }}</NButton></NSpace></template>
    </NModal>

    <!-- 保存挂载预设 Modal -->
    <NModal v-model:show="showPresetModal" preset="card" :title="$t('state.savePresetTitle')" style="width: 480px; background: #18181b;">
      <NForm label-placement="top">
        <NFormItem :label="$t('state.presetName')"><NInput v-model:value="presetForm.name" :placeholder="$t('state.presetNamePlaceholder')" /></NFormItem>
        <NFormItem :label="$t('state.descriptionOptional')"><NInput v-model:value="presetForm.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" /></NFormItem>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showPresetModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" @click="confirmSavePreset">{{ $t('common.save') }}</NButton></NSpace></template>
    </NModal>

    <!-- 新会话初始化向导 Modal -->
    <NModal v-model:show="showInitWizard" preset="card" :title="$t('state.initWizardTitle')" style="width: 560px; background: #18181b;">
      <div style="color: #a1a1aa; font-size: 13px; margin-bottom: 16px;">
        <i18n-t keypath="state.initWizardDesc" tag="span">
          <template #id><strong style="color: #e4e4e7;">{{ conversationId }}</strong></template>
        </i18n-t>
      </div>
      <NForm label-placement="top">
        <NFormItem :label="$t('state.mountLibrariesLabel')">
          <NSelect
            :value="wizardForm.library_ids"
            multiple
            filterable
            :options="memoryLibraryOptions"
            :placeholder="$t('state.selectMountLibraries')"
            @update:value="handleWizardLibrariesChange"
          />
        </NFormItem>
        <NFormItem :label="$t('state.writeTargetLibLabel')">
          <NSelect
            v-model:value="wizardForm.write_library_id"
            :options="memoryLibraryOptions.filter((item) => wizardForm.library_ids.includes(item.value))"
            :placeholder="$t('state.writeTargetLibPlaceholder')"
          />
        </NFormItem>
        <NFormItem :label="$t('state.templateLabel2')">
          <NSelect v-model:value="wizardForm.template_id" :options="templateOptions" :placeholder="$t('state.selectStateTemplate')" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showInitWizard = false">{{ $t('common.cancel') }}</NButton>
          <NButton type="primary" @click="confirmInitWizard">{{ $t('state.initSession') }}</NButton>
        </NSpace>
      </template>
    </NModal>

    <!-- 复制到新会话 Modal -->
    <NModal v-model:show="showCopyModal" preset="card" :title="$t('state.copyTitle')" style="width: 480px; background: #18181b;">
      <NForm label-placement="top">
        <NFormItem :label="$t('state.targetConversationId')"><NSelect v-model:value="copyForm.target_conversation_id" :options="conversationOptions" filterable tag :placeholder="$t('state.inputNewId')" /></NFormItem>
        <NFormItem :label="$t('state.copyMounts')"><NSwitch v-model:value="copyForm.copy_mounts" /></NFormItem>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showCopyModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" @click="confirmCopy">{{ $t('state.copy') }}</NButton></NSpace></template>
    </NModal>

    <!-- 添加标签页 Modal -->
    <!-- ?????? Modal -->
    <NModal v-model:show="showConversationImportModal" preset="card" :title="$t('state.importConversationTitle')" style="width: 560px; background: #18181b;">
      <NForm label-placement="top">
        <NFormItem :label="$t('state.targetConversationId')"><NSelect v-model:value="importForm.target_conversation_id" :options="conversationOptions" filterable tag :placeholder="$t('state.inputNewId')" /></NFormItem>
        <NFormItem :label="$t('state.importTemplateSnapshot')"><NSwitch v-model:value="importForm.import_template_snapshot" /></NFormItem>
        <NFormItem :label="$t('state.overwriteState')"><NSwitch v-model:value="importForm.overwrite_state" /></NFormItem>
        <div class="km-muted">{{ $t('state.importConversationHelp') }}</div>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showConversationImportModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" @click="confirmConversationImport">{{ $t('common.import') }}</NButton></NSpace></template>
    </NModal>

    <NModal v-model:show="showAddTabModal" preset="card" :title="$t('state.addTab')" style="width: 400px; background: #18181b;">
      <NForm label-placement="top">
        <NFormItem :label="$t('state.tabLabel')"><NInput v-model:value="newTabLabel" :placeholder="$t('state.tabLabelPlaceholder')" @keyup.enter="addTab" /></NFormItem>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showAddTabModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" @click="addTab">{{ $t('common.confirm') }}</NButton></NSpace></template>
    </NModal>

    <!-- 重命名标签页 Modal -->
    <NModal v-model:show="showRenameTabModal" preset="card" :title="$t('state.renameTab')" style="width: 400px; background: #18181b;">
      <NForm label-placement="top">
        <NFormItem :label="$t('state.tabLabel')"><NInput v-model:value="renameTabLabel" :placeholder="$t('state.tabLabelPlaceholder')" @keyup.enter="renameTab" /></NFormItem>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showRenameTabModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" @click="renameTab">{{ $t('common.confirm') }}</NButton></NSpace></template>
    </NModal>

    <!-- 帮助弹窗 -->
    <NModal :show="!!helpModal" preset="card" :title="$t('state.helpTitle')" style="width: 640px; background: #18181b;" :mask-closable="true" @update:show="(v: boolean) => { if (!v) helpModal = '' }">
      <div v-if="helpModal === 'overview'" class="help-content">
        <p>{{ $t('state.help.overview.intro') }}</p>
        <p><strong>{{ $t('state.help.overview.contextTitle') }}</strong>: {{ $t('state.help.overview.contextDesc') }}</p>
        <p><strong>{{ $t('state.help.overview.configTitle') }}</strong>: {{ $t('state.help.overview.configDesc') }}</p>
        <p><strong>{{ $t('state.help.overview.boardTitle') }}</strong>: {{ $t('state.help.overview.boardDesc') }}</p>
        <p><strong>{{ $t('state.help.overview.tabsTitle') }}</strong>: {{ $t('state.help.overview.tabsDesc') }}</p>
      </div>
      <div v-else-if="helpModal === 'config'" class="help-content">
        <p><strong>{{ $t('state.stateTemplate') }}</strong>: {{ $t('state.help.config.template') }}</p>
        <p><strong>{{ $t('state.mountLibraries') }}</strong>: {{ $t('state.help.config.mount') }}</p>
        <p><strong>{{ $t('state.writeTarget') }}</strong>: {{ $t('state.help.config.write') }}</p>
        <p><strong>{{ $t('state.mountPresets') }}</strong>: {{ $t('state.help.config.preset') }}</p>
        <p><strong>{{ $t('state.exportConversation') }} / {{ $t('state.importConversation') }}</strong>: {{ $t('state.help.config.importExport') }}</p>
        <p><strong>{{ $t('state.deleteTemplate') }}</strong>: {{ $t('state.help.config.templateDelete') }}</p>
        <p><strong>{{ $t('state.manualFill') }}</strong>: {{ $t('state.help.config.fill') }}</p>
        <p><strong>{{ $t('state.projectFromMemory') }}</strong>: {{ $t('state.help.config.project') }}</p>
        <p><strong>{{ $t('state.moreActions') }}</strong>: {{ $t('state.help.config.danger') }}</p>
      </div>
    </NModal>
  </div>
</template>

<style scoped>
.km-muted {
  color: #71717a;
  font-size: 12px;
  margin-top: 2px;
}
.help-icon {
  display: none;
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
.gate-debug-preview {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.6;
  color: #e4e4e7;
  background: #09090b;
  padding: 16px;
  border-radius: 6px;
  max-height: 70vh;
  overflow-y: auto;
  margin: 0;
}
.preset-delete {
  color: #71717a;
  font-size: 11px;
  margin-left: 4px;
  cursor: pointer;
}
.preset-delete:hover {
  color: #ef4444;
}
</style>
