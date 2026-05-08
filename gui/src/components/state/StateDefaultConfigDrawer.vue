<script setup lang="ts">
import {
  NButton,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NSelect,
  NSpace,
} from 'naive-ui'
import type { ConversationConfig } from './types'

defineProps<{
  show: boolean
  saving: boolean
  defaultConfig: ConversationConfig | null
  profileOptions: any[]
  profileRenderLabel: ((option: any) => any) | undefined
  selectedDefaultProfileHint: string
  tableTemplateOptions: any[]
  templateRenderLabel: ((option: any) => any) | undefined
  mountPresetOptions: any[]
  memoryPolicyOptions: Array<{ label: string, value: string }>
  statePolicyOptions: Array<{ label: string, value: string }>
  injectionPolicyOptions: Array<{ label: string, value: string }>
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  updateProfile: [value: string]
  updateTableTemplate: [value: string | null]
  updateMountPreset: [value: string | null]
  updateMemoryWritePolicy: [value: string]
  updateStateUpdatePolicy: [value: string]
  updateInjectionPolicy: [value: string]
  save: []
}>()
</script>

<template>
  <NDrawer :show="show" width="min(560px, 96vw)" placement="right" @update:show="emit('update:show', $event)">
    <NDrawerContent title="新会话默认配置" closable>
      <p class="hint-text" style="margin-bottom: 16px;">
        这里设置的是<b>未来新出现的会话</b>使用的初始配置（识别到新的 conversation_id 时自动应用）。已存在会话不会被覆盖；要修改当前会话请使用页面上的“当前会话策略”。
      </p>
      <NForm v-if="defaultConfig" label-placement="top">
        <NFormItem label="默认会话方案">
          <NSelect :value="defaultConfig.profile_id" :options="profileOptions" :render-label="profileRenderLabel" @update:value="emit('updateProfile', $event)" />
        </NFormItem>
        <div v-if="selectedDefaultProfileHint" class="hint-text" style="margin-bottom: 12px;">{{ selectedDefaultProfileHint }}</div>
        <NFormItem label="默认表格模板">
          <NSelect :value="defaultConfig.table_template_id" filterable :options="tableTemplateOptions" :render-label="templateRenderLabel" @update:value="emit('updateTableTemplate', $event)" />
        </NFormItem>
        <NFormItem label="默认挂载组合预设">
          <NSelect :value="defaultConfig.mount_preset_id" filterable :options="mountPresetOptions" @update:value="emit('updateMountPreset', $event)" />
        </NFormItem>
        <NFormItem label="默认长期记忆写入">
          <NSelect :value="defaultConfig.memory_write_policy" :options="memoryPolicyOptions" @update:value="emit('updateMemoryWritePolicy', $event)" />
        </NFormItem>
        <NFormItem label="默认状态板更新">
          <NSelect :value="defaultConfig.state_update_policy" :options="statePolicyOptions" @update:value="emit('updateStateUpdatePolicy', $event)" />
        </NFormItem>
        <NFormItem label="默认注入策略">
          <NSelect :value="defaultConfig.injection_policy" :options="injectionPolicyOptions" @update:value="emit('updateInjectionPolicy', $event)" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="emit('update:show', false)">关闭</NButton>
          <NButton type="primary" :loading="saving" @click="emit('save')">保存</NButton>
        </NSpace>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>
