import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import i18n from './i18n'
import { resolveBackendUrl } from './api'
import './style.css'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: () => import('./views/Dashboard.vue') },
    { path: '/memories', component: () => import('./views/Memories.vue') },
    { path: '/memory-graph', component: () => import('./views/MemoryGraph.vue') },
    { path: '/inbox', component: () => import('./views/Inbox.vue') },
    { path: '/characters', component: () => import('./views/Characters.vue') },
    { path: '/state', component: () => import('./views/ConversationState.vue') },
    { path: '/settings', component: () => import('./views/Settings.vue') },
  ],
})

async function bootstrap() {
  // 挂载前解析实际后端端口（通过 Tauri 读取 .port 文件）
  await resolveBackendUrl()

  const app = createApp(App)
  app.use(i18n)
  app.use(router)
  app.mount('#app')
}

bootstrap()
