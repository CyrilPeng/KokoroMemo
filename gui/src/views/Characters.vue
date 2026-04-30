<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import {
  NButton, NCard, NDataTable, NEmpty, NForm, NFormItem, NIcon, NModal,
  NSelect, NSpace, NSpin, NSwitch, NTag, useMessage,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { CreateOutline, HelpCircleOutline } from '@vicons/ionicons5'
import { apiFetch } from '../api'

const message = useMessage()
const { t } = useI18n()

const characters = ref<any[]>([])
const templates = ref<any[]>([])
const libraries = ref<any[]>([])
const loading = ref(true)
const showEditModal = ref(false)
const editingCharacter = ref<any>(null)
const editForm = ref({
  template_id: null as string | null,
  library_ids: ['lib_default'] as string[],
  write_library_id: 'lib_default',
  auto_apply: true,
})
const helpModal = ref(false)

const templateOptions = computed(() => [
  { label: t('characters.noTemplate'), value: null as any },
  ...templates.value.map((tpl) => ({ label: tpl.name, value: tpl.template_id })),
])

const libraryOptions = computed(() => libraries.value.map((lib) => ({
  label: `${lib.name}${lib.card_count ? `（${lib.card_count}）` : ''}`,
  value: lib.library_id,
})))

const writeLibraryOptions = computed(() =>
  libraryOptions.value.filter((opt) => editForm.value.library_ids.includes(opt.value))
)

const columns = computed(() => [
  { title: t('characters.column.id'), key: 'character_id', minWidth: 200, ellipsis: { tooltip: true } },
  { title: t('characters.column.conversations'), key: 'conversation_count', width: 100 },
  { title: t('characters.column.lastSeen'), key: 'last_seen_at', width: 160 },
  {
    title: t('characters.column.template'), key: 'template_id', width: 180,
    render: (row: any) => row.template_id
      ? (templates.value.find((t) => t.template_id === row.template_id)?.name || row.template_id)
      : h('span', { style: 'color: #71717a;' }, t('characters.unset')),
  },
  {
    title: t('characters.column.libraries'), key: 'library_ids', minWidth: 180, ellipsis: { tooltip: true },
    render: (row: any) => row.library_ids?.length
      ? row.library_ids.map((id: string) => libraries.value.find((l) => l.library_id === id)?.name || id).join(', ')
      : h('span', { style: 'color: #71717a;' }, t('characters.unset')),
  },
  {
    title: t('characters.column.autoApply'), key: 'auto_apply', width: 100,
    render: (row: any) => row.template_id || row.library_ids?.length
      ? h(NTag, { size: 'small', type: row.auto_apply ? 'success' : 'default' }, {
          default: () => row.auto_apply ? t('characters.on') : t('characters.off'),
        })
      : '—',
  },
  {
    title: t('characters.column.actions'), key: 'actions', width: 100,
    render: (row: any) => h(NButton, {
      size: 'tiny', quaternary: true, onClick: () => openEditModal(row),
    }, {
      icon: () => h(NIcon, null, { default: () => h(CreateOutline) }),
      default: () => t('characters.edit'),
    }),
  },
])

async function fetchAll() {
  loading.value = true
  try {
    const [charResp, tplResp, libResp] = await Promise.all([
      apiFetch('/admin/discovered-characters'),
      apiFetch('/admin/state/templates'),
      apiFetch('/admin/memory-libraries'),
    ])
    if (charResp.ok) characters.value = (await charResp.json()).items || []
    if (tplResp.ok) templates.value = (await tplResp.json()).items || []
    if (libResp.ok) libraries.value = (await libResp.json()).items || []
  } catch (e: any) {
    message.error(t('characters.loadFailed', { error: e.message || e }))
  }
  loading.value = false
}

function openEditModal(row: any) {
  editingCharacter.value = row
  editForm.value = {
    template_id: row.template_id ?? null,
    library_ids: row.library_ids?.length ? [...row.library_ids] : ['lib_default'],
    write_library_id: row.write_library_id || 'lib_default',
    auto_apply: row.auto_apply ?? true,
  }
  showEditModal.value = true
}

async function saveDefaults() {
  if (!editingCharacter.value) return
  try {
    const resp = await apiFetch(`/admin/characters/${editingCharacter.value.character_id}/defaults`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editForm.value),
    })
    const data = await resp.json()
    if (data.status !== 'ok') throw new Error(data.message || t('common.saveFailed'))
    showEditModal.value = false
    message.success(t('characters.saved'))
    await fetchAll()
  } catch (e: any) {
    message.error(e.message || String(e))
  }
}

onMounted(fetchAll)
</script>

<template>
  <div>
    <div style="margin-bottom: 28px; display: flex; justify-content: space-between; align-items: flex-start;">
      <div>
        <h1 style="font-size: 24px; font-weight: 600; color: #e4e4e7; margin-bottom: 4px;">{{ $t('characters.title') }}</h1>
        <p style="color: #71717a; font-size: 14px; margin: 0;">{{ $t('characters.subtitle') }}</p>
      </div>
      <NButton quaternary @click="helpModal = true">
        <template #icon><NIcon><HelpCircleOutline /></NIcon></template>
        {{ $t('characters.helpButton') }}
      </NButton>
    </div>

    <NCard style="background: #18181b; border: 1px solid #27272a;">
      <NSpin :show="loading">
        <NEmpty v-if="!characters.length && !loading" :description="$t('characters.empty')" />
        <NDataTable v-else :columns="columns" :data="characters" :pagination="{ pageSize: 20 }" />
      </NSpin>
    </NCard>

    <NModal v-model:show="showEditModal" preset="card" :title="$t('characters.editTitle')" style="width: 560px; background: #18181b;">
      <div v-if="editingCharacter" style="color: #71717a; font-size: 13px; margin-bottom: 14px;">
        {{ $t('characters.idLabel') }} <strong style="color: #e4e4e7;">{{ editingCharacter.character_id }}</strong>
      </div>
      <NForm label-placement="top">
        <NFormItem :label="$t('characters.template')">
          <NSelect v-model:value="editForm.template_id" :options="templateOptions" :placeholder="$t('characters.templatePlaceholder')" />
        </NFormItem>
        <NFormItem :label="$t('characters.libraries')">
          <NSelect v-model:value="editForm.library_ids" multiple filterable :options="libraryOptions" :placeholder="$t('characters.librariesPlaceholder')" />
        </NFormItem>
        <NFormItem :label="$t('characters.writeLibrary')">
          <NSelect v-model:value="editForm.write_library_id" :options="writeLibraryOptions" :placeholder="$t('characters.writeLibraryPlaceholder')" />
        </NFormItem>
        <NFormItem :label="$t('characters.autoApplyLabel')">
          <NSwitch v-model:value="editForm.auto_apply" />
          <span style="color: #71717a; font-size: 12px; margin-left: 12px;">{{ $t('characters.autoApplyHint') }}</span>
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showEditModal = false">{{ $t('common.cancel') }}</NButton>
          <NButton type="primary" @click="saveDefaults">{{ $t('common.save') }}</NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal v-model:show="helpModal" preset="card" :title="$t('characters.helpTitle')" style="width: 600px; background: #18181b;" :mask-closable="true">
      <div class="help-content">
        <p>{{ $t('characters.help.intro') }}</p>
        <p><strong>{{ $t('characters.help.discoveryTitle') }}</strong>: {{ $t('characters.help.discovery') }}</p>
        <p><strong>{{ $t('characters.help.templateTitle') }}</strong>: {{ $t('characters.help.template') }}</p>
        <p><strong>{{ $t('characters.help.librariesTitle') }}</strong>: {{ $t('characters.help.libraries') }}</p>
        <p><strong>{{ $t('characters.help.autoApplyTitle') }}</strong>: {{ $t('characters.help.autoApply') }}</p>
      </div>
    </NModal>
  </div>
</template>

<style scoped>
.help-content p {
  color: #d4d4d8;
  font-size: 15px;
  line-height: 1.85;
  margin: 10px 0;
}
.help-content p strong {
  color: #ffffff;
  font-weight: 600;
}
</style>
