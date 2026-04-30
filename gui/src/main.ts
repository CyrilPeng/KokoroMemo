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
    { path: '/state', component: () => import('./views/ConversationState.vue') },
    { path: '/settings', component: () => import('./views/Settings.vue') },
  ],
})

async function bootstrap() {
  // Resolve actual backend port before mounting (reads .port file via Tauri)
  await resolveBackendUrl()

  const app = createApp(App)
  app.use(i18n)
  app.use(router)
  app.mount('#app')
}

bootstrap()
