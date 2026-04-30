<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { createWebSocket } from '../api'

const message = useMessage()
const router = useRouter()
const { t } = useI18n()

let ws: WebSocket | null = null
let reconnectTimer: number | null = null
let stopped = false

function dispatchToWindow(data: any) {
  try {
    window.dispatchEvent(new CustomEvent('kokoromemo:event', { detail: data }))
  } catch {}
}

function showNotification(data: any) {
  if (data.event === 'inbox_new') {
    const content = (data.content || '').slice(0, 40)
    message.info(t('events.inboxNew', { content }), {
      duration: 5000,
      closable: true,
      onClick: () => router.push('/inbox'),
    })
  } else if (data.event === 'card_approved') {
    const content = (data.content || '').slice(0, 40)
    message.success(t('events.cardApproved', { content }), {
      duration: 4000,
      closable: true,
    })
  }
}

function connect() {
  if (stopped) return
  try {
    ws = createWebSocket((data) => {
      dispatchToWindow(data)
      showNotification(data)
    })
    ws.onclose = () => {
      ws = null
      if (stopped) return
      reconnectTimer = window.setTimeout(connect, 5000)
    }
    ws.onerror = () => {
      try { ws?.close() } catch {}
    }
  } catch {
    if (!stopped) reconnectTimer = window.setTimeout(connect, 5000)
  }
}

onMounted(() => {
  setTimeout(connect, 1000)
})

onBeforeUnmount(() => {
  stopped = true
  if (reconnectTimer) clearTimeout(reconnectTimer)
  try { ws?.close() } catch {}
})
</script>

<template>
  <span style="display: none;"></span>
</template>
