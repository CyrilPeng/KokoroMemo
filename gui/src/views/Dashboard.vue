<script setup lang="ts">
import { ref, computed, onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NCard, NGrid, NGridItem, NTag, NSpin, NSpace, NButton, NStatistic, NIcon, NModal } from 'naive-ui'
import { HelpCircleOutline } from '@vicons/ionicons5'
import { useI18n } from 'vue-i18n'
import { apiFetch, getServerUrl, setServerUrl } from '../api'
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
      const actualUrl = `http://127.0.0.1:${health.value.actual_port}`
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

onMounted(() => {
  window.setTimeout(() => {
    fetchHealth()
    fetchStats()
  }, 0)
})

function onWsEvent(e: any) {
  const data = e.detail
  if (data?.event === 'inbox_new' || data?.event === 'card_approved') {
    fetchStats()
  }
}
onMounted(() => window.addEventListener('kokoromemo:event', onWsEvent))
onBeforeUnmount(() => window.removeEventListener('kokoromemo:event', onWsEvent))
</script>

<template>
  <div>
    <div style="margin-bottom: 28px; display: flex; justify-content: space-between; align-items: flex-start;">
      <div>
        <h1 style="font-size: 24px; font-weight: 600; color: #e4e4e7; margin-bottom: 4px;">{{ $t('dashboard.title') }}</h1>
        <p style="color: #71717a; font-size: 14px; margin: 0;">{{ $t('dashboard.subtitle') }}</p>
      </div>
      <NButton quaternary @click="helpModal = true">
        <template #icon><NIcon><HelpCircleOutline /></NIcon></template>
        {{ $t('common.help') }}
      </NButton>
    </div>

    <NSpin :show="loading">
      <div v-if="health">
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
              <NCard style="background: #18181b; border: 1px solid #27272a;">
                <NStatistic :label="$t('dashboard.totalMemories')" :value="totalApproved" />
                <div style="color: #52525b; font-size: 12px; margin-top: 4px;">{{ $t('dashboard.totalAll') }} {{ totalCards }}</div>
              </NCard>
            </NGridItem>
            <NGridItem span="4 m:1">
              <NCard hoverable style="background: #18181b; border: 1px solid #27272a; cursor: pointer;" @click="router.push('/inbox')">
                <NStatistic :label="$t('dashboard.inboxPending')" :value="inboxPending" />
                <div style="color: #52525b; font-size: 12px; margin-top: 4px;">{{ $t('dashboard.awaitingReview') }}</div>
              </NCard>
            </NGridItem>
            <NGridItem span="4 m:1">
              <NCard style="background: #18181b; border: 1px solid #27272a;">
                <NStatistic :label="$t('dashboard.gateRequests24h')" :value="gateTotal" />
                <div style="color: #52525b; font-size: 12px; margin-top: 4px;">{{ $t('dashboard.skipRate') }} {{ gateSkipRate }}</div>
              </NCard>
            </NGridItem>
            <NGridItem span="4 m:1">
              <NCard style="background: #18181b; border: 1px solid #27272a;">
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

    <NModal v-model:show="helpModal" preset="card" :title="$t('dashboard.help.title')" style="width: 600px; background: #18181b;" :mask-closable="true">
      <div class="help-content">
        <p>{{ $t('dashboard.help.intro') }}</p>
        <p><strong>{{ $t('dashboard.totalMemories') }}</strong>: {{ $t('dashboard.help.totalMemories') }}</p>
        <p><strong>{{ $t('dashboard.inboxPending') }}</strong>: {{ $t('dashboard.help.inboxPending') }}</p>
        <p><strong>{{ $t('dashboard.gateRequests24h') }}</strong>: {{ $t('dashboard.help.gateRequests') }}</p>
        <p><strong>{{ $t('dashboard.dailyGrowth7d') }}</strong>: {{ $t('dashboard.help.dailyGrowth') }}</p>
        <p><strong>{{ $t('dashboard.cardsByType') }}</strong>: {{ $t('dashboard.help.cardsByType') }}</p>
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
