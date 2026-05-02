<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
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
  darkTheme,
} from 'naive-ui'
import type { MenuOption, GlobalThemeOverrides } from 'naive-ui'
import { invoke } from '@tauri-apps/api/core'
import { open as shellOpen } from '@tauri-apps/plugin-shell'
import {
  HomeOutline,
  BulbOutline,
  ReaderOutline,
  MailOutline,
  PersonOutline,
  GitNetworkOutline,
  SettingsOutline,
  LogoGithub,
} from '@vicons/ionicons5'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()

const serverVersion = ref('')
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
  try {
    await invoke('set_close_to_tray', { enabled })
  } catch (e) {
    // Browser dev mode or older desktop builds without this command.
  }
}

onMounted(syncCloseToTraySetting)

async function openGitHub() {
  try {
    await shellOpen('https://github.com/CyrilPeng/KokoroMemo')
  } catch {
    window.open('https://github.com/CyrilPeng/KokoroMemo', '_blank')
  }
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
      <NLayout has-sider style="height: 100vh; background: #0f0f11;">
        <NLayoutSider
          bordered
          :width="220"
          :native-scrollbar="false"
          style="background: #18181b;"
        >
          <div style="padding: 20px 24px; display: flex; align-items: center; gap: 10px;">
            <img src="./assets/logo.png" style="width: 32px; height: 32px; border-radius: 8px;" />
            <span style="font-size: 18px; font-weight: 600; color: #e4e4e7;">KokoroMemo</span>
          </div>
          <NMenu
            :options="menuOptions"
            :value="route.path"
            @update:value="handleMenuUpdate"
            :indent="24"
          />
          <div style="position: absolute; bottom: 16px; left: 24px; right: 24px; display: flex; align-items: center; gap: 8px;">
            <NIcon :size="18" style="cursor: pointer; color: #71717a;" @click="openGitHub">
              <LogoGithub />
            </NIcon>
            <span style="font-size: 12px; color: #52525b;">{{ serverVersion ? `v${serverVersion} · ${$t('common.tagline')}` : $t('common.tagline') }}</span>
          </div>
        </NLayoutSider>
        <NLayoutContent :native-scrollbar="false" content-style="padding: 32px;">
          <RouterView />
        </NLayoutContent>
      </NLayout>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>
