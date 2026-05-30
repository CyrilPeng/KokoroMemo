<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NModal, NInput, NIcon } from 'naive-ui'
import { SearchOutline } from '@vicons/ionicons5'

interface Command {
  id: string
  label: string
  category: string
  action: () => void
}

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()

const router = useRouter()
const { t } = useI18n()
const query = ref('')
const inputRef = ref<InstanceType<typeof NInput> | null>(null)

const commands = computed<Command[]>(() => {
  const nav = [
    { id: 'nav_dashboard', label: t('nav.dashboard'), path: '/dashboard', category: t('command.category.pages') },
    { id: 'nav_memories', label: t('nav.memories'), path: '/memories', category: t('command.category.pages') },
    { id: 'nav_memoryGraph', label: t('nav.memoryGraph'), path: '/memory-graph', category: t('command.category.pages') },
    { id: 'nav_inbox', label: t('nav.inbox'), path: '/inbox', category: t('command.category.pages') },
    { id: 'nav_conversations', label: '会话管理', path: '/conversations', category: t('command.category.pages') },
    { id: 'nav_state', label: t('nav.state'), path: '/state', category: t('command.category.pages') },
    { id: 'nav_characters', label: t('nav.characters'), path: '/characters', category: t('command.category.pages') },
    { id: 'nav_settings', label: t('nav.settings'), path: '/settings', category: t('command.category.pages') },
  ]
  const actions = [
    { id: 'action_testConnectivity', label: t('command.actions.testConnectivity'), path: '/settings', category: t('command.category.actions') },
    { id: 'action_rebuildIndex', label: t('command.actions.rebuildIndex'), path: '/settings', category: t('command.category.actions') },
    { id: 'action_exportMemories', label: t('command.actions.exportMemories'), path: '/memories', category: t('command.category.actions') },
  ]
  const raw = [...nav, ...actions]
  const q = query.value.trim().toLowerCase()
  const filtered = q ? raw.filter(c => c.label.toLowerCase().includes(q) || c.category.toLowerCase().includes(q)) : raw
  return filtered.map(c => ({
    id: c.id,
    label: c.label,
    category: c.category,
    action: () => {
      router.push(c.path)
      emit('update:show', false)
    },
  }))
})

const selectedIndex = ref(0)

watch(query, () => { selectedIndex.value = 0 })
watch(() => props.show, (visible) => {
  if (visible) {
    query.value = ''
    selectedIndex.value = 0
    nextTick(() => inputRef.value?.focus())
  }
})

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    selectedIndex.value = Math.min(selectedIndex.value + 1, commands.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    selectedIndex.value = Math.max(selectedIndex.value - 1, 0)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const cmd = commands.value[selectedIndex.value]
    if (cmd) cmd.action()
  }
}

function executeCommand(cmd: Command) {
  cmd.action()
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    :closable="false"
    :mask-closable="true"
    style="max-width: 560px; margin-top: 15vh;"
    :segmented="{ content: true }"
    :content-style="{ padding: 0 }"
    @update:show="emit('update:show', $event)"
  >
    <div class="cmd-palette-root">
      <div class="cmd-search">
        <NInput
          ref="inputRef"
          v-model:value="query"
          :placeholder="t('command.placeholder')"
          size="large"
          clearable
          @keydown="onKeydown"
        >
          <template #prefix>
            <NIcon :component="SearchOutline" />
          </template>
        </NInput>
      </div>

      <div class="cmd-list">
        <template v-for="(cmd, index) in commands" :key="cmd.id">
          <div
            v-if="index === 0 || commands[index - 1].category !== cmd.category"
            class="cmd-category"
          >
            {{ cmd.category }}
          </div>
          <div
            :class="['cmd-item', { selected: selectedIndex === index }]"
            @click="executeCommand(cmd)"
            @mouseenter="selectedIndex = index"
          >
            {{ cmd.label }}
          </div>
        </template>
        <div v-if="!commands.length" class="cmd-empty">
          {{ t('command.noResults') }}
        </div>
      </div>

      <div class="cmd-footer">
        <span class="cmd-footer-hints">
          ↑↓ {{ t('command.footer.navigate') }} · Enter {{ t('command.footer.execute') }} · Esc {{ t('command.footer.close') }}
        </span>
      </div>
    </div>
  </NModal>
</template>

<style scoped>
.cmd-palette-root {
  background: #18181b;
}
.cmd-search {
  padding: 12px 16px;
  border-bottom: 1px solid #27272a;
}
.cmd-list {
  max-height: 360px;
  overflow-y: auto;
  padding: 8px 0;
}
.cmd-category {
  padding: 4px 16px;
  color: #52525b;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.cmd-item {
  padding: 8px 16px;
  color: #e4e4e7;
  font-size: 14px;
  cursor: pointer;
  background: transparent;
  border-left: 3px solid transparent;
  transition: background 0.1s;
}
.cmd-item.selected {
  background: rgba(167, 139, 250, 0.12);
  border-left-color: #a78bfa;
}
.cmd-empty {
  padding: 24px;
  text-align: center;
  color: #52525b;
}
.cmd-footer {
  padding: 8px 16px;
  border-top: 1px solid #27272a;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.cmd-footer-hints {
  color: #52525b;
  font-size: 11px;
}
</style>
