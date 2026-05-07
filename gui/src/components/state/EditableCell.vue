<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { apiFetch } from '../../api'

const props = defineProps<{
  value: string
  rowId: string
  columnKey: string
  maxChars?: number
  adminToken?: string
}>()

const emit = defineEmits<{
  saved: [columnKey: string, newValue: string]
}>()

const editing = ref(false)
const localValue = ref('')
const saving = ref(false)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const showHistory = ref(false)
const historyItems = ref<any[]>([])
const historyLoading = ref(false)

function startEdit() {
  localValue.value = props.value || ''
  editing.value = true
  nextTick(() => inputRef.value?.focus())
}

function cancelEdit() {
  editing.value = false
}

async function commitEdit() {
  if (!editing.value) return
  const trimmed = localValue.value
  if (trimmed === (props.value || '')) {
    editing.value = false
    return
  }
  saving.value = true
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (props.adminToken) headers['Authorization'] = `Bearer ${props.adminToken}`
    const resp = await apiFetch(
      `/admin/state/table-rows/${encodeURIComponent(props.rowId)}/cells/${encodeURIComponent(props.columnKey)}`,
      { method: 'PATCH', headers, body: JSON.stringify({ value: trimmed }) },
    )
    const data = await resp.json()
    if (resp.ok && data.status === 'ok') {
      emit('saved', props.columnKey, trimmed)
    }
  } catch { /* silent */ }
  saving.value = false
  editing.value = false
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    cancelEdit()
  } else if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    commitEdit()
  }
}

async function toggleHistory(e: Event) {
  e.stopPropagation()
  if (showHistory.value) {
    showHistory.value = false
    return
  }
  historyLoading.value = true
  showHistory.value = true
  try {
    const headers: Record<string, string> = {}
    if (props.adminToken) headers['Authorization'] = `Bearer ${props.adminToken}`
    const resp = await apiFetch(
      `/admin/state/table-rows/${encodeURIComponent(props.rowId)}/cells/${encodeURIComponent(props.columnKey)}/history?limit=10`,
      { headers },
    )
    const data = await resp.json()
    historyItems.value = data.items || []
  } catch { /* silent */ }
  historyLoading.value = false
}

async function restoreValue(val: string) {
  saving.value = true
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (props.adminToken) headers['Authorization'] = `Bearer ${props.adminToken}`
    const resp = await apiFetch(
      `/admin/state/table-rows/${encodeURIComponent(props.rowId)}/cells/${encodeURIComponent(props.columnKey)}`,
      { method: 'PATCH', headers, body: JSON.stringify({ value: val }) },
    )
    const data = await resp.json()
    if (resp.ok && data.status === 'ok') {
      emit('saved', props.columnKey, val)
      showHistory.value = false
    }
  } catch { /* silent */ }
  saving.value = false
}
</script>

<template>
  <div class="editable-cell" @click.stop="startEdit">
    <textarea
      v-if="editing"
      ref="inputRef"
      v-model="localValue"
      class="cell-input"
      :maxlength="maxChars || undefined"
      :disabled="saving"
      rows="2"
      @blur="commitEdit"
      @keydown="onKeydown"
    />
    <template v-else>
      <span class="cell-display" :class="{ empty: !value }">{{ value || '-' }}</span>
      <span class="history-icon" title="历史" @click.stop="toggleHistory">⏱</span>
    </template>
    <div v-if="showHistory" class="history-popup" @click.stop>
      <div v-if="historyLoading" style="padding: 8px; color: #888;">加载中...</div>
      <div v-else-if="!historyItems.length" style="padding: 8px; color: #888;">无历史记录</div>
      <div v-else>
        <div v-for="item in historyItems" :key="item.event_id" class="history-item">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="color: #a1a1aa; font-size: 11px;">{{ item.created_at }}</span>
            <span v-if="item.old_value != null" class="restore-btn" @click.stop="restoreValue(item.old_value)">恢复</span>
          </div>
          <div v-if="item.new_value != null" style="color: #63e2b7;">→ {{ item.new_value }}</div>
          <div v-if="item.old_value != null" style="color: #e88080; text-decoration: line-through;">{{ item.old_value }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.editable-cell {
  cursor: text;
  min-height: 28px;
  width: 100%;
  position: relative;
}
.cell-display {
  display: block;
  padding: 2px 0;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
}
.cell-display.empty {
  color: #666;
}
.history-icon {
  position: absolute;
  top: 0;
  right: 0;
  cursor: pointer;
  font-size: 11px;
  opacity: 0;
  transition: opacity 0.15s;
}
.editable-cell:hover .history-icon {
  opacity: 0.6;
}
.history-icon:hover {
  opacity: 1 !important;
}
.cell-input {
  width: 100%;
  min-height: 48px;
  padding: 4px 6px;
  border: 1px solid #63e2b7;
  border-radius: 3px;
  background: #1a1a2e;
  color: #e0e0e0;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
  outline: none;
  font-family: inherit;
}
.cell-input:focus {
  border-color: #63e2b7;
  box-shadow: 0 0 0 2px rgba(99, 226, 183, 0.15);
}
.history-popup {
  position: absolute;
  top: 100%;
  right: 0;
  z-index: 100;
  min-width: 240px;
  max-width: 360px;
  max-height: 260px;
  overflow-y: auto;
  background: #1e1e2e;
  border: 1px solid #444;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  padding: 4px;
}
.history-item {
  padding: 6px 8px;
  border-bottom: 1px solid #333;
  font-size: 12px;
}
.history-item:last-child {
  border-bottom: none;
}
.restore-btn {
  cursor: pointer;
  color: #f0a020;
  font-size: 11px;
}
.restore-btn:hover {
  text-decoration: underline;
}
</style>
