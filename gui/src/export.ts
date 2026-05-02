import { isTauri } from '@tauri-apps/api/core'

export async function saveJsonExport(defaultFileName: string, data: unknown): Promise<string | null> {
  const contents = JSON.stringify(data, null, 2)

  if (isTauri()) {
    const { save } = await import('@tauri-apps/plugin-dialog')
    const { invoke } = await import('@tauri-apps/api/core')
    const selectedPath = await save({
      title: defaultFileName,
      defaultPath: defaultFileName,
      filters: [{ name: 'JSON', extensions: ['json'] }],
    })
    if (!selectedPath) return null
    await invoke('write_text_file', { path: selectedPath, contents })
    return selectedPath
  }

  const filePicker = (window as any).showSaveFilePicker
  if (typeof filePicker === 'function') {
    const handle = await filePicker({
      suggestedName: defaultFileName,
      types: [{ description: 'JSON', accept: { 'application/json': ['.json'] } }],
    })
    const writable = await handle.createWritable()
    await writable.write(contents)
    await writable.close()
    return handle.name || defaultFileName
  }

  const blob = new Blob([contents], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = defaultFileName
  anchor.click()
  URL.revokeObjectURL(url)
  return defaultFileName
}
