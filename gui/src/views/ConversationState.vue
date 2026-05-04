<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
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
import { AddOutline, HelpCircleOutline, RefreshOutline } from '@vicons/ionicons5'
import { apiFetch } from '../api'
import { saveJsonExport } from '../export'

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
  template_id?: string | null
  table_template_id?: string | null
  mount_preset_id?: string | null
  memory_write_policy: string
  state_update_policy: string
  injection_policy: string
  created_from_default?: boolean
}

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const previewLoading = ref(false)
const conversationId = ref(localStorage.getItem('kokoromemo.stateConversationId') || '')
const adminToken = ref(localStorage.getItem('kokoromemo.adminToken') || '')
const conversations = ref<any[]>([])
const template = ref<any | null>(null)
const rows = ref<StateRow[]>([])
const config = ref<ConversationConfig | null>(null)
const defaultConfig = ref<ConversationConfig | null>(null)
const profiles = ref<any[]>([])
const boardTemplates = ref<any[]>([])
const tableTemplates = ref<any[]>([])
const mountPresets = ref<any[]>([])
const activeTableKey = ref('')
const preview = ref({ preview: '', char_count: 0, max_chars: 0, item_count: 0 })
const showEditModal = ref(false)
const showFillModal = ref(false)
const showHelpModal = ref(false)
const showRenameModal = ref(false)
const editingTable = ref<StateTable | null>(null)
const editingRow = ref<StateRow | null>(null)
const editValues = ref<Record<string, string>>({})
const editMeta = ref({ priority: 80, confidence: 0.9 })
const fillForm = ref({ user_message: '', assistant_message: '' })
const renameForm = ref({ title: '' })

const profileOptions = computed(() => profiles.value.map((item) => ({ label: item.name, value: item.profile_id })))
const boardTemplateOptions = computed(() => [
  { label: '不使用旧字段模板', value: null },
  ...boardTemplates.value.map((item) => ({ label: item.name, value: item.template_id })),
])
const tableTemplateOptions = computed(() => [
  { label: '不使用表格模板', value: null },
  ...tableTemplates.value.map((item) => ({ label: item.name, value: item.template_id })),
])
const mountPresetOptions = computed(() => [
  { label: '不套用挂载预设', value: null },
  ...mountPresets.value.map((item) => ({ label: item.name, value: item.preset_id })),
])
const conversationOptions = computed(() => conversations.value.map((item) => ({
  label: `${conversationDisplayName(item)} · ${item.character_display_name || item.character_id || '未知角色'} · ${item.last_seen_at || item.conversation_id}`,
  value: item.conversation_id,
})))
const selectedConversation = computed(() => conversations.value.find((item) => item.conversation_id === conversationId.value.trim()) || null)
const memoryPolicyOptions = [
  { label: '关闭长期记忆写入', value: 'disabled' },
  { label: '生成候选待审核', value: 'candidate' },
  { label: '仅稳定设定候选', value: 'stable_only' },
  { label: '自动判断', value: 'auto' },
]
const statePolicyOptions = [
  { label: '关闭状态更新', value: 'disabled' },
  { label: '仅手动维护', value: 'manual' },
  { label: '自动更新状态板', value: 'auto' },
]
const injectionPolicyOptions = [
  { label: '不注入', value: 'none' },
  { label: '仅长期记忆', value: 'memory_only' },
  { label: '仅状态板', value: 'state_only' },
  { label: '状态板优先', value: 'state_first' },
  { label: '混合注入', value: 'mixed' },
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
  localStorage.setItem('kokoromemo.stateConversationId', conversationId.value.trim())
  localStorage.setItem('kokoromemo.adminToken', adminToken.value.trim())
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
    if (!activeTableKey.value && tables.value.length) activeTableKey.value = tables.value[0].table_key
    await fetchPreview()
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
    const [profilesResp, boardResp, tableResp, presetResp] = await Promise.all([
      apiFetch('/admin/conversation-profiles', { headers: authHeaders() }),
      apiFetch('/admin/state/templates', { headers: authHeaders() }),
      apiFetch('/admin/state/table-templates', { headers: authHeaders() }),
      apiFetch('/admin/memory-mount-presets', { headers: authHeaders() }),
    ])
    if (profilesResp.ok) profiles.value = (await profilesResp.json()).items || []
    if (boardResp.ok) boardTemplates.value = (await boardResp.json()).items || []
    if (tableResp.ok) tableTemplates.value = (await tableResp.json()).items || []
    if (presetResp.ok) mountPresets.value = (await presetResp.json()).items || []
  } catch (error) {
    console.warn('load state config options failed', error)
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
    template_id: profile.template_id,
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
    template_id: profile.template_id,
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
      body: JSON.stringify(config.value),
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

async function runFill() {
  if (!conversationId.value.trim()) return
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/state/fill`, {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({ ...fillForm.value, table_only: true }),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '填充失败')
    message.success(`AI 填充完成：应用 ${data.applied}，跳过 ${data.skipped}`)
    showFillModal.value = false
    await fetchBoard()
  } catch (error: any) {
    message.error(error.message || '填充失败')
  } finally {
    saving.value = false
  }
}

async function exportBoard() {
  if (!template.value) return
  const payload = { conversation_id: conversationId.value.trim(), template: template.value, rows: rows.value }
  const savedPath = await saveJsonExport(`state_board_${conversationId.value.trim()}.json`, payload)
  message.success(savedPath ? `已导出到 ${savedPath}` : '已导出')
}

function columnsFor(table: StateTable) {
  const valueColumns = table.columns.map((column) => ({
    title: column.name,
    key: column.column_key,
    minWidth: 140,
    ellipsis: { tooltip: true },
    render: (row: StateRow) => row.values?.[column.column_key] || '-',
  }))
  return [
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

onMounted(() => {
  fetchOptions()
  fetchConversations()
  fetchDefaultConfig()
  if (conversationId.value.trim()) fetchBoard()
})
</script>

<template>
  <div class="state-page">
    <NSpace vertical size="large">
      <NCard>
        <template #header>
          <NSpace align="center">
            <span>会话状态板</span>
            <NButton quaternary size="small" @click="showHelpModal = true">
              <template #icon><NIcon :component="HelpCircleOutline" /></template>
            </NButton>
          </NSpace>
        </template>
        <NGrid :cols="24" :x-gap="12" :y-gap="12">
          <NGridItem :span="10">
            <NSelect
              v-model:value="conversationId"
              filterable
              clearable
              tag
              :options="conversationOptions"
              placeholder="选择会话"
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

      <NAlert v-if="template" type="info" :show-icon="false">
        当前模板：{{ template.name }}。状态板已改为“表格模板 + 行级状态 + 操作式更新”，新增内容写入对应表格行，注入时按优先级压缩输出。
      </NAlert>

      <NCard v-if="defaultConfig" title="新会话默认配置">
        <NForm label-placement="top">
          <NGrid :cols="24" :x-gap="12" :y-gap="12">
            <NGridItem :span="8">
              <NFormItem label="默认会话方案">
                <NSelect v-model:value="defaultConfig.profile_id" :options="profileOptions" @update:value="applyProfileToDefault" />
              </NFormItem>
            </NGridItem>
            <NGridItem :span="8">
              <NFormItem label="默认表格模板">
                <NSelect v-model:value="defaultConfig.table_template_id" filterable :options="tableTemplateOptions" />
              </NFormItem>
            </NGridItem>
            <NGridItem :span="8">
              <NFormItem label="默认挂载组合预设">
                <NSelect v-model:value="defaultConfig.mount_preset_id" filterable :options="mountPresetOptions" />
              </NFormItem>
            </NGridItem>
            <NGridItem :span="8">
              <NFormItem label="默认长期记忆写入">
                <NSelect v-model:value="defaultConfig.memory_write_policy" :options="memoryPolicyOptions" />
              </NFormItem>
            </NGridItem>
            <NGridItem :span="8">
              <NFormItem label="默认状态板更新">
                <NSelect v-model:value="defaultConfig.state_update_policy" :options="statePolicyOptions" />
              </NFormItem>
            </NGridItem>
            <NGridItem :span="8">
              <NFormItem label="默认注入策略">
                <NSelect v-model:value="defaultConfig.injection_policy" :options="injectionPolicyOptions" />
              </NFormItem>
            </NGridItem>
          </NGrid>
          <NSpace justify="space-between" align="center">
            <NAlert type="info" :show-icon="false" style="flex: 1">
              仅影响之后第一次出现的新 conversation_id；已有会话不会被自动覆盖。
            </NAlert>
            <NButton type="primary" :loading="saving" @click="saveDefaultConfig">保存新会话默认配置</NButton>
          </NSpace>
        </NForm>
      </NCard>

      <NCard v-if="config" title="当前会话策略">
        <NForm label-placement="top">
          <NGrid :cols="24" :x-gap="12" :y-gap="12">
            <NGridItem :span="8">
              <NFormItem label="会话方案">
                <NSelect v-model:value="config.profile_id" :options="profileOptions" @update:value="applyProfileToConfig" />
              </NFormItem>
            </NGridItem>
            <NGridItem :span="8">
              <NFormItem label="状态板表格模板">
                <NSelect v-model:value="config.table_template_id" filterable :options="tableTemplateOptions" />
              </NFormItem>
            </NGridItem>
            <NGridItem :span="8">
              <NFormItem label="旧字段模板（兼容兜底）">
                <NSelect v-model:value="config.template_id" filterable :options="boardTemplateOptions" />
              </NFormItem>
            </NGridItem>
            <NGridItem :span="8">
              <NFormItem label="挂载组合预设">
                <NSelect v-model:value="config.mount_preset_id" filterable :options="mountPresetOptions" />
              </NFormItem>
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
            <NGridItem :span="16">
              <NFormItem label="说明">
                <NAlert type="default" :show-icon="false">
                  该配置即使当前会话没有任何状态数据也会保存。RimTalk / 殖民地模拟建议使用“仅状态板”并关闭长期记忆写入。
                </NAlert>
              </NFormItem>
            </NGridItem>
          </NGrid>
          <NSpace justify="end">
            <NButton :loading="loading" @click="fetchBoard">重新加载</NButton>
            <NButton type="primary" :loading="saving" @click="saveConfig">保存会话策略</NButton>
          </NSpace>
        </NForm>
      </NCard>

      <NSpin :show="loading">
        <NGrid :cols="24" :x-gap="16" :y-gap="16">
          <NGridItem :span="16">
            <NCard title="状态表格">
              <NAlert v-if="template && rows.length === 0" type="info" style="margin-bottom: 12px">
                当前会话暂无状态行，但已可配置模板、挂载预设和记忆策略。下一轮对话或手动新增后会按当前策略写入状态表格。
              </NAlert>
              <NTabs v-if="tables.length" v-model:value="activeTableKey" type="line" animated>
                <NTabPane v-for="table in tables" :key="table.table_key" :name="table.table_key" :tab="`${table.name} (${(rowsByTable[table.table_key] || []).length})`">
                  <NSpace vertical size="medium">
                    <NAlert type="default" :show-icon="false">{{ table.description || '无说明' }}</NAlert>
                    <NSpace>
                      <NButton type="primary" size="small" @click="openCreate(table)">
                        <template #icon><NIcon :component="AddOutline" /></template>
                        新增状态行
                      </NButton>
                      <NButton size="small" @click="fetchPreview">刷新注入预览</NButton>
                    </NSpace>
                    <NDataTable :columns="columnsFor(table)" :data="rowsByTable[table.table_key] || []" :pagination="{ pageSize: 8 }" />
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
                  <NTag size="small">{{ preview.char_count }} / {{ preview.max_chars }} 字符，{{ preview.item_count }} 行</NTag>
                  <NInput :value="preview.preview" type="textarea" readonly :autosize="{ minRows: 12, maxRows: 24 }" placeholder="加载后显示注入到模型的状态板文本" />
                </NSpace>
              </NCard>

              <NCard title="AI 填充调试">
                <NSpace vertical>
                  <NInput v-model:value="fillForm.user_message" type="textarea" placeholder="用户消息" :autosize="{ minRows: 3, maxRows: 6 }" />
                  <NInput v-model:value="fillForm.assistant_message" type="textarea" placeholder="助手回复" :autosize="{ minRows: 3, maxRows: 8 }" />
                  <NButton type="primary" :loading="saving" :disabled="!conversationId.trim()" @click="runFill">运行表格填充</NButton>
                </NSpace>
              </NCard>
            </NSpace>
          </NGridItem>
        </NGrid>
      </NSpin>
    </NSpace>

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

    <NModal v-model:show="showEditModal" preset="card" style="width: 720px" :title="editingRow ? '编辑状态行' : '新增状态行'">
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

    <NModal v-model:show="showHelpModal" preset="card" style="width: 760px" title="会话状态板帮助">
      <NSpace vertical>
        <NAlert type="success" :show-icon="false">本模块已从“模板字段填空”重构为“表格化状态板”，更接近 st-memory-enhancement 的行级状态维护方式。</NAlert>
        <p><b>状态表格</b>：每个标签是一张表，例如当前场景、角色状态、关系状态、扮演规则、承诺任务、重要事件、重要物品。</p>
        <p><b>状态行</b>：每行是一条可被插入、更新或删除的状态。AI 填充器会尽量更新既有行，避免把所有内容堆到一个大文本框。</p>
        <p><b>会话策略</b>：决定当前会话是否写入长期记忆、是否自动更新状态板，以及请求时注入长期记忆还是状态板。没有状态数据时也可以先保存策略。</p>
        <p><b>RimTalk / 殖民地模拟</b>：建议套用对应方案，长期记忆写入选择“关闭”，注入策略选择“仅状态板”，避免把资源、小人状态、临时事件写入长期记忆。</p>
        <p><b>新会话默认配置</b>：决定第一次出现的新 conversation_id 使用什么模板和策略。请在开始 RimTalk 或跑团前先选好默认方案，第一轮对话就会使用正确状态板。</p>
        <p><b>注入预览</b>：展示真正注入模型的压缩文本，超过字符预算时按表格优先级截断。</p>
        <p><b>AI 填充调试</b>：粘贴一轮用户消息和助手回复，观察表格操作结果。只应记录影响后续连续性的内容，避免流水账。</p>
      </NSpace>
    </NModal>
  </div>
</template>

<style scoped>
.state-page {
  padding: 20px;
}
</style>
