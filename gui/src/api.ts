const DEFAULT_SERVER_URL = 'http://127.0.0.1:14514'
const DEFAULT_TIMEOUT_MS = 8000

let _resolvedUrl: string | null = null

export function getServerUrl() {
  const stored = localStorage.getItem('kokoromemo.serverUrl')
  if (_resolvedUrl) return _resolvedUrl
  // Web 模式由后端提供前端页面，直接使用同源地址。
  if (!(window as any).__TAURI_INTERNALS__) return window.location.origin
  if (stored) return stored
  return DEFAULT_SERVER_URL
}

export function setServerUrl(url: string) {
  const normalized = url.trim().replace(/\/$/, '') || DEFAULT_SERVER_URL
  localStorage.setItem('kokoromemo.serverUrl', normalized)
  _resolvedUrl = normalized
  return normalized
}

/**
 * 通过 Tauri 命令发现实际后端端口。
 * Web 模式或发现失败时回退到同源地址/默认地址。
 */
export async function resolveBackendUrl(): Promise<string> {
  // 仅在 Tauri 内运行时尝试读取后端端口。
  if ((window as any).__TAURI_INTERNALS__) {
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const port: number = await invoke('get_backend_port')
      const url = `http://127.0.0.1:${port}`
      _resolvedUrl = url
      localStorage.setItem('kokoromemo.serverUrl', url)
      return url
    } catch (e) {
      console.warn('读取后端端口失败，使用默认地址:', e)
    }
  }
  const url = !(window as any).__TAURI_INTERNALS__
    ? window.location.origin
    : localStorage.getItem('kokoromemo.serverUrl') || DEFAULT_SERVER_URL
  _resolvedUrl = url
  return url
}

export async function apiFetch(path: string, init?: RequestInit & { timeoutMs?: number }) {
  const base = getServerUrl()
  const timeoutMs = init?.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const externalSignal = init?.signal
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)

  if (externalSignal) {
    if (externalSignal.aborted) controller.abort()
    else externalSignal.addEventListener('abort', () => controller.abort(), { once: true })
  }

  const { timeoutMs: _timeoutMs, signal: _signal, ...fetchInit } = init || {}
  try {
    return await fetch(`${base}${path}`, { ...fetchInit, signal: controller.signal })
  } finally {
    window.clearTimeout(timer)
  }
}

export function createWebSocket(onMessage: (data: any) => void): WebSocket {
  const base = getServerUrl().replace(/^http/, 'ws')
  const ws = new WebSocket(`${base}/ws`)
  ws.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data))
    } catch {}
  }
  return ws
}
