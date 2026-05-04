<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import {
  NAlert, NButton, NCard, NDataTable, NDescriptions, NDescriptionsItem,
  NDrawer, NDrawerContent, NDynamicTags, NEmpty, NForm, NFormItem, NGrid,
  NGridItem, NIcon, NInput, NModal, NSelect, NSpace, NSpin, NSwitch, NTabPane,
  NTabs, NTag, useDialog, useMessage,
} from 'naive-ui'
import { CreateOutline, HelpCircleOutline, OpenOutline, RefreshOutline } from '@vicons/ionicons5'
import { apiFetch } from '../api'

type Character = Record<string, any>

const message = useMessage()
const dialog = useDialog()

const loading = ref(false)
const saving = ref(false)
const characters = ref<Character[]>([])
const profiles = ref<any[]>([])
const boardTemplates = ref<any[]>([])
const tableTemplates = ref<any[]>([])
const libraries = ref<any[]>([])
const mountPresets = ref<any[]>([])
const conversations = ref<any[]>([])
const selected = ref<Character | null>(null)
const showDrawer = ref(false)
const showHelp = ref(false)
const keyword = ref('')
const profileFilter = ref<string | null>(null)

const profileOptions = computed(() => profiles.value.map((item) => ({ label: item.name, value: item.profile_id })))
const filterProfileOptions = computed(() => [{ label: '全部方案', value: null }, ...profileOptions.value])
const tableTemplateOptions = computed(() => [{ label: '不使用表格模板', value: null }, ...tableTemplates.value.map((item) => ({ label: item.name, value: item.template_id }))])
const boardTemplateOptions = computed(() => [{ label: '不使用旧字段模板', value: null }, ...boardTemplates.value.map((item) => ({ label: item.name, value: item.template_id }))])
const libraryOptions = computed(() => libraries.value.map((item) => ({ label: `${item.name}${item.card_count ? `（${item.card_count}）` : ''}`, value: item.library_id })))
const writeLibraryOptions = computed(() => libraryOptions.value.filter((item) => form.value.library_ids.includes(item.value)))
const mountPresetOptions = computed(() => [{ label: '不套用挂载预设', value: null }, ...mountPresets.value.map((item) => ({ label: item.name, value: item.preset_id }))])
const memoryPolicyOptions = [
  { label: '关闭长期记忆写入', value: 'disabled' },
  { label: '生成候选待审核', value: 'candidate' },
  { label: '仅稳定设定候选', value: 'stable_only' },
  { label: '自动判断', value: 'auto' },
]
const statePolicyOptions = [
  { label: '关闭状态更新', value: 'disabled' },
  { label: '仅手动维护', value: 'manual' },
  { label: '自动更新状态板', value: 'auto' },
]
const injectionPolicyOptions = [
  { label: '不注入', value: 'none' },
  { label: '仅长期记忆', value: 'memory_only' },
  { label: '仅状态板', value: 'state_only' },
  { label: '状态板优先', value: 'state_first' },
  { label: '混合注入', value: 'mixed' },
]

const form = ref({
  display_name: '',
  aliases: [] as string[],
  notes: '',
  source: '',
  profile_id: 'airp_roleplay',
  template_id: null as string | null,
  table_template_id: null as string | null,
  mount_preset_id: null as string | null,
  memory_write_policy: 'candidate',
  state_update_policy: 'auto',
  injection_policy: 'mixed',
  library_ids: ['lib_default'] as string[],
  write_library_id: 'lib_default',
  auto_apply: true,
})

const filteredCharacters = computed(() => characters.value.filter((item) => {
  const text = `${item.character_id} ${item.display_name || ''} ${(item.aliases || []).join(' ')}`.toLowerCase()
  const okKeyword = !keyword.value.trim() || text.includes(keyword.value.trim().toLowerCase())
  const okProfile = !profileFilter.value || item.profile_id === profileFilter.value
  return okKeyword && okProfile
}))

function profileName(profileId?: string | null) {
  return profiles.value.find((item) => item.profile_id === profileId)?.name || profileId || '未配置'
}
function tableTemplateName(templateId?: string | null) {
  return tableTemplates.value.find((item) => item.template_id === templateId)?.name || templateId || '未配置'
}
function policyLabel(options: any[], value?: string | null) {
  return options.find((item) => item.value === value)?.label || value || '未配置'
}
function health(row: Character) {
  if (!row.profile_id) return { type: 'warning', label: '未配置' }
  if (row.profile_id === 'rimtalk_colony' && row.memory_write_policy !== 'disabled') return { type: 'error', label: '可能污染记忆' }
  if (row.injection_policy === 'state_only') return { type: 'success', label: '状态板优先' }
  return { type: 'success', label: '已配置' }
}

const columns = computed(() => [
  {
    title: '角色', key: 'character', minWidth: 220, render: (row: Character) => h('div', [
      h('div', { style: 'font-weight: 600;' }, row.display_name || row.character_id),
      h('div', { style: 'font-size: 12px; color: #71717a;' }, row.character_id),
    ]),
  },
  { title: '会话', key: 'conversation_count', width: 80 },
  { title: '最近活跃', key: 'last_seen_at', width: 160, render: (row: Character) => row.last_seen_at || '-' },
  { title: '默认方案', key: 'profile_id', minWidth: 180, render: (row: Character) => profileName(row.profile_id) },
  { title: '表格模板', key: 'table_template_id', minWidth: 190, ellipsis: { tooltip: true }, render: (row: Character) => tableTemplateName(row.table_template_id) },
  { title: '长期记忆', key: 'memory_write_policy', width: 150, render: (row: Character) => policyLabel(memoryPolicyOptions, row.memory_write_policy) },
  { title: '健康', key: 'health', width: 130, render: (row: Character) => {
    const hlt = health(row)
    return h(NTag, { type: hlt.type as any, size: 'small' }, { default: () => hlt.label })
  } },
  { title: '操作', key: 'actions', width: 130, render: (row: Character) => h(NButton, { size: 'small', quaternary: true, onClick: () => openCharacter(row) }, { icon: () => h(NIcon, null, { default: () => h(CreateOutline) }), default: () => '管理' }) },
])

async function fetchAll() {
  loading.value = true
  try {
    const charResp = await apiFetch('/admin/characters', { timeoutMs: 5000 })
    if (charResp.ok) characters.value = (await charResp.json()).items || []
  } catch (error: any) {
    message.error(`加载角色失败：${error.message || error}`)
  } finally {
    loading.value = false
  }

  const results = await Promise.allSettled([
    apiFetch('/admin/conversation-profiles', { timeoutMs: 5000 }),
    apiFetch('/admin/state/templates', { timeoutMs: 5000 }),
    apiFetch('/admin/state/table-templates', { timeoutMs: 5000 }),
    apiFetch('/admin/memory-libraries', { timeoutMs: 5000 }),
    apiFetch('/admin/memory-mount-presets', { timeoutMs: 5000 }),
  ])
  const [profilesResp, boardResp, tableResp, libResp, presetResp] = results.map((item) => item.status === 'fulfilled' ? item.value : null)
  if (profilesResp?.ok) profiles.value = (await profilesResp.json()).items || []
  if (boardResp?.ok) boardTemplates.value = (await boardResp.json()).items || []
  if (tableResp?.ok) tableTemplates.value = (await tableResp.json()).items || []
  if (libResp?.ok) libraries.value = (await libResp.json()).items || []
  if (presetResp?.ok) mountPresets.value = (await presetResp.json()).items || []
}

async function openCharacter(row: Character) {
  selected.value = row
  form.value = {
    display_name: row.display_name || '', aliases: [...(row.aliases || [])], notes: row.notes || '', source: row.source || '',
    profile_id: row.profile_id || 'airp_roleplay', template_id: row.template_id ?? null, table_template_id: row.table_template_id ?? null,
    mount_preset_id: row.mount_preset_id ?? null, memory_write_policy: row.memory_write_policy || 'candidate',
    state_update_policy: row.state_update_policy || 'auto', injection_policy: row.injection_policy || 'mixed',
    library_ids: row.library_ids?.length ? [...row.library_ids] : ['lib_default'], write_library_id: row.write_library_id || 'lib_default',
    auto_apply: row.auto_apply ?? true,
  }
  showDrawer.value = true
  await fetchConversations(row.character_id)
}

async function fetchConversations(characterId: string) {
  const resp = await apiFetch(`/admin/characters/${encodeURIComponent(characterId)}/conversations`)
  if (resp.ok) conversations.value = (await resp.json()).items || []
}

function applyProfile(profileId: string) {
  const profile = profiles.value.find((item) => item.profile_id === profileId)
  if (!profile) return
  form.value = {
    ...form.value,
    profile_id: profile.profile_id,
    template_id: profile.template_id,
    table_template_id: profile.table_template_id,
    mount_preset_id: profile.mount_preset_id,
    memory_write_policy: profile.memory_write_policy,
    state_update_policy: profile.state_update_policy,
    injection_policy: profile.injection_policy,
  }
}

async function saveCharacter() {
  if (!selected.value) return
  saving.value = true
  try {
    await apiFetch(`/admin/characters/${encodeURIComponent(selected.value.character_id)}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form.value),
    })
    const resp = await apiFetch(`/admin/characters/${encodeURIComponent(selected.value.character_id)}/defaults`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form.value),
    })
    const data = await resp.json()
    if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '保存失败')
    message.success('角色配置已保存')
    await fetchAll()
    const refreshed = characters.value.find((item) => item.character_id === selected.value?.character_id)
    if (refreshed) await openCharacter(refreshed)
  } catch (error: any) {
    message.error(error.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function applyToConversations() {
  if (!selected.value) return
  dialog.warning({
    title: '应用到已有会话？',
    content: '将把当前角色默认策略和挂载库应用到该角色所有已有会话。',
    positiveText: '应用', negativeText: '取消',
    onPositiveClick: async () => {
      const resp = await apiFetch(`/admin/characters/${encodeURIComponent(selected.value!.character_id)}/apply-defaults`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ overwrite_existing: true }),
      })
      const data = await resp.json()
      if (!resp.ok || data.status !== 'ok') throw new Error(data.detail || data.message || '应用失败')
      message.success(`已更新 ${data.updated} 个会话`)
      await fetchConversations(selected.value!.character_id)
    },
  })
}

function openStateBoard(conversationId: string) {
  localStorage.setItem('kokoromemo.stateConversationId', conversationId)
  window.location.hash = '#/state'
}

onMounted(fetchAll)
</script>

<template>
  <div class="characters-page">
    <NSpace vertical size="large">
      <NCard>
        <template #header>
          <NSpace align="center">
            <span>角色中心</span>
            <NButton quaternary size="small" @click="showHelp = true"><template #icon><NIcon :component="HelpCircleOutline" /></template></NButton>
          </NSpace>
        </template>
        <NSpace vertical>
          <NAlert type="info" :show-icon="false">角色中心用于管理角色档案、默认会话策略、记忆库绑定和该角色已有会话。RimTalk / 殖民地角色建议使用“仅状态板”并关闭长期记忆写入。</NAlert>
          <NGrid cols="1 m:24" item-responsive responsive="screen" :x-gap="12" :y-gap="12">
            <NGridItem span="1 m:10"><NInput v-model:value="keyword" placeholder="搜索角色 ID、名称或别名" clearable /></NGridItem>
            <NGridItem span="1 m:6"><NSelect v-model:value="profileFilter" :options="filterProfileOptions" /></NGridItem>
            <NGridItem span="1 m:8"><NSpace justify="end"><NButton :loading="loading" @click="fetchAll"><template #icon><NIcon :component="RefreshOutline" /></template>刷新</NButton></NSpace></NGridItem>
          </NGrid>
        </NSpace>
      </NCard>

      <NSpin :show="loading">
        <NCard>
          <NDataTable v-if="filteredCharacters.length" :columns="columns" :data="filteredCharacters" :pagination="{ pageSize: 12 }" :scroll-x="1040" />
          <NEmpty v-else description="暂无角色或没有匹配结果" />
        </NCard>
      </NSpin>
    </NSpace>

    <NDrawer v-model:show="showDrawer" width="min(900px, 100vw)">
      <NDrawerContent v-if="selected" :title="selected.display_name || selected.character_id" closable>
        <NTabs type="line" animated>
          <NTabPane name="profile" tab="基础档案">
            <NForm label-placement="top">
              <NGrid :cols="2" :x-gap="12">
                <NGridItem><NFormItem label="显示名称"><NInput v-model:value="form.display_name" placeholder="便于识别的角色名" /></NFormItem></NGridItem>
                <NGridItem><NFormItem label="来源"><NInput v-model:value="form.source" placeholder="RimTalk / SillyTavern / 手动" /></NFormItem></NGridItem>
              </NGrid>
              <NFormItem label="别名"><NDynamicTags v-model:value="form.aliases" /></NFormItem>
              <NFormItem label="备注"><NInput v-model:value="form.notes" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" /></NFormItem>
              <NDescriptions bordered size="small" :column="2">
                <NDescriptionsItem label="角色 ID">{{ selected.character_id }}</NDescriptionsItem>
                <NDescriptionsItem label="会话数">{{ selected.conversation_count || 0 }}</NDescriptionsItem>
                <NDescriptionsItem label="首次出现">{{ selected.first_seen_at || '-' }}</NDescriptionsItem>
                <NDescriptionsItem label="最近活跃">{{ selected.last_seen_at || '-' }}</NDescriptionsItem>
              </NDescriptions>
            </NForm>
          </NTabPane>

          <NTabPane name="strategy" tab="默认策略">
            <NForm label-placement="top">
              <NGrid :cols="2" :x-gap="12">
                <NGridItem><NFormItem label="默认会话方案"><NSelect v-model:value="form.profile_id" :options="profileOptions" @update:value="applyProfile" /></NFormItem></NGridItem>
                <NGridItem><NFormItem label="自动应用到新会话"><NSwitch v-model:value="form.auto_apply" /></NFormItem></NGridItem>
                <NGridItem><NFormItem label="表格状态板模板"><NSelect v-model:value="form.table_template_id" filterable :options="tableTemplateOptions" /></NFormItem></NGridItem>
                <NGridItem><NFormItem label="旧字段模板（兼容）"><NSelect v-model:value="form.template_id" filterable :options="boardTemplateOptions" /></NFormItem></NGridItem>
                <NGridItem><NFormItem label="长期记忆写入"><NSelect v-model:value="form.memory_write_policy" :options="memoryPolicyOptions" /></NFormItem></NGridItem>
                <NGridItem><NFormItem label="状态板更新"><NSelect v-model:value="form.state_update_policy" :options="statePolicyOptions" /></NFormItem></NGridItem>
                <NGridItem><NFormItem label="注入策略"><NSelect v-model:value="form.injection_policy" :options="injectionPolicyOptions" /></NFormItem></NGridItem>
                <NGridItem><NFormItem label="挂载组合预设"><NSelect v-model:value="form.mount_preset_id" filterable :options="mountPresetOptions" /></NFormItem></NGridItem>
              </NGrid>
              <NAlert type="warning" :show-icon="false">该配置影响该角色之后的新会话；如需修改已有会话，请保存后使用“应用到已有会话”。</NAlert>
            </NForm>
          </NTabPane>

          <NTabPane name="libraries" tab="记忆库绑定">
            <NForm label-placement="top">
              <NFormItem label="默认挂载记忆库"><NSelect v-model:value="form.library_ids" multiple filterable :options="libraryOptions" /></NFormItem>
              <NFormItem label="默认写入库"><NSelect v-model:value="form.write_library_id" :options="writeLibraryOptions" /></NFormItem>
              <NAlert type="default" :show-icon="false">新记忆会写入默认写入库；召回时会从挂载库中检索。RimTalk 状态变化建议不要写入长期记忆。</NAlert>
            </NForm>
          </NTabPane>

          <NTabPane name="conversations" tab="相关会话">
            <NSpace vertical>
              <NAlert type="default" :show-icon="false">共 {{ conversations.length }} 个会话。可批量套用当前角色默认策略，修复仍在使用旧模板或错误记忆策略的会话。</NAlert>
              <NDataTable :data="conversations" :pagination="{ pageSize: 8 }" :columns="[
                { title: '会话 ID', key: 'conversation_id', minWidth: 220, ellipsis: { tooltip: true } },
                { title: '客户端', key: 'client_name', width: 120, render: (row: any) => row.client_name || '-' },
                { title: '最近活跃', key: 'last_seen_at', width: 160 },
                { title: '当前方案', key: 'config', width: 180, render: (row: any) => profileName(row.config?.profile_id) },
                { title: '操作', key: 'actions', width: 120, render: (row: any) => h(NButton, { size: 'tiny', quaternary: true, onClick: () => openStateBoard(row.conversation_id) }, { icon: () => h(NIcon, null, { default: () => h(OpenOutline) }), default: () => '状态板' }) },
              ]" />
            </NSpace>
          </NTabPane>

          <NTabPane name="diagnosis" tab="诊断与工具">
            <NSpace vertical>
              <NAlert :type="health({ ...selected, ...form }).type as any" :show-icon="false">当前诊断：{{ health({ ...selected, ...form }).label }}</NAlert>
              <p>RimTalk / 殖民地模拟角色建议：默认方案为 RimTalk，长期记忆写入关闭，注入策略为仅状态板。</p>
              <NButton type="warning" @click="applyToConversations">应用当前默认策略到已有会话</NButton>
            </NSpace>
          </NTabPane>
        </NTabs>
        <template #footer>
          <NSpace justify="end">
            <NButton @click="showDrawer = false">关闭</NButton>
            <NButton type="primary" :loading="saving" @click="saveCharacter">保存角色配置</NButton>
          </NSpace>
        </template>
      </NDrawerContent>
    </NDrawer>

    <NModal v-model:show="showHelp" preset="card" title="角色中心帮助" style="width: 720px">
      <NSpace vertical>
        <p><b>角色档案</b>：为 character_id 添加显示名称、别名和备注，方便识别。</p>
        <p><b>默认策略</b>：决定该角色新会话默认使用什么状态板模板、是否写长期记忆、注入什么上下文。</p>
        <p><b>记忆库绑定</b>：决定该角色默认从哪些记忆库召回，以及新记忆写入哪个库。</p>
        <p><b>相关会话</b>：查看该角色已有会话，并可批量套用当前默认策略。</p>
      </NSpace>
    </NModal>
  </div>
</template>

<style scoped>
.characters-page {
  padding: 20px;
}

@media (max-width: 768px) {
  .characters-page {
    padding: 0;
  }

  .characters-page :deep(.n-card__content),
  .characters-page :deep(.n-card-header) {
    padding: 14px;
  }
}
</style>
