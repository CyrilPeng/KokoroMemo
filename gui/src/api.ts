const DEFAULT_SERVER_URL = 'http://127.0.0.1:14514'

export function getServerUrl() {
  return localStorage.getItem('kokoromemo.serverUrl') || DEFAULT_SERVER_URL
}

export function setServerUrl(url: string) {
  const normalized = url.trim().replace(/\/$/, '') || DEFAULT_SERVER_URL
  localStorage.setItem('kokoromemo.serverUrl', normalized)
  return normalized
}

export async function apiFetch(path: string, init?: RequestInit) {
  const base = getServerUrl()
  return fetch(`${base}${path}`, init)
}
