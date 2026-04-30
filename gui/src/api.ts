const DEFAULT_SERVER_URL = 'http://127.0.0.1:14514'

let _resolvedUrl: string | null = null

export function getServerUrl() {
  return _resolvedUrl || localStorage.getItem('kokoromemo.serverUrl') || DEFAULT_SERVER_URL
}

export function setServerUrl(url: string) {
  const normalized = url.trim().replace(/\/$/, '') || DEFAULT_SERVER_URL
  localStorage.setItem('kokoromemo.serverUrl', normalized)
  _resolvedUrl = normalized
  return normalized
}

/**
 * Call Tauri get_backend_port to discover the actual backend port.
 * Falls back to DEFAULT_SERVER_URL if not in Tauri or on error.
 */
export async function resolveBackendUrl(): Promise<string> {
  // Only attempt Tauri port detection if running inside Tauri
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
  const url = localStorage.getItem('kokoromemo.serverUrl') || DEFAULT_SERVER_URL
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
