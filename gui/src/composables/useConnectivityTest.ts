import { ref } from 'vue'
import type { useMessage } from 'naive-ui'
import { apiFetch, friendlyError } from '../api'

export function useConnectivityTest(
  message: ReturnType<typeof useMessage>,
  t: (key: string, params?: Record<string, any>) => string,
) {
  const connectTestLoading = ref<Record<string, boolean>>({})
  const connectTestResult = ref<Record<string, { status: string; latency_ms: number; message: string }>>({})

  async function runConnectivityTest(target: string) {
    connectTestLoading.value = { ...connectTestLoading.value, [target]: true }
    connectTestResult.value = { ...connectTestResult.value, [target]: undefined as any }
    try {
      const resp = await apiFetch('/admin/connectivity-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target }),
        timeoutMs: target === 'all' ? 60000 : 20000,
      })
      const data = await resp.json()
      if (data.status === 'ok' && data.results) {
        if (target === 'all') {
          connectTestResult.value = { ...connectTestResult.value, ...data.results }
          const allOk = Object.values(data.results as Record<string, any>).every((r: any) => r.status === 'ok' || r.status === 'skipped')
          message[allOk ? 'success' : 'warning'](allOk ? t('settings.connectTestAllPass') : t('settings.connectTestPartial'))
        } else {
          const r = data.results[target]
          connectTestResult.value = { ...connectTestResult.value, [target]: r }
          if (r?.status === 'ok') message.success(t('settings.connectTestPass', { latency: r.latency_ms }))
          else if (r?.status === 'skipped') message.info(t('settings.connectTestSkipped'))
          else message.error(t('settings.connectTestFail', { error: r?.message || 'unknown' }))
        }
      } else {
        message.error(friendlyError(data.message || 'test failed', 'settings.connectTest'))
      }
    } catch (e: any) {
      message.error(t('settings.connectTestFail', { error: e?.message || String(e) }))
    }
    connectTestLoading.value = { ...connectTestLoading.value, [target]: false }
  }

  return {
    connectTestLoading,
    connectTestResult,
    runConnectivityTest,
  }
}
