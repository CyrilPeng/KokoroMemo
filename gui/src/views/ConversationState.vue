<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import {
  NButton,
  NCard,
  NDataTable,
  NDivider,
  NDropdown,
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
  NSwitch,
  NTabPane,
  NTabs,
  NTag,
  NTooltip,
  useMessage,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { apiFetch } from '../api'

const { t } = useI18n()
const message = useMessage()
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
const editForm = ref({ field_id: '', item_value: '', priority: 70, confidence: 0.8, user_locked: false, linked_card_ids: '' })
const templateJson = ref('')
const fillForm = ref({ user_message: '', assistant_message: '' })
const configLoaded = ref(false)
const stateItemCount = ref(0)
const isNewSession = ref(false)
const presets = ref<any[]>([])
const showPresetModal = ref(false)
const presetForm = ref({ name: '', description: '' })
const showCopyModal = ref(false)
const copyForm = ref({ target_conversation_id: '', copy_mounts: true })
const showInitWizard = ref(false)
const wizardForm = ref({ library_ids: ['lib_default'] as string[], write_library_id: 'lib_default', template_id: 'tpl_roleplay_general' })

const templateOptions = computed(() => templates.value.map((item) => ({ label: `${item.name}${item.is_builtin ? `(${t('common.builtin')})` : ''}`, value: item.template_id })))
const memoryLibraryOptions = computed(() => memoryLibraries.value.map((item) => ({ label: `${item.name}${item.card_count ? `（${item.card_count}）` : ''}`, value: item.library_id })))
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
const legacyItems = computed(() => stateItems.value.filter((item) => !item.field_id))

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

async function fetchConfig() {
  if (!conversationId.value.trim()) return
  const resp = await apiFetch(`/admin/conversations/${conversationId.value}/config`, { headers: authHeaders() })
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
  loading.value = true
  try {
    await Promise.all([fetchTemplates(), fetchMemoryLibraries(), fetchPresets()])
    const [templateResp, stateResp, decisionResp, eventResp] = await Promise.all([
      apiFetch(`/admin/conversations/${conversationId.value}/state/template`, { headers: authHeaders() }),
      apiFetch(`/admin/conversations/${conversationId.value}/state?limit=500`, { headers: authHeaders() }),
      apiFetch(`/admin/conversations/${conversationId.value}/retrieval-decisions?limit=100`, { headers: authHeaders() }),
      apiFetch(`/admin/conversations/${conversationId.value}/state/events?limit=100`, { headers: authHeaders() }),
    ])
    currentTemplate.value = await templateResp.json()
    selectedTemplateId.value = currentTemplate.value?.template_id || ''
    stateItems.value = (await stateResp.json()).items || []
    decisions.value = (await decisionResp.json()).items || []
    events.value = (await eventResp.json()).items || []
    stateItemCount.value = stateItems.value.filter((item) => item.status === 'active').length
    await fetchConfig()
    saveLocalInputs()
  } catch (e: any) {
    message.error(t('state.messages.loadFailed', { error: e.message || e }))
  }
  loading.value = false
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

function openCreateModal(field?: any) {
  editingItem.value = null
  editForm.value = { field_id: field?.field_id || '', item_value: '', priority: 70, confidence: 0.8, user_locked: false, linked_card_ids: '' }
  showEditModal.value = true
}

function openEditModal(row: any, field?: any) {
  editingItem.value = row
  editForm.value = {
    field_id: row.field_id || field?.field_id || '',
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
  const body = JSON.stringify({
    template_id: currentTemplate.value?.template_id,
    tab_id: field?.tab_id,
    field_id: field?.field_id,
    field_key: field?.field_key,
    category: categoryForField(field?.field_key),
    item_key: field?.field_key,
    title: field?.label,
    item_value: editForm.value.item_value,
    priority: editForm.value.priority,
    confidence: editForm.value.confidence,
    user_locked: editForm.value.user_locked,
    linked_card_ids: editForm.value.linked_card_ids
      ? editForm.value.linked_card_ids.split(',').map((s: string) => s.trim()).filter(Boolean)
      : [],
  })
  const url = editingItem.value ? `/admin/state/${editingItem.value.item_id}` : `/admin/conversations/${conversationId.value}/state`
  const method = editingItem.value ? 'PATCH' : 'POST'
  try {
    const resp = await apiFetch(url, { method, headers: authHeaders(true), body })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || t('common.saveFailed'))
    showEditModal.value = false
    message.success(t('state.messages.stateItemSaved'))
    fetchAll()
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

async function resolveItem(row: any) {
  await apiFetch(`/admin/state/${row.item_id}/resolve`, { method: 'POST', headers: authHeaders(true), body: JSON.stringify({ reason: t('state.messages.done') }) })
  message.success(t('state.messages.markedDone'))
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
  const resp = await apiFetch(`/admin/memory-mount-presets/${presetId}`, { method: 'DELETE', headers: authHeaders() })
  const data = await resp.json()
  if (data.status === 'ok') {
    message.success(t('state.messages.presetDeleted'))
    await fetchPresets()
  }
}

function handlePresetAction(key: string, preset: any) {
  if (key === 'apply') {
    applyPreset(preset)
  } else if (key === 'export') {
    exportSinglePreset(preset.preset_id)
  } else if (key === 'delete') {
    deletePreset(preset.preset_id)
  }
}

async function exportSinglePreset(presetId: string) {
  try {
    const resp = await apiFetch(`/admin/memory-mount-presets/${presetId}/export`, { headers: authHeaders() })
    const data = await resp.json()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `mount_preset_${presetId}.json`
    a.click()
    URL.revokeObjectURL(url)
    message.success(t('state.messages.presetExported'))
  } catch (e: any) {
    message.error(e.message || t('common.exportFailed'))
  }
}

async function exportTemplate() {
  if (!selectedTemplateId.value) return
  try {
    const resp = await apiFetch(`/admin/state/templates/${selectedTemplateId.value}/export`, { headers: authHeaders() })
    const data = await resp.json()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `template_${selectedTemplateId.value}.json`
    a.click()
    URL.revokeObjectURL(url)
    message.success(t('state.messages.templateExported'))
  } catch (e: any) {
    message.error(e.message || t('common.exportFailed'))
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
    const blob = new Blob([JSON.stringify(exported, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'mount_presets.json'
    a.click()
    URL.revokeObjectURL(url)
    message.success(t('state.messages.presetsExported', { count: exported.length }))
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

function fieldRows(tab: any) {
  return (tab.fields || []).map((field: any) => ({ field, item: itemByField.value[field.field_id] || null }))
}

function hButton(label: string, onClick: () => void) {
  return h('button', { class: 'km-link-button', onClick }, label)
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

const boardColumns = [
  { title: t('state.column.field'), key: 'label', width: 160, render: (row: any) => h('div', [h('div', row.field.label), h('div', { class: 'km-muted' }, row.field.field_key)]) },
  { title: t('state.column.value'), key: 'value', ellipsis: { tooltip: true }, render: (row: any) => row.item?.item_value || row.item?.content || row.field.default_value || '—' },
  { title: t('state.column.confidence'), key: 'confidence', width: 90, render: (row: any) => row.item ? Number(row.item.confidence).toFixed(2) : '—' },
  { title: t('state.column.priority'), key: 'priority', width: 80, render: (row: any) => row.item?.priority ?? '—' },
  { title: t('state.column.linkedCards'), key: 'linked_cards', width: 120, render: (row: any) => row.item?.linked_card_ids?.length ? h(NTag, { size: 'small', type: 'info' }, { default: () => `${row.item.linked_card_ids.length}` }) : '—' },
  { title: t('state.column.source'), key: 'source', width: 120, render: (row: any) => row.item?.source || '—' },
  { title: t('state.column.updatedAt'), key: 'updated_at', width: 170, render: (row: any) => row.item?.updated_at || '—' },
  { title: t('state.column.locked'), key: 'locked', width: 80, render: (row: any) => row.item?.user_locked ? h(NTag, { size: 'small', type: 'warning' }, { default: () => t('state.column.locked') }) : '—' },
  { title: t('state.column.actions'), key: 'actions', width: 180, render: (row: any) => row.item ? [hButton(t('state.actions.edit'), () => openEditModal(row.item, row.field)), hButton(t('state.actions.done'), () => resolveItem(row.item)), hButton(t('state.actions.delete'), () => deleteItem(row.item))] : hButton(t('state.actions.fill'), () => openCreateModal(row.field)) },
]

const legacyColumns = [
  { title: t('state.column.category'), key: 'category', width: 110 },
  { title: t('state.column.key'), key: 'item_key', width: 160 },
  { title: t('state.column.content'), key: 'item_value', ellipsis: { tooltip: true } },
  { title: t('state.column.priority'), key: 'priority', width: 80 },
  { title: t('state.column.status'), key: 'status', width: 90, render: (row: any) => h(NTag, { size: 'small', type: row.status === 'active' ? 'success' : row.status === 'resolved' ? 'warning' : 'default' }, { default: () => row.status }) },
  { title: t('state.column.source'), key: 'source', width: 120 },
  { title: t('state.column.actions'), key: 'actions', width: 180, render: (row: any) => [hButton(t('state.actions.edit'), () => openEditModal(row)), hButton(t('state.actions.done'), () => resolveItem(row)), hButton(t('state.actions.delete'), () => deleteItem(row))] },
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
]

const eventColumns = [
  { title: t('state.column.time'), key: 'created_at', width: 170 },
  { title: t('state.column.event'), key: 'event_type', width: 160 },
  { title: t('state.column.item'), key: 'item_id', width: 180 },
  { title: t('state.column.oldValue'), key: 'old_value', ellipsis: { tooltip: true } },
  { title: t('state.column.newValue'), key: 'new_value', ellipsis: { tooltip: true } },
]

onMounted(() => {
  const saved = localStorage.getItem('kokoromemo.lastConversationId')
  const savedToken = localStorage.getItem('kokoromemo.adminToken')
  if (saved) conversationId.value = saved
  if (savedToken) adminToken.value = savedToken
  Promise.all([fetchTemplates(), fetchMemoryLibraries(), fetchPresets()]).catch(() => {})
})
</script>

<template>
  <div>
    <div style="margin-bottom: 28px;">
      <h1 style="font-size: 24px; font-weight: 600; color: #e4e4e7; margin-bottom: 4px;">{{ $t('state.title') }}</h1>
      <p style="color: #71717a; font-size: 14px;">{{ $t('state.subtitle') }}</p>
    </div>

    <!-- 会话配置面板 -->
    <NCard :title="$t('state.configCard')" style="background: #18181b; border: 1px solid #27272a; margin-bottom: 16px;">
      <NGrid :cols="4" :x-gap="12" :y-gap="12" responsive="screen" item-responsive>
        <NGridItem span="4 m:2">
          <NFormItem :label="$t('state.conversationId')" label-placement="top" style="margin-bottom: 0;">
            <NSpace :wrap="false">
              <NInput v-model:value="conversationId" :placeholder="$t('state.inputConversationId')" style="width: 280px;" @blur="saveLocalInputs" />
              <NButton type="primary" @click="fetchAll">{{ $t('common.load') }}</NButton>
            </NSpace>
          </NFormItem>
        </NGridItem>
        <NGridItem span="4 m:2">
          <NFormItem :label="$t('state.adminToken')" label-placement="top" style="margin-bottom: 0;">
            <NInput v-model:value="adminToken" type="password" :placeholder="$t('state.adminTokenPlaceholder')" style="width: 220px;" @blur="saveLocalInputs" />
          </NFormItem>
        </NGridItem>

        <NGridItem span="4 m:2">
          <NFormItem :label="$t('state.stateTemplate')" label-placement="top" style="margin-bottom: 0;">
            <NSpace :wrap="false">
              <NSelect v-model:value="selectedTemplateId" :options="templateOptions" :placeholder="$t('state.selectTemplate')" style="width: 260px;" />
              <NButton @click="changeTemplate" :disabled="!configLoaded">{{ $t('state.switch') }}</NButton>
              <NButton @click="openTemplateModal">{{ $t('state.create') }}</NButton>
              <NButton @click="exportTemplate" :disabled="!selectedTemplateId">{{ $t('common.export') }}</NButton>
              <NButton @click="triggerImportTemplate">{{ $t('common.import') }}</NButton>
            </NSpace>
          </NFormItem>
        </NGridItem>
        <NGridItem span="4 m:2">
          <NFormItem :label="$t('state.writeTarget')" label-placement="top" style="margin-bottom: 0;">
            <NSelect v-model:value="writeLibraryId" :options="memoryLibraryOptions.filter((item) => mountedLibraryIds.includes(item.value))" :placeholder="$t('state.writeTargetPlaceholder')" style="width: 220px;" />
          </NFormItem>
        </NGridItem>

        <NGridItem span="4">
          <NFormItem :label="$t('state.mountLibraries')" label-placement="top" style="margin-bottom: 0;">
            <NSelect
              :value="mountedLibraryIds"
              multiple
              filterable
              :options="memoryLibraryOptions"
              :placeholder="$t('state.mountLibrariesPlaceholder')"
              @update:value="handleMountedLibrariesChange"
            />
          </NFormItem>
        </NGridItem>

        <NGridItem span="4">
          <NFormItem :label="$t('state.mountPresets')" label-placement="top" style="margin-bottom: 0;">
            <NSpace align="center" :wrap="true">
              <NDropdown
                v-for="preset in presets"
                :key="preset.preset_id"
                trigger="click"
                :options="[
                  { label: t('state.presetActions.apply'), key: 'apply' },
                  { label: t('state.presetActions.export'), key: 'export' },
                  { type: 'divider', key: 'd1' },
                  { label: t('state.presetActions.delete'), key: 'delete' },
                ]"
                @select="(key: string) => handlePresetAction(key, preset)"
              >
                <NButton size="small" quaternary type="info">{{ preset.name }}</NButton>
              </NDropdown>
              <NButton size="small" dashed @click="saveAsPreset" :disabled="!mountedLibraryIds.length">{{ $t('state.saveAsPreset') }}</NButton>
              <NButton size="small" dashed @click="triggerImportPreset">{{ $t('state.importPreset') }}</NButton>
              <NButton size="small" dashed @click="exportAllPresets" :disabled="!presets.length">{{ $t('state.exportAllPresets') }}</NButton>
            </NSpace>
          </NFormItem>
        </NGridItem>
      </NGrid>

      <!-- 会话状态摘要 -->
      <NDivider style="margin: 12px 0;" />
      <NSpace align="center" justify="space-between" :wrap="true">
        <NSpace align="center" :wrap="true">
          <NTag v-if="isNewSession" type="warning" size="small">{{ $t('state.newSession') }}</NTag>
          <NTag v-else type="success" size="small">{{ $t('state.configured') }}</NTag>
          <span style="color: #a1a1aa; font-size: 13px;">
            {{ $t('state.templateLabel') }}<strong style="color: #e4e4e7;">{{ currentTemplate?.name || $t('state.noTemplate') }}</strong>
            &nbsp;|&nbsp;
            {{ $t('state.mountLabel') }}<strong style="color: #e4e4e7;">{{ mountedLibraryNames }}</strong>
            &nbsp;|&nbsp;
            {{ $t('state.stateItems') }}<strong style="color: #e4e4e7;">{{ stateItemCount }}</strong>
          </span>
        </NSpace>
        <NSpace>
          <NButton type="primary" @click="saveFullConfig" :disabled="!conversationId.trim()">{{ $t('state.saveConfig') }}</NButton>
          <NButton @click="openCopyModal" :disabled="!stateItemCount">{{ $t('state.copyToNew') }}</NButton>
          <NPopconfirm @positive-click="resetState">
            <template #trigger><NButton :disabled="!stateItemCount">{{ $t('state.resetToEmpty') }}</NButton></template>
            {{ $t('state.resetConfirm') }}
          </NPopconfirm>
          <NPopconfirm @positive-click="clearState">
            <template #trigger><NButton :disabled="!stateItemCount">{{ $t('state.clearState') }}</NButton></template>
            {{ $t('state.clearConfirm') }}
          </NPopconfirm>
        </NSpace>
      </NSpace>
    </NCard>

    <!-- 操作按钮栏 -->
    <NCard style="background: #18181b; border: 1px solid #27272a; margin-bottom: 16px;">
      <NSpace align="center" :wrap="true">
        <NButton @click="showFillModal = true" :disabled="!configLoaded">{{ $t('state.manualFill') }}</NButton>
        <NButton @click="rebuildFromCards" :disabled="!configLoaded">{{ $t('state.projectFromMemory') }}</NButton>
        <NTooltip trigger="hover">
          <template #trigger><span class="help-icon">?</span></template>
          {{ $t('state.fillHelp') }}
        </NTooltip>
      </NSpace>
    </NCard>

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
          <NTabs v-if="currentTemplate" type="card" animated>
            <NTabPane v-for="tab in currentTemplate.tabs" :key="tab.tab_id" :name="tab.tab_id" :tab="tab.label">
              <NCard style="background: #18181b; border: 1px solid #27272a; margin-bottom: 12px;">
                <template #header>
                  <NSpace align="center"><span>{{ tab.label }}</span><NTag size="small">{{ $t('state.fieldCount', { count: tab.fields?.length || 0 }) }}</NTag></NSpace>
                </template>
                <p style="color: #71717a; margin-top: 0;">{{ tab.description || $t('state.noDescription') }}</p>
                <NDataTable :columns="boardColumns" :data="fieldRows(tab)" :pagination="false" />
              </NCard>
            </NTabPane>
          </NTabs>
          <NCard v-if="legacyItems.length" :title="$t('state.legacyItems')" style="background: #18181b; border: 1px solid #27272a; margin-top: 16px;">
            <NDataTable :columns="legacyColumns" :data="legacyItems" :pagination="{ pageSize: 8 }" />
          </NCard>
        </NTabPane>
        <NTabPane name="gate" :tab="$t('state.tabs.gate')"><NDataTable :columns="decisionColumns" :data="decisions" :pagination="{ pageSize: 12 }" /></NTabPane>
        <NTabPane name="events" :tab="$t('state.tabs.events')"><NDataTable :columns="eventColumns" :data="events" :pagination="{ pageSize: 12 }" /></NTabPane>
      </NTabs>
    </NSpin>

    <!-- 编辑状态项 Modal -->
    <NModal v-model:show="showEditModal" preset="card" :title="$t('state.editStateItem')" style="width: 620px; background: #18181b;">
      <NForm label-placement="top">
        <NFormItem :label="$t('state.fieldLabel')"><NSelect v-model:value="editForm.field_id" :options="fieldOptions" filterable /></NFormItem>
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
        <NFormItem :label="$t('state.targetConversationId')"><NInput v-model:value="copyForm.target_conversation_id" :placeholder="$t('state.inputNewId')" /></NFormItem>
        <NFormItem :label="$t('state.copyMounts')"><NSwitch v-model:value="copyForm.copy_mounts" /></NFormItem>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showCopyModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" @click="confirmCopy">{{ $t('state.copy') }}</NButton></NSpace></template>
    </NModal>
  </div>
</template>

<style scoped>
.km-link-button {
  margin-right: 8px;
  border: none;
  background: transparent;
  color: #a78bfa;
  cursor: pointer;
}
.km-muted {
  color: #71717a;
  font-size: 12px;
  margin-top: 2px;
}
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
