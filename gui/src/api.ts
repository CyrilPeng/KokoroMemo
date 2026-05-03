const DEFAULT_SERVER_URL = 'http://127.0.0.1:14514'

let _resolvedUrl: string | null = null

export function getServerUrl() {
  const stored = localStorage.getItem('kokoromemo.serverUrl')
  if (_resolvedUrl) return _resolvedUrl
  // Web 模式（非 Tauri）下由后端提供前端，使用同源地址
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
 * 调用 Tauri get_backend_port 发现实际后端端口。
 * 非 Tauri 环境或出错时回退到 DEFAULT_SERVER_URL。
 */
export async function resolveBackendUrl(): Promise<string> {
  // 仅在 Tauri 内运行时尝试检测端口
  if ((window as any).__TAURI_INTERNALS__) {
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const port: number = await invoke('get_backend_port')
      const url = `http://127.0.0.1:${port}`
      _resolvedUrl = url
      localStorage.setItem('kokoromemo.serverUrl', url)
      return url
    } catch (e) {
      console.warn('get_backend_port failed, falling back to default:', e)
    }
  }
  const url = !(window as any).__TAURI_INTERNALS__
    ? window.location.origin
    : localStorage.getItem('kokoromemo.serverUrl') || DEFAULT_SERVER_URL
  _resolvedUrl = url
  return url
}

export async function apiFetch(path: string, init?: RequestInit) {
  const base = getServerUrl()
  return fetch(`${base}${path}`, init)
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
