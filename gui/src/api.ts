const DEFAULT_SERVER_URL = 'http://127.0.0.1:14514'
const DEFAULT_TIMEOUT_MS = 8000
const PROBE_TIMEOUT_MS = 1200

let _resolvedUrl: string | null = null
let _resolvingUrl: Promise<string> | null = null

function isWebMode() {
  return !(window as any).__TAURI_INTERNALS__
}

function sameOriginUrl() {
  return window.location.origin.replace(/\/$/, '')
}

export function getServerUrl() {
  const stored = localStorage.getItem('kokoromemo.serverUrl')
  // Web 模式由后端提供前端页面，直接使用同源地址。
  // Android 浏览器里 localStorage 可能残留 14514 以外的端口；同源访问最稳定，也能避免仪表盘误判离线。
  if (isWebMode()) return sameOriginUrl()
  if (_resolvedUrl) return _resolvedUrl
  if (stored) return stored
  return DEFAULT_SERVER_URL
}

export function setServerUrl(url: string) {
  if (isWebMode()) {
    _resolvedUrl = sameOriginUrl()
    localStorage.removeItem('kokoromemo.serverUrl')
    return _resolvedUrl
  }
  const normalized = url.trim().replace(/\/$/, '') || DEFAULT_SERVER_URL
  localStorage.setItem('kokoromemo.serverUrl', normalized)
  _resolvedUrl = normalized
  return normalized
}

async function fetchJsonWithTimeout(url: string, timeoutMs = PROBE_TIMEOUT_MS) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const resp = await fetch(url, { signal: controller.signal, cache: 'no-store' })
    if (!resp.ok) return null
    return await resp.json()
  } catch {
    return null
  } finally {
    window.clearTimeout(timer)
  }
}

async function fetchTextWithTimeout(url: string, timeoutMs = PROBE_TIMEOUT_MS) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const resp = await fetch(url, { signal: controller.signal, cache: 'no-store' })
    if (!resp.ok) return ''
    return await resp.text()
  } catch {
    return ''
  } finally {
    window.clearTimeout(timer)
  }
}

async function tryHealthBase(base: string): Promise<string | null> {
  const normalized = base.replace(/\/$/, '')
  const data = await fetchJsonWithTimeout(`${normalized}/health`)
  if (data?.status !== 'ok') return null
  const actualPort = Number(data.actual_port || data.server_port)
  if (actualPort && window.location.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:${actualPort}`
  }
  return normalized
}

async function discoverWebBackendUrl(): Promise<string> {
  const origin = sameOriginUrl()
  const fromOrigin = await tryHealthBase(origin)
  if (fromOrigin) return origin

  const portText = await fetchTextWithTimeout(`${origin}/.port`, 600)
  const port = Number(portText.trim())
  if (port) {
    const fromPortFile = await tryHealthBase(`${window.location.protocol}//${window.location.hostname}:${port}`)
    if (fromPortFile) return `${window.location.protocol}//${window.location.hostname}:${port}`
  }

  return origin
}

/**
 * 通过 Tauri 命令发现实际后端端口。
 * Web 模式或发现失败时回退到同源地址/默认地址。
 */
export async function resolveBackendUrl(): Promise<string> {
  if (_resolvingUrl) return _resolvingUrl
  _resolvingUrl = resolveBackendUrlInner().finally(() => {
    _resolvingUrl = null
  })
  return _resolvingUrl
}

async function resolveBackendUrlInner(): Promise<string> {
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
  if (isWebMode()) {
    const url = await discoverWebBackendUrl()
    _resolvedUrl = url
    return url
  }
  const url = localStorage.getItem('kokoromemo.serverUrl') || DEFAULT_SERVER_URL
  _resolvedUrl = url
  localStorage.setItem('kokoromemo.serverUrl', url)
  return url
}

export async function apiFetch(path: string, init?: RequestInit & { timeoutMs?: number }) {
  let base = getServerUrl()
  const timeoutMs = init?.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const externalSignal = init?.signal
  const { timeoutMs: _timeoutMs, signal: _signal, ...fetchInit } = init || {}

  async function requestOnce(targetBase: string) {
    const controller = new AbortController()
    const timer = window.setTimeout(() => controller.abort(), timeoutMs)
    if (externalSignal) {
      if (externalSignal.aborted) controller.abort()
      else externalSignal.addEventListener('abort', () => controller.abort(), { once: true })
    }
    try {
      return await fetch(`${targetBase}${path}`, { ...fetchInit, signal: controller.signal })
    } finally {
      window.clearTimeout(timer)
    }
  }

  let resp: Response
  try {
    resp = await requestOnce(base)
  } catch (error) {
    _resolvedUrl = null
    base = await resolveBackendUrl()
    resp = await requestOnce(base)
  }
  if (!isWebMode() && (resp.status === 404 || resp.status === 0)) {
    _resolvedUrl = null
    base = await resolveBackendUrl()
    resp = await requestOnce(base)
  }
  return resp
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
