import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
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

const app = createApp(App)
app.use(router)
app.mount('#app')
