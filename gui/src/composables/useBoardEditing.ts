import { ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { apiFetch } from '../api'
import type { StateRow, StateTable } from '../components/state/types'

export function useBoardEditing(options: {
  conversationId: Ref<string>
  adminToken: Ref<string>
  saving: Ref<boolean>
  fetchBoard: () => Promise<void>
}) {
  const { conversationId, adminToken, saving } = options
  const { fetchBoard } = options
  const { t } = useI18n()
  const message = useMessage()

  function authHeaders(json = false) {
    const headers: Record<string, string> = {}
    if (json) headers['Content-Type'] = 'application/json'
    if (adminToken.value.trim()) headers.Authorization = `Bearer ${adminToken.value.trim()}`
    return headers
  }

  // ── Refs ───────────────────────────────────────────────
  const showEditModal = ref(false)
  const editingTable = ref<StateTable | null>(null)
  const editingRow = ref<StateRow | null>(null)
  const editValues = ref<Record<string, string>>({})
  const editMeta = ref({ priority: 80, confidence: 0.9 })
  const checkedRowKeys = ref<string[]>([])
  const batchPriority = ref<number | null>(80)

  // ── Row open / save ──────────────────────────────────
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

  function duplicateRow(table: StateTable, row: StateRow) {
    editingTable.value = table
    editingRow.value = null
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

  // ── Batch operations ───────────────────────────────────
  async function batchAction(action: string, value?: any) {
    if (!checkedRowKeys.value.length) return
    saving.value = true
    try {
      const resp = await apiFetch('/admin/state/table-rows/batch', {
        method: 'POST',
        headers: authHeaders(true),
        body: JSON.stringify({ action, row_ids: checkedRowKeys.value, value }),
      })
      const data = await resp.json()
      if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message)
      message.success(t('state.batch.done', { count: data.affected }))
      checkedRowKeys.value = []
      await fetchBoard()
    } catch (error: any) {
      message.error(error.message || t('state.batch.failed'))
    } finally {
      saving.value = false
    }
  }

  function onCellSaved(row: StateRow, columnKey: string, value: string) {
    if (row.values) row.values[columnKey] = value
  }

  return {
    showEditModal,
    editingTable,
    editingRow,
    editValues,
    editMeta,
    checkedRowKeys,
    batchPriority,
    openCreate,
    openEdit,
    duplicateRow,
    saveRow,
    deleteRow,
    batchAction,
    onCellSaved,
  }
}
