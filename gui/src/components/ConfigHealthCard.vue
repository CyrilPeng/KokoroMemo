<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NCard, NProgress, NTag, NButton, NSpace } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { apiFetch } from '../api'

const router = useRouter()
const { t } = useI18n()
const loading = ref(true)
const configStatus = ref<any>(null)

async function fetchStatus() {
  loading.value = true
  try {
    const resp = await apiFetch('/admin/config-status', { timeoutMs: 5000 })
    if (resp.ok) {
      configStatus.value = await resp.json()
    }
  } catch {
    // ignore
  }
  loading.value = false
}

function tagType(comp: any): 'success' | 'warning' | 'default' {
  if (comp?.configured) return 'success'
  if (comp?.required) return 'warning'
  return 'default'
}

function statusLabel(comp: any): string {
  if (comp?.reason === 'disabled') return t('dashboard.configStatus.disabled')
  if (comp?.configured) return t('dashboard.configStatus.configured')
  if (!comp?.required) return t('dashboard.configStatus.optionalNotSet')
  const missing = (comp?.missing || []).join(', ')
  return t('dashboard.configStatus.missing', { missing })
}

onMounted(fetchStatus)
</script>

<template>
  <NCard style="background: #18181b; border: 1px solid #27272a;">
    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px;">
      <div style="color: #71717a; font-size: 13px;">{{ t('dashboard.configStatus.title') }}</div>
      <NProgress
        type="circle"
        :percentage="configStatus?.health_score ?? 0"
        :stroke-width="6"
        :color="
          configStatus && configStatus.health_score >= 100
            ? '#4ade80'
            : configStatus && configStatus.health_score >= 60
              ? '#facc15'
              : '#f87171'
        "
        rail-color="#27272a"
        style="width: 52px; height: 52px;"
      >
        <span style="font-size: 12px; font-weight: 600; color: #e4e4e7;">{{ configStatus?.health_score ?? 0 }}%</span>
      </NProgress>
    </div>

    <NSpace vertical :size="6">
      <div
        v-for="(comp, key) in (configStatus?.components || {})"
        :key="key"
        style="display: flex; align-items: center; gap: 10px; padding: 6px 0;"
      >
        <span style="color: #e4e4e7; font-size: 14px; min-width: 100px;">{{ comp.name }}</span>
        <span style="color: #a1a1aa; font-size: 13px; flex: 1;">{{ statusLabel(comp) }}</span>
        <NTag :type="tagType(comp)" size="tiny" round>
          {{ comp.required ? t('dashboard.configStatus.required') : t('dashboard.configStatus.optional') }}
        </NTag>
      </div>
    </NSpace>

    <div style="margin-top: 14px;">
      <NButton
        v-if="configStatus && configStatus.health_score < 100"
        type="primary"
        size="small"
        @click="router.push('/settings')"
      >
        {{ t('dashboard.configStatus.goToSettings') }}
      </NButton>
      <NTag v-else-if="configStatus" type="success" size="small" round>
        {{ t('dashboard.configStatus.allReady') }}
      </NTag>
    </div>
  </NCard>
</template>
