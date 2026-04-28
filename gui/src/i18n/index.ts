import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN'
import enUS from './en-US'

const messages = {
  'zh-CN': zhCN,
  'en-US': enUS,
}

function detectLanguage(): string {
  const saved = localStorage.getItem('kokoromemo.language')
  if (saved && messages[saved as keyof typeof messages]) return saved

  const nav = navigator.language || ''
  if (nav.startsWith('zh')) return 'zh-CN'
  return 'en-US'
}

const i18n = createI18n({
  legacy: false,
  locale: detectLanguage(),
  fallbackLocale: 'zh-CN',
  messages,
})

export default i18n

export function setLanguage(locale: string) {
  ;(i18n.global.locale as any).value = locale
  localStorage.setItem('kokoromemo.language', locale)
}

export function getLanguage(): string {
  return (i18n.global.locale as any).value
}
