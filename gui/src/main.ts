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
  conversations: () => import('./views/Conversations.vue'),
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
    { path: '/conversations', component: viewLoaders.conversations },
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

function warmupBackendUrl() {
  if (!(window as any).__TAURI_INTERNALS__) return
  resolveBackendUrl().catch((error) => {
    console.warn('Backend port discovery failed; requests will retry:', error)
  })
}

function bootstrap() {
  const app = createApp(App)
  app.use(i18n)
  app.use(router)
  app.mount('#app')
  warmupBackendUrl()
  preloadViews()
}

bootstrap()
