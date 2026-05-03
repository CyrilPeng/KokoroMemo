<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import EventBridge from './components/EventBridge.vue'
import { apiFetch } from './api'
import {
  NConfigProvider,
  NLayout,
  NLayoutSider,
  NLayoutContent,
  NMenu,
  NIcon,
  NMessageProvider,
  NDialogProvider,
  NButton,
  darkTheme,
} from 'naive-ui'
import type { MenuOption, GlobalThemeOverrides } from 'naive-ui'
import {
  HomeOutline,
  BulbOutline,
  ReaderOutline,
  MailOutline,
  PersonOutline,
  GitNetworkOutline,
  SettingsOutline,
  LogoGithub,
  MenuOutline,
} from '@vicons/ionicons5'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()

const serverVersion = ref('')
const isMobile = ref(false)
const mobileMenuOpen = ref(false)
let mediaQuery: MediaQueryList | null = null

function updateMobileFlag() {
  isMobile.value = Boolean(mediaQuery?.matches ?? window.innerWidth <= 768)
}

onMounted(() => {
  mediaQuery = window.matchMedia('(max-width: 768px)')
  updateMobileFlag()
  mediaQuery.addEventListener?.('change', updateMobileFlag)
})

onBeforeUnmount(() => {
  mediaQuery?.removeEventListener?.('change', updateMobileFlag)
})

onMounted(async () => {
  try {
    const resp = await apiFetch('/health')
    if (resp.ok) {
      const data = await resp.json()
      serverVersion.value = data.version || ''
    }
  } catch {}
})

function renderIcon(icon: any) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const menuOptions = computed<MenuOption[]>(() => [
  { label: t('nav.dashboard'), key: '/dashboard', icon: renderIcon(HomeOutline) },
  { label: t('nav.memories'), key: '/memories', icon: renderIcon(BulbOutline) },
  { label: t('nav.memoryGraph'), key: '/memory-graph', icon: renderIcon(GitNetworkOutline) },
  { label: t('nav.inbox'), key: '/inbox', icon: renderIcon(MailOutline) },
  { label: t('nav.state'), key: '/state', icon: renderIcon(ReaderOutline) },
  { label: t('nav.characters'), key: '/characters', icon: renderIcon(PersonOutline) },
  { label: t('nav.settings'), key: '/settings', icon: renderIcon(SettingsOutline) },
])

function handleMenuUpdate(key: string) {
  router.push(key)
}


async function syncCloseToTraySetting() {
  const enabled = localStorage.getItem('kokoromemo.closeToTray') === 'true'
  if (!(window as any).__TAURI_INTERNALS__) return
  try {
    const { invoke } = await import('@tauri-apps/api/core')
    await invoke('set_close_to_tray', { enabled })
  } catch (e) {
    // 浏览器开发模式或旧版桌面端可能没有该命令。
  }
}

onMounted(syncCloseToTraySetting)

async function openGitHub() {
  const url = 'https://github.com/CyrilPeng/KokoroMemo'
  if ((window as any).__TAURI_INTERNALS__) {
    try {
      const { open } = await import('@tauri-apps/plugin-shell')
      await open(url)
      return
    } catch {}
  }
  window.open(url, '_blank')
}

function handleMobileMenuUpdate(key: string) {
  handleMenuUpdate(key)
  mobileMenuOpen.value = false
}
const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#a78bfa',
    primaryColorHover: '#c4b5fd',
    primaryColorPressed: '#7c3aed',
    bodyColor: '#0f0f11',
    cardColor: '#18181b',
    modalColor: '#18181b',
    popoverColor: '#18181b',
    borderColor: '#27272a',
    dividerColor: '#27272a',
    inputColor: '#27272a',
    tableHeaderColor: '#18181b',
  },
  Card: {
    borderRadius: '12px',
  },
  Menu: {
    itemTextColor: '#a1a1aa',
    itemTextColorActive: '#e4e4e7',
    itemIconColor: '#a1a1aa',
    itemIconColorActive: '#a78bfa',
    itemColorActive: 'rgba(167, 139, 250, 0.1)',
    itemColorActiveHover: 'rgba(167, 139, 250, 0.15)',
  },
}
</script>

<template>
  <NConfigProvider :theme="darkTheme" :theme-overrides="themeOverrides">
    <NMessageProvider>
      <NDialogProvider>
      <EventBridge />
      <NLayout class="app-shell" :has-sider="!isMobile">
        <NLayoutSider
          v-if="!isMobile"
          bordered
          :width="220"
          :native-scrollbar="false"
          class="app-sidebar"
        >
          <div class="brand-block">
            <img src="./assets/logo.png" class="brand-logo" />
            <span class="brand-title">KokoroMemo</span>
          </div>
          <NMenu
            :options="menuOptions"
            :value="route.path"
            @update:value="handleMenuUpdate"
            :indent="24"
          />
          <div class="sidebar-footer">
            <NIcon :size="18" style="cursor: pointer; color: #71717a;" @click="openGitHub">
              <LogoGithub />
            </NIcon>
            <span class="footer-text">{{ serverVersion ? `v${serverVersion} - ${$t('common.tagline')}` : $t('common.tagline') }}</span>
          </div>
        </NLayoutSider>

        <NLayoutContent :native-scrollbar="false" :content-style="isMobile ? 'padding: 72px 14px 20px;' : 'padding: 32px;'">
          <div v-if="isMobile" class="mobile-topbar">
            <NButton quaternary circle @click="mobileMenuOpen = true" aria-label="Open navigation">
              <template #icon><NIcon><MenuOutline /></NIcon></template>
            </NButton>
            <div class="mobile-brand">
              <img src="./assets/logo.png" class="mobile-logo" />
              <span>KokoroMemo</span>
            </div>
            <span class="mobile-version">{{ serverVersion ? `v${serverVersion}` : '' }}</span>
          </div>
          <RouterView />
        </NLayoutContent>
      </NLayout>

      <div v-if="isMobile && mobileMenuOpen" class="mobile-menu-mask" @click="mobileMenuOpen = false">
        <aside class="mobile-menu-panel" @click.stop>
          <NButton class="mobile-menu-close" quaternary circle @click="mobileMenuOpen = false" aria-label="Close navigation">×</NButton>
          <div class="brand-block mobile-drawer-brand">
            <img src="./assets/logo.png" class="brand-logo" />
            <span class="brand-title">KokoroMemo</span>
          </div>
          <NMenu
            :options="menuOptions"
            :value="route.path"
            @update:value="handleMobileMenuUpdate"
            :indent="24"
          />
          <div class="mobile-drawer-footer">
            <NIcon :size="18" style="cursor: pointer; color: #71717a;" @click="openGitHub">
              <LogoGithub />
            </NIcon>
            <span class="footer-text">{{ serverVersion ? `v${serverVersion} - ${$t('common.tagline')}` : $t('common.tagline') }}</span>
          </div>
        </aside>
      </div>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>


<style scoped>
.app-shell {
  height: 100vh;
  background: #0f0f11;
}
.app-sidebar {
  background: #18181b;
  position: relative;
}
.brand-block {
  padding: 20px 24px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-logo {
  width: 32px;
  height: 32px;
  border-radius: 8px;
}
.brand-title {
  font-size: 18px;
  font-weight: 600;
  color: #e4e4e7;
}
.sidebar-footer {
  position: absolute;
  bottom: 16px;
  left: 24px;
  right: 24px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.footer-text {
  font-size: 12px;
  color: #52525b;
}
.mobile-topbar {
  position: fixed;
  z-index: 100;
  top: 0;
  left: 0;
  right: 0;
  height: 56px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(24, 24, 27, 0.96);
  border-bottom: 1px solid #27272a;
  backdrop-filter: blur(12px);
}
.mobile-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #e4e4e7;
  font-weight: 600;
}
.mobile-logo {
  width: 26px;
  height: 26px;
  border-radius: 7px;
}
.mobile-version {
  min-width: 44px;
  text-align: right;
  color: #71717a;
  font-size: 12px;
}
.mobile-drawer-brand {
  padding-top: 10px;
}
.mobile-menu-mask {
  position: fixed;
  z-index: 1000;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
}
.mobile-menu-panel {
  position: relative;
  width: min(280px, 82vw);
  height: 100%;
  background: #18181b;
  border-right: 1px solid #27272a;
  box-shadow: 12px 0 32px rgba(0, 0, 0, 0.35);
}
.mobile-menu-close {
  position: absolute;
  top: 10px;
  right: 10px;
  color: #a1a1aa;
}
.mobile-drawer-footer {
  margin: 20px 24px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
@media (max-width: 768px) {
  :deep(.n-layout-scroll-container) {
    min-width: 0;
  }
}
</style>
