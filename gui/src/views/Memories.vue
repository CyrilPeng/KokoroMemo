<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import {
  NCard, NDataTable, NTag, NEmpty, NSpin, NButton, NSpace, NSelect,
  NPagination, NPopconfirm, NModal, NForm, NFormItem, NInput,
  NSlider, useMessage,
} from 'naive-ui'

const message = useMessage()
const memories = ref<any[]>([])
const loading = ref(true)
const total = ref(0)
const page = ref(1)
const pageSize = 20
const scopeFilter = ref<string | null>(null)
const serverUrl = 'http://127.0.0.1:14514'

// Edit modal state
const showEditModal = ref(false)
const editingCard = ref<any>(null)
const editForm = ref({
  content: '',
  card_type: 'preference',
  scope: 'global',
  importance: 0.5,
})

const scopeOptions = [
  { label: '全部', value: '' },
  { label: '全局', value: 'global' },
  { label: '角色', value: 'character' },
  { label: '会话', value: 'conversation' },
]

const typeOptions = [
  { label: '偏好', value: 'preference' },
  { label: '边界', value: 'boundary' },
  { label: '关系', value: 'relationship' },
  { label: '事件', value: 'event' },
  { label: '承诺', value: 'promise' },
  { label: '纠正', value: 'correction' },
  { label: '摘要', value: 'summary' },
]

const scopeEditOptions = [
  { label: '全局', value: 'global' },
  { label: '角色', value: 'character' },
  { label: '会话', value: 'conversation' },
]

const columns = [
  {
    title: '内容',
    key: 'content',
    ellipsis: { tooltip: true },
    minWidth: 200,
  },
  {
    title: '类型',
    key: 'memory_type',
    width: 80,
    render: (row: any) => {
      const typeMap: Record<string, string> = {
        preference: '偏好', relationship: '关系', event: '事件',
        promise: '承诺', boundary: '边界', correction: '纠正', summary: '摘要',
      }
      return typeMap[row.memory_type] || row.memory_type
    },
  },
  {
    title: '作用域',
    key: 'scope',
    width: 70,
    render: (row: any) => {
      const map: Record<string, string> = { global: '全局', character: '角色', conversation: '会话' }
      return map[row.scope] || row.scope
    },
  },
  {
    title: '重要性',
    key: 'importance',
    width: 70,
    render: (row: any) => (row.importance * 100).toFixed(0) + '%',
  },
  {
    title: '创建时间',
    key: 'created_at',
    width: 150,
  },
  {
    title: '操作',
    key: 'actions',
    width: 120,
    render: (row: any) => {
      return h(NSpace, { size: 4 }, {
        default: () => [
          h(NButton, {
            size: 'tiny', type: 'info', quaternary: true,
            onClick: () => openEditModal(row),
          }, { default: () => '编辑' }),
          h(NPopconfirm, {
            onPositiveClick: () => deleteCard(row.card_id),
          }, {
            trigger: () => h(NButton, { size: 'tiny', type: 'error', quaternary: true }, { default: () => '删除' }),
            default: () => '确认删除此记忆？',
          }),
        ],
      })
    },
  },
]

function openEditModal(row: any) {
  editingCard.value = row
  editForm.value = {
    content: row.content || '',
    card_type: row.memory_type || 'preference',
    scope: row.scope || 'global',
    importance: row.importance || 0.5,
  }
  showEditModal.value = true
}

async function saveEdit() {
  if (!editingCard.value) return
  const cardId = editingCard.value.card_id
  try {
    const resp = await fetch(`${serverUrl}/admin/memories/${cardId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editForm.value),
    })
    const data = await resp.json()
    if (data.status === 'ok') {
      message.success('已保存')
      showEditModal.value = false
      fetchMemories()
    } else {
      message.error(data.message || '保存失败')
    }
  } catch (e) {
    message.error('请求失败')
  }
}

async function fetchMemories() {
  loading.value = true
  const offset = (page.value - 1) * pageSize
  let url = `${serverUrl}/admin/memories?limit=${pageSize}&offset=${offset}`
  if (scopeFilter.value) {
    url += `&scope=${scopeFilter.value}`
  }
  try {
    const resp = await fetch(url)
    if (resp.ok) {
      const data = await resp.json()
      memories.value = data.memories || []
      total.value = data.total || 0
    }
  } catch (e) {
    memories.value = []
    total.value = 0
  }
  loading.value = false
}

function handlePageChange(p: number) {
  page.value = p
  fetchMemories()
}

function handleScopeChange(val: string) {
  scopeFilter.value = val || null
  page.value = 1
  fetchMemories()
}

async function deleteCard(cardId: string) {
  try {
    const resp = await fetch(`${serverUrl}/admin/memories/${cardId}`, { method: 'DELETE' })
    const data = await resp.json()
    if (data.status === 'ok') {
      message.success('已删除')
      fetchMemories()
    } else {
      message.error(data.message || '删除失败')
    }
  } catch (e) {
    message.error('请求失败')
  }
}

onMounted(fetchMemories)
</script>

<template>
  <div>
    <div style="margin-bottom: 28px;">
      <h1 style="font-size: 24px; font-weight: 600; color: #e4e4e7; margin-bottom: 4px;">记忆管理</h1>
      <p style="color: #71717a; font-size: 14px;">查看和管理已存储的长期记忆</p>
    </div>

    <NCard style="background: #18181b; border: 1px solid #27272a;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
        <NSpace>
          <NSelect
            :options="scopeOptions"
            placeholder="筛选作用域"
            style="width: 140px;"
            :value="scopeFilter || ''"
            @update:value="handleScopeChange"
            size="small"
          />
          <NTag size="small" round style="color: #71717a;">
            共 {{ total }} 条记忆
          </NTag>
        </NSpace>
        <NButton size="small" @click="fetchMemories" quaternary style="color: #71717a;">
          刷新
        </NButton>
      </div>

      <NSpin :show="loading">
        <NDataTable
          v-if="memories.length > 0"
          :columns="columns"
          :data="memories"
          :bordered="false"
          size="small"
          :single-line="false"
          style="--n-td-color: #18181b; --n-th-color: #1f1f23;"
        />
        <NEmpty v-else description="暂无记忆数据" style="padding: 60px 0;">
          <template #extra>
            <p style="color: #52525b; font-size: 13px;">与 AI 角色对话后，记忆将自动在此展示</p>
          </template>
        </NEmpty>
      </NSpin>

      <div v-if="total > pageSize" style="display: flex; justify-content: center; margin-top: 16px;">
        <NPagination
          :page="page"
          :page-size="pageSize"
          :item-count="total"
          @update:page="handlePageChange"
        />
      </div>
    </NCard>

    <!-- Edit Modal -->
    <NModal v-model:show="showEditModal" preset="card" title="编辑记忆" style="width: 520px; background: #18181b;">
      <NForm label-placement="top" :show-feedback="false" style="gap: 16px; display: flex; flex-direction: column;">
        <NFormItem label="记忆内容">
          <NInput
            v-model:value="editForm.content"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            placeholder="输入记忆内容"
          />
        </NFormItem>
        <div style="display: flex; gap: 12px;">
          <NFormItem label="类型" style="flex: 1;">
            <NSelect v-model:value="editForm.card_type" :options="typeOptions" />
          </NFormItem>
          <NFormItem label="作用域" style="flex: 1;">
            <NSelect v-model:value="editForm.scope" :options="scopeEditOptions" />
          </NFormItem>
        </div>
        <NFormItem label="重要性">
          <div style="display: flex; align-items: center; gap: 12px; width: 100%;">
            <NSlider v-model:value="editForm.importance" :min="0" :max="1" :step="0.05" style="flex: 1;" />
            <span style="color: #a1a1aa; font-size: 13px; min-width: 40px; text-align: right;">
              {{ (editForm.importance * 100).toFixed(0) }}%
            </span>
          </div>
        </NFormItem>
      </NForm>
      <template #action>
        <NSpace justify="end">
          <NButton @click="showEditModal = false">取消</NButton>
          <NButton type="primary" @click="saveEdit">保存</NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>
