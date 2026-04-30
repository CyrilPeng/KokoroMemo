<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  NButton, NCard, NDataTable, NEmpty, NForm, NFormItem, NInput, NModal,
  NPagination, NPopconfirm, NSelect, NSpace, NSpin, NTag, useMessage,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { apiFetch } from '../api'

const message = useMessage()
const { t } = useI18n()
const items = ref<any[]>([])
const loading = ref(true)
const total = ref(0)
const page = ref(1)
const pageSize = 20
const statusFilter = ref('pending')
const showRejectModal = ref(false)
const rejectingId = ref('')
const rejectNote = ref('')

const statusOptions = computed(() => [
  { label: t('inbox.statusFilter.pending'), value: 'pending' },
  { label: t('inbox.statusFilter.approved'), value: 'approved' },
  { label: t('inbox.statusFilter.rejected'), value: 'rejected' },
])

function parsePayload(row: any): any {
  try { return JSON.parse(row.payload_json || '{}') } catch { return {} }
}

function riskTag(risk: string) {
  const type = risk === 'high' ? 'error' : risk === 'medium' ? 'warning' : 'success'
  return h(NTag, { size: 'small', type }, { default: () => risk || 'low' })
}

const columns = computed(() => [
  {
    title: t('inbox.column.content'), key: 'content', minWidth: 280, ellipsis: { tooltip: true },
    render: (row: any) => parsePayload(row).content || '—',
  },
  {
    title: t('inbox.column.type'), key: 'card_type', width: 100,
    render: (row: any) => parsePayload(row).card_type || '—',
  },
  {
    title: t('inbox.column.scope'), key: 'scope', width: 90,
    render: (row: any) => parsePayload(row).scope || '—',
  },
  {
    title: t('inbox.column.risk'), key: 'risk_level', width: 90,
    render: (row: any) => riskTag(row.risk_level),
  },
  {
    title: t('inbox.column.source'), key: 'conversation_id', width: 140, ellipsis: { tooltip: true },
    render: (row: any) => row.conversation_id || '—',
  },
  {
    title: t('inbox.column.reason'), key: 'reason', minWidth: 160, ellipsis: { tooltip: true },
    render: (row: any) => row.reason || '—',
  },
  { title: t('inbox.column.createdAt'), key: 'created_at', width: 150 },
  {
    title: t('inbox.column.actions'), key: 'actions', width: 180,
    render: (row: any) => row.status === 'pending'
      ? h(NSpace, { size: 4 }, { default: () => [
          h(NPopconfirm, { positiveText: t('common.confirm'), negativeText: t('common.cancel'), onPositiveClick: () => approveItem(row.inbox_id) }, {
            trigger: () => h(NButton, { size: 'tiny', type: 'primary' }, { default: () => t('inbox.actions.approve') }),
            default: () => t('inbox.confirmApprove'),
          }),
          h(NButton, { size: 'tiny', type: 'error', quaternary: true, onClick: () => openRejectModal(row.inbox_id) }, { default: () => t('inbox.actions.reject') }),
        ] })
      : h(NTag, { size: 'small', type: row.status === 'approved' ? 'success' : 'default' }, { default: () => row.status }),
  },
])

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
    message.error(e.message || String(e))
  }
}

function openRejectModal(inboxId: string) {
  rejectingId.value = inboxId
  rejectNote.value = ''
  showRejectModal.value = true
}

async function confirmReject() {
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
    message.error(e.message || String(e))
  }
}

function handleStatusChange(val: string) {
  statusFilter.value = val
  page.value = 1
  fetchInbox()
}

onMounted(fetchInbox)

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
    <div style="margin-bottom: 28px;">
      <h1 style="font-size: 24px; font-weight: 600; color: #e4e4e7; margin-bottom: 4px;">{{ $t('inbox.title') }}</h1>
      <p style="color: #71717a; font-size: 14px;">{{ $t('inbox.subtitle') }}</p>
    </div>

    <NCard style="background: #18181b; border: 1px solid #27272a;">
      <NSpace justify="space-between" align="center" style="margin-bottom: 16px; width: 100%;" wrap>
        <NSpace wrap>
          <NSelect :value="statusFilter" :options="statusOptions" style="width: 140px;" size="small" @update:value="handleStatusChange" />
          <NTag size="small" round style="color: #71717a;">{{ $t('inbox.totalCount', { count: total }) }}</NTag>
        </NSpace>
        <NButton size="small" @click="fetchInbox">{{ $t('common.load') }}</NButton>
      </NSpace>

      <NSpin :show="loading">
        <NEmpty v-if="!items.length && !loading" :description="$t('inbox.empty')" />
        <NDataTable v-else :columns="columns" :data="items" :pagination="false" />
      </NSpin>

      <div v-if="total > pageSize" style="display: flex; justify-content: center; margin-top: 16px;">
        <NPagination v-model:page="page" :page-count="Math.ceil(total / pageSize)" @update:page="fetchInbox" />
      </div>
    </NCard>

    <NModal v-model:show="showRejectModal" preset="card" :title="$t('inbox.actions.reject')" style="width: 480px; background: #18181b;">
      <NForm label-placement="top">
        <NFormItem :label="$t('inbox.rejectNote')">
          <NInput v-model:value="rejectNote" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" :placeholder="$t('inbox.rejectNotePlaceholder')" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showRejectModal = false">{{ $t('common.cancel') }}</NButton>
          <NButton type="error" @click="confirmReject">{{ $t('inbox.actions.reject') }}</NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>
