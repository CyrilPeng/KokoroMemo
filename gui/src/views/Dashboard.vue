<script setup lang="ts">
import { ref, computed, onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NCard, NGrid, NGridItem, NIcon, NProgress, NSpace, NSpin, NStatistic, NTag } from 'naive-ui'
import { RefreshOutline } from '@vicons/ionicons5'
import { useI18n } from 'vue-i18n'
import { apiFetch, getServerUrl, setServerUrl } from '../api'
import HelpModal from '../components/HelpModal.vue'
import PageHeader from '../components/PageHeader.vue'
import ConfigHealthCard from '../components/ConfigHealthCard.vue'
const router = useRouter()
const { t } = useI18n()
function typeLabel(type: string): string {
  const key = `memories.typeLabels.${type}`
  const translated = t(key)
  return translated === key ? type : translated
}
const health = ref<any>(null)
const stats = ref<any>(null)
const loading = ref(false)
const serverUrl = ref(getServerUrl())
const helpModal = ref(false)

const totalApproved = computed(() => stats.value?.cards_by_status?.approved || 0)
const inboxPending = computed(() => stats.value?.inbox_pending || 0)
const inboxDiscarded = computed(() => stats.value?.inbox_discarded || 0)
const recentConversations = ref<any[]>([])
const latestConfig = ref<any | null>(null)
const firstRunStatus = ref<any | null>(null)
const continuityLoading = ref(false)
const firstRunLoading = ref(false)
type TagType = 'default' | 'error' | 'success' | 'warning' | 'info' | 'primary'
type FirstRunItem = {
  key: string
  label: string
  hint: string
  done: boolean
  target?: string
  action?: string
  optional?: boolean
}
type FirstRunStep = {
  key: string
  done: boolean
  optional?: boolean
  target?: string | null
  action_key?: string | null
  count?: number
}

const latestConversation = computed(() => recentConversations.value[0] || null)
const latestConversationName = computed(() => {
  const item = latestConversation.value
  if (!item) return t('dashboard.continuity.noConversation')
  return item.title?.trim() || item.conversation_id || t('common.unnamed')
})
const latestCharacterName = computed(() => {
  const item = latestConversation.value
  if (!item?.character_id) return t('dashboard.continuity.noCharacter')
  return item.character_display_name || item.character_id
})

function mappedLabel(section: string, value?: string | null) {
  if (!value) return t('common.notConfigured')
  const key = `dashboard.continuity.${section}.${value}`
  const translated = t(key)
  return translated === key ? value : translated
}

const continuityTone = computed<{ tagType: TagType; label: string }>(() => {
  if (!latestConversation.value) {
    return { tagType: 'info', label: t('dashboard.continuity.noConversationStatus') }
  }
  const diagnostics = latestConversation.value.diagnostics || []
  const hasError = diagnostics.some((item: any) => item.type === 'error')
  const hasWarning = diagnostics.some((item: any) => item.type === 'warning')
  if (hasError) return { tagType: 'error', label: t('dashboard.continuity.needsAttention') }
  if (hasWarning) return { tagType: 'warning', label: t('dashboard.continuity.needsReview') }
  return { tagType: 'success', label: t('dashboard.continuity.ready') }
})

const stateBoardSummary = computed(() => {
  if (!latestConfig.value) return t('common.notConfigured')
  const rowCount = latestConfig.value.state_row_count ?? latestConfig.value.state_item_count ?? 0
  const policy = mappedLabel('statePolicies', latestConfig.value.state_update_policy)
  return t('dashboard.continuity.stateSummary', { policy, count: rowCount })
})

const fallbackFirstRunSteps = computed<FirstRunStep[]>(() => [
  { key: 'config', done: false, target: '/settings', action_key: 'openSettings', count: 0 },
  { key: 'role', done: false, target: '/characters', action_key: 'openRoles', count: 0 },
  { key: 'conversation', done: false, target: '/settings', action_key: 'openSettings', count: 0 },
  { key: 'candidate', done: false, target: '/inbox', action_key: 'openInbox', count: 0 },
  { key: 'approved', done: false, target: '/memories', action_key: 'openMemories', count: 0 },
  { key: 'state', done: false, target: '/state', action_key: 'openState', count: 0 },
  { key: 'benchmark', done: false, optional: true, count: 0 },
])
const rawFirstRunSteps = computed<FirstRunStep[]>(() => (
  firstRunStatus.value?.steps?.length ? firstRunStatus.value.steps : fallbackFirstRunSteps.value
))

function firstRunHint(step: FirstRunStep) {
  const suffix = step.done ? 'Ready' : 'Pending'
  const key = `dashboard.firstRun.hints.${step.key}${suffix}`
  const translated = t(key, { count: step.count ?? 0 })
  return translated === key ? t('dashboard.firstRun.hints.unknown') : translated
}

const firstRunItems = computed<FirstRunItem[]>(() => rawFirstRunSteps.value.map((step) => {
  const labelKey = `dashboard.firstRun.steps.${step.key}`
  const actionKey = step.action_key ? `dashboard.firstRun.actions.${step.action_key}` : ''
  const label = t(labelKey)
  const action = actionKey ? t(actionKey) : ''
  return {
    key: step.key,
    label: label === labelKey ? step.key : label,
    hint: firstRunHint(step),
    done: step.done,
    optional: Boolean(step.optional),
    target: step.target || undefined,
    action: action && action !== actionKey ? action : undefined,
  }
}))
const firstRunRequiredTotal = computed(() => firstRunStatus.value?.progress?.total || firstRunItems.value.filter((item) => !item.optional).length)
const firstRunReadyCount = computed(() => firstRunStatus.value?.progress?.done || firstRunItems.value.filter((item) => !item.optional && item.done).length)
const firstRunProgress = computed(() => firstRunStatus.value?.progress?.percentage || 0)
const firstRunCoreReady = computed(() => Boolean(firstRunStatus.value?.ready))
const firstRunTone = computed<{ tagType: TagType; label: string }>(() => (
  firstRunCoreReady.value
    ? { tagType: 'success', label: t('dashboard.firstRun.ready') }
    : { tagType: 'warning', label: t('dashboard.firstRun.inProgress') }
))

const dashboardHelpSections = computed(() => [
  { title: t('dashboard.help.intro'), body: '' },
  { title: t('dashboard.totalMemories'), body: t('dashboard.help.totalMemories') },
  { title: t('dashboard.inboxPending'), body: t('dashboard.help.inboxPending') },
  { title: t('dashboard.gateRequests24h'), body: t('dashboard.help.gateRequests') },
  { title: t('dashboard.dailyGrowth7d'), body: t('dashboard.help.dailyGrowth') },
  { title: t('dashboard.cardsByType'), body: t('dashboard.help.cardsByType') },
])
const totalCards = computed(() => {
  if (!stats.value?.cards_by_status) return 0
  return Object.values(stats.value.cards_by_status as Record<string, number>).reduce((a: number, b: number) => a + b, 0)
})
const gateTotal = computed(() => {
  if (!stats.value?.gate_stats_24h) return 0
  return Object.values(stats.value.gate_stats_24h as Record<string, number>).reduce((a: number, b: number) => a + b, 0)
})
const gateSkipRate = computed(() => {
  if (!gateTotal.value) return '-'
  const skipped = (stats.value?.gate_stats_24h?.[0] || stats.value?.gate_stats_24h?.['0']) || 0
  return Math.round((skipped / gateTotal.value) * 100) + '%'
})

async function fetchHealth() {
  loading.value = true
  try {
    serverUrl.value = getServerUrl()
    const resp = await apiFetch('/health', { timeoutMs: 4000 })
    health.value = await resp.json()
    if (health.value?.actual_port) {
      const actualUrl = window.__TAURI_INTERNALS__
        ? `http://127.0.0.1:${health.value.actual_port}`
        : window.location.origin
      serverUrl.value = actualUrl
      setServerUrl(actualUrl)
    }
  } catch (e) {
    health.value = null
  }
  loading.value = false
}

async function fetchStats() {
  try {
    const resp = await apiFetch('/admin/stats', { timeoutMs: 5000 })
    stats.value = await resp.json()
  } catch (e) {
    stats.value = null
  }
}

const actionItems = ref<any[]>([])

async function fetchActionItems() {
  try {
    const resp = await apiFetch('/admin/action-items', { timeoutMs: 5000 })
    if (resp.ok) {
      const data = await resp.json()
      actionItems.value = data.items || []
    }
  } catch {}
}

async function fetchFirstRunStatus() {
  try {
    const resp = await apiFetch('/admin/airp-first-run-status', { timeoutMs: 5000 })
    if (resp.ok) firstRunStatus.value = await resp.json()
  } catch {
    firstRunStatus.value = null
  }
}

async function fetchContinuityOverview() {
  continuityLoading.value = true
  latestConfig.value = null
  try {
    const resp = await apiFetch('/admin/conversations?limit=5&status=active', { timeoutMs: 8000 })
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || data.message || 'load conversations failed')
    recentConversations.value = data.items || []
    const conversationId = recentConversations.value[0]?.conversation_id
    if (conversationId) {
      const configResp = await apiFetch(`/admin/conversations/${encodeURIComponent(conversationId)}/config`, { timeoutMs: 8000 })
      if (configResp.ok) latestConfig.value = await configResp.json()
    }
  } catch {
    recentConversations.value = []
  } finally {
    continuityLoading.value = false
  }
}

function openStateBoard(conversationId?: string | null) {
  if (conversationId) localStorage.setItem('kokoromemo.stateConversationId', conversationId)
  router.push('/state')
}

async function refreshFirstRunStatus() {
  firstRunLoading.value = true
  await Promise.allSettled([
    fetchHealth(),
    fetchStats(),
    fetchActionItems(),
    fetchFirstRunStatus(),
    fetchContinuityOverview(),
  ])
  firstRunLoading.value = false
}

function openFirstRunTarget(item: FirstRunItem) {
  if (!item.target) return
  if (item.target === '/state') {
    openStateBoard(latestConversation.value?.conversation_id)
    return
  }
  router.push(item.target)
}

onMounted(() => {
  window.setTimeout(() => {
    refreshFirstRunStatus()
  }, 0)
})

function onWsEvent(e: any) {
  const data = e.detail
  if (data?.event === 'inbox_new' || data?.event === 'card_approved') {
    fetchStats()
    fetchActionItems()
    fetchFirstRunStatus()
    fetchContinuityOverview()
  }
}
onMounted(() => window.addEventListener('kokoromemo:event', onWsEvent))
onBeforeUnmount(() => window.removeEventListener('kokoromemo:event', onWsEvent))
</script>

<template>
  <div>
    <PageHeader :title="$t('dashboard.title')" :subtitle="$t('dashboard.subtitle')" show-help @help="helpModal = true" />

    <NSpin :show="loading">
      <div v-if="health">
        <ConfigHealthCard style="margin-bottom: 16px;" />

        <NCard class="first-run-card">
          <template #header>
            <div class="section-title-row">
              <span>{{ t('dashboard.firstRun.title') }}</span>
              <NTag :type="firstRunTone.tagType" size="small" round>
                {{ firstRunTone.label }}
              </NTag>
            </div>
          </template>
          <template #header-extra>
            <NButton size="small" quaternary :loading="firstRunLoading" @click="refreshFirstRunStatus">
              <template #icon><NIcon :component="RefreshOutline" /></template>
              {{ $t('common.refresh') }}
            </NButton>
          </template>
          <div class="first-run-summary">
            <NProgress
              type="line"
              :percentage="firstRunProgress"
              :height="8"
              :border-radius="8"
              :fill-border-radius="8"
              :indicator-placement="'inside'"
              :color="firstRunCoreReady ? '#4ade80' : '#facc15'"
              rail-color="#27272a"
            />
            <span>{{ t('dashboard.firstRun.progress', { done: firstRunReadyCount, total: firstRunRequiredTotal }) }}</span>
          </div>
          <div class="first-run-grid">
            <button
              v-for="item in firstRunItems"
              :key="item.key"
              class="first-run-step"
              :class="{ done: item.done, optional: item.optional }"
              :disabled="!item.target"
              @click="openFirstRunTarget(item)"
            >
              <span class="step-status" aria-hidden="true" />
              <span class="step-copy">
                <span class="step-title-row">
                  <span class="step-title">{{ item.label }}</span>
                  <NTag :type="item.done ? 'success' : item.optional ? 'info' : 'warning'" size="tiny" round>
                    {{ item.done ? t('dashboard.firstRun.done') : item.optional ? t('dashboard.firstRun.optional') : t('dashboard.firstRun.pending') }}
                  </NTag>
                </span>
                <span class="step-hint">{{ item.hint }}</span>
                <span v-if="item.action" class="step-action">{{ item.action }}</span>
              </span>
            </button>
          </div>
        </NCard>

        <!-- 角色连续性总览 -->
        <NCard class="continuity-card">
          <template #header>
            <div class="section-title-row">
              <span>{{ t('dashboard.continuity.title') }}</span>
              <NTag :type="continuityTone.tagType" size="small" round>
                {{ continuityTone.label }}
              </NTag>
            </div>
          </template>
          <template #header-extra>
            <NButton size="small" quaternary :loading="continuityLoading" @click="fetchContinuityOverview">
              {{ $t('common.refresh') }}
            </NButton>
          </template>
          <NGrid :cols="4" :x-gap="14" :y-gap="14" responsive="screen" item-responsive>
            <NGridItem span="4 m:2 l:1">
              <div class="continuity-metric">
                <div class="metric-label">{{ t('dashboard.continuity.latestConversation') }}</div>
                <div class="metric-value">{{ latestConversationName }}</div>
                <div class="metric-hint">{{ latestConversation?.last_seen_at || t('dashboard.continuity.noRecentActivity') }}</div>
              </div>
            </NGridItem>
            <NGridItem span="4 m:2 l:1">
              <div class="continuity-metric">
                <div class="metric-label">{{ t('dashboard.continuity.currentRole') }}</div>
                <div class="metric-value">{{ latestCharacterName }}</div>
                <div class="metric-hint">{{ latestConfig?.profile_id ? mappedLabel('profiles', latestConfig.profile_id) : t('common.notConfigured') }}</div>
              </div>
            </NGridItem>
            <NGridItem span="4 m:2 l:1">
              <div class="continuity-metric">
                <div class="metric-label">{{ t('dashboard.continuity.stateBoard') }}</div>
                <div class="metric-value">{{ stateBoardSummary }}</div>
                <div class="metric-hint">{{ latestConfig?.table_template_name || t('common.notConfigured') }}</div>
              </div>
            </NGridItem>
            <NGridItem span="4 m:2 l:1">
              <div class="continuity-metric">
                <div class="metric-label">{{ t('dashboard.continuity.memoryPolicy') }}</div>
                <div class="metric-value">{{ mappedLabel('memoryPolicies', latestConfig?.memory_write_policy) }}</div>
                <div class="metric-hint">{{ t('dashboard.continuity.pendingReview', { count: inboxPending }) }}</div>
              </div>
            </NGridItem>
          </NGrid>
          <div class="continuity-footer">
            <NSpace>
              <NTag size="small" round>{{ t('dashboard.continuity.injectionPolicy') }}: {{ mappedLabel('injectionPolicies', latestConfig?.injection_policy) }}</NTag>
              <NTag size="small" round>{{ t('dashboard.continuity.retrievalPolicy') }}: {{ mappedLabel('retrievalPolicies', latestConfig?.retrieval_profile_id) }}</NTag>
            </NSpace>
            <NSpace>
              <NButton size="small" @click="router.push('/inbox')">{{ t('dashboard.quickActions.reviewInbox') }}</NButton>
              <NButton size="small" :disabled="!latestConversation" @click="openStateBoard(latestConversation?.conversation_id)">
                {{ t('dashboard.quickActions.openStateBoard') }}
              </NButton>
              <NButton size="small" @click="router.push('/characters')">{{ t('dashboard.quickActions.manageRoles') }}</NButton>
            </NSpace>
          </div>
        </NCard>

        <!-- 待处理事项 -->
        <NCard v-if="actionItems.length" style="background: #18181b; border: 1px solid #27272a; margin-bottom: 16px;">
          <div style="color: #71717a; font-size: 13px; margin-bottom: 10px;">{{ t('dashboard.actionItems.title') }}</div>
          <NSpace>
            <div
              v-for="item in actionItems"
              :key="item.key"
              style="display: flex; align-items: center; gap: 8px; padding: 8px 14px; background: #27272a; border-radius: 8px; cursor: pointer;"
              @click="router.push(item.target)"
            >
              <NTag :type="item.severity === 'error' ? 'error' : 'warning'" size="small" round>
                {{ item.count }}
              </NTag>
              <span style="color: #e4e4e7; font-size: 14px;">{{ item.label }}</span>
            </div>
          </NSpace>
        </NCard>

        <!-- 快捷操作 -->
        <NCard style="background: #18181b; border: 1px solid #27272a; margin-bottom: 16px;">
          <div style="color: #71717a; font-size: 13px; margin-bottom: 10px;">{{ t('dashboard.quickActions.title') }}</div>
          <NSpace>
            <NButton size="small" @click="router.push('/settings')">
              {{ t('dashboard.quickActions.testConnectivity') }}
            </NButton>
            <NButton size="small" @click="openStateBoard(latestConversation?.conversation_id)">
              {{ t('dashboard.quickActions.openStateBoard') }}
            </NButton>
            <NButton size="small" @click="router.push('/characters')">
              {{ t('dashboard.quickActions.manageRoles') }}
            </NButton>
            <NButton size="small" @click="router.push('/memories')">
              {{ t('dashboard.quickActions.openMemories') }}
            </NButton>
          </NSpace>
        </NCard>

        <NGrid :cols="3" :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
          <NGridItem span="3 m:1">
            <NCard style="background: #18181b; border: 1px solid #27272a;">
              <div style="display: flex; align-items: center; justify-content: space-between;">
                <div>
                  <div style="color: #71717a; font-size: 13px; margin-bottom: 8px;">{{ $t('dashboard.serverStatus') }}</div>
                  <NTag :type="health.status === 'ok' ? 'success' : 'error'" size="medium" round>
                    {{ health.status === 'ok' ? $t('dashboard.running') : $t('dashboard.error') }}
                  </NTag>
                </div>
                <NButton size="small" quaternary @click="fetchHealth" style="color: #71717a;">
                  {{ $t('common.refresh') }}
                </NButton>
              </div>
              <div style="margin-top: 12px; font-size: 13px; color: #52525b;">
                {{ $t('dashboard.listeningPort') }} {{ health.server_port || health.actual_port || '-' }}
              </div>
            </NCard>
          </NGridItem>

          <NGridItem span="3 m:1">
            <NCard style="background: #18181b; border: 1px solid #27272a;">
              <div style="color: #71717a; font-size: 13px; margin-bottom: 8px;">{{ $t('dashboard.embeddingModel') }}</div>
              <div style="font-size: 15px; font-weight: 500; color: #e4e4e7; margin-bottom: 8px;">
                {{ health.embedding?.model || $t('common.notConfigured') }}
              </div>
              <NSpace>
                <NTag :type="health.embedding?.enabled ? 'success' : 'warning'" size="small" round>
                  {{ health.embedding?.enabled ? $t('common.enabled') : $t('common.disabled') }}
                </NTag>
                <span style="color: #52525b; font-size: 12px;">
                  {{ $t('dashboard.dimension') }} {{ health.embedding?.dimension || '-' }}
                </span>
              </NSpace>
            </NCard>
          </NGridItem>

          <NGridItem span="3 m:1">
            <NCard style="background: #18181b; border: 1px solid #27272a;">
              <div style="color: #71717a; font-size: 13px; margin-bottom: 8px;">{{ $t('dashboard.rerankModel') }}</div>
              <div style="font-size: 15px; font-weight: 500; color: #e4e4e7; margin-bottom: 8px;">
                {{ health.rerank?.model || $t('common.notConfigured') }}
              </div>
              <NTag :type="health.rerank?.enabled ? 'success' : 'info'" size="small" round>
                {{ health.rerank?.enabled ? $t('common.enabled') : $t('common.disabled') }}
              </NTag>
            </NCard>
          </NGridItem>
        </NGrid>

        <NCard style="background: #18181b; border: 1px solid #27272a; margin-top: 16px;">
          <div style="color: #71717a; font-size: 13px; margin-bottom: 8px;">{{ $t('dashboard.llmConfig') }}</div>
          <div style="font-size: 15px; font-weight: 500; color: #e4e4e7;">
            {{ health.llm?.model || $t('common.notConfigured') }}
          </div>
        </NCard>

        <!-- 统计区域 -->
        <div v-if="stats" style="margin-top: 24px;">
          <h2 style="font-size: 16px; font-weight: 600; color: #e4e4e7; margin-bottom: 12px;">{{ $t('dashboard.statsTitle') }}</h2>
          <NGrid :cols="4" :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
            <NGridItem span="4 m:1">
              <NCard class="dashboard-stat-card" style="background: #18181b; border: 1px solid #27272a;">
                <NStatistic :label="$t('dashboard.totalMemories')" :value="totalApproved" />
                <div style="color: #52525b; font-size: 12px; margin-top: 4px;">{{ $t('dashboard.totalAll') }} {{ totalCards }}</div>
              </NCard>
            </NGridItem>
            <NGridItem span="4 m:1">
              <NCard class="dashboard-stat-card" hoverable style="background: #18181b; border: 1px solid #27272a; cursor: pointer;" @click="router.push('/inbox')">
                <NStatistic :label="$t('dashboard.inboxPending')" :value="inboxPending" />
                <div style="color: #52525b; font-size: 12px; margin-top: 4px;">{{ $t('dashboard.awaitingReview') }}</div>
              </NCard>
            </NGridItem>
            <NGridItem span="4 m:1">
              <NCard class="dashboard-stat-card" hoverable style="background: #18181b; border: 1px solid #27272a; cursor: pointer;" @click="router.push('/inbox')">
                <NStatistic :label="$t('dashboard.inboxDiscarded')" :value="inboxDiscarded" />
                <div style="color: #52525b; font-size: 12px; margin-top: 4px;">{{ $t('dashboard.discardedHint') }}</div>
              </NCard>
            </NGridItem>
            <NGridItem span="4 m:1">
              <NCard class="dashboard-stat-card" style="background: #18181b; border: 1px solid #27272a;">
                <NStatistic :label="$t('dashboard.gateRequests24h')" :value="gateTotal" />
                <div style="color: #52525b; font-size: 12px; margin-top: 4px;">{{ $t('dashboard.skipRate') }} {{ gateSkipRate }}</div>
              </NCard>
            </NGridItem>
            <NGridItem span="4 m:1">
              <NCard class="dashboard-stat-card" style="background: #18181b; border: 1px solid #27272a;">
                <NStatistic :label="$t('dashboard.dailyGrowth7d')" :value="stats.daily_growth?.length ? stats.daily_growth.reduce((s: number, d: any) => s + d.count, 0) : 0" />
                <div v-if="stats.daily_growth?.length" style="color: #52525b; font-size: 12px; margin-top: 4px;">
                  {{ stats.daily_growth.map((d: any) => d.count).join(' \u2192 ') }}
                </div>
              </NCard>
            </NGridItem>
          </NGrid>

          <NCard v-if="stats.cards_by_type && Object.keys(stats.cards_by_type).length" style="background: #18181b; border: 1px solid #27272a; margin-top: 16px;">
            <div style="color: #71717a; font-size: 13px; margin-bottom: 8px;">{{ $t('dashboard.cardsByType') }}</div>
            <NSpace>
              <NTag v-for="(count, type) in stats.cards_by_type" :key="type" size="small" round>
                {{ typeLabel(String(type)) }}: {{ count }}
              </NTag>
            </NSpace>
          </NCard>
        </div>
      </div>

      <NCard v-else style="background: #18181b; border: 1px solid #27272a;">
        <div style="text-align: center; padding: 40px 0;">
          <div style="font-size: 40px; margin-bottom: 16px;">⚠️</div>
          <div style="font-size: 16px; color: #e4e4e7; margin-bottom: 8px;">{{ $t('dashboard.cannotConnect') }}</div>
          <div style="color: #71717a; font-size: 14px;">{{ $t('dashboard.ensureBackendRunning') }} {{ serverUrl }}</div>
          <NButton style="margin-top: 16px;" type="primary" @click="fetchHealth">{{ $t('dashboard.retry') }}</NButton>
        </div>
      </NCard>
    </NSpin>

    <HelpModal v-model:show="helpModal" :title="$t('dashboard.help.title')" :sections="dashboardHelpSections" />
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

.dashboard-stat-card {
  height: 100%;
}

.dashboard-stat-card :deep(.n-card__content) {
  min-height: 86px;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.first-run-card {
  background: #18181b;
  border: 1px solid #27272a;
  margin-bottom: 16px;
}

.first-run-summary {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) auto;
  align-items: center;
  gap: 12px;
  color: #a1a1aa;
  font-size: 12px;
  margin-bottom: 14px;
}

.first-run-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
}

.first-run-step {
  min-height: 116px;
  width: 100%;
  border: 1px solid #27272a;
  border-radius: 8px;
  background: #111113;
  color: inherit;
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr);
  gap: 10px;
  padding: 12px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.18s ease, background-color 0.18s ease;
}

.first-run-step:disabled {
  cursor: default;
}

.first-run-step:not(:disabled):hover {
  border-color: #3f3f46;
  background: #17171a;
}

.first-run-step.done {
  border-color: rgba(74, 222, 128, 0.38);
}

.first-run-step.optional {
  background: #151518;
}

.step-status {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  margin-top: 5px;
  background: #facc15;
  box-shadow: 0 0 0 4px rgba(250, 204, 21, 0.12);
}

.first-run-step.done .step-status {
  background: #4ade80;
  box-shadow: 0 0 0 4px rgba(74, 222, 128, 0.12);
}

.first-run-step.optional:not(.done) .step-status {
  background: #60a5fa;
  box-shadow: 0 0 0 4px rgba(96, 165, 250, 0.12);
}

.step-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.step-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.step-title {
  color: #f4f4f5;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.step-hint {
  color: #a1a1aa;
  font-size: 12px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.step-action {
  color: #c4b5fd;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
}

.continuity-card {
  background: #18181b;
  border: 1px solid #27272a;
  margin-bottom: 16px;
}

.section-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  color: #e4e4e7;
  font-size: 15px;
  font-weight: 600;
}

.continuity-metric {
  min-height: 116px;
  padding: 12px 14px;
  border: 1px solid #27272a;
  border-radius: 8px;
  background: #111113;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.metric-label {
  color: #71717a;
  font-size: 12px;
}

.metric-value {
  color: #f4f4f5;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.metric-hint {
  color: #71717a;
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.continuity-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 14px;
}

@media (max-width: 640px) {
  .first-run-summary {
    grid-template-columns: 1fr;
  }

  .first-run-grid {
    grid-template-columns: 1fr;
  }

  .first-run-step {
    min-height: 104px;
  }
}
</style>
