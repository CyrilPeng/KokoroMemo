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

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const previewLoading = ref(false)
const conversationId = ref(localStorage.getItem('kokoromemo.stateConversationId') || '')
const adminToken = ref(localStorage.getItem('kokoromemo.adminToken') || '')
const template = ref<any | null>(null)
const rows = ref<StateRow[]>([])
const activeTableKey = ref('')
const preview = ref({ preview: '', char_count: 0, max_chars: 0, item_count: 0 })
const showEditModal = ref(false)
const showFillModal = ref(false)
const showHelpModal = ref(false)
const editingTable = ref<StateTable | null>(null)
const editingRow = ref<StateRow | null>(null)
const editValues = ref<Record<string, string>>({})
const editMeta = ref({ priority: 80, confidence: 0.9 })
const fillForm = ref({ user_message: '', assistant_message: '' })

const tables = computed<StateTable[]>(() => template.value?.tables || [])
const rowsByTable = computed(() => {
  const result: Record<string, StateRow[]> = {}
  for (const row of rows.value) {
    if (!result[row.table_key]) result[row.table_key] = []
    result[row.table_key].push(row)
  }
  return result
})
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
            <NInput v-model:value="conversationId" placeholder="输入 conversation_id" @keyup.enter="fetchBoard" />
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
            </NSpace>
          </NGridItem>
        </NGrid>
      </NCard>

      <NAlert v-if="template" type="info" :show-icon="false">
        当前模板：{{ template.name }}。状态板已改为“表格模板 + 行级状态 + 操作式更新”，新增内容写入对应表格行，注入时按优先级压缩输出。
      </NAlert>

      <NSpin :show="loading">
        <NGrid :cols="24" :x-gap="16" :y-gap="16">
          <NGridItem :span="16">
            <NCard title="状态表格">
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
