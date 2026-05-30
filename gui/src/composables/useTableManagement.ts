import { ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { apiFetch, friendlyError } from '../api'
import type { StateTable, ConversationConfig } from '../components/state/types'

export function useTableManagement(options: {
  template: Ref<any>
  config: Ref<ConversationConfig | null>
  adminToken: Ref<string>
  saving: Ref<boolean>
  activeTableKey: Ref<string>
  mountedLibraryIds: Ref<string[]>
  writeLibraryId: Ref<string | null>
  fetchOptions: () => Promise<void>
  saveConfig: () => Promise<void>
  fetchBoard: () => Promise<void>
}) {
  const { template, config, adminToken, saving, activeTableKey, mountedLibraryIds, writeLibraryId } = options
  const { fetchOptions, saveConfig, fetchBoard } = options
  const { t } = useI18n()
  const message = useMessage()

  function authHeaders(json = false) {
    const headers: Record<string, string> = {}
    if (json) headers['Content-Type'] = 'application/json'
    if (adminToken.value.trim()) headers.Authorization = `Bearer ${adminToken.value.trim()}`
    return headers
  }

  // ── Refs ───────────────────────────────────────────────
  const showAddTabModal = ref(false)
  const showEditTabModal = ref(false)
  const showAddColumnModal = ref(false)
  const showEditColumnModal = ref(false)
  const showRenameTemplateModal = ref(false)
  const showPresetModal = ref(false)
  const showProfileModal = ref(false)

  const tabForm = ref({ table_key: '', name: '', description: '' })
  const columnForm = ref({ table_key: '', column_key: '', name: '', description: '', max_chars: 240, required: 0 })
  const renameTemplateForm = ref({ template_id: '', name: '' })
  const presetForm = ref({ preset_id: '', name: '', description: '' })
  const profileForm = ref({ profile_id: '', name: '', description: '' })
  const editingTabKey = ref('')
  const editingColumnKey = ref('')

  // ── Template helpers ───────────────────────────────────
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

  // ── Tab CRUD ───────────────────────────────────────────
  function openAddTab() {
    tabForm.value = { table_key: '', name: '', description: '' }
    showAddTabModal.value = true
  }

  function openEditTab(table: StateTable) {
    editingTabKey.value = table.table_key
    tabForm.value = { table_key: table.table_key, name: table.name, description: table.description || '' }
    showEditTabModal.value = true
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
      localStorage.setItem('kokoromemo.stateActiveTableKey', activeTableKey.value)
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
      message.error(friendlyError(error.message || '', 'state.saveTab'))
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
        localStorage.setItem('kokoromemo.stateActiveTableKey', activeTableKey.value)
      }
      message.success('标签页已删除')
      await applyTemplateUpdate(data.template)
    } catch (error: any) {
      message.error(friendlyError(error.message || '', 'state.deleteTab'))
    } finally {
      saving.value = false
    }
  }

  // ── Column CRUD ────────────────────────────────────────
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
      message.error(friendlyError(error.message || '', 'state.saveColumn'))
    } finally {
      saving.value = false
    }
  }

  // ── Template clone / rename / delete ──────────────────
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

  // ── Preset CRUD ────────────────────────────────────────
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

  // ── Profile CRUD ───────────────────────────────────────
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
      if (data.profile?.profile_id) config.value!.profile_id = data.profile.profile_id
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

  return {
    // Tab management
    showAddTabModal,
    showEditTabModal,
    tabForm,
    editingTabKey,
    openAddTab,
    openEditTab,
    saveNewTab,
    saveEditTab,
    deleteTab,
    // Column management
    showAddColumnModal,
    showEditColumnModal,
    columnForm,
    editingColumnKey,
    openAddColumn,
    openEditColumn,
    saveNewColumn,
    saveEditColumn,
    // Template operations
    showRenameTemplateModal,
    renameTemplateForm,
    cloneCurrentTemplate,
    openRenameTemplate,
    renameTemplate,
    deleteTemplate,
    // Preset management
    showPresetModal,
    presetForm,
    openPresetModal,
    savePreset,
    deletePreset,
    // Profile management
    showProfileModal,
    profileForm,
    openProfileModal,
    saveProfile,
    deleteProfile,
  }
}
