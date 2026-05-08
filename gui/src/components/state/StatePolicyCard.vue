<script setup lang="ts">
import { computed } from 'vue'
import { AddOutline, CreateOutline, TrashOutline } from '@vicons/ionicons5'
import {
  NAlert,
  NButton,
  NCard,
  NForm,
  NFormItem,
  NGrid,
  NGridItem,
  NIcon,
  NPopconfirm,
  NSelect,
  NSpace,
  NTag,
} from 'naive-ui'
import type { ConversationConfig } from './types'

const props = defineProps<{
  config: ConversationConfig
  loading: boolean
  saving: boolean
  profileOptions: any[]
  profileRenderLabel: ((option: any) => any) | undefined
  selectedProfileHint: string
  tableTemplateOptions: any[]
  templateRenderLabel: ((option: any) => any) | undefined
  mountPresetOptions: any[]
  memoryLibraryOptions: Array<{ label: string, value: string }>
  writeLibraryOptions: Array<{ label: string, value: string }>
  mountedLibraryIds: string[]
  writeLibraryId: string | null
  memoryPolicyOptions: Array<{ label: string, value: string }>
  statePolicyOptions: Array<{ label: string, value: string }>
  injectionPolicyOptions: Array<{ label: string, value: string }>
  activeProfile?: any
  activeTemplate?: any
  activePreset?: any
}>()

const emit = defineEmits<{
  updateProfile: [value: string]
  updateTableTemplate: [value: string | null]
  updateMountPreset: [value: string | null]
  updateMountedLibraries: [value: string[]]
  updateWriteLibraryId: [value: string | null]
  updateMemoryWritePolicy: [value: string]
  updateStateUpdatePolicy: [value: string]
  updateInjectionPolicy: [value: string]
  openProfileModal: [profile?: any]
  deleteProfile: [profile: any]
  cloneTemplate: []
  openRenameTemplate: [template: any]
  deleteTemplate: [template: any]
  openPresetModal: [preset?: any]
  deletePreset: [preset: any]
  saveMounts: []
  reload: []
  saveConfig: []
}>()

const summaryTags = computed(() => ([
  props.activeProfile?.name ? { label: `方案：${props.activeProfile.name}`, type: 'info' as const } : null,
  props.activeTemplate?.name ? { label: `模板：${props.activeTemplate.name}`, type: 'success' as const } : null,
  props.activePreset?.name ? { label: `挂载预设：${props.activePreset.name}`, type: 'warning' as const } : null,
]).filter(Boolean))
</script>

<template>
  <NCard title="当前会话策略">
    <NSpace vertical size="medium">
      <NAlert v-if="config.created_from_default" type="info" :show-icon="false">
        当前会话仍沿用默认配置；你可以在这里按会话单独覆盖。
      </NAlert>
      <NSpace v-if="summaryTags.length" size="small" :wrap="true">
        <NTag v-for="item in summaryTags" :key="item.label" :type="item.type">{{ item.label }}</NTag>
      </NSpace>
      <NForm label-placement="top">
        <NGrid :cols="24" :x-gap="12" :y-gap="12">
          <NGridItem :span="8">
            <NFormItem label="会话方案">
              <NSelect :value="config.profile_id" :options="profileOptions" :render-label="profileRenderLabel" @update:value="emit('updateProfile', $event)" />
            </NFormItem>
            <div v-if="selectedProfileHint" class="hint-text">{{ selectedProfileHint }}</div>
            <NSpace style="margin-top: 6px;">
              <NButton size="tiny" @click="emit('openProfileModal')">
                <template #icon><NIcon :component="AddOutline" size="14" /></template>
                新建方案
              </NButton>
              <NButton v-if="activeProfile?.is_builtin === false" size="tiny" @click="emit('openProfileModal', activeProfile)">
                <template #icon><NIcon :component="CreateOutline" size="14" /></template>
                重命名
              </NButton>
              <NPopconfirm v-if="activeProfile?.is_builtin === false" @positive-click="emit('deleteProfile', activeProfile)">
                <template #trigger>
                  <NButton size="tiny" type="error" quaternary>
                    <template #icon><NIcon :component="TrashOutline" size="14" /></template>
                    删除
                  </NButton>
                </template>
                删除当前自定义方案？
              </NPopconfirm>
            </NSpace>
          </NGridItem>
          <NGridItem :span="8">
            <NFormItem label="状态板表格模板">
              <NSelect :value="config.table_template_id" filterable :options="tableTemplateOptions" :render-label="templateRenderLabel" @update:value="emit('updateTableTemplate', $event)" />
            </NFormItem>
            <NSpace style="margin-top: 6px;">
              <NButton size="tiny" :disabled="!config.table_template_id" @click="emit('cloneTemplate')">
                <template #icon><NIcon :component="AddOutline" size="14" /></template>
                新建模板
              </NButton>
              <NButton v-if="activeTemplate?.is_builtin === false" size="tiny" @click="emit('openRenameTemplate', activeTemplate)">
                <template #icon><NIcon :component="CreateOutline" size="14" /></template>
                重命名
              </NButton>
              <NPopconfirm v-if="activeTemplate?.is_builtin === false" @positive-click="emit('deleteTemplate', activeTemplate)">
                <template #trigger>
                  <NButton size="tiny" type="error" quaternary>
                    <template #icon><NIcon :component="TrashOutline" size="14" /></template>
                    删除
                  </NButton>
                </template>
                删除当前自定义模板？
              </NPopconfirm>
            </NSpace>
          </NGridItem>
          <NGridItem :span="8">
            <NFormItem label="挂载组合预设">
              <NSelect :value="config.mount_preset_id" filterable :options="mountPresetOptions" @update:value="emit('updateMountPreset', $event)" />
            </NFormItem>
            <NSpace>
              <NButton size="tiny" :disabled="!config.mount_preset_id" @click="emit('openPresetModal', activePreset)">编辑</NButton>
              <NPopconfirm v-if="config.mount_preset_id" @positive-click="activePreset && emit('deletePreset', activePreset)">
                <template #trigger><NButton size="tiny" type="error" quaternary>删除</NButton></template>
                删除当前挂载预设？
              </NPopconfirm>
            </NSpace>
          </NGridItem>
          <NGridItem :span="16">
            <NFormItem label="挂载的长期记忆库">
              <NSelect
                multiple
                filterable
                :value="mountedLibraryIds"
                :options="memoryLibraryOptions"
                placeholder="选择一个或多个记忆库"
                @update:value="emit('updateMountedLibraries', $event)"
              />
            </NFormItem>
            <div class="hint-text">挂载库决定本会话能召回哪些长期记忆，可用于隔离不同角色或世界观。</div>
          </NGridItem>
          <NGridItem :span="8">
            <NFormItem label="新记忆写入到">
              <NSelect :value="writeLibraryId" :options="writeLibraryOptions" :disabled="!mountedLibraryIds.length" placeholder="必须是已挂载的库" @update:value="emit('updateWriteLibraryId', $event)" />
            </NFormItem>
            <NButton size="tiny" :loading="saving" :disabled="!mountedLibraryIds.length" @click="emit('saveMounts')">保存挂载</NButton>
          </NGridItem>
          <NGridItem :span="8">
            <NFormItem label="长期记忆写入">
              <NSelect :value="config.memory_write_policy" :options="memoryPolicyOptions" @update:value="emit('updateMemoryWritePolicy', $event)" />
            </NFormItem>
          </NGridItem>
          <NGridItem :span="8">
            <NFormItem label="状态板更新">
              <NSelect :value="config.state_update_policy" :options="statePolicyOptions" @update:value="emit('updateStateUpdatePolicy', $event)" />
            </NFormItem>
          </NGridItem>
          <NGridItem :span="8">
            <NFormItem label="注入策略">
              <NSelect :value="config.injection_policy" :options="injectionPolicyOptions" @update:value="emit('updateInjectionPolicy', $event)" />
            </NFormItem>
          </NGridItem>
        </NGrid>
        <NSpace justify="end">
          <NButton :loading="loading" @click="emit('reload')">重新加载</NButton>
          <NButton type="primary" :loading="saving" @click="emit('saveConfig')">保存会话策略</NButton>
        </NSpace>
      </NForm>
    </NSpace>
  </NCard>
</template>
