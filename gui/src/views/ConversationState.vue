<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import {
  NButton,
  NCard,
  NDataTable,
  NDivider,
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
import { apiFetch } from '../api'

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
const editForm = ref({ field_id: '', item_value: '', priority: 70, confidence: 0.8, user_locked: false })
const templateJson = ref('')
const fillForm = ref({ user_message: '', assistant_message: '' })
const configLoaded = ref(false)
const stateItemCount = ref(0)
const isNewSession = ref(false)
const presets = ref<any[]>([])
const showPresetModal = ref(false)
const presetForm = ref({ name: '', description: '' })

const templateOptions = computed(() => templates.value.map((item) => ({ label: `${item.name}${item.is_builtin ? '（内置）' : ''}`, value: item.template_id })))
const memoryLibraryOptions = computed(() => memoryLibraries.value.map((item) => ({ label: `${item.name}${item.card_count ? `（${item.card_count}）` : ''}`, value: item.library_id })))
const mountedLibraryNames = computed(() => memoryMounts.value.map((item) => item.name).join(' + ') || '未挂载')
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
    message.warning('请输入 conversation_id')
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
    message.error(`加载失败：${e.message || e}`)
  }
  loading.value = false
}

async function saveFullConfig() {
  if (!ensureConversationId()) return
  if (!mountedLibraryIds.value.length) {
    message.warning('请至少挂载一个长期记忆库')
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
    if (data.status !== 'ok') throw new Error(data.message || '保存失败')
    message.success('会话配置已保存')
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
  message.success('状态板模板已切换')
  fetchAll()
}

function openCreateModal(field?: any) {
  editingItem.value = null
  editForm.value = { field_id: field?.field_id || '', item_value: '', priority: 70, confidence: 0.8, user_locked: false }
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
  })
  const url = editingItem.value ? `/admin/state/${editingItem.value.item_id}` : `/admin/conversations/${conversationId.value}/state`
  const method = editingItem.value ? 'PATCH' : 'POST'
  try {
    const resp = await apiFetch(url, { method, headers: authHeaders(true), body })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || '保存失败')
    showEditModal.value = false
    message.success('状态项已保存')
    fetchAll()
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

async function resolveItem(row: any) {
  await apiFetch(`/admin/state/${row.item_id}/resolve`, { method: 'POST', headers: authHeaders(true), body: JSON.stringify({ reason: 'GUI 标记完成' }) })
  message.success('已标记完成')
  fetchAll()
}

async function deleteItem(row: any) {
  await apiFetch(`/admin/state/${row.item_id}`, { method: 'DELETE', headers: authHeaders() })
  message.success('已删除')
  fetchAll()
}

async function rebuildFromCards() {
  if (!ensureConversationId()) return
  const resp = await apiFetch(`/admin/conversations/${conversationId.value}/state/rebuild`, { method: 'POST', headers: authHeaders(true), body: JSON.stringify({}) })
  const data = await resp.json()
  message.success(`已投影 ${data.projected || 0} 条长期卡片`)
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
    if (data.status !== 'ok') throw new Error(data.message || '清空失败')
    message.success(`已清空 ${data.cleared || 0} 个状态项`)
    fetchAll()
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

function openTemplateModal() {
  templateJson.value = JSON.stringify({
    name: '自定义状态板',
    description: '按你的玩法自定义标签页和字段',
    tabs: [
      { tab_key: 'main', label: '主要状态', fields: [{ field_key: 'current_goal', label: '当前目标', description: 'AI 需要维护的当前目标', ai_writable: true, include_in_prompt: true }] },
    ],
  }, null, 2)
  showTemplateModal.value = true
}

async function saveTemplate() {
  try {
    const payload = JSON.parse(templateJson.value)
    const resp = await apiFetch('/admin/state/templates', { method: 'POST', headers: authHeaders(true), body: JSON.stringify(payload) })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || '保存失败')
    showTemplateModal.value = false
    message.success('模板已保存')
    await fetchTemplates()
    selectedTemplateId.value = data.template_id
  } catch (e: any) {
    message.error(`模板保存失败：${e.message || e}`)
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
    message.error(data.message || '填表失败')
    return
  }
  showFillModal.value = false
  message.success(`AI 填表完成：写入 ${data.applied || 0} 项，跳过 ${data.skipped || 0} 项`)
  fetchAll()
}

function applyPreset(preset: any) {
  try {
    const libraryIds: string[] = JSON.parse(preset.library_ids_json || '[]')
    if (libraryIds.length) {
      mountedLibraryIds.value = libraryIds
      writeLibraryId.value = preset.write_library_id || libraryIds[0]
      message.success(`已应用预设：${preset.name}`)
    }
  } catch {
    message.error('预设数据解析失败')
  }
}

async function saveAsPreset() {
  if (!mountedLibraryIds.value.length) {
    message.warning('请先选择挂载的记忆库')
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
        name: presetForm.value.name || '未命名挂载组合',
        description: presetForm.value.description,
        library_ids: mountedLibraryIds.value,
        write_library_id: writeLibraryId.value,
      }),
    })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || '保存失败')
    showPresetModal.value = false
    presetForm.value = { name: '', description: '' }
    message.success('挂载组合预设已保存')
    await fetchPresets()
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

async function deletePreset(presetId: string) {
  const resp = await apiFetch(`/admin/memory-mount-presets/${presetId}`, { method: 'DELETE', headers: authHeaders() })
  const data = await resp.json()
  if (data.status === 'ok') {
    message.success('预设已删除')
    await fetchPresets()
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
  { title: '字段', key: 'label', width: 160, render: (row: any) => h('div', [h('div', row.field.label), h('div', { class: 'km-muted' }, row.field.field_key)]) },
  { title: '当前值', key: 'value', ellipsis: { tooltip: true }, render: (row: any) => row.item?.item_value || row.item?.content || row.field.default_value || '—' },
  { title: '置信度', key: 'confidence', width: 90, render: (row: any) => row.item ? Number(row.item.confidence).toFixed(2) : '—' },
  { title: '来源', key: 'source', width: 120, render: (row: any) => row.item?.source || '—' },
  { title: '更新时间', key: 'updated_at', width: 170, render: (row: any) => row.item?.updated_at || '—' },
  { title: '锁定', key: 'locked', width: 80, render: (row: any) => row.item?.user_locked ? h(NTag, { size: 'small', type: 'warning' }, { default: () => '锁定' }) : '—' },
  { title: '操作', key: 'actions', width: 180, render: (row: any) => row.item ? [hButton('编辑', () => openEditModal(row.item, row.field)), hButton('完成', () => resolveItem(row.item)), hButton('删除', () => deleteItem(row.item))] : hButton('填写', () => openCreateModal(row.field)) },
]

const legacyColumns = [
  { title: '类别', key: 'category', width: 110 },
  { title: '键', key: 'item_key', width: 160 },
  { title: '内容', key: 'item_value', ellipsis: { tooltip: true } },
  { title: '来源', key: 'source', width: 120 },
  { title: '操作', key: 'actions', width: 180, render: (row: any) => [hButton('编辑', () => openEditModal(row)), hButton('完成', () => resolveItem(row)), hButton('删除', () => deleteItem(row))] },
]

const decisionColumns = [
  { title: '时间', key: 'created_at', width: 170 },
  { title: '模式', key: 'mode', width: 90 },
  { title: '检索', key: 'should_retrieve', width: 80, render: (row: any) => row.should_retrieve ? '是' : '否' },
  { title: '原因', key: 'reason', ellipsis: { tooltip: true } },
  { title: '最新用户输入', key: 'latest_user_text', ellipsis: { tooltip: true } },
]

const eventColumns = [
  { title: '时间', key: 'created_at', width: 170 },
  { title: '事件', key: 'event_type', width: 160 },
  { title: '条目', key: 'item_id', width: 180 },
  { title: '旧值', key: 'old_value', ellipsis: { tooltip: true } },
  { title: '新值', key: 'new_value', ellipsis: { tooltip: true } },
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
      <h1 style="font-size: 24px; font-weight: 600; color: #e4e4e7; margin-bottom: 4px;">会话状态板</h1>
      <p style="color: #71717a; font-size: 14px;">管理当前会话配置、状态板模板和长期记忆挂载。</p>
    </div>

    <!-- 会话配置面板 -->
    <NCard title="当前会话配置" style="background: #18181b; border: 1px solid #27272a; margin-bottom: 16px;">
      <NGrid :cols="4" :x-gap="12" :y-gap="12" responsive="screen" item-responsive>
        <NGridItem span="4 m:2">
          <NFormItem label="会话 ID" label-placement="top" style="margin-bottom: 0;">
            <NSpace :wrap="false">
              <NInput v-model:value="conversationId" placeholder="输入 conversation_id" style="width: 280px;" @blur="saveLocalInputs" />
              <NButton type="primary" @click="fetchAll">加载</NButton>
            </NSpace>
          </NFormItem>
        </NGridItem>
        <NGridItem span="4 m:2">
          <NFormItem label="管理密钥" label-placement="top" style="margin-bottom: 0;">
            <NInput v-model:value="adminToken" type="password" placeholder="ADMIN_TOKEN（未配置可留空）" style="width: 220px;" @blur="saveLocalInputs" />
          </NFormItem>
        </NGridItem>

        <NGridItem span="4 m:2">
          <NFormItem label="状态板模板" label-placement="top" style="margin-bottom: 0;">
            <NSpace :wrap="false">
              <NSelect v-model:value="selectedTemplateId" :options="templateOptions" placeholder="选择模板" style="width: 260px;" />
              <NButton @click="changeTemplate" :disabled="!configLoaded">切换</NButton>
              <NButton @click="openTemplateModal">新建</NButton>
            </NSpace>
          </NFormItem>
        </NGridItem>
        <NGridItem span="4 m:2">
          <NFormItem label="写入目标" label-placement="top" style="margin-bottom: 0;">
            <NSelect v-model:value="writeLibraryId" :options="memoryLibraryOptions.filter((item) => mountedLibraryIds.includes(item.value))" placeholder="自动记忆写入库" style="width: 220px;" />
          </NFormItem>
        </NGridItem>

        <NGridItem span="4">
          <NFormItem label="挂载记忆库" label-placement="top" style="margin-bottom: 0;">
            <NSelect
              :value="mountedLibraryIds"
              multiple
              filterable
              :options="memoryLibraryOptions"
              placeholder="选择一个或多个长期记忆库"
              @update:value="handleMountedLibrariesChange"
            />
          </NFormItem>
        </NGridItem>

        <NGridItem span="4">
          <NFormItem label="挂载组合预设" label-placement="top" style="margin-bottom: 0;">
            <NSpace align="center" :wrap="true">
              <NButton v-for="preset in presets" :key="preset.preset_id" size="small" quaternary type="info" @click="applyPreset(preset)">
                {{ preset.name }}
                <template #icon>
                  <NPopconfirm @positive-click="deletePreset(preset.preset_id)">
                    <template #trigger><span class="preset-delete" @click.stop>x</span></template>
                    确认删除预设？
                  </NPopconfirm>
                </template>
              </NButton>
              <NButton size="small" dashed @click="saveAsPreset" :disabled="!mountedLibraryIds.length">保存当前为预设</NButton>
            </NSpace>
          </NFormItem>
        </NGridItem>
      </NGrid>

      <!-- 会话状态摘要 -->
      <NDivider style="margin: 12px 0;" />
      <NSpace align="center" justify="space-between" :wrap="true">
        <NSpace align="center" :wrap="true">
          <NTag v-if="isNewSession" type="warning" size="small">新会话</NTag>
          <NTag v-else type="success" size="small">已配置</NTag>
          <span style="color: #a1a1aa; font-size: 13px;">
            模板：<strong style="color: #e4e4e7;">{{ currentTemplate?.name || '未选择' }}</strong>
            &nbsp;|&nbsp;
            挂载：<strong style="color: #e4e4e7;">{{ mountedLibraryNames }}</strong>
            &nbsp;|&nbsp;
            状态项：<strong style="color: #e4e4e7;">{{ stateItemCount }}</strong>
          </span>
        </NSpace>
        <NSpace>
          <NButton type="primary" @click="saveFullConfig" :disabled="!conversationId.trim()">保存配置</NButton>
          <NPopconfirm @positive-click="clearState">
            <template #trigger><NButton :disabled="!stateItemCount">清空状态板</NButton></template>
            确认清空当前会话的所有状态项？
          </NPopconfirm>
        </NSpace>
      </NSpace>
    </NCard>

    <!-- 操作按钮栏 -->
    <NCard style="background: #18181b; border: 1px solid #27272a; margin-bottom: 16px;">
      <NSpace align="center" :wrap="true">
        <NButton @click="showFillModal = true" :disabled="!configLoaded">手动 AI 填表</NButton>
        <NButton @click="rebuildFromCards" :disabled="!configLoaded">从长期记忆投影</NButton>
        <NTooltip trigger="hover">
          <template #trigger><span class="help-icon">?</span></template>
          AI 填表只更新可写字段。锁定字段不会被 AI 覆盖。投影将长期记忆中的偏好和边界卡片投射到状态板。
        </NTooltip>
      </NSpace>
    </NCard>

    <!-- 新会话初始化提示 -->
    <NCard v-if="configLoaded && isNewSession" style="background: rgba(167, 139, 250, 0.08); border: 1px solid #a78bfa; margin-bottom: 16px;">
      <NSpace align="center" justify="space-between">
        <div>
          <div style="color: #e4e4e7; font-weight: 600; margin-bottom: 4px;">这是一个新会话</div>
          <div style="color: #a1a1aa; font-size: 13px;">当前会话尚未配置。请在上方选择记忆库组合和状态板模板，然后点击"保存配置"。</div>
        </div>
        <NButton type="primary" @click="saveFullConfig">快速初始化</NButton>
      </NSpace>
    </NCard>

    <NSpin :show="loading">
      <NTabs type="line" animated>
        <NTabPane name="board" tab="状态板">
          <NTabs v-if="currentTemplate" type="card" animated>
            <NTabPane v-for="tab in currentTemplate.tabs" :key="tab.tab_id" :name="tab.tab_id" :tab="tab.label">
              <NCard style="background: #18181b; border: 1px solid #27272a; margin-bottom: 12px;">
                <template #header>
                  <NSpace align="center"><span>{{ tab.label }}</span><NTag size="small">{{ tab.fields?.length || 0 }} 字段</NTag></NSpace>
                </template>
                <p style="color: #71717a; margin-top: 0;">{{ tab.description || '无描述' }}</p>
                <NDataTable :columns="boardColumns" :data="fieldRows(tab)" :pagination="false" />
              </NCard>
            </NTabPane>
          </NTabs>
          <NCard v-if="legacyItems.length" title="旧类别状态项" style="background: #18181b; border: 1px solid #27272a; margin-top: 16px;">
            <NDataTable :columns="legacyColumns" :data="legacyItems" :pagination="{ pageSize: 8 }" />
          </NCard>
        </NTabPane>
        <NTabPane name="gate" tab="Gate 调试"><NDataTable :columns="decisionColumns" :data="decisions" :pagination="{ pageSize: 12 }" /></NTabPane>
        <NTabPane name="events" tab="变更事件"><NDataTable :columns="eventColumns" :data="events" :pagination="{ pageSize: 12 }" /></NTabPane>
      </NTabs>
    </NSpin>

    <!-- 编辑状态项 Modal -->
    <NModal v-model:show="showEditModal" preset="card" title="状态项" style="width: 620px; background: #18181b;">
      <NForm label-placement="top">
        <NFormItem label="字段"><NSelect v-model:value="editForm.field_id" :options="fieldOptions" filterable /></NFormItem>
        <NFormItem label="内容"><NInput v-model:value="editForm.item_value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" /></NFormItem>
        <NGrid :cols="3" :x-gap="12">
          <NGridItem><NFormItem label="优先级"><NInputNumber v-model:value="editForm.priority" :min="0" :max="100" style="width: 100%;" /></NFormItem></NGridItem>
          <NGridItem><NFormItem label="置信度"><NInputNumber v-model:value="editForm.confidence" :min="0" :max="1" :step="0.05" style="width: 100%;" /></NFormItem></NGridItem>
          <NGridItem><NFormItem label="锁定"><NSwitch v-model:value="editForm.user_locked" /></NFormItem></NGridItem>
        </NGrid>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showEditModal = false">取消</NButton><NButton type="primary" @click="saveItem">保存</NButton></NSpace></template>
    </NModal>

    <!-- 新建模板 Modal -->
    <NModal v-model:show="showTemplateModal" preset="card" title="新建状态板模板（JSON）" style="width: 760px; background: #18181b;">
      <NInput v-model:value="templateJson" type="textarea" :autosize="{ minRows: 18, maxRows: 28 }" />
      <template #footer><NSpace justify="end"><NButton @click="showTemplateModal = false">取消</NButton><NButton type="primary" @click="saveTemplate">保存模板</NButton></NSpace></template>
    </NModal>

    <!-- AI 填表 Modal -->
    <NModal v-model:show="showFillModal" preset="card" title="手动运行 AI 填表" style="width: 680px; background: #18181b;">
      <NForm label-placement="top">
        <NFormItem label="用户发言"><NInput v-model:value="fillForm.user_message" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" /></NFormItem>
        <NFormItem label="助手回复"><NInput v-model:value="fillForm.assistant_message" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" /></NFormItem>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showFillModal = false">取消</NButton><NButton type="primary" @click="runStateFiller">运行</NButton></NSpace></template>
    </NModal>

    <!-- 保存挂载预设 Modal -->
    <NModal v-model:show="showPresetModal" preset="card" title="保存挂载组合预设" style="width: 480px; background: #18181b;">
      <NForm label-placement="top">
        <NFormItem label="预设名称"><NInput v-model:value="presetForm.name" placeholder="例如：跑团常用、日常聊天" /></NFormItem>
        <NFormItem label="描述（可选）"><NInput v-model:value="presetForm.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" /></NFormItem>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="showPresetModal = false">取消</NButton><NButton type="primary" @click="confirmSavePreset">保存</NButton></NSpace></template>
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
