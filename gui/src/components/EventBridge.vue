<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { createWebSocket } from '../api'

const message = useMessage()
const { t } = useI18n()

let ws: WebSocket | null = null
let reconnectTimer: number | null = null
let stopped = false

function isMobileBrowser() {
  return /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '')
}

function shouldConnectWebSocket() {
  // Web UI 由后端同源提供时，实时通知不是首屏必需能力。
  // Android/Termux 轻量依赖可能没有 WebSocket 支持，浏览器模式下直接跳过，避免 /ws 升级失败导致页面卡住。
  if (!(window as any).__TAURI_INTERNALS__) return false
  return !isMobileBrowser()
}

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
  if (!shouldConnectWebSocket()) return
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
