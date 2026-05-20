<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NCard, NInput, NSpace, NTag } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import type { StateRow, StateTable } from './types'

const props = defineProps<{
  preview: { preview: string, char_count: number, max_chars: number, item_count: number }
  previewLoading: boolean
  retrievalTraces: any[]
  retrievalTraceDetail: any | null
  retrievalLoading: boolean
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
  refreshRetrievalTraces: []
  selectRetrievalTrace: [traceId: string]
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

function parseList(value: any): string[] {
  if (Array.isArray(value)) return value
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function score(value: any) {
  return typeof value === 'number' ? value.toFixed(3) : '-'
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

    <NCard title="注入来源">
      <template #header-extra>
        <NButton size="tiny" :loading="retrievalLoading" @click="emit('refreshRetrievalTraces')">刷新</NButton>
      </template>
      <NSpace vertical>
        <div v-if="!retrievalTraces.length" class="hint-text">暂无检索与注入记录。完成一次聊天后会显示本轮长期记忆来源。</div>
        <div v-else class="trace-list">
          <button
            v-for="trace in retrievalTraces"
            :key="trace.trace_id"
            class="trace-item"
            :class="{ active: retrievalTraceDetail?.trace_id === trace.trace_id }"
            type="button"
            @click="emit('selectRetrievalTrace', trace.trace_id)"
          >
            <NSpace align="center" size="small" wrap>
              <NTag size="tiny" :type="trace.should_retrieve ? 'success' : 'warning'">
                {{ trace.should_retrieve ? '检索' : '跳过' }}
              </NTag>
              <NTag size="tiny" type="info">{{ trace.final_injected_count || 0 }} 条注入</NTag>
              <span class="trace-time">{{ trace.created_at }}</span>
            </NSpace>
            <div class="trace-reason">{{ trace.trigger_reason || '-' }}</div>
            <div class="trace-query">{{ trace.query_text || '-' }}</div>
            <div class="trace-libraries">
              <NTag v-for="libraryId in parseList(trace.mounted_library_ids_json)" :key="libraryId" size="tiny">
                {{ libraryId }}
              </NTag>
            </div>
          </button>
        </div>

        <div v-if="retrievalTraceDetail" class="candidate-list">
          <div class="candidate-title">候选与最终注入</div>
          <div v-if="!retrievalTraceDetail.candidates?.length" class="hint-text">本次没有候选记忆。</div>
          <div v-for="candidate in retrievalTraceDetail.candidates || []" :key="candidate.candidate_id" class="candidate-item">
            <NSpace align="center" size="small" wrap>
              <NTag size="tiny" :type="candidate.selected ? 'success' : 'default'">
                {{ candidate.selected ? '已注入' : '未注入' }}
              </NTag>
              <NTag size="tiny">{{ candidate.route || '-' }}</NTag>
              <NTag size="tiny" type="info">{{ candidate.library_id || '-' }}</NTag>
              <span class="candidate-score">score {{ score(candidate.final_score) }}</span>
            </NSpace>
            <div class="candidate-preview">{{ candidate.content_preview || candidate.card_id || '-' }}</div>
            <div class="candidate-meta">
              {{ candidate.injection_reason || candidate.filtered_reason || '-' }}
            </div>
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

.trace-list,
.candidate-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
}

.trace-item {
  width: 100%;
  padding: 8px;
  text-align: left;
  color: #e5e7eb;
  background: #18181b;
  border: 1px solid #2f2f36;
  border-radius: 6px;
  cursor: pointer;
}

.trace-item:hover,
.trace-item.active {
  border-color: #63e2b7;
}

.trace-time,
.candidate-score,
.candidate-meta {
  color: #888;
  font-size: 12px;
}

.trace-reason,
.trace-query,
.candidate-preview {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
}

.trace-query,
.candidate-preview {
  color: #cbd5e1;
}

.trace-libraries {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.candidate-title {
  color: #e5e7eb;
  font-size: 13px;
  font-weight: 600;
}

.candidate-item {
  padding: 8px 0;
  border-bottom: 1px solid #333;
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
