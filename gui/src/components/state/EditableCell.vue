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
    <span v-else class="cell-display" :class="{ empty: !value }">{{ value || '-' }}</span>
  </div>
</template>

<style scoped>
.editable-cell {
  cursor: text;
  min-height: 28px;
  width: 100%;
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
</style>
