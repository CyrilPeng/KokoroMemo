<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  NButton, NCard, NDataTable, NEmpty, NForm, NFormItem, NInput, NModal,
  NPagination, NPopconfirm, NSelect, NSpace, NSpin, NTag, useMessage,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { apiFetch, friendlyError } from '../api'
import type { InboxItem } from '../types/memory'
import HelpModal from '../components/HelpModal.vue'
import PageHeader from '../components/PageHeader.vue'

const message = useMessage()
const { t } = useI18n()
const items = ref<InboxItem[]>([])
const loading = ref(true)
const total = ref(0)
const page = ref(1)
const pageSize = 20
const statusFilter = ref('pending')
const showRejectModal = ref(false)
const rejectingId = ref('')
const rejectNote = ref('')
const rejectReason = ref<string | null>(null)
const helpModal = ref(false)
const processingIds = ref<Set<string>>(new Set())
const checkedRowKeys = ref<string[]>([])
const batchLoading = ref(false)
const riskFilter = ref('all')
const cardTypeFilter = ref('all')
const reviewClassFilter = ref('all')

const inboxHelpSections = computed(() => [
  { title: t('inbox.help.intro'), body: '' },
  { title: t('inbox.help.sourceTitle'), body: t('inbox.help.source') },
  { title: t('inbox.help.statusTitle'), body: t('inbox.help.status') },
  { title: t('inbox.help.approveTitle'), body: t('inbox.help.approve') },
  { title: t('inbox.help.rejectTitle'), body: t('inbox.help.reject') },
  { title: t('inbox.help.discardedTitle'), body: t('inbox.help.discarded') },
  { title: t('inbox.help.discardedLimitTitle'), body: t('inbox.help.discardedLimit') },
  { title: t('inbox.help.riskTitle'), body: t('inbox.help.risk') },
])

function isProcessing(inboxId: string) {
  return processingIds.value.has(inboxId)
}

function setProcessing(inboxId: string, processing: boolean) {
  const next = new Set(processingIds.value)
  if (processing) next.add(inboxId)
  else next.delete(inboxId)
  processingIds.value = next
}

const statusOptions = computed(() => [
  { label: t('inbox.statusFilter.pending'), value: 'pending' },
  { label: t('inbox.statusFilter.approved'), value: 'approved' },
  { label: t('inbox.statusFilter.discarded'), value: 'discarded,rejected' },
])

const riskFilterOptions = computed(() => [
  { label: t('inbox.filters.allRisks'), value: 'all' },
  { label: t('inbox.risk.high'), value: 'high' },
  { label: t('inbox.risk.medium'), value: 'medium' },
  { label: t('inbox.risk.low'), value: 'low' },
])

const cardTypeOptions = computed(() => [
  { label: t('inbox.filters.allTypes'), value: 'all' },
  ...['preference', 'boundary', 'relationship', 'event', 'promise', 'correction', 'world_state', 'summary']
    .map((value) => ({ label: typeLabel(value), value })),
])

const reviewClassOptions = computed(() => [
  { label: t('inbox.filters.allClasses'), value: 'all' },
  { label: t('inbox.reviewClass.boundary'), value: 'boundary' },
  { label: t('inbox.reviewClass.relationship'), value: 'relationship' },
  { label: t('inbox.reviewClass.roleContinuity'), value: 'role_continuity' },
  { label: t('inbox.reviewClass.storyState'), value: 'story_state' },
  { label: t('inbox.reviewClass.possibleNoise'), value: 'possible_noise' },
])

const rejectReasonOptions = computed(() => [
  { label: t('inbox.rejectReasons.temporaryPlot'), value: 'temporary_plot' },
  { label: t('inbox.rejectReasons.jokeOrHypothesis'), value: 'joke_or_hypothesis' },
  { label: t('inbox.rejectReasons.modelFabrication'), value: 'model_fabrication' },
  { label: t('inbox.rejectReasons.duplicate'), value: 'duplicate' },
  { label: t('inbox.rejectReasons.tooVague'), value: 'too_vague' },
])

function parsePayload(row: InboxItem): Record<string, any> {
  try { return JSON.parse(row.payload_json || '{}') } catch { return {} }
}

function candidateContent(row: InboxItem): string {
  return parsePayload(row).content || '—'
}

function candidateType(row: InboxItem): string {
  return parsePayload(row).card_type || row.candidate_type || ''
}

function candidateNumber(row: InboxItem, key: string): number {
  const value = Number(parsePayload(row)[key])
  return Number.isFinite(value) ? value : 0
}

function typeLabel(type: string): string {
  if (!type) return '—'
  const key = `memories.typeLabels.${type}`
  const translated = t(key)
  return translated === key ? type : translated
}

function scopeLabel(scope: string): string {
  if (!scope) return '—'
  const key = `memories.scopeLabels.${scope}`
  const translated = t(key)
  return translated === key ? scope : translated
}

function discardReasonLabel(reason?: string | null): string {
  if (!reason) return '—'
  const key = `inbox.discardReason.${reason}`
  const translated = t(key)
  return translated === key ? reason : translated
}

function isDiscardedView() {
  return statusFilter.value.includes('discarded') || statusFilter.value === 'rejected'
}

function riskTag(risk: string) {
  const type = risk === 'high' ? 'error' : risk === 'medium' ? 'warning' : 'success'
  return h(NTag, { size: 'small', type }, { default: () => t(`inbox.risk.${risk || 'low'}`) })
}

function reviewClass(row: InboxItem): string {
  const type = candidateType(row)
  const importance = candidateNumber(row, 'importance')
  const confidence = candidateNumber(row, 'confidence')
  if (type === 'boundary') return 'boundary'
  if (type === 'relationship') return 'relationship'
  if (['preference', 'correction'].includes(type)) return 'role_continuity'
  if (['event', 'promise', 'world_state', 'summary'].includes(type)) return 'story_state'
  if (row.risk_level === 'low' && (importance < 0.55 || confidence < 0.65)) return 'possible_noise'
  return 'role_continuity'
}

function reviewClassLabel(value: string): string {
  const key = `inbox.reviewClass.${value === 'role_continuity' ? 'roleContinuity' : value === 'story_state' ? 'storyState' : value === 'possible_noise' ? 'possibleNoise' : value}`
  const translated = t(key)
  return translated === key ? value : translated
}

function reviewClassTag(row: InboxItem) {
  const value = reviewClass(row)
  const type = value === 'boundary' ? 'error' : value === 'relationship' ? 'warning' : value === 'possible_noise' ? 'default' : 'info'
  return h(NTag, { size: 'small', type }, { default: () => reviewClassLabel(value) })
}

function clearSelection() {
  checkedRowKeys.value = []
}

const visibleItems = computed(() => items.value.filter((row) => {
  if (riskFilter.value !== 'all' && row.risk_level !== riskFilter.value) return false
  if (cardTypeFilter.value !== 'all' && candidateType(row) !== cardTypeFilter.value) return false
  if (reviewClassFilter.value !== 'all' && reviewClass(row) !== reviewClassFilter.value) return false
  return true
}))

const reviewSummary = computed(() => {
  const pending = items.value.filter((item) => item.status === 'pending')
  return {
    highRisk: pending.filter((item) => item.risk_level === 'high').length,
    boundary: pending.filter((item) => reviewClass(item) === 'boundary').length,
    relationship: pending.filter((item) => reviewClass(item) === 'relationship').length,
    possibleNoise: pending.filter((item) => reviewClass(item) === 'possible_noise').length,
  }
})

function applyRejectReason(value: string | null) {
  rejectReason.value = value
  if (!value) return
  const option = rejectReasonOptions.value.find((item) => item.value === value)
  if (option) rejectNote.value = option.label
}

const columns = computed(() => {
  const base: any[] = [
    { type: 'selection' },
    {
      title: t('inbox.column.content'), key: 'content', minWidth: 280, ellipsis: { tooltip: true },
      render: (row: InboxItem) => h('div', { class: 'candidate-cell' }, [
        h('div', { class: 'candidate-content' }, candidateContent(row)),
        h('div', { class: 'candidate-meta' }, [
          reviewClassTag(row),
          h('span', { class: 'candidate-score' }, t('inbox.scoreLine', {
            importance: candidateNumber(row, 'importance').toFixed(2),
            confidence: candidateNumber(row, 'confidence').toFixed(2),
          })),
        ]),
      ]),
    },
    {
      title: t('inbox.column.type'), key: 'card_type', width: 100,
      render: (row: InboxItem) => typeLabel(candidateType(row)),
    },
    {
      title: t('inbox.column.scope'), key: 'scope', width: 90,
      render: (row: InboxItem) => scopeLabel(parsePayload(row).scope),
    },
    {
      title: t('inbox.column.risk'), key: 'risk_level', width: 90,
      render: (row: InboxItem) => riskTag(row.risk_level),
    },
    {
      title: t('inbox.column.source'), key: 'conversation_id', width: 140, ellipsis: { tooltip: true },
      render: (row: InboxItem) => row.conversation_id || '—',
    },
  ]
  if (isDiscardedView()) {
    base.push({
      title: t('inbox.discardReason.label'), key: 'discard_reason', width: 130, ellipsis: { tooltip: true },
      render: (row: InboxItem) => h(NTag, { size: 'small', type: 'warning' }, { default: () => discardReasonLabel(row.discard_reason) }),
    })
    base.push({
      title: t('inbox.relatedCard'), key: 'related_card_id', width: 130, ellipsis: { tooltip: true },
      render: (row: InboxItem) => row.related_card_id || '—',
    })
  } else {
    base.push({
      title: t('inbox.column.reason'), key: 'reason', minWidth: 160, ellipsis: { tooltip: true },
      render: (row: InboxItem) => row.reason || '—',
    })
  }
  base.push({ title: t('inbox.column.createdAt'), key: 'created_at', width: 150 })
  base.push({
    title: t('inbox.column.actions'), key: 'actions', width: 200,
    render: (row: InboxItem) => {
      if (row.status === 'pending') {
        return h(NSpace, { size: 4 }, { default: () => [
          h(NPopconfirm, { positiveText: t('common.confirm'), negativeText: t('common.cancel'), onPositiveClick: () => approveItem(row.inbox_id) }, {
            trigger: () => h(NButton, { size: 'tiny', type: 'primary', loading: isProcessing(row.inbox_id), disabled: isProcessing(row.inbox_id) }, { default: () => t('inbox.actions.approve') }),
            default: () => t('inbox.confirmApprove'),
          }),
          h(NButton, { size: 'tiny', type: 'error', quaternary: true, loading: isProcessing(row.inbox_id), disabled: isProcessing(row.inbox_id), onClick: () => openRejectModal(row.inbox_id) }, { default: () => t('inbox.actions.reject') }),
        ] })
      }
      if (row.status === 'discarded' || row.status === 'rejected') {
        return h(NSpace, { size: 4 }, { default: () => [
          h(NPopconfirm, { positiveText: t('common.confirm'), negativeText: t('common.cancel'), onPositiveClick: () => restoreItem(row.inbox_id) }, {
            trigger: () => h(NButton, { size: 'tiny', type: 'primary', quaternary: true, loading: isProcessing(row.inbox_id), disabled: isProcessing(row.inbox_id) }, { default: () => t('inbox.actions.restore') }),
            default: () => t('inbox.confirmRestore'),
          }),
          h(NPopconfirm, { positiveText: t('common.confirm'), negativeText: t('common.cancel'), onPositiveClick: () => deleteItem(row.inbox_id) }, {
            trigger: () => h(NButton, { size: 'tiny', type: 'error', quaternary: true, loading: isProcessing(row.inbox_id), disabled: isProcessing(row.inbox_id) }, { default: () => t('inbox.actions.delete') }),
            default: () => t('inbox.confirmDelete'),
          }),
        ] })
      }
      return h(NTag, { size: 'small', type: row.status === 'approved' ? 'success' : 'default' }, { default: () => row.status })
    },
  })
  return base
})

async function fetchInbox() {
  loading.value = true
  try {
    const offset = (page.value - 1) * pageSize
    const resp = await apiFetch(`/admin/inbox?status=${statusFilter.value}&limit=${pageSize}&offset=${offset}`)
    if (resp.ok) {
      const data = await resp.json()
      items.value = data.items || []
      total.value = data.total || 0
    }
  } catch (e: any) {
    message.error(t('inbox.messages.loadFailed', { error: e.message || e }))
  }
  loading.value = false
}

async function approveItem(inboxId: string) {
  if (isProcessing(inboxId)) return
  setProcessing(inboxId, true)
  try {
    const resp = await apiFetch(`/admin/inbox/${inboxId}/approve`, { method: 'POST' })
    const data = await resp.json()
    if (data.status === 'ok') {
      message.success(t('inbox.messages.approved'))
      await fetchInbox()
    } else {
      message.error(data.message || t('common.failed'))
    }
  } catch (e: any) {
    message.error(friendlyError(e.message || String(e), 'inbox.approve'))
  } finally {
    setProcessing(inboxId, false)
  }
}

function openRejectModal(inboxId: string) {
  rejectingId.value = inboxId
  rejectNote.value = ''
  rejectReason.value = null
  showRejectModal.value = true
}

async function confirmReject() {
  if (rejectingId.value === '__batch__') {
    showRejectModal.value = false
    await batchAction('reject', rejectNote.value)
    return
  }
  if (!rejectingId.value || isProcessing(rejectingId.value)) return
  setProcessing(rejectingId.value, true)
  try {
    const resp = await apiFetch(`/admin/inbox/${rejectingId.value}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: rejectNote.value }),
    })
    const data = await resp.json()
    if (data.status === 'ok') {
      showRejectModal.value = false
      message.success(t('inbox.messages.rejected'))
      await fetchInbox()
    } else {
      message.error(data.message || t('common.failed'))
    }
  } catch (e: any) {
    message.error(friendlyError(e.message || String(e), 'inbox.reject'))
  } finally {
    if (rejectingId.value) setProcessing(rejectingId.value, false)
  }
}

async function restoreItem(inboxId: string) {
  if (isProcessing(inboxId)) return
  setProcessing(inboxId, true)
  try {
    const resp = await apiFetch(`/admin/inbox/${inboxId}/restore`, { method: 'POST' })
    const data = await resp.json()
    if (data.status === 'ok') {
      message.success(t('inbox.messages.restored'))
      await fetchInbox()
    } else {
      message.error(data.message || t('common.failed'))
    }
  } catch (e: any) {
    message.error(friendlyError(e.message || String(e), 'inbox.restore'))
  } finally {
    setProcessing(inboxId, false)
  }
}

async function deleteItem(inboxId: string) {
  if (isProcessing(inboxId)) return
  setProcessing(inboxId, true)
  try {
    const resp = await apiFetch(`/admin/inbox/${inboxId}`, { method: 'DELETE' })
    const data = await resp.json()
    if (data.status === 'ok') {
      message.success(t('inbox.messages.deleted'))
      await fetchInbox()
    } else {
      message.error(data.message || t('common.failed'))
    }
  } catch (e: any) {
    message.error(friendlyError(e.message || String(e), 'inbox.delete'))
  } finally {
    setProcessing(inboxId, false)
  }
}

async function batchAction(action: 'approve' | 'reject', note = '') {
  if (!checkedRowKeys.value.length) return
  batchLoading.value = true
  try {
    const resp = await apiFetch('/admin/inbox/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, inbox_ids: checkedRowKeys.value, note }),
    })
    const data = await resp.json()
    if (data.status === 'ok') {
      message.success(action === 'approve'
        ? t('inbox.messages.batchApproved', { count: data.ok })
        : t('inbox.messages.batchRejected', { count: data.ok }))
      checkedRowKeys.value = []
      await fetchInbox()
    } else if (data.status === 'partial') {
      message.warning(t('inbox.messages.batchPartial', { ok: data.ok, failed: data.failed }))
      checkedRowKeys.value = []
      await fetchInbox()
    } else {
      message.error(data.message || t('common.failed'))
    }
  } catch (e: any) {
    message.error(friendlyError(e.message || String(e), 'inbox.cleanup'))
  }
  batchLoading.value = false
}

async function approveHighConfidence() {
  const highConfIds = visibleItems.value
    .filter((item: InboxItem) => {
      if (item.status !== 'pending') return false
      const p = parsePayload(item)
      return (p.importance || 0) >= 0.7 && (p.confidence || 0) >= 0.8
    })
    .map((item: InboxItem) => item.inbox_id)
  if (!highConfIds.length) {
    message.info(t('inbox.messages.noHighConfidence'))
    return
  }
  batchLoading.value = true
  try {
    const resp = await apiFetch('/admin/inbox/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'approve', inbox_ids: highConfIds }),
    })
    const data = await resp.json()
    if (data.status === 'ok' || data.status === 'partial') {
      message.success(t('inbox.messages.batchApproved', { count: data.ok }))
      await fetchInbox()
    } else {
      message.error(data.message || t('common.failed'))
    }
  } catch (e: any) {
    message.error(friendlyError(e.message || String(e), 'inbox.permanentDelete'))
  }
  batchLoading.value = false
}

function onKeydown(e: KeyboardEvent) {
  const ae = document.activeElement as HTMLElement | null
  if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA' || ae.isContentEditable)) return
  if (!checkedRowKeys.value.length) return
  if (e.key === 'a' || e.key === 'A') { e.preventDefault(); batchAction('approve') }
  if (e.key === 'r' || e.key === 'R') {
    e.preventDefault()
    if (rejectNote.value) { batchAction('reject', rejectNote.value) }
    else { batchAction('reject') }
  }
}

function handleStatusChange(val: string) {
  statusFilter.value = val
  page.value = 1
  checkedRowKeys.value = []
  riskFilter.value = 'all'
  cardTypeFilter.value = 'all'
  reviewClassFilter.value = 'all'
  fetchInbox()
}

onMounted(fetchInbox)
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

function onWsEvent(e: any) {
  const data = e.detail
  if (data?.event === 'inbox_new' || data?.event === 'card_approved') {
    fetchInbox()
  }
}
onMounted(() => window.addEventListener('kokoromemo:event', onWsEvent))
onBeforeUnmount(() => window.removeEventListener('kokoromemo:event', onWsEvent))
</script>

<template>
  <div>
    <PageHeader :title="$t('inbox.title')" :subtitle="$t('inbox.subtitle')" show-help @help="helpModal = true" />

    <NCard style="background: #18181b; border: 1px solid #27272a;">
      <NSpace justify="space-between" align="center" style="margin-bottom: 16px; width: 100%;" wrap>
        <NSpace wrap>
          <NSelect :value="statusFilter" :options="statusOptions" style="width: 140px;" size="small" @update:value="handleStatusChange" />
          <NTag size="small" round style="color: #71717a;">{{ $t('inbox.totalCount', { count: total }) }}</NTag>
        </NSpace>
        <NButton size="small" @click="fetchInbox">{{ $t('common.load') }}</NButton>
      </NSpace>

      <NCard v-if="statusFilter === 'pending'" class="review-overview-card">
        <div class="review-overview-grid">
          <div class="review-overview-item">
            <div class="review-overview-label">{{ $t('inbox.overview.highRisk') }}</div>
            <div class="review-overview-value">{{ reviewSummary.highRisk }}</div>
          </div>
          <div class="review-overview-item">
            <div class="review-overview-label">{{ $t('inbox.overview.boundary') }}</div>
            <div class="review-overview-value">{{ reviewSummary.boundary }}</div>
          </div>
          <div class="review-overview-item">
            <div class="review-overview-label">{{ $t('inbox.overview.relationship') }}</div>
            <div class="review-overview-value">{{ reviewSummary.relationship }}</div>
          </div>
          <div class="review-overview-item">
            <div class="review-overview-label">{{ $t('inbox.overview.possibleNoise') }}</div>
            <div class="review-overview-value">{{ reviewSummary.possibleNoise }}</div>
          </div>
        </div>
      </NCard>

      <NCard class="review-filter-card">
        <NSpace align="center" wrap>
          <NSelect
            v-model:value="reviewClassFilter"
            :options="reviewClassOptions"
            size="small"
            style="width: 180px;"
            @update:value="clearSelection"
          />
          <NSelect
            v-model:value="riskFilter"
            :options="riskFilterOptions"
            size="small"
            style="width: 140px;"
            @update:value="clearSelection"
          />
          <NSelect
            v-model:value="cardTypeFilter"
            :options="cardTypeOptions"
            size="small"
            style="width: 150px;"
            @update:value="clearSelection"
          />
          <NTag size="small" round>{{ $t('inbox.visibleCount', { count: visibleItems.length }) }}</NTag>
        </NSpace>
      </NCard>

      <NCard v-if="statusFilter === 'pending'" style="background: #18181b; border: 1px solid #27272a; margin-bottom: 12px;">
        <NSpace align="center">
          <NButton
            size="small"
            type="primary"
            :loading="batchLoading"
            :disabled="!checkedRowKeys.length"
            @click="batchAction('approve')"
          >
            {{ $t('inbox.batch.approveSelected', { n: checkedRowKeys.length }) }}
          </NButton>
          <NButton
            size="small"
            type="error"
            :loading="batchLoading"
            :disabled="!checkedRowKeys.length"
            @click="showRejectModal = true; rejectingId = '__batch__'; rejectReason = null; rejectNote = ''"
          >
            {{ $t('inbox.batch.rejectSelected', { n: checkedRowKeys.length }) }}
          </NButton>
          <NButton
            size="small"
            :loading="batchLoading"
            @click="approveHighConfidence"
          >
            {{ $t('inbox.batch.approveHighConfidence') }}
          </NButton>
          <span style="color: #71717a; font-size: 12px; margin-left: 8px;">
            {{ $t('inbox.batch.shortcuts') }}
          </span>
        </NSpace>
      </NCard>

      <NSpin :show="loading">
        <NEmpty v-if="!items.length && !loading" :description="$t('inbox.empty')" />
        <NDataTable
          v-else
          :columns="columns"
          :data="visibleItems"
          :pagination="false"
          :row-key="(row: any) => row.inbox_id"
          v-model:checked-row-keys="checkedRowKeys"
        />
      </NSpin>

      <div v-if="total > pageSize" style="display: flex; justify-content: center; margin-top: 16px;">
        <NPagination v-model:page="page" :page-count="Math.ceil(total / pageSize)" @update:page="fetchInbox" />
      </div>
    </NCard>

    <NModal v-model:show="showRejectModal" preset="card" :title="$t('inbox.actions.reject')" style="width: min(480px, 96vw); background: #18181b;">
      <NForm label-placement="top">
        <NFormItem :label="$t('inbox.rejectReasonPreset')">
          <NSelect
            :value="rejectReason"
            :options="rejectReasonOptions"
            clearable
            :placeholder="$t('inbox.rejectReasonPresetPlaceholder')"
            @update:value="applyRejectReason"
          />
        </NFormItem>
        <NFormItem :label="$t('inbox.rejectNote')">
          <NInput v-model:value="rejectNote" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" :placeholder="$t('inbox.rejectNotePlaceholder')" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showRejectModal = false">{{ $t('common.cancel') }}</NButton>
          <NButton type="error" :loading="rejectingId === '__batch__' ? batchLoading : isProcessing(rejectingId)" :disabled="rejectingId === '__batch__' ? batchLoading : isProcessing(rejectingId)" @click="confirmReject">{{ $t('inbox.actions.reject') }}</NButton>
        </NSpace>
      </template>
    </NModal>

    <HelpModal v-model:show="helpModal" :title="$t('inbox.help.title')" :sections="inboxHelpSections" />
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

.review-overview-card,
.review-filter-card {
  background: #18181b;
  border: 1px solid #27272a;
  margin-bottom: 12px;
}

.review-overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.review-overview-item {
  min-height: 76px;
  padding: 10px 12px;
  border: 1px solid #27272a;
  border-radius: 8px;
  background: #111113;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.review-overview-label {
  color: #71717a;
  font-size: 12px;
}

.review-overview-value {
  color: #f4f4f5;
  font-size: 22px;
  font-weight: 600;
  line-height: 1.2;
}

.candidate-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.candidate-content {
  color: #e4e4e7;
  line-height: 1.5;
  white-space: normal;
  overflow-wrap: anywhere;
}

.candidate-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.candidate-score {
  color: #71717a;
  font-size: 12px;
}

@media (max-width: 760px) {
  .review-overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
