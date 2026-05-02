<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NCard, NDataTable, NEmpty, NForm, NFormItem, NIcon, NInput, NInputNumber, NModal,
  NPagination, NPopconfirm, NSelect, NSlider, NSpace, NSpin, NTag, useMessage,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { HelpCircleOutline } from '@vicons/ionicons5'
import { apiFetch } from '../api'
import { saveJsonExport } from '../export'
import type { MemoryCard } from '../types/memory'

const message = useMessage()
const { t } = useI18n()
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
  { label: t('memories.allLibraries'), value: '' },
  ...libraries.value.map((item) => ({ label: `${item.name}${item.card_count ? `（${item.card_count}）` : ''}`, value: item.library_id })),
])
const libraryEditOptions = computed(() => libraries.value.map((item) => ({ label: item.name, value: item.library_id })))

const scopeOptions = [
  { label: t('memories.scopeLabels.all'), value: '' },
  { label: t('memories.scopeLabels.global'), value: 'global' },
  { label: t('memories.scopeLabels.character'), value: 'character' },
  { label: t('memories.scopeLabels.conversation'), value: 'conversation' },
]

const typeOptions = [
  { label: t('memories.typeLabels.preference'), value: 'preference' },
  { label: t('memories.typeLabels.boundary'), value: 'boundary' },
  { label: t('memories.typeLabels.relationship'), value: 'relationship' },
  { label: t('memories.typeLabels.event'), value: 'event' },
  { label: t('memories.typeLabels.promise'), value: 'promise' },
  { label: t('memories.typeLabels.correction'), value: 'correction' },
  { label: t('memories.typeLabels.world_state'), value: 'world_state' },
  { label: t('memories.typeLabels.summary'), value: 'summary' },
]

const scopeEditOptions = [
  { label: t('memories.scopeLabels.global'), value: 'global' },
  { label: t('memories.scopeLabels.character'), value: 'character' },
  { label: t('memories.scopeLabels.conversation'), value: 'conversation' },
]

const columns = [
  { title: t('memories.column.library'), key: 'library_id', width: 130, render: (row: MemoryCard) => libraryName(row.library_id) },
  { title: t('memories.column.content'), key: 'content', ellipsis: { tooltip: true }, minWidth: 240 },
  { title: t('memories.column.type'), key: 'memory_type', width: 90, render: (row: MemoryCard) => typeLabel(row.memory_type ?? row.card_type) },
  { title: t('memories.column.scope'), key: 'scope', width: 80, render: (row: MemoryCard) => t(`memories.scopeLabels.${row.scope}`) || row.scope },
  { title: t('memories.column.importance'), key: 'importance', width: 80, render: (row: MemoryCard) => `${(row.importance * 100).toFixed(0)}%` },
  { title: t('memories.column.createdAt'), key: 'created_at', width: 150 },
  {
    title: t('memories.column.actions'), key: 'actions', width: 130,
    render: (row: MemoryCard) => h(NSpace, { size: 4 }, { default: () => [
      h(NButton, { size: 'tiny', type: 'info', quaternary: true, onClick: () => openEditModal(row) }, { default: () => t('common.edit') }),
      h(NPopconfirm, { positiveText: t('common.confirm'), negativeText: t('common.cancel'), onPositiveClick: () => deleteCard(row.card_id) }, {
        trigger: () => h(NButton, { size: 'tiny', type: 'error', quaternary: true }, { default: () => t('common.delete') }),
        default: () => t('common.confirm') + t('common.delete') + '?',
      }),
    ] }),
  },
]

function libraryName(libraryId: string) {
  return libraries.value.find((item) => item.library_id === libraryId)?.name || libraryId || t('memories.defaultLibrary')
}

function typeLabel(type: string) {
  const typeMap: Record<string, string> = { preference: t('memories.typeLabels.preference'), relationship: t('memories.typeLabels.relationship'), event: t('memories.typeLabels.event'), promise: t('memories.typeLabels.promise'), boundary: t('memories.typeLabels.boundary'), correction: t('memories.typeLabels.correction'), world_state: t('memories.typeLabels.world_state'), summary: t('memories.typeLabels.summary') }
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

function openEditModal(row: MemoryCard) {
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
      message.success(t('common.saved'))
      showEditModal.value = false
      fetchMemories()
    } else {
      message.error(data.message || t('common.saveFailed'))
    }
  } catch (e) {
    message.error(t('common.requestFailed'))
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
    message.error(data.message || t('common.saveFailed'))
    return
  }
  if (data.library_id) selectedLibraryId.value = data.library_id
  showLibraryModal.value = false
  message.success(t('memories.librarySaved'))
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
    message.error(data.message || t('memories.saveAsFailed'))
    return
  }
  selectedLibraryId.value = data.library_id
  showPresetModal.value = false
  message.success(t('memories.savedAsPreset'))
  fetchMemories()
}

async function deleteLibrary() {
  if (!selectedLibraryId.value) return
  const resp = await apiFetch(`/admin/memory-libraries/${selectedLibraryId.value}`, { method: 'DELETE' })
  const data = await resp.json()
  if (data.status === 'ok') {
    selectedLibraryId.value = ''
    message.success(t('memories.libraryDeleted'))
    fetchMemories()
  } else {
    message.error(data.message || t('common.deleteFailed'))
  }
}

async function deleteCard(cardId: string) {
  const resp = await apiFetch(`/admin/memories/${cardId}`, { method: 'DELETE' })
  const data = await resp.json()
  if (data.status === 'ok') {
    message.success(t('memories.memoryDeleted'))
    fetchMemories()
  } else {
    message.error(data.message || t('common.deleteFailed'))
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
    const savedPath = await saveJsonExport(`library_${selectedLibraryId.value}.json`, data)
    if (savedPath) message.success(t('memories.libraryExported'))
  } catch (e: any) {
    message.error(e.message || t('common.exportFailed'))
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
        message.success(t('memories.libraryImported', { count: result.imported_cards || 0 }))
        fetchMemories()
      } else {
        message.error(result.message || t('common.importFailed'))
      }
    } catch (e: any) {
      message.error(t('memories.importFailed', { error: e.message || e }))
    }
  }
  input.click()
}

const showSillyTavernModal = ref(false)
const showExtractModal = ref(false)
const sillyTavernImporting = ref(false)
const stForm = ref({ content: '', filename: '', character_id: '' })
const extractForm = ref({ conversation_id: '', character_id: '', max_pairs: 50, turns_imported: 0 })
const router = useRouter()
const helpModal = ref(false)

function openSillyTavernImport() {
  stForm.value = { content: '', filename: '', character_id: '' }
  showSillyTavernModal.value = true
}

function pickSillyTavernFile() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.jsonl,.json,.txt'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    stForm.value.filename = file.name
    stForm.value.content = await file.text()
  }
  input.click()
}

async function confirmSillyTavernImport() {
  if (!stForm.value.content.trim()) {
    message.warning(t('memories.stPickFile'))
    return
  }
  sillyTavernImporting.value = true
  try {
    const resp = await apiFetch('/admin/import/sillytavern', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content: stForm.value.content,
        character_id: stForm.value.character_id || undefined,
      }),
    })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || t('memories.importFailedShort'))
    showSillyTavernModal.value = false
    extractForm.value = {
      conversation_id: data.conversation_id,
      character_id: data.character_name || stForm.value.character_id || '',
      max_pairs: 50,
      turns_imported: data.turns_imported || 0,
    }
    showExtractModal.value = true
  } catch (e: any) {
    message.error(e.message || String(e))
  }
  sillyTavernImporting.value = false
}

async function confirmExtract() {
  try {
    const resp = await apiFetch(`/admin/import/${extractForm.value.conversation_id}/extract-memories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        character_id: extractForm.value.character_id || undefined,
        max_pairs: extractForm.value.max_pairs,
      }),
    })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || t('memories.extractFailed'))
    showExtractModal.value = false
    message.success(t('memories.stExtractDone', { extracted: data.extracted_pairs, total: data.total_pairs }))
    router.push('/inbox')
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

function skipExtract() {
  showExtractModal.value = false
  message.success(t('memories.stImportedNoExtract'))
}

onMounted(fetchMemories)
</script>

<template>
  <div>
    <div style="margin-bottom: 28px; display: flex; justify-content: space-between; align-items: flex-start;">
      <div>
        <h1 style="font-size: 24px; font-weight: 600; color: #e4e4e7; margin-bottom: 4px;">{{ $t('memories.title') }}</h1>
        <p style="color: #71717a; font-size: 14px; margin: 0;">{{ $t('memories.subtitle') }}</p>
      </div>
      <NButton quaternary @click="helpModal = true">
        <template #icon><NIcon><HelpCircleOutline /></NIcon></template>
        {{ $t('common.help') }}
      </NButton>
    </div>

    <NCard style="background: #18181b; border: 1px solid #27272a;">
      <NSpace justify="space-between" align="center" style="margin-bottom: 16px; width: 100%;" wrap>
        <NSpace wrap>
          <NSelect v-model:value="selectedLibraryId" :options="libraryOptions" :placeholder="$t('memories.selectLibrary')" style="width: 260px;" size="small" @update:value="handleFilterChange" />
          <NSelect :options="scopeOptions" :placeholder="$t('memories.filterScope')" style="width: 140px;" :value="scopeFilter || ''" size="small" @update:value="(val) => { scopeFilter = val || null; handleFilterChange() }" />
          <NTag size="small" round style="color: #71717a;">{{ $t('memories.totalCount', { count: total }) }}</NTag>
        </NSpace>
        <NSpace wrap>
          <NButton size="small" @click="openCreateModal">{{ $t('memories.addEntry') }}</NButton>
          <NButton size="small" @click="openCreateLibrary">{{ $t('memories.createLibrary') }}</NButton>
          <NButton size="small" :disabled="!selectedLibraryId" @click="openEditLibrary">{{ $t('memories.editLibrary') }}</NButton>
          <NButton size="small" :disabled="!selectedLibraryId" @click="openPresetModal">{{ $t('memories.saveAsPreset') }}</NButton>
          <NPopconfirm :positive-text="$t('common.confirm')" :negative-text="$t('common.cancel')" @positive-click="deleteLibrary"><template #trigger><NButton size="small" type="error" quaternary :disabled="!selectedLibraryId">{{ $t('memories.deleteLibrary') }}</NButton></template>{{ $t('memories.deleteLibraryConfirm') }}</NPopconfirm>
          <NButton size="small" :disabled="!selectedLibraryId" @click="exportLibrary">{{ $t('memories.exportLibrary') }}</NButton>
          <NButton size="small" @click="triggerImportLibrary">{{ $t('memories.importLibrary') }}</NButton>
          <NButton size="small" @click="openSillyTavernImport">{{ $t('memories.importSillyTavern') }}</NButton>
          <NButton size="small" @click="fetchMemories" quaternary style="color: #71717a;">{{ $t('common.refresh') }}</NButton>
        </NSpace>
      </NSpace>

      <NSpin :show="loading">
        <NDataTable v-if="memories.length > 0" :columns="columns" :data="memories" :bordered="false" size="small" :single-line="false" style="--n-td-color: #18181b; --n-th-color: #1f1f23;" />
        <NEmpty v-else :description="$t('memories.noData')" style="padding: 60px 0;"><template #extra><p style="color: #52525b; font-size: 13px;">{{ $t('memories.noDataHint') }}</p></template></NEmpty>
      </NSpin>

      <div v-if="total > pageSize" style="display: flex; justify-content: center; margin-top: 16px;">
        <NPagination :page="page" :page-size="pageSize" :item-count="total" @update:page="(p) => { page = p; fetchMemories() }" />
      </div>
    </NCard>

    <NModal v-model:show="showEditModal" preset="card" :title="editingCard ? $t('memories.editMemory') : $t('memories.createMemory')" style="width: 560px; background: #18181b;">
      <NForm label-placement="top" :show-feedback="false" style="gap: 16px; display: flex; flex-direction: column;">
        <NFormItem :label="$t('memories.library')"><NSelect v-model:value="editForm.library_id" :options="libraryEditOptions" /></NFormItem>
        <NFormItem :label="$t('memories.memoryContent')"><NInput v-model:value="editForm.content" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :placeholder="$t('memories.inputContent')" /></NFormItem>
        <div style="display: flex; gap: 12px;">
          <NFormItem :label="$t('memories.type')" style="flex: 1;"><NSelect v-model:value="editForm.card_type" :options="typeOptions" /></NFormItem>
          <NFormItem :label="$t('memories.scope')" style="flex: 1;"><NSelect v-model:value="editForm.scope" :options="scopeEditOptions" /></NFormItem>
        </div>
        <NFormItem :label="$t('memories.importance')"><div style="display: flex; align-items: center; gap: 12px; width: 100%;"><NSlider v-model:value="editForm.importance" :min="0" :max="1" :step="0.05" style="flex: 1;" /><span style="color: #a1a1aa; font-size: 13px; min-width: 40px; text-align: right;">{{ (editForm.importance * 100).toFixed(0) }}%</span></div></NFormItem>
      </NForm>
      <template #action><NSpace justify="end"><NButton @click="showEditModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" @click="saveEdit">{{ $t('common.save') }}</NButton></NSpace></template>
    </NModal>

    <NModal v-model:show="showLibraryModal" preset="card" :title="editingLibrary ? $t('memories.editLibraryTitle') : $t('memories.createLibraryTitle')" style="width: 520px; background: #18181b;">
      <NForm label-placement="top"><NFormItem :label="$t('memories.libraryName')"><NInput v-model:value="libraryForm.name" /></NFormItem><NFormItem :label="$t('memories.description')"><NInput v-model:value="libraryForm.description" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" /></NFormItem></NForm>
      <template #action><NSpace justify="end"><NButton @click="showLibraryModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" @click="saveLibrary">{{ $t('common.save') }}</NButton></NSpace></template>
    </NModal>

    <NModal v-model:show="showPresetModal" preset="card" :title="$t('memories.saveAsPresetTitle')" style="width: 560px; background: #18181b;">
      <NForm label-placement="top"><NFormItem :label="$t('memories.presetName')"><NInput v-model:value="presetForm.name" /></NFormItem><NFormItem :label="$t('memories.sourceLibraries')"><NSelect v-model:value="presetForm.source_library_ids" multiple :options="libraryEditOptions" /></NFormItem><NFormItem :label="$t('memories.description')"><NInput v-model:value="presetForm.description" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" /></NFormItem></NForm>
      <template #action><NSpace justify="end"><NButton @click="showPresetModal = false">{{ $t('common.cancel') }}</NButton><NButton type="primary" @click="savePreset">{{ $t('memories.saveAs') }}</NButton></NSpace></template>
    </NModal>

    <NModal v-model:show="showSillyTavernModal" preset="card" :title="$t('memories.importSillyTavern')" style="width: 560px; background: #18181b;">
      <NForm label-placement="top">
        <NFormItem :label="$t('memories.stFile')">
          <NSpace :wrap="false">
            <NButton @click="pickSillyTavernFile">{{ $t('memories.stPickFileButton') }}</NButton>
            <span v-if="stForm.filename" style="color: #d4d4d8; font-size: 13px; align-self: center;">{{ stForm.filename }}</span>
            <span v-else style="color: #71717a; font-size: 13px; align-self: center;">{{ $t('memories.stNoFile') }}</span>
          </NSpace>
        </NFormItem>
        <NFormItem :label="$t('memories.stCharacterId')">
          <NInput v-model:value="stForm.character_id" :placeholder="$t('memories.stCharacterIdPlaceholder')" />
        </NFormItem>
        <p style="color: #71717a; font-size: 12px; margin: 0;">{{ $t('memories.stHint') }}</p>
      </NForm>
      <template #action>
        <NSpace justify="end">
          <NButton @click="showSillyTavernModal = false">{{ $t('common.cancel') }}</NButton>
          <NButton type="primary" :loading="sillyTavernImporting" @click="confirmSillyTavernImport">{{ $t('memories.stImport') }}</NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal v-model:show="showExtractModal" preset="card" :title="$t('memories.stExtractTitle')" style="width: 480px; background: #18181b;">
      <p style="color: #d4d4d8; font-size: 14px; margin-top: 0;">
        {{ $t('memories.stExtractDesc', { count: extractForm.turns_imported }) }}
      </p>
      <NForm label-placement="top">
        <NFormItem :label="$t('memories.stMaxPairs')">
          <NInputNumber v-model:value="extractForm.max_pairs" :min="1" :max="500" style="width: 100%;" />
        </NFormItem>
      </NForm>
      <template #action>
        <NSpace justify="end">
          <NButton @click="skipExtract">{{ $t('memories.stSkipExtract') }}</NButton>
          <NButton type="primary" @click="confirmExtract">{{ $t('memories.stRunExtract') }}</NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal v-model:show="helpModal" preset="card" :title="$t('memories.help.title')" style="width: 640px; background: #18181b;" :mask-closable="true">
      <div class="help-content">
        <p>{{ $t('memories.help.intro') }}</p>
        <p><strong>{{ $t('memories.help.libraryTitle') }}</strong>: {{ $t('memories.help.library') }}</p>
        <p><strong>{{ $t('memories.help.presetTitle') }}</strong>: {{ $t('memories.help.preset') }}</p>
        <p><strong>{{ $t('memories.help.scopeTitle') }}</strong>: {{ $t('memories.help.scope') }}</p>
        <p><strong>{{ $t('memories.help.typeTitle') }}</strong>: {{ $t('memories.help.type') }}</p>
        <p><strong>{{ $t('memories.help.importTitle') }}</strong>: {{ $t('memories.help.import') }}</p>
        <p><strong>{{ $t('memories.help.flowTitle') }}</strong>: {{ $t('memories.help.flow') }}</p>
      </div>
    </NModal>
  </div>
</template>

<style scoped>
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
</style>
