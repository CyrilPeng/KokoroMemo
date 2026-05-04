<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NAlert, NButton, NCard, NDataTable, NDescriptions, NDescriptionsItem,
  NEmpty, NForm, NFormItem, NGrid, NGridItem, NInput, NModal, NPopconfirm,
  NSelect, NSpace, NSpin, NTag, useMessage,
} from 'naive-ui'
import { apiFetch } from '../api'
import { saveJsonExport } from '../export'

type Conversation = Record<string, any>
type Character = Record<string, any>

const router = useRouter()
const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const batchSaving = ref(false)
const conversations = ref<Conversation[]>([])
const characters = ref<Character[]>([])
const keyword = ref('')
const characterFilter = ref<string | null>(null)
const clientFilter = ref<string | null>(null)
const checkedConversationIds = ref<string[]>([])
const batchCharacterId = ref<string | null>(null)
const showEditModal = ref(false)
const showPreviewModal = ref(false)
const showImportModal = ref(false)
const previewLoading = ref(false)
const editing = ref<Conversation | null>(null)
const editForm = ref({ title: '', character_id: null as string | null })
const previewConversation = ref<Conversation | null>(null)
const previewMessages = ref<any[]>([])
const importText = ref('')
const importTargetId = ref('')
const importOverwrite = ref(false)

function displayName(item: Conversation) {
  return item.title?.trim() || item.conversation_id || '未命名会话'
}

function characterName(characterId?: string | null) {
  if (!characterId) return '未知角色'
  const character = characters.value.find((item) => item.character_id === characterId)
  return character?.display_name || characterId
}

function briefText(value?: string | null, maxLength = 72) {
  const text = (value || '').replace(/\s+/g, ' ').trim()
  if (!text) return '暂无'
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text
}

const characterOptions = computed(() => characters.value.map((item) => ({
  label: item.display_name ? `${item.display_name}（${item.character_id}）` : item.character_id,
  value: item.character_id,
})))

const characterFilterOptions = computed(() => [
  { label: '全部角色', value: null },
  ...characterOptions.value,
])

const clientFilterOptions = computed(() => {
  const clients = Array.from(new Set(conversations.value.map((item) => item.client_name).filter(Boolean)))
  return [{ label: '全部客户端', value: null }, ...clients.map((client) => ({ label: client, value: client }))]
})

const filteredConversations = computed(() => conversations.value.filter((item) => {
  const query = keyword.value.trim().toLowerCase()
  const diagnostics = (item.diagnostics || []).map((diag: any) => diag.label).join(' ')
  const searchable = `${item.title || ''} ${item.conversation_id || ''} ${item.character_id || ''} ${item.character_display_name || ''} ${item.client_name || ''} ${item.last_user_message || ''} ${item.last_assistant_message || ''} ${diagnostics}`.toLowerCase()
  if (query && !searchable.includes(query)) return false
  if (characterFilter.value && item.character_id !== characterFilter.value) return false
  if (clientFilter.value && item.client_name !== clientFilter.value) return false
  return true
}))

const selectedConversations = computed(() => conversations.value.filter((item) => checkedConversationIds.value.includes(item.conversation_id)))

const columns = computed(() => [
  { type: 'selection' as const, width: 48 },
  {
    title: '会话', key: 'title', minWidth: 240, render: (row: Conversation) => h('div', [
      h('div', { style: 'font-weight: 600;' }, displayName(row)),
      h('div', { style: 'font-size: 12px; color: #71717a;' }, row.conversation_id),
    ]),
  },
  { title: '角色', key: 'character_id', minWidth: 180, render: (row: Conversation) => characterName(row.character_id) },
  { title: '客户端', key: 'client_name', width: 130, render: (row: Conversation) => row.client_name || '-' },
  {
    title: '最近消息', key: 'summary', minWidth: 260, render: (row: Conversation) => h('div', { class: 'summary-cell' }, [
      h('div', [h('span', { class: 'summary-role' }, '用户：'), briefText(row.last_user_message, 56)]),
      h('div', [h('span', { class: 'summary-role' }, '助手：'), briefText(row.last_assistant_message, 56)]),
      h('div', { class: 'summary-count' }, `${row.message_count || 0} 条消息，${row.turn_count || 0} 个轮次`),
    ]),
  },
  { title: '最近活跃', key: 'last_seen_at', width: 170, render: (row: Conversation) => row.last_seen_at || '-' },
  {
    title: '诊断', key: 'diagnostics', minWidth: 180, render: (row: Conversation) => {
      const diagnostics = row.diagnostics || []
      if (!diagnostics.length) return h(NTag, { size: 'small', type: 'success' }, { default: () => '正常' })
      return h(NSpace, { size: 4 }, {
        default: () => diagnostics.map((diag: any) => h(NTag, { size: 'small', type: diag.type || 'default' }, { default: () => diag.label })),
      })
    },
  },
  {
    title: '操作', key: 'actions', width: 300, render: (row: Conversation) => h(NSpace, { size: 6 }, {
      default: () => [
        h(NButton, { size: 'tiny', quaternary: true, onClick: () => openPreview(row) }, { default: () => '预览' }),
        h(NButton, { size: 'tiny', quaternary: true, onClick: () => openEdit(row) }, { default: () => '编辑' }),
        h(NButton, { size: 'tiny', quaternary: true, onClick: () => openState(row) }, { default: () => '状态板' }),
        h(NButton, { size: 'tiny', quaternary: true, onClick: () => exportConversation(row) }, { default: () => '导出' }),
        h(NPopconfirm, { onPositiveClick: () => deleteConversation(row) }, {
          trigger: () => h(NButton, { size: 'tiny', type: 'error', quaternary: true }, { default: () => '删除' }),
          default: () => '删除该会话记录？不会删除磁盘聊天文件。',
        }),
      ],
    }),
  },
])

function conversationRowKey(row: Conversation) {
  return row.conversation_id
}

async function fetchAll() {
  loading.value = true
  try {
    const [convResp, charResp] = await Promise.all([
      apiFetch('/admin/conversations?limit=200', { timeoutMs: 8000 }),
      apiFetch('/admin/characters', { timeoutMs: 8000 }),
    ])
    const convData = await convResp.json()
    const charData = await charResp.json()
    if (!convResp.ok) throw new Error(convData.detail || convData.message || '加载会话失败')
    if (!charResp.ok) throw new Error(charData.detail || charData.message || '加载角色失败')
    conversations.value = convData.items || []
    characters.value = charData.items || []
  } catch (error: any) {
    message.error(error.message || '加载会话失败')
  } finally {
    loading.value = false
  }
}

function openEdit(row: Conversation) {
  editing.value = row
  editForm.value = { title: row.title || '', character_id: row.character_id || null }
  showEditModal.value = true
}

async function saveEdit() {
  if (!editing.value) return
  saving.value = true
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(editing.value.conversation_id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editForm.value),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '保存会话失败')
    const index = conversations.value.findIndex((item) => item.conversation_id === editing.value?.conversation_id)
    if (index >= 0) conversations.value[index] = { ...conversations.value[index], ...data.item }
    message.success('会话已保存')
    showEditModal.value = false
  } catch (error: any) {
    message.error(error.message || '保存会话失败')
  } finally {
    saving.value = false
  }
}

async function openPreview(row: Conversation) {
  previewConversation.value = row
  previewMessages.value = []
  showPreviewModal.value = true
  previewLoading.value = true
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(row.conversation_id)}/preview?limit=24`)
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || data.message || '加载预览失败')
    previewConversation.value = { ...row, ...(data.conversation || {}) }
    previewMessages.value = data.messages || []
  } catch (error: any) {
    message.error(error.message || '加载预览失败')
  } finally {
    previewLoading.value = false
  }
}

function openState(row: Conversation) {
  localStorage.setItem('kokoromemo.stateConversationId', row.conversation_id)
  router.push('/state')
}

async function deleteConversation(row: Conversation) {
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(row.conversation_id)}`, { method: 'DELETE' })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '删除会话失败')
    conversations.value = conversations.value.filter((item) => item.conversation_id !== row.conversation_id)
    message.success('会话已删除')
  } catch (error: any) {
    message.error(error.message || '删除会话失败')
  }
}

async function exportConversation(row: Conversation) {
  try {
    const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(row.conversation_id)}/export`)
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || data.message || '导出会话配置失败')
    const savedPath = await saveJsonExport(`conversation_${row.conversation_id}.json`, data)
    if (savedPath) message.success('会话配置已导出')
  } catch (error: any) {
    message.error(error.message || '导出会话配置失败')
  }
}

function openImportModal() {
  importText.value = ''
  importTargetId.value = ''
  importOverwrite.value = false
  showImportModal.value = true
}

function triggerImportFile() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json,application/json'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    importText.value = await file.text()
  }
  input.click()
}

async function importConversationConfig() {
  try {
    const payload = JSON.parse(importText.value)
    if (importTargetId.value.trim()) payload.target_conversation_id = importTargetId.value.trim()
    payload.overwrite_state = importOverwrite.value
    const resp = await apiFetch('/admin/conversations/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '导入会话配置失败')
    message.success(`已导入 ${data.imported_items || 0} 条状态项`)
    showImportModal.value = false
    await fetchAll()
  } catch (error: any) {
    message.error(error.message || '导入会话配置失败')
  }
}

async function batchAssignCharacter() {
  if (!checkedConversationIds.value.length || !batchCharacterId.value) return
  batchSaving.value = true
  try {
    for (const conversationId of checkedConversationIds.value) {
      const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ character_id: batchCharacterId.value }),
      })
      const data = await resp.json()
      if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || `更新会话 ${conversationId} 失败`)
      const index = conversations.value.findIndex((item) => item.conversation_id === conversationId)
      if (index >= 0) conversations.value[index] = { ...conversations.value[index], ...data.item }
    }
    message.success(`已更新 ${checkedConversationIds.value.length} 个会话的角色归属`)
  } catch (error: any) {
    message.error(error.message || '批量改归属失败')
  } finally {
    batchSaving.value = false
  }
}

async function batchApplyDefaults() {
  if (!selectedConversations.value.length) return
  const grouped = new Map<string, string[]>()
  for (const item of selectedConversations.value) {
    if (!item.character_id) continue
    grouped.set(item.character_id, [...(grouped.get(item.character_id) || []), item.conversation_id])
  }
  if (!grouped.size) {
    message.warning('所选会话没有可套用默认策略的角色归属')
    return
  }
  batchSaving.value = true
  try {
    let updated = 0
    for (const [characterId, conversationIds] of grouped.entries()) {
      const resp = await apiFetch(`/admin/characters/${encodeURIComponent(characterId)}/apply-defaults`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_ids: conversationIds, apply_policy: true, apply_mounts: true, overwrite_existing: true }),
      })
      const data = await resp.json()
      if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || `套用角色 ${characterName(characterId)} 默认策略失败`)
      updated += data.updated || 0
    }
    message.success(`已为 ${updated} 个会话套用角色默认策略`)
    await fetchAll()
  } catch (error: any) {
    message.error(error.message || '批量套用默认策略失败')
  } finally {
    batchSaving.value = false
  }
}

async function batchDeleteConversations() {
  if (!checkedConversationIds.value.length) return
  batchSaving.value = true
  try {
    for (const conversationId of checkedConversationIds.value) {
      const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId)}`, { method: 'DELETE' })
      const data = await resp.json()
      if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || `删除会话 ${conversationId} 失败`)
    }
    conversations.value = conversations.value.filter((item) => !checkedConversationIds.value.includes(item.conversation_id))
    message.success(`已删除 ${checkedConversationIds.value.length} 个会话记录`)
    checkedConversationIds.value = []
  } catch (error: any) {
    message.error(error.message || '批量删除会话失败')
  } finally {
    batchSaving.value = false
  }
}

onMounted(fetchAll)
</script>

<template>
  <div class="conversations-page">
    <NSpace vertical size="large">
      <NCard>
        <template #header>会话管理</template>
        <NSpace vertical>
          <NAlert type="info" :show-icon="false">
            会话名称只是便于辨认的别名，后端仍使用原始 conversation_id 识别会话。
          </NAlert>
          <NGrid cols="1 m:24" item-responsive responsive="screen" :x-gap="12" :y-gap="12">
            <NGridItem span="1 m:9"><NInput v-model:value="keyword" placeholder="搜索名称、ID、角色、客户端、最近消息或诊断" clearable /></NGridItem>
            <NGridItem span="1 m:6"><NSelect v-model:value="characterFilter" :options="characterFilterOptions" filterable /></NGridItem>
            <NGridItem span="1 m:5"><NSelect v-model:value="clientFilter" :options="clientFilterOptions" /></NGridItem>
            <NGridItem span="1 m:4"><NSpace justify="end"><NButton @click="openImportModal">导入</NButton><NButton :loading="loading" @click="fetchAll">刷新</NButton></NSpace></NGridItem>
          </NGrid>
          <NAlert v-if="checkedConversationIds.length" type="info" :show-icon="false">
            <NSpace align="center" :wrap="true">
              <span>已选择 {{ checkedConversationIds.length }} 个会话</span>
              <NSelect v-model:value="batchCharacterId" :options="characterOptions" filterable clearable placeholder="批量改归属到角色" style="width: min(320px, 80vw)" />
              <NButton size="small" type="primary" :loading="batchSaving" :disabled="!batchCharacterId" @click="batchAssignCharacter">改归属</NButton>
              <NButton size="small" :loading="batchSaving" @click="batchApplyDefaults">套用默认策略</NButton>
              <NPopconfirm @positive-click="batchDeleteConversations">
                <template #trigger><NButton size="small" type="error" :loading="batchSaving">批量删除</NButton></template>
                删除选中的会话记录？不会删除磁盘聊天文件。
              </NPopconfirm>
              <NButton size="small" quaternary @click="checkedConversationIds = []">清空选择</NButton>
            </NSpace>
          </NAlert>
        </NSpace>
      </NCard>

      <NSpin :show="loading">
        <NCard>
          <NDataTable
            v-if="filteredConversations.length"
            v-model:checked-row-keys="checkedConversationIds"
            :columns="columns"
            :data="filteredConversations"
            :row-key="conversationRowKey"
            :pagination="{ pageSize: 12 }"
            :scroll-x="1420"
          />
          <NEmpty v-else description="暂无会话或没有匹配结果" />
        </NCard>
      </NSpin>
    </NSpace>

    <NModal v-model:show="showEditModal" preset="card" title="编辑会话" style="width: min(560px, 96vw)">
      <NForm label-placement="top">
        <NFormItem label="会话名称">
          <NInput v-model:value="editForm.title" placeholder="例如：芙莉莲主线第 3 章" clearable />
        </NFormItem>
        <NFormItem label="角色归属">
          <NSelect v-model:value="editForm.character_id" :options="characterOptions" filterable clearable placeholder="选择角色" />
        </NFormItem>
        <NFormItem label="原始会话 ID">
          <NInput :value="editing?.conversation_id || ''" readonly />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showEditModal = false">取消</NButton>
          <NButton type="primary" :loading="saving" @click="saveEdit">保存</NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal v-model:show="showPreviewModal" preset="card" title="会话预览" style="width: min(820px, 96vw)">
      <NSpin :show="previewLoading">
        <NSpace vertical>
          <NDescriptions v-if="previewConversation" bordered size="small" :column="2">
            <NDescriptionsItem label="会话名称">{{ displayName(previewConversation) }}</NDescriptionsItem>
            <NDescriptionsItem label="角色">{{ characterName(previewConversation.character_id) }}</NDescriptionsItem>
            <NDescriptionsItem label="客户端">{{ previewConversation.client_name || '-' }}</NDescriptionsItem>
            <NDescriptionsItem label="最近活跃">{{ previewConversation.last_seen_at || '-' }}</NDescriptionsItem>
            <NDescriptionsItem label="消息数量">{{ previewConversation.message_count || 0 }} 条消息，{{ previewConversation.turn_count || 0 }} 个轮次</NDescriptionsItem>
            <NDescriptionsItem label="原始 ID">{{ previewConversation.conversation_id }}</NDescriptionsItem>
          </NDescriptions>
          <NEmpty v-if="!previewMessages.length" description="暂无可预览消息" />
          <div v-else class="preview-list">
            <div v-for="(item, index) in previewMessages" :key="index" class="preview-message">
              <div class="preview-role">{{ item.name || item.role }}</div>
              <div class="preview-content">{{ item.content || '-' }}</div>
            </div>
          </div>
        </NSpace>
      </NSpin>
    </NModal>

    <NModal v-model:show="showImportModal" preset="card" title="导入会话配置" style="width: min(720px, 96vw)">
      <NSpace vertical>
        <NAlert type="info" :show-icon="false">可导入从会话管理或状态板导出的 JSON 配置，包含状态板模板、挂载库和状态项。</NAlert>
        <NSpace>
          <NButton @click="triggerImportFile">选择 JSON 文件</NButton>
          <NPopconfirm @positive-click="importOverwrite = !importOverwrite">
            <template #trigger><NTag :type="importOverwrite ? 'warning' : 'default'">{{ importOverwrite ? '覆盖已有状态' : '追加导入状态' }}</NTag></template>
            切换导入模式？覆盖模式会先清空目标会话已有状态项。
          </NPopconfirm>
        </NSpace>
        <NForm label-placement="top">
          <NFormItem label="目标会话 ID（留空则使用导出文件中的 ID）">
            <NInput v-model:value="importTargetId" placeholder="例如：my_conversation_id" clearable />
          </NFormItem>
          <NFormItem label="JSON 内容">
            <NInput v-model:value="importText" type="textarea" :autosize="{ minRows: 8, maxRows: 18 }" placeholder="粘贴导出的会话配置 JSON" />
          </NFormItem>
        </NForm>
      </NSpace>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showImportModal = false">取消</NButton>
          <NButton type="primary" :disabled="!importText.trim()" @click="importConversationConfig">导入</NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.conversations-page {
  padding: 20px;
}

.summary-cell {
  line-height: 1.55;
}

.summary-role,
.summary-count {
  color: #a1a1aa;
  font-size: 12px;
}

.preview-list {
  max-height: 60vh;
  overflow: auto;
}

.preview-message {
  padding: 10px 12px;
  border: 1px solid #27272a;
  border-radius: 8px;
  margin-bottom: 10px;
  background: #18181b;
}

.preview-role {
  color: #a1a1aa;
  font-size: 12px;
  margin-bottom: 6px;
}

.preview-content {
  white-space: pre-wrap;
  color: #e4e4e7;
  line-height: 1.7;
}

@media (max-width: 768px) {
  .conversations-page {
    padding: 0;
  }
}
</style>
