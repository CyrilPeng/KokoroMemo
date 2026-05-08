<script setup lang="ts">
import { computed } from 'vue'
import { AddOutline, CreateOutline, TrashOutline } from '@vicons/ionicons5'
import {
  NButton,
  NCard,
  NDivider,
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

type SummaryTag = { label: string, type: 'default' | 'info' | 'success' | 'warning' | 'error' }

const summaryTags = computed<SummaryTag[]>(() => ([
  props.activeProfile?.name ? { label: `方案：${props.activeProfile.name}`, type: 'info' as const } : null,
  props.activeTemplate?.name ? { label: `模板：${props.activeTemplate.name}`, type: 'success' as const } : null,
  props.config.created_from_default ? { label: '继承默认', type: 'default' as const } : { label: '已单独配置', type: 'warning' as const },
].filter((item): item is NonNullable<typeof item> => item !== null)))

</script>

<template>
  <NCard>
    <template #header>
      <NSpace align="center" :wrap="true" size="small">
        <span class="policy-title">当前会话策略</span>
        <NTag v-for="item in summaryTags" :key="item.label" :type="item.type" size="small" round>{{ item.label }}</NTag>
      </NSpace>
    </template>

    <NForm label-placement="top">
      <NSpace vertical size="large">
        <section class="policy-section">
          <div class="section-head">
            <span class="section-title">方案与模板</span>
          </div>
          <NGrid :cols="24" :x-gap="12" :y-gap="12">
            <NGridItem :span="12">
              <NFormItem>
                <template #label>
                  <div class="field-label">
                    <span>会话方案</span>
                    <NButton size="tiny" tertiary @click="emit('openProfileModal')">
                      <template #icon><NIcon :component="AddOutline" size="14" /></template>
                      新建方案
                    </NButton>
                  </div>
                </template>
                <NSelect :value="config.profile_id" :options="profileOptions" :render-label="profileRenderLabel" @update:value="emit('updateProfile', $event)" />
              </NFormItem>
              <NSpace v-if="activeProfile?.is_builtin === false" size="small">
                <NButton size="tiny" @click="emit('openProfileModal', activeProfile)">
                  <template #icon><NIcon :component="CreateOutline" size="14" /></template>
                  重命名
                </NButton>
                <NPopconfirm @positive-click="emit('deleteProfile', activeProfile)">
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

            <NGridItem :span="12">
              <NFormItem>
                <template #label>
                  <div class="field-label">
                    <span>状态板表格模板</span>
                    <NButton size="tiny" tertiary :disabled="!config.table_template_id" @click="emit('cloneTemplate')">
                      <template #icon><NIcon :component="AddOutline" size="14" /></template>
                      新建模板
                    </NButton>
                  </div>
                </template>
                <NSelect :value="config.table_template_id" filterable :options="tableTemplateOptions" :render-label="templateRenderLabel" @update:value="emit('updateTableTemplate', $event)" />
              </NFormItem>
              <NSpace v-if="activeTemplate?.is_builtin === false" size="small">
                <NButton size="tiny" @click="emit('openRenameTemplate', activeTemplate)">
                  <template #icon><NIcon :component="CreateOutline" size="14" /></template>
                  重命名
                </NButton>
                <NPopconfirm @positive-click="emit('deleteTemplate', activeTemplate)">
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
          </NGrid>
        </section>

        <section class="policy-section">
          <div class="section-head">
            <span class="section-title">记忆库挂载</span>
          </div>
          <NGrid :cols="24" :x-gap="12" :y-gap="12">
            <NGridItem :span="8">
              <NFormItem>
                <template #label>
                  <div class="field-label">
                    <span>挂载组合预设</span>
                    <NButton size="tiny" tertiary @click="emit('openPresetModal')">新建预设</NButton>
                  </div>
                </template>
                <NSelect :value="config.mount_preset_id" filterable :options="mountPresetOptions" @update:value="emit('updateMountPreset', $event)" />
              </NFormItem>
              <NSpace v-if="config.mount_preset_id" size="small">
                <NButton size="tiny" :disabled="!config.mount_preset_id" @click="emit('openPresetModal', activePreset)">编辑</NButton>
                <NPopconfirm @positive-click="activePreset && emit('deletePreset', activePreset)">
                  <template #trigger><NButton size="tiny" type="error" quaternary>删除</NButton></template>
                  删除当前挂载预设？
                </NPopconfirm>
              </NSpace>
            </NGridItem>
            <NGridItem :span="10">
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
            </NGridItem>
            <NGridItem :span="6">
              <NFormItem label="新记忆写入到">
                <NSelect :value="writeLibraryId" :options="writeLibraryOptions" :disabled="!mountedLibraryIds.length" placeholder="必须是已挂载的库" @update:value="emit('updateWriteLibraryId', $event)" />
              </NFormItem>
              <NButton size="tiny" :loading="saving" :disabled="!mountedLibraryIds.length" @click="emit('saveMounts')">保存挂载</NButton>
            </NGridItem>
          </NGrid>
        </section>

        <section class="policy-section">
          <div class="section-head">
            <span class="section-title">自动化策略</span>
          </div>
          <NGrid :cols="24" :x-gap="12" :y-gap="12">
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
        </section>

        <NDivider style="margin: 0" />
        <NSpace justify="end">
          <NButton :loading="loading" @click="emit('reload')">重新加载</NButton>
          <NButton type="primary" :loading="saving" @click="emit('saveConfig')">保存会话策略</NButton>
        </NSpace>
      </NSpace>
    </NForm>
  </NCard>
</template>

<style scoped>
.policy-title {
  font-weight: 700;
}

.policy-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title {
  font-size: 14px;
  font-weight: 650;
}

.field-label {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

@media (max-width: 900px) {
  .policy-section :deep(.n-grid) {
    grid-template-columns: minmax(0, 1fr) !important;
  }
}
</style>
