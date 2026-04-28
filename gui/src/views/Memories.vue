<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import {
  NButton, NCard, NDataTable, NEmpty, NForm, NFormItem, NInput, NModal,
  NPagination, NPopconfirm, NSelect, NSlider, NSpace, NSpin, NTag, useMessage,
} from 'naive-ui'
import { apiFetch } from '../api'

const message = useMessage()
const memories = ref<any[]>([])
const libraries = ref<any[]>([])
const loading = ref(true)
const total = ref(0)
const page = ref(1)
const pageSize = 20
const scopeFilter = ref<string | null>(null)
const selectedLibraryId = ref('')
const showEditModal = ref(false)
const showLibraryModal = ref(false)
const showPresetModal = ref(false)
const editingCard = ref<any>(null)
const editingLibrary = ref<any>(null)
const libraryForm = ref({ name: '', description: '' })
const presetForm = ref({ name: '', description: '', source_library_ids: [] as string[] })
const editForm = ref({
  library_id: '',
  content: '',
  card_type: 'preference',
  scope: 'global',
  importance: 0.5,
  confidence: 0.7,
  is_pinned: false,
})

const libraryOptions = computed(() => [
  { label: '全部记忆库', value: '' },
  ...libraries.value.map((item) => ({ label: `${item.name}${item.card_count ? `（${item.card_count}）` : ''}`, value: item.library_id })),
])
const libraryEditOptions = computed(() => libraries.value.map((item) => ({ label: item.name, value: item.library_id })))

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
  { label: '世界状态', value: 'world_state' },
  { label: '摘要', value: 'summary' },
]

const scopeEditOptions = [
  { label: '全局', value: 'global' },
  { label: '角色', value: 'character' },
  { label: '会话', value: 'conversation' },
]

const columns = [
  { title: '记忆库', key: 'library_id', width: 130, render: (row: any) => libraryName(row.library_id) },
  { title: '内容', key: 'content', ellipsis: { tooltip: true }, minWidth: 240 },
  { title: '类型', key: 'memory_type', width: 90, render: (row: any) => typeLabel(row.memory_type) },
  { title: '作用域', key: 'scope', width: 80, render: (row: any) => ({ global: '全局', character: '角色', conversation: '会话' } as Record<string, string>)[row.scope] || row.scope },
  { title: '重要性', key: 'importance', width: 80, render: (row: any) => `${(row.importance * 100).toFixed(0)}%` },
  { title: '创建时间', key: 'created_at', width: 150 },
  {
    title: '操作', key: 'actions', width: 130,
    render: (row: any) => h(NSpace, { size: 4 }, { default: () => [
      h(NButton, { size: 'tiny', type: 'info', quaternary: true, onClick: () => openEditModal(row) }, { default: () => '编辑' }),
      h(NPopconfirm, { onPositiveClick: () => deleteCard(row.card_id) }, {
        trigger: () => h(NButton, { size: 'tiny', type: 'error', quaternary: true }, { default: () => '删除' }),
        default: () => '确认删除此记忆？',
      }),
    ] }),
  },
]

function libraryName(libraryId: string) {
  return libraries.value.find((item) => item.library_id === libraryId)?.name || libraryId || '默认记忆库'
}

function typeLabel(type: string) {
  const typeMap: Record<string, string> = { preference: '偏好', relationship: '关系', event: '事件', promise: '承诺', boundary: '边界', correction: '纠正', world_state: '世界', summary: '摘要' }
  return typeMap[type] || type
}

async function fetchLibraries() {
  const resp = await apiFetch('/admin/memory-libraries')
  const data = await resp.json()
  libraries.value = data.items || []
  if (!selectedLibraryId.value && libraries.value.length) selectedLibraryId.value = libraries.value[0].library_id
}

async function fetchMemories() {
  loading.value = true
  const offset = (page.value - 1) * pageSize
  let url = `/admin/memories?limit=${pageSize}&offset=${offset}`
  if (scopeFilter.value) url += `&scope=${scopeFilter.value}`
  if (selectedLibraryId.value) url += `&library_id=${selectedLibraryId.value}`
  try {
    await fetchLibraries()
    const resp = await apiFetch(url)
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

function openCreateModal() {
  editingCard.value = null
  editForm.value = { library_id: selectedLibraryId.value || libraries.value[0]?.library_id || 'lib_default', content: '', card_type: 'preference', scope: 'global', importance: 0.5, confidence: 0.7, is_pinned: false }
  showEditModal.value = true
}

function openEditModal(row: any) {
  editingCard.value = row
  editForm.value = { library_id: row.library_id || selectedLibraryId.value, content: row.content || '', card_type: row.memory_type || 'preference', scope: row.scope || 'global', importance: row.importance || 0.5, confidence: row.confidence || 0.7, is_pinned: !!row.is_pinned }
  showEditModal.value = true
}

async function saveEdit() {
  const payload = JSON.stringify(editForm.value)
  const url = editingCard.value ? `/admin/memories/${editingCard.value.card_id}` : '/admin/memories'
  const method = editingCard.value ? 'PUT' : 'POST'
  try {
    const resp = await apiFetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: payload })
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

function openCreateLibrary() {
  editingLibrary.value = null
  libraryForm.value = { name: '', description: '' }
  showLibraryModal.value = true
}

function openEditLibrary() {
  const library = libraries.value.find((item) => item.library_id === selectedLibraryId.value)
  if (!library) return
  editingLibrary.value = library
  libraryForm.value = { name: library.name, description: library.description || '' }
  showLibraryModal.value = true
}

async function saveLibrary() {
  const url = editingLibrary.value ? `/admin/memory-libraries/${editingLibrary.value.library_id}` : '/admin/memory-libraries'
  const method = editingLibrary.value ? 'PUT' : 'POST'
  const resp = await apiFetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(libraryForm.value) })
  const data = await resp.json()
  if (data.status !== 'ok') {
    message.error(data.message || '保存失败')
    return
  }
  if (data.library_id) selectedLibraryId.value = data.library_id
  showLibraryModal.value = false
  message.success('记忆库已保存')
  fetchMemories()
}

function openPresetModal() {
  presetForm.value = { name: '', description: '', source_library_ids: selectedLibraryId.value ? [selectedLibraryId.value] : [] }
  showPresetModal.value = true
}

async function savePreset() {
  const resp = await apiFetch('/admin/memory-libraries', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(presetForm.value) })
  const data = await resp.json()
  if (data.status !== 'ok') {
    message.error(data.message || '另存失败')
    return
  }
  selectedLibraryId.value = data.library_id
  showPresetModal.value = false
  message.success('已另存为新预设')
  fetchMemories()
}

async function deleteLibrary() {
  if (!selectedLibraryId.value) return
  const resp = await apiFetch(`/admin/memory-libraries/${selectedLibraryId.value}`, { method: 'DELETE' })
  const data = await resp.json()
  if (data.status === 'ok') {
    selectedLibraryId.value = ''
    message.success('记忆库已删除')
    fetchMemories()
  } else {
    message.error(data.message || '删除失败')
  }
}

async function deleteCard(cardId: string) {
  const resp = await apiFetch(`/admin/memories/${cardId}`, { method: 'DELETE' })
  const data = await resp.json()
  if (data.status === 'ok') {
    message.success('已删除')
    fetchMemories()
  } else {
    message.error(data.message || '删除失败')
  }
}

function handleFilterChange() {
  page.value = 1
  fetchMemories()
}

async function exportLibrary() {
  if (!selectedLibraryId.value) return
  try {
    const resp = await apiFetch(`/admin/memory-libraries/${selectedLibraryId.value}/export`)
    const data = await resp.json()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `library_${selectedLibraryId.value}.json`
    a.click()
    URL.revokeObjectURL(url)
    message.success('记忆库已导出')
  } catch (e: any) {
    message.error(e.message || '导出失败')
  }
}

function triggerImportLibrary() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const resp = await apiFetch('/admin/memory-libraries/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      const result = await resp.json()
      if (result.status === 'ok') {
        selectedLibraryId.value = result.library_id
        message.success(`已导入记忆库（${result.imported_cards || 0} 条记忆）`)
        fetchMemories()
      } else {
        message.error(result.message || '导入失败')
      }
    } catch (e: any) {
      message.error(`导入失败：${e.message || e}`)
    }
  }
  input.click()
}

onMounted(fetchMemories)
</script>

<template>
  <div>
    <div style="margin-bottom: 28px;">
      <h1 style="font-size: 24px; font-weight: 600; color: #e4e4e7; margin-bottom: 4px;">记忆管理</h1>
      <p style="color: #71717a; font-size: 14px;">管理长期记忆库。长期记忆类似全局世界书，可按游戏/角色自由切换或组合挂载。</p>
    </div>

    <NCard style="background: #18181b; border: 1px solid #27272a;">
      <NSpace justify="space-between" align="center" style="margin-bottom: 16px; width: 100%;" wrap>
        <NSpace wrap>
          <NSelect v-model:value="selectedLibraryId" :options="libraryOptions" placeholder="选择记忆库" style="width: 260px;" size="small" @update:value="handleFilterChange" />
          <NSelect :options="scopeOptions" placeholder="筛选作用域" style="width: 140px;" :value="scopeFilter || ''" size="small" @update:value="(val) => { scopeFilter = val || null; handleFilterChange() }" />
          <NTag size="small" round style="color: #71717a;">共 {{ total }} 条记忆</NTag>
        </NSpace>
        <NSpace wrap>
          <NButton size="small" @click="openCreateModal">新增词条</NButton>
          <NButton size="small" @click="openCreateLibrary">新建记忆库</NButton>
          <NButton size="small" :disabled="!selectedLibraryId" @click="openEditLibrary">编辑记忆库</NButton>
          <NButton size="small" :disabled="!selectedLibraryId" @click="openPresetModal">另存为预设</NButton>
          <NPopconfirm @positive-click="deleteLibrary"><template #trigger><NButton size="small" type="error" quaternary :disabled="!selectedLibraryId">删除记忆库</NButton></template>确认删除当前自定义记忆库？默认记忆库不可删除。</NPopconfirm>
          <NButton size="small" :disabled="!selectedLibraryId" @click="exportLibrary">导出</NButton>
          <NButton size="small" @click="triggerImportLibrary">导入</NButton>
          <NButton size="small" @click="fetchMemories" quaternary style="color: #71717a;">刷新</NButton>
        </NSpace>
      </NSpace>

      <NSpin :show="loading">
        <NDataTable v-if="memories.length > 0" :columns="columns" :data="memories" :bordered="false" size="small" :single-line="false" style="--n-td-color: #18181b; --n-th-color: #1f1f23;" />
        <NEmpty v-else description="暂无记忆数据" style="padding: 60px 0;"><template #extra><p style="color: #52525b; font-size: 13px;">可新增词条，或在对话中由记忆判断模型自动写入</p></template></NEmpty>
      </NSpin>

      <div v-if="total > pageSize" style="display: flex; justify-content: center; margin-top: 16px;">
        <NPagination :page="page" :page-size="pageSize" :item-count="total" @update:page="(p) => { page = p; fetchMemories() }" />
      </div>
    </NCard>

    <NModal v-model:show="showEditModal" preset="card" :title="editingCard ? '编辑记忆' : '新增记忆'" style="width: 560px; background: #18181b;">
      <NForm label-placement="top" :show-feedback="false" style="gap: 16px; display: flex; flex-direction: column;">
        <NFormItem label="记忆库"><NSelect v-model:value="editForm.library_id" :options="libraryEditOptions" /></NFormItem>
        <NFormItem label="记忆内容"><NInput v-model:value="editForm.content" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="输入记忆内容" /></NFormItem>
        <div style="display: flex; gap: 12px;">
          <NFormItem label="类型" style="flex: 1;"><NSelect v-model:value="editForm.card_type" :options="typeOptions" /></NFormItem>
          <NFormItem label="作用域" style="flex: 1;"><NSelect v-model:value="editForm.scope" :options="scopeEditOptions" /></NFormItem>
        </div>
        <NFormItem label="重要性"><div style="display: flex; align-items: center; gap: 12px; width: 100%;"><NSlider v-model:value="editForm.importance" :min="0" :max="1" :step="0.05" style="flex: 1;" /><span style="color: #a1a1aa; font-size: 13px; min-width: 40px; text-align: right;">{{ (editForm.importance * 100).toFixed(0) }}%</span></div></NFormItem>
      </NForm>
      <template #action><NSpace justify="end"><NButton @click="showEditModal = false">取消</NButton><NButton type="primary" @click="saveEdit">保存</NButton></NSpace></template>
    </NModal>

    <NModal v-model:show="showLibraryModal" preset="card" :title="editingLibrary ? '编辑记忆库' : '新建记忆库'" style="width: 520px; background: #18181b;">
      <NForm label-placement="top"><NFormItem label="名称"><NInput v-model:value="libraryForm.name" /></NFormItem><NFormItem label="描述"><NInput v-model:value="libraryForm.description" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" /></NFormItem></NForm>
      <template #action><NSpace justify="end"><NButton @click="showLibraryModal = false">取消</NButton><NButton type="primary" @click="saveLibrary">保存</NButton></NSpace></template>
    </NModal>

    <NModal v-model:show="showPresetModal" preset="card" title="另存为记忆预设" style="width: 560px; background: #18181b;">
      <NForm label-placement="top"><NFormItem label="预设名称"><NInput v-model:value="presetForm.name" /></NFormItem><NFormItem label="来源记忆库"><NSelect v-model:value="presetForm.source_library_ids" multiple :options="libraryEditOptions" /></NFormItem><NFormItem label="描述"><NInput v-model:value="presetForm.description" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" /></NFormItem></NForm>
      <template #action><NSpace justify="end"><NButton @click="showPresetModal = false">取消</NButton><NButton type="primary" @click="savePreset">另存</NButton></NSpace></template>
    </NModal>
  </div>
</template>
