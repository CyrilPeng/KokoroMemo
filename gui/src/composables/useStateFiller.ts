import { ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { apiFetch } from '../api'

export function useStateFiller(options: {
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
  const showFillModal = ref(false)
  const showFillPreviewModal = ref(false)
  const fillPreviewOps = ref<any[]>([])
  const showUndoAlert = ref(false)
  const lastFillEventIds = ref<string[]>([])
  const fillForm = ref({ user_message: '', assistant_message: '' })

  // ── Fill operations ────────────────────────────────────
  async function runFillPreview() {
    if (!conversationId.value.trim()) return
    saving.value = true
    try {
      const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/state/fill`, {
        method: 'POST',
        headers: authHeaders(true),
        body: JSON.stringify({ ...fillForm.value, table_only: true, preview: true }),
      })
      const data = await resp.json()
      if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || t('state.messages.fillFailed'))
      fillPreviewOps.value = data.operations || []
      if (!fillPreviewOps.value.length) {
        message.info(t('state.messages.fillNoChanges'))
      } else {
        showFillPreviewModal.value = true
      }
    } catch (error: any) {
      message.error(error.message || t('state.messages.fillFailed'))
    } finally {
      saving.value = false
    }
  }

  async function runFillConfirm() {
    if (!conversationId.value.trim()) return
    saving.value = true
    showFillPreviewModal.value = false
    try {
      const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/state/fill`, {
        method: 'POST',
        headers: authHeaders(true),
        body: JSON.stringify({ ...fillForm.value, table_only: true, operations: fillPreviewOps.value }),
      })
      const data = await resp.json()
      if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || t('state.messages.fillFailed'))
      message.success(t('state.messages.fillDone', { applied: data.applied, skipped: data.skipped }))
      showFillModal.value = false
      await fetchBoard()
      const eventsResp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/state/events?limit=20`, { headers: authHeaders() })
      const eventsData = await eventsResp.json()
      const recentIds = (eventsData.items || [])
        .filter((e: any) => e.event_type !== 'revert')
        .slice(0, data.applied)
        .map((e: any) => e.event_id)
      if (recentIds.length) {
        lastFillEventIds.value = recentIds
        showUndoAlert.value = true
      }
    } catch (error: any) {
      message.error(error.message || t('state.messages.fillFailed'))
    } finally {
      saving.value = false
    }
  }

  async function revertLastFill() {
    if (!lastFillEventIds.value.length || !conversationId.value.trim()) return
    saving.value = true
    try {
      const resp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId.value.trim())}/state/revert`, {
        method: 'POST',
        headers: authHeaders(true),
        body: JSON.stringify({ event_ids: lastFillEventIds.value }),
      })
      const data = await resp.json()
      if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message)
      message.success(t('state.messages.reverted', { count: data.reverted }))
      showUndoAlert.value = false
      lastFillEventIds.value = []
      await fetchBoard()
    } catch (error: any) {
      message.error(error.message || t('state.messages.revertFailed'))
    } finally {
      saving.value = false
    }
  }

  return {
    showFillModal,
    showFillPreviewModal,
    fillPreviewOps,
    showUndoAlert,
    lastFillEventIds,
    fillForm,
    runFillPreview,
    runFillConfirm,
    revertLastFill,
  }
}
