const DEFAULT_SERVER_URL = 'http://127.0.0.1:14514'
const DEFAULT_TIMEOUT_MS = 12000
const MOBILE_TIMEOUT_MS = 20000
const PROBE_TIMEOUT_MS = 1200

let _resolvedUrl: string | null = null
let _resolvingUrl: Promise<string> | null = null

function isWebMode() {
  return !window.__TAURI_INTERNALS__
}

function isMobileBrowser() {
  return /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '')
}

function sameOriginUrl() {
  return window.location.origin.replace(/\/$/, '')
}

function getAdminToken() {
  return localStorage.getItem('kokoromemo.adminToken')?.trim() || ''
}

function toWebSocketBaseUrl(base: string) {
  return base.replace(/^http/, 'ws').replace(/\/$/, '')
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
  if (window.__TAURI_INTERNALS__) {
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
  const timeoutMs = init?.timeoutMs ?? (isWebMode() && isMobileBrowser() ? MOBILE_TIMEOUT_MS : DEFAULT_TIMEOUT_MS)
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

export async function createWebSocket(onMessage: (data: any) => void): Promise<WebSocket> {
  const base = toWebSocketBaseUrl(await resolveBackendUrl())
  const token = getAdminToken()
  const url = token ? `${base}/ws?token=${encodeURIComponent(token)}` : `${base}/ws`
  const ws = new WebSocket(url)
  ws.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data))
    } catch {}
  }
  return ws
}

/**
 * 将原始错误信息映射为用户友好的提示文本。
 * @param raw 原始错误字符串（如 "Failed to fetch"、"HTTP 401: Invalid API key"）
 * @param context 触发上下文（如 "inbox.approve"、"settings.testConnectivity"），用于定制提示
 * @returns 友好的错误提示文本
 */
export function friendlyError(raw: string, _context?: string): string {
  if (!raw) return '未知错误'

  const lower = raw.toLowerCase()

  // 网络层错误
  if (lower.includes('failed to fetch') || lower.includes('networkerror')) {
    return '无法连接到后端服务，请确认后端已启动并且 URL 正确。'
  }
  if (lower.includes('aborted') || lower.includes('timeout') || lower.includes('timed out')) {
    return '请求超时，可能是网络不稳定或服务响应过慢，请稍后再试。'
  }

  // HTTP 错误码
  if (/http 401|unauthorized|invalid api key/i.test(raw)) {
    return 'API Key 无效或已过期，请在设置中检查对应的 API Key。'
  }
  if (/http 403|forbidden/i.test(raw)) {
    return '访问被拒绝，可能需要配置 Admin Token 或允许远程访问。'
  }
  if (/http 404|not found/i.test(raw)) {
    return '请求的资源不存在，请检查 URL 或配置。'
  }
  if (/http 429|too many requests|rate limit/i.test(raw)) {
    return '请求过于频繁，已被限流，请稍后再试。'
  }
  if (/http 500|internal server error/i.test(raw)) {
    return '服务内部错误，请查看后端日志或在设置页检查连通性。'
  }
  if (/http 502|503|504|bad gateway|service unavailable|gateway timeout/i.test(raw)) {
    return '上游服务暂时不可用，可能是模型服务商的问题，请稍后再试。'
  }

  // LLM 相关错误
  if (/context.?length|max.?tokens|token.?limit/i.test(raw)) {
    return '请求内容过长，超出模型上下文窗口，可减少历史消息或调高 max_tokens。'
  }
  if (/model.?not.?found|model.?does.?not.?exist|invalid.?model/i.test(raw)) {
    return '模型名称不存在，请在设置中确认当前使用的模型名。'
  }

  // Embedding/Rerank 相关
  if (/dimension.?mismatch|embedding.?size/i.test(raw)) {
    return '向量维度不匹配，可能切换了 Embedding 模型但未重建索引，请在设置中重建向量索引。'
  }

  // 数据库错误
  if (/disk.?full|no space left/i.test(raw)) {
    return '磁盘空间不足，请清理磁盘后重试。'
  }
  if (/database.?locked|busy.?timeout/i.test(raw)) {
    return '数据库被锁定，可能是并发操作冲突，请稍后再试。'
  }

  // 兜底：返回原始信息（截断到 120 字符）
  return raw.length > 120 ? raw.slice(0, 120) + '...' : raw
}
