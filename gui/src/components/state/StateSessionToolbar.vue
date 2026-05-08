<script setup lang="ts">
import { computed } from 'vue'
import { RefreshOutline, SettingsOutline } from '@vicons/ionicons5'
import {
  NButton,
  NCard,
  NGrid,
  NGridItem,
  NIcon,
  NInput,
  NPopconfirm,
  NSelect,
  NSpace,
  NTag,
} from 'naive-ui'

const props = defineProps<{
  conversationId: string
  adminToken: string
  conversationOptions: Array<{ label: string, value: string }>
  templateName?: string | null
  rowCount: number
  loading: boolean
  saving: boolean
  hasTemplate: boolean
  canRenameConversation: boolean
}>()

const emit = defineEmits<{
  'update:conversationId': [value: string]
  'update:adminToken': [value: string]
  load: []
  export: []
  import: []
  rename: []
  delete: []
  openDefaults: []
}>()

const deleteDisabled = computed(() => !props.conversationId.trim())
</script>

<template>
  <NCard>
    <template #header>
      <NSpace align="center" justify="space-between" style="width:100%">
        <NSpace align="center">
          <span>当前会话</span>
          <NTag v-if="templateName" size="small" type="info">模板：{{ templateName }}</NTag>
          <NTag v-if="rowCount" size="small">{{ rowCount }} 条状态</NTag>
        </NSpace>
        <NSpace align="center">
          <NButton size="small" @click="emit('openDefaults')">
            <template #icon><NIcon :component="SettingsOutline" /></template>
            新会话默认配置
          </NButton>
        </NSpace>
      </NSpace>
    </template>
    <NGrid :cols="24" :x-gap="12" :y-gap="12">
      <NGridItem :span="10">
        <NSelect
          :value="conversationId"
          filterable
          clearable
          :options="conversationOptions"
          :placeholder="conversationOptions.length ? '选择会话' : '无数据'"
          :disabled="!conversationOptions.length"
          @update:value="emit('update:conversationId', $event || '')"
        />
      </NGridItem>
      <NGridItem :span="8">
        <NInput
          :value="adminToken"
          type="password"
          show-password-on="click"
          placeholder="Admin Token（可选）"
          @update:value="emit('update:adminToken', $event)"
        />
      </NGridItem>
      <NGridItem :span="6">
        <NSpace>
          <NButton type="primary" :loading="loading" @click="emit('load')">
            <template #icon><NIcon :component="RefreshOutline" /></template>
            加载
          </NButton>
          <NButton :disabled="!hasTemplate" @click="emit('export')">导出</NButton>
          <NButton @click="emit('import')">导入</NButton>
          <NButton :disabled="!canRenameConversation" @click="emit('rename')">重命名</NButton>
          <NPopconfirm
            :disabled="deleteDisabled"
            positive-text="删除"
            negative-text="取消"
            @positive-click="emit('delete')"
          >
            <template #trigger>
              <NButton type="error" quaternary :disabled="deleteDisabled" :loading="saving">删除会话</NButton>
            </template>
            删除当前会话记录？此操作会从会话列表移除该 ID，但不会删除磁盘上的聊天文件。
          </NPopconfirm>
        </NSpace>
      </NGridItem>
    </NGrid>
  </NCard>
</template>
