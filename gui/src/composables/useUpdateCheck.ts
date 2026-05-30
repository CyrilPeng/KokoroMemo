import { ref } from 'vue'
import type { useMessage } from 'naive-ui'
import { apiFetch } from '../api'

const UPDATE_MANIFEST_URLS = [
  { name: 'GitHub', url: 'https://github.com/CyrilPeng/KokoroMemo/releases/latest/download/latest.json' },
  { name: 'GitHub Proxy', url: 'https://gh-proxy.org/https://github.com/CyrilPeng/KokoroMemo/releases/latest/download/latest.json' },
]
const GITEE_LATEST_RELEASE_API = 'https://gitee.com/api/v5/repos/CyrilPeng/KokoroMemo/releases/latest'
const CURRENT_VERSION_FALLBACK = '0.8.0'

async function getTauriAppVersion(): Promise<string> {
  if (!window.__TAURI_INTERNALS__) throw new Error('not tauri')
  const { getVersion } = await import('@tauri-apps/api/app')
  return await getVersion()
}

export function useUpdateCheck(
  message: ReturnType<typeof useMessage>,
  t: (key: string, params?: Record<string, any>) => string,
) {
  const updateChecking = ref(false)
  const updateInfo = ref<{
    checked: boolean
    hasUpdate: boolean
    currentVersion: string
    latestVersion: string
    releaseUrl: string
    sourceName: string
    assetName: string
    downloadUrl: string
    androidCommand: string
    error: string
  }>({
    checked: false,
    hasUpdate: false,
    currentVersion: '',
    latestVersion: '',
    releaseUrl: '',
    sourceName: '',
    assetName: '',
    downloadUrl: '',
    androidCommand: 'bash update.sh',
    error: '',
  })

  function normalizeVersion(version: string) {
    return version.trim().replace(/^v/i, '').split(/[+-]/)[0]
  }

  function compareVersions(a: string, b: string) {
    const left = normalizeVersion(a).split('.').map((part) => Number.parseInt(part, 10) || 0)
    const right = normalizeVersion(b).split('.').map((part) => Number.parseInt(part, 10) || 0)
    const length = Math.max(left.length, right.length)
    for (let i = 0; i < length; i += 1) {
      const diff = (left[i] || 0) - (right[i] || 0)
      if (diff !== 0) return diff > 0 ? 1 : -1
    }
    return 0
  }

  async function getCurrentAppVersion() {
    try {
      return await getTauriAppVersion()
    } catch (e) {
      try {
        const resp = await apiFetch('/health')
        if (resp.ok) {
          const data = await resp.json()
          return data.version || CURRENT_VERSION_FALLBACK
        }
      } catch {}
      return CURRENT_VERSION_FALLBACK
    }
  }

  function detectUpdateAssetKey() {
    const ua = navigator.userAgent || ''
    const platform = navigator.platform || ''
    if (/Android/i.test(ua)) return 'android-termux-aarch64'
    if (/Win/i.test(platform)) return 'windows-msi-x64'
    if (/Mac/i.test(platform)) return 'macos-app-arm64'
    if (/Linux/i.test(platform)) return 'linux-appimage-x64'
    return 'windows-msi-x64'
  }

  async function fetchJsonWithTimeout(url: string, timeoutMs = 8000) {
    const controller = new AbortController()
    const timer = window.setTimeout(() => controller.abort(), timeoutMs)
    try {
      const resp = await fetch(url, { cache: 'no-store', signal: controller.signal })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      return await resp.json()
    } finally {
      window.clearTimeout(timer)
    }
  }

  async function fetchGiteeUpdateManifest() {
    const release = await fetchJsonWithTimeout(GITEE_LATEST_RELEASE_API)
    const tag = release?.tag_name || release?.name
    const attachments = Array.isArray(release?.attach_files)
      ? release.attach_files
      : Array.isArray(release?.assets)
        ? release.assets
        : []
    const manifestAsset = attachments.find((item: any) => (item?.name || item?.filename) === 'latest.json')
    const manifestUrl = manifestAsset?.browser_download_url
      || manifestAsset?.download_url
      || manifestAsset?.url
      || manifestAsset?.html_url
      || (tag ? `https://gitee.com/CyrilPeng/KokoroMemo/releases/download/${tag}/latest.json` : '')
    if (!manifestUrl) throw new Error('missing latest manifest')
    return await fetchJsonWithTimeout(manifestUrl)
  }

  async function fetchUpdateManifest() {
    const errors: string[] = []
    try {
      const resp = await apiFetch('/admin/update-manifest', { timeoutMs: 10000 })
      const payload = await resp.json()
      if (resp.ok && payload.status === 'ok') {
        return {
          sourceName: payload.sourceName || payload.source_name || '后端代理',
          data: payload.data,
          errors: Array.isArray(payload.errors) ? payload.errors : [],
        }
      }
      errors.push(`后端代理: ${payload.message || payload.detail || `HTTP ${resp.status}`}`)
      if (Array.isArray(payload.errors)) errors.push(...payload.errors)
    } catch (e) {
      errors.push(`后端代理: ${e instanceof Error ? e.message : String(e)}`)
    }
    for (const source of UPDATE_MANIFEST_URLS) {
      try {
        return { sourceName: source.name, data: await fetchJsonWithTimeout(source.url), errors }
      } catch (e) {
        errors.push(`${source.name}: ${e instanceof Error ? e.message : String(e)}`)
      }
    }
    try {
      return { sourceName: 'Gitee', data: await fetchGiteeUpdateManifest(), errors }
    } catch (e) {
      errors.push(`Gitee: ${e instanceof Error ? e.message : String(e)}`)
    }
    throw new Error(errors.join('；') || 'manifest unavailable')
  }

  function pickUpdateAsset(manifest: any) {
    const assets = manifest?.assets || {}
    const key = detectUpdateAssetKey()
    const asset = assets[key] || assets['windows-msi-x64'] || Object.values(assets)[0] || null
    if (!asset || typeof asset !== 'object') return { assetName: '', downloadUrl: '' }
    const mirrors = Array.isArray((asset as any).mirrors) ? (asset as any).mirrors : []
    const firstMirror = mirrors.find((item: any) => item?.url)
    return {
      assetName: (asset as any).name || '',
      downloadUrl: (asset as any).url || firstMirror?.url || '',
    }
  }

  async function checkForUpdates(silent = false) {
    updateChecking.value = true
    try {
      const currentVersion = await getCurrentAppVersion()
      const { sourceName, data } = await fetchUpdateManifest()
      const latestVersion = data.version || data.tag || ''
      const releaseUrl = data.release_url || data.changelog_url || 'https://github.com/CyrilPeng/KokoroMemo/releases/latest'
      const { assetName, downloadUrl } = pickUpdateAsset(data)
      const hasUpdate = latestVersion ? compareVersions(latestVersion, currentVersion) > 0 : false
      updateInfo.value = {
        checked: true,
        hasUpdate,
        currentVersion,
        latestVersion,
        releaseUrl,
        sourceName,
        assetName,
        downloadUrl,
        androidCommand: 'bash update.sh',
        error: '',
      }
      if (!silent) {
        message[hasUpdate ? 'success' : 'info'](
          hasUpdate ? t('settings.updateAvailable') : t('settings.noUpdateAvailable'),
        )
      }
    } catch (e) {
      updateInfo.value = {
        ...updateInfo.value,
        checked: true,
        error: e instanceof Error ? e.message : String(e),
      }
      if (!silent) message.error(t('settings.updateCheckFailed'))
    } finally {
      updateChecking.value = false
    }
  }

  async function openExternal(url: string) {
    try {
      if (!window.__TAURI_INTERNALS__) throw new Error('not tauri')
      const { open } = await import('@tauri-apps/plugin-shell')
      await open(url)
    } catch {
      window.open(url, '_blank', 'noopener,noreferrer')
    }
  }

  function openReleasePage() {
    if (updateInfo.value.releaseUrl) {
      openExternal(updateInfo.value.releaseUrl)
    }
  }

  function downloadUpdateAsset() {
    if (updateInfo.value.downloadUrl) openExternal(updateInfo.value.downloadUrl)
  }

  return {
    updateChecking,
    updateInfo,
    compareVersions,
    checkForUpdates,
    openReleasePage,
    openExternal,
    downloadUpdateAsset,
    openPortModal: undefined as any, // placeholder, not needed
  }
}
