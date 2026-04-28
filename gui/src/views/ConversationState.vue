<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  NButton,
  NCard,
  NDataTable,
  NForm,
  NFormItem,
  NGrid,
  NGridItem,
  NInput,
  NInputNumber,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NTabs,
  NTabPane,
  useMessage,
} from 'naive-ui'

const serverUrl = 'http://127.0.0.1:14514'
const message = useMessage()
const loading = ref(false)
const conversationId = ref('')
const adminToken = ref('')
const stateItems = ref<any[]>([])
const decisions = ref<any[]>([])
const events = ref<any[]>([])
const showEditModal = ref(false)
const editingItem = ref<any | null>(null)
const editForm = ref({ category: 'scene', item_key: '', item_value: '', priority: 50, confidence: 0.8 })

const categoryOptions = [
  { label: '当前场景', value: 'scene' },
  { label: '关键人物', value: 'key_person' },
  { label: '主线任务', value: 'main_quest' },
  { label: '支线任务', value: 'side_quest' },
  { label: '承诺与约定', value: 'promise' },
  { label: '开放伏笔', value: 'open_loop' },
  { label: '关系状态', value: 'relationship' },
  { label: '稳定边界', value: 'boundary' },
  { label: '偏好', value: 'preference' },
  { label: '地点', value: 'location' },
  { label: '物品', value: 'item' },
  { label: '世界状态', value: 'world_state' },
  { label: '近期摘要', value: 'recent_summary' },
  { label: '情绪氛围', value: 'mood' },
]

const groupedItems = computed(() => {
  const groups: Record<string, any[]> = {}
  for (const item of stateItems.value) {
    const label = categoryOptions.find((c) => c.value === item.category)?.label || item.category
    groups[label] = groups[label] || []
    groups[label].push(item)
  }
  return groups
})

function ensureConversationId() {
  if (!conversationId.value.trim()) {
    message.warning('请输入 conversation_id')
    return false
  }
  return true
}

async function fetchAll() {
  if (!ensureConversationId()) return
  loading.value = true
  try {
    const [stateResp, decisionResp, eventResp] = await Promise.all([
      fetch(`${serverUrl}/admin/conversations/${conversationId.value}/state?limit=300`, { headers: authHeaders() }),
      fetch(`${serverUrl}/admin/conversations/${conversationId.value}/retrieval-decisions?limit=100`, { headers: authHeaders() }),
      fetch(`${serverUrl}/admin/conversations/${conversationId.value}/state/events?limit=100`, { headers: authHeaders() }),
    ])
    stateItems.value = (await stateResp.json()).items || []
    decisions.value = (await decisionResp.json()).items || []
    events.value = (await eventResp.json()).items || []
  } catch (e: any) {
    message.error(`加载失败：${e.message || e}`)
  }
  loading.value = false
}

function openCreateModal() {
  editingItem.value = null
  editForm.value = { category: 'scene', item_key: '', item_value: '', priority: 50, confidence: 0.8 }
  showEditModal.value = true
}

function openEditModal(row: any) {
  editingItem.value = row
  editForm.value = {
    category: row.category,
    item_key: row.item_key,
    item_value: row.item_value || row.content,
    priority: row.priority,
    confidence: row.confidence,
  }
  showEditModal.value = true
}

async function saveItem() {
  if (!ensureConversationId()) return
  const body = JSON.stringify(editForm.value)
  const url = editingItem.value
    ? `${serverUrl}/admin/state/${editingItem.value.item_id}`
    : `${serverUrl}/admin/conversations/${conversationId.value}/state`
  const method = editingItem.value ? 'PATCH' : 'POST'
  try {
    const resp = await fetch(url, { method, headers: authHeaders(true), body })
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
  await fetch(`${serverUrl}/admin/state/${row.item_id}/resolve`, {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify({ reason: 'GUI 标记完成' }),
  })
  message.success('已标记完成')
  fetchAll()
}

async function deleteItem(row: any) {
  await fetch(`${serverUrl}/admin/state/${row.item_id}`, { method: 'DELETE', headers: authHeaders() })
  message.success('已删除')
  fetchAll()
}

async function rebuildFromCards() {
  if (!ensureConversationId()) return
  const resp = await fetch(`${serverUrl}/admin/conversations/${conversationId.value}/state/rebuild`, {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify({}),
  })
  const data = await resp.json()
  message.success(`已投影 ${data.projected || 0} 条长期边界/偏好`)
  fetchAll()
}

const stateColumns = [
  { title: '类别', key: 'category', width: 110 },
  { title: '键', key: 'item_key', width: 160 },
  { title: '内容', key: 'item_value', ellipsis: { tooltip: true } },
  { title: '状态', key: 'status', width: 90, render: (row: any) => row.status === 'active' ? '活跃' : row.status },
  { title: '优先级', key: 'priority', width: 80 },
  { title: '置信度', key: 'confidence', width: 90, render: (row: any) => Number(row.confidence).toFixed(2) },
  { title: '更新时间', key: 'updated_at', width: 160 },
  {
    title: '操作', key: 'actions', width: 220,
    render: (row: any) => [
      hButton('编辑', () => openEditModal(row)),
      hButton('完成', () => resolveItem(row)),
      hButton('删除', () => deleteItem(row)),
    ],
  },
]

const decisionColumns = [
  { title: '时间', key: 'created_at', width: 160 },
  { title: '请求', key: 'request_id', width: 160 },
  { title: '是否召回', key: 'should_retrieve', width: 90, render: (row: any) => row.should_retrieve ? '是' : '否' },
  { title: '原因', key: 'reason', width: 160 },
  { title: '用户输入', key: 'latest_user_text', ellipsis: { tooltip: true } },
  { title: '状态置信度', key: 'avg_state_confidence', width: 110, render: (row: any) => row.avg_state_confidence == null ? '-' : Number(row.avg_state_confidence).toFixed(2) },
]

const eventColumns = [
  { title: '时间', key: 'created_at', width: 160 },
  { title: '事件', key: 'event_type', width: 160 },
  { title: '条目', key: 'item_id', width: 180 },
  { title: '旧值', key: 'old_value', ellipsis: { tooltip: true } },
  { title: '新值', key: 'new_value', ellipsis: { tooltip: true } },
]

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

import { h } from 'vue'
onMounted(() => {
  const saved = localStorage.getItem('kokoromemo.lastConversationId')
  const savedToken = localStorage.getItem('kokoromemo.adminToken')
  if (saved) conversationId.value = saved
  if (savedToken) adminToken.value = savedToken
})
</script>

<template>
  <div>
    <div style="margin-bottom: 28px;">
      <h1 style="font-size: 24px; font-weight: 600; color: #e4e4e7; margin-bottom: 4px;">会话状态板</h1>
      <p style="color: #71717a; font-size: 14px;">查看当前剧情热状态，并调试 Retrieval Gate 决策。</p>
    </div>

    <NCard style="background: #18181b; border: 1px solid #27272a; margin-bottom: 16px;">
      <NSpace align="center">
        <NInput v-model:value="conversationId" placeholder="conversation_id" style="width: 360px;" @blur="saveLocalInputs" />
        <NInput v-model:value="adminToken" type="password" placeholder="ADMIN_TOKEN（未配置可留空）" style="width: 240px;" @blur="saveLocalInputs" />
        <NButton type="primary" @click="fetchAll">加载</NButton>
        <NButton @click="openCreateModal">新增状态项</NButton>
        <NButton @click="rebuildFromCards">从长期卡片投影</NButton>
      </NSpace>
    </NCard>

    <NSpin :show="loading">
      <NTabs type="line" animated>
        <NTabPane name="board" tab="状态板">
          <NGrid :cols="2" :x-gap="16" :y-gap="16" responsive="screen" item-responsive style="margin-bottom: 16px;">
            <NGridItem v-for="(items, label) in groupedItems" :key="label" span="2 m:1">
              <NCard style="background: #18181b; border: 1px solid #27272a;">
                <template #header>
                  <NSpace align="center"><span>{{ label }}</span><NTag size="small">{{ items.length }}</NTag></NSpace>
                </template>
                <div v-for="item in items" :key="item.item_id" style="padding: 8px 0; border-bottom: 1px solid #27272a;">
                  <div style="color: #e4e4e7; font-size: 14px;">{{ item.item_value }}</div>
                  <div style="color: #71717a; font-size: 12px; margin-top: 4px;">{{ item.item_key }} · P{{ item.priority }} · {{ Number(item.confidence).toFixed(2) }}</div>
                </div>
              </NCard>
            </NGridItem>
          </NGrid>
          <NDataTable :columns="stateColumns" :data="stateItems" :pagination="{ pageSize: 12 }" />
        </NTabPane>
        <NTabPane name="gate" tab="Gate 调试">
          <NDataTable :columns="decisionColumns" :data="decisions" :pagination="{ pageSize: 12 }" />
        </NTabPane>
        <NTabPane name="events" tab="变更事件">
          <NDataTable :columns="eventColumns" :data="events" :pagination="{ pageSize: 12 }" />
        </NTabPane>
      </NTabs>
    </NSpin>

    <NModal v-model:show="showEditModal" preset="card" title="状态项" style="width: 560px; background: #18181b;">
      <NForm label-placement="top">
        <NFormItem label="类别"><NSelect v-model:value="editForm.category" :options="categoryOptions" /></NFormItem>
        <NFormItem label="键"><NInput v-model:value="editForm.item_key" placeholder="例如 current_location" /></NFormItem>
        <NFormItem label="内容"><NInput v-model:value="editForm.item_value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" /></NFormItem>
        <NGrid :cols="2" :x-gap="12">
          <NGridItem><NFormItem label="优先级"><NInputNumber v-model:value="editForm.priority" :min="0" :max="100" style="width: 100%;" /></NFormItem></NGridItem>
          <NGridItem><NFormItem label="置信度"><NInputNumber v-model:value="editForm.confidence" :min="0" :max="1" :step="0.05" style="width: 100%;" /></NFormItem></NGridItem>
        </NGrid>
      </NForm>
      <template #footer>
        <NSpace justify="end"><NButton @click="showEditModal = false">取消</NButton><NButton type="primary" @click="saveItem">保存</NButton></NSpace>
      </template>
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
</style>
