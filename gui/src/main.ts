import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import i18n from './i18n'
import { resolveBackendUrl } from './api'
import './style.css'

const viewLoaders = {
  dashboard: () => import('./views/Dashboard.vue'),
  memories: () => import('./views/Memories.vue'),
  memoryGraph: () => import('./views/MemoryGraph.vue'),
  inbox: () => import('./views/Inbox.vue'),
  characters: () => import('./views/Characters.vue'),
  state: () => import('./views/ConversationState.vue'),
  settings: () => import('./views/Settings.vue'),
}

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: viewLoaders.dashboard },
    { path: '/memories', component: viewLoaders.memories },
    { path: '/memory-graph', component: viewLoaders.memoryGraph },
    { path: '/inbox', component: viewLoaders.inbox },
    { path: '/characters', component: viewLoaders.characters },
    { path: '/state', component: viewLoaders.state },
    { path: '/settings', component: viewLoaders.settings },
  ],
})

function shouldPreloadViews() {
  if (!(window as any).__TAURI_INTERNALS__) return false
  return !/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '')
}

function preloadViews() {
  if (!shouldPreloadViews()) return
  const run = () => {
    for (const loader of Object.values(viewLoaders)) loader().catch(() => {})
  }
  const requestIdleCallback = (window as any).requestIdleCallback as undefined | ((cb: () => void, options?: { timeout: number }) => number)
  if (requestIdleCallback) requestIdleCallback(run, { timeout: 2000 })
  else window.setTimeout(run, 800)
}

async function bootstrap() {
  // 桌面端需要先通过 Tauri 获取实际后端端口；浏览器模式直接走同源，避免移动端首屏等待探测。
  if ((window as any).__TAURI_INTERNALS__) await resolveBackendUrl()

  const app = createApp(App)
  app.use(i18n)
  app.use(router)
  app.mount('#app')
  preloadViews()
}

bootstrap()
