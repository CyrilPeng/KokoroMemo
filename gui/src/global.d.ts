// Global type declarations for browser APIs and Tauri environment

interface Window {
  /**
   * Tauri runtime internals, present when running inside Tauri webview
   */
  __TAURI_INTERNALS__?: unknown

  /**
   * File System Access API - not available in all browsers
   * @see https://developer.mozilla.org/en-US/docs/Web/API/Window/showSaveFilePicker
   */
  showSaveFilePicker?: (options?: {
    suggestedName?: string
    types?: Array<{
      description?: string
      accept: Record<string, string[]>
    }>
    excludeAcceptAllOption?: boolean
  }) => Promise<FileSystemFileHandle>

  /**
   * Request idle callback API - not available in Safari
   * @see https://developer.mozilla.org/en-US/docs/Web/API/Window/requestIdleCallback
   */
  requestIdleCallback?: (
    callback: IdleRequestCallback,
    options?: IdleRequestOptions
  ) => number
}
