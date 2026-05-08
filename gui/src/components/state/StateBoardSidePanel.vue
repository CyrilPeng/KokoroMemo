<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NCard, NInput, NSpace, NTag } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import type { StateRow, StateTable } from './types'

const props = defineProps<{
  preview: { preview: string, char_count: number, max_chars: number, item_count: number }
  previewLoading: boolean
  tables: StateTable[]
  rowsByTable: Record<string, StateRow[]>
  fillForm: { user_message: string, assistant_message: string }
  saving: boolean
  canFill: boolean
  showHistory: boolean
  historyEvents: any[]
  historyLoading: boolean
}>()

const emit = defineEmits<{
  refreshPreview: []
  previewFill: []
  directFill: []
  refreshHistory: []
  'update:fillForm': [value: { user_message: string, assistant_message: string }]
}>()

const { t } = useI18n()
const estimatedTokens = computed(() => Math.ceil((props.preview.char_count || 0) / 2.5))

function updateFillForm(key: 'user_message' | 'assistant_message', value: string) {
  emit('update:fillForm', { ...props.fillForm, [key]: value })
}

function eventTagType(eventType: string) {
  if (eventType.includes('insert')) return 'success'
  if (eventType.includes('delete') || eventType.includes('resolve')) return 'error'
  if (eventType === 'revert') return 'warning'
  return 'info'
}
</script>

<template>
  <NSpace vertical size="medium">
    <NCard title="注入预览">
      <template #header-extra>
        <NButton size="tiny" :loading="previewLoading" @click="emit('refreshPreview')">刷新</NButton>
      </template>
      <NSpace vertical>
        <NTag size="small">{{ preview.char_count }} / {{ preview.max_chars }} 字符，{{ preview.item_count }} 行，≈{{ estimatedTokens }} tokens</NTag>
        <NInput :value="preview.preview" type="textarea" readonly :autosize="{ minRows: 12, maxRows: 24 }" placeholder="加载后显示注入到模型的状态板文本" />
        <div v-if="tables.length" class="hint-text">
          <div v-for="table in tables" :key="table.table_key">
            {{ table.name }}: {{ (rowsByTable[table.table_key] || []).length }} 行
          </div>
        </div>
      </NSpace>
    </NCard>

    <NCard title="AI 填充调试">
      <NSpace vertical>
        <NInput :value="fillForm.user_message" type="textarea" placeholder="用户消息" :autosize="{ minRows: 3, maxRows: 6 }" @update:value="updateFillForm('user_message', $event)" />
        <NInput :value="fillForm.assistant_message" type="textarea" placeholder="助手回复" :autosize="{ minRows: 3, maxRows: 8 }" @update:value="updateFillForm('assistant_message', $event)" />
        <NSpace>
          <NButton type="primary" :loading="saving" :disabled="!canFill" @click="emit('previewFill')">{{ t('state.fill.previewBtn') }}</NButton>
          <NButton :loading="saving" :disabled="!canFill" @click="emit('directFill')">{{ t('state.fill.directBtn') }}</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NCard v-if="showHistory" :title="t('state.history.title')">
      <template #header-extra>
        <NButton size="tiny" :loading="historyLoading" @click="emit('refreshHistory')">{{ t('common.refresh') }}</NButton>
      </template>
      <div v-if="!historyEvents.length" class="hint-text">{{ t('state.history.empty') }}</div>
      <div v-else class="history-list">
        <div v-for="evt in historyEvents" :key="evt.event_id" class="history-item">
          <NSpace align="center" size="small">
            <NTag size="tiny" :type="eventTagType(evt.event_type)">{{ evt.event_type }}</NTag>
            <span style="color: #a1a1aa;">{{ evt.table_key || '-' }}</span>
            <span style="color: #666;">{{ evt.created_at }}</span>
          </NSpace>
          <div v-if="evt.reason" class="history-reason">{{ evt.reason }}</div>
          <div v-if="evt.after && Object.keys(evt.after).length" class="history-after">
            <span v-for="(val, key) in evt.after" :key="key" style="margin-right: 8px;">{{ key }}={{ val }}</span>
          </div>
        </div>
      </div>
    </NCard>
  </NSpace>
</template>

<style scoped>
.hint-text {
  color: #a1a1aa;
  font-size: 12px;
  line-height: 1.6;
  margin: 4px 0 0 0;
}

.history-list {
  max-height: 400px;
  overflow-y: auto;
}

.history-item {
  padding: 6px 0;
  border-bottom: 1px solid #333;
  font-size: 12px;
}

.history-reason {
  margin-top: 2px;
  color: #888;
}

.history-after {
  margin-top: 2px;
  color: #63e2b7;
}
</style>
