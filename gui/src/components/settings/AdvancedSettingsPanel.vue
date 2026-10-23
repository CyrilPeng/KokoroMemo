<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NDynamicTags,
  NForm,
  NFormItem,
  NInputNumber,
  NMenu,
  NCard,
  NSelect,
  NSlider,
  NSpace,
  NSwitch,
  useMessage,
} from 'naive-ui'
import { apiFetch, friendlyError } from '../../api'

const config = defineModel<Record<string, any>>('config', { required: true })
const emit = defineEmits<{ (event: 'open-help', key: string): void }>()
const { t } = useI18n()
const message = useMessage()

const advancedSection = ref('memoryTop')
const conversationIdentityModes = computed(() => [
  { label: t('settings.adv.convIdentityRequest'), value: 'request' },
  { label: t('settings.adv.convIdentityApiKey'), value: 'api_key' },
])
const retrievalGateModes = computed(() => [
  { label: t('settings.adv.gateModeAuto'), value: 'auto' },
  { label: t('settings.adv.gateModeAlways'), value: 'always' },
  { label: t('settings.adv.gateModeNever'), value: 'never' },
  { label: t('settings.adv.gateModeKeyword'), value: 'keyword_only' },
])
const advancedMenuOptions = computed(() => [
  { label: t('settings.adv.memoryTop'), key: 'memoryTop' },
  { label: t('settings.adv.conversation'), key: 'conversation' },
  { label: t('settings.adv.scopes'), key: 'scopes' },
  { label: t('settings.adv.extraction'), key: 'extraction' },
  { label: t('settings.adv.scoring'), key: 'scoring' },
  { label: t('settings.adv.retrievalGate'), key: 'gate' },
  { label: t('settings.adv.hotContext'), key: 'hotContext' },
])
const scoringTotal = computed(() => {
  return (config.value.score_vector || 0)
    + (config.value.score_importance || 0)
    + (config.value.score_recency || 0)
    + (config.value.score_scope || 0)
    + (config.value.score_confidence || 0)
})

async function cleanupDiscardedInbox() {
  try {
    const resp = await apiFetch('/admin/inbox/cleanup-discarded', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keep_limit: config.value.ext_discarded_keep_limit }),
    })
    const data = await resp.json()
    if (data.status === 'ok') {
      message.success(t('settings.adv.extDiscardedCleaned', { removed: data.removed, keep: data.keep_limit }))
    } else {
      message.error(data.message || t('common.failed'))
    }
  } catch (e: any) {
    message.error(friendlyError(e.message || String(e), 'settings.operation'))
  }
}
</script>

<template>
  <NCard style="background: #18181b; border: 1px solid #27272a;">
    <template #header>
      <NSpace align="center">
        <span>{{ $t('settings.adv.title') }}</span>
      </NSpace>
    </template>
    <p style="color: #71717a; font-size: 13px; margin: 0 0 14px;">{{ $t('settings.adv.subtitle') }}</p>

    <div class="adv-layout">
      <div class="adv-sidebar">
        <NMenu
          :options="advancedMenuOptions"
          :value="advancedSection"
          :indent="14"
          @update:value="(v: string) => { advancedSection = v }"
        />
      </div>
      <div class="adv-content">
        <div v-if="advancedSection === 'memoryTop'">
          <div class="adv-section-header">
            <h3 class="adv-section-title">{{ $t('settings.adv.memoryTop') }}</h3>
            <NButton quaternary size="tiny" @click="emit('open-help', 'adv_memoryTop')"><span class="help-icon">?</span></NButton>
          </div>
          <NForm label-placement="left" label-width="220" :show-feedback="false" class="adv-form">
            <NFormItem :label="$t('settings.adv.injectEnabled')"><NSwitch v-model:value="config.inject_enabled" /></NFormItem>
            <NFormItem :label="$t('settings.adv.extractionEnabled')"><NSwitch v-model:value="config.extraction_enabled" /></NFormItem>
            <NFormItem :label="$t('settings.adv.maxRecentTurns')"><NInputNumber v-model:value="config.max_recent_turns_for_query" :min="1" :max="50" style="width: 200px;" /></NFormItem>
            <NFormItem :label="$t('settings.adv.vectorTopK')"><NInputNumber v-model:value="config.vector_top_k" :min="1" :max="200" style="width: 200px;" /></NFormItem>
          </NForm>
        </div>

        <div v-else-if="advancedSection === 'conversation'">
          <div class="adv-section-header">
            <h3 class="adv-section-title">{{ $t('settings.adv.conversation') }}</h3>
            <NButton quaternary size="tiny" @click="emit('open-help', 'adv_conversation')"><span class="help-icon">?</span></NButton>
          </div>
          <NForm label-placement="left" label-width="220" :show-feedback="false" class="adv-form">
            <NFormItem :label="$t('settings.adv.convIdentityMode')">
              <NSelect v-model:value="config.conv_identity_mode" :options="conversationIdentityModes" style="width: 260px;" />
            </NFormItem>
            <NFormItem :label="$t('settings.adv.convAutoGap')">
              <NInputNumber v-model:value="config.conv_auto_gap" :min="0" :max="1440" style="width: 160px;" />
              <span style="color: #71717a; font-size: 12px; margin-left: 12px;">{{ $t('settings.adv.convAutoGapHint') }}</span>
            </NFormItem>
            <NFormItem :label="$t('settings.adv.convDetectCount')"><NSwitch v-model:value="config.conv_detect_count_reset" /></NFormItem>
          </NForm>
        </div>

        <div v-else-if="advancedSection === 'scopes'">
          <div class="adv-section-header">
            <h3 class="adv-section-title">{{ $t('settings.adv.scopes') }}</h3>
            <NButton quaternary size="tiny" @click="emit('open-help', 'adv_scopes')"><span class="help-icon">?</span></NButton>
          </div>
          <NForm label-placement="left" label-width="220" :show-feedback="false" class="adv-form">
            <NFormItem :label="$t('settings.adv.scopeGlobal')"><NSwitch v-model:value="config.scope_global" /></NFormItem>
            <NFormItem :label="$t('settings.adv.scopeCharacter')"><NSwitch v-model:value="config.scope_character" /></NFormItem>
            <NFormItem :label="$t('settings.adv.scopeConversation')"><NSwitch v-model:value="config.scope_conversation" /></NFormItem>
          </NForm>
        </div>

        <div v-else-if="advancedSection === 'extraction'">
          <div class="adv-section-header">
            <h3 class="adv-section-title">{{ $t('settings.adv.extraction') }}</h3>
            <NButton quaternary size="tiny" @click="emit('open-help', 'adv_extraction')"><span class="help-icon">?</span></NButton>
          </div>
          <NForm label-placement="left" label-width="220" :show-feedback="false" class="adv-form">
            <NFormItem :label="$t('settings.adv.extMinImportance')">
              <NSlider v-model:value="config.ext_min_importance" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 360px;" />
            </NFormItem>
            <NFormItem :label="$t('settings.adv.extMinConfidence')">
              <NSlider v-model:value="config.ext_min_confidence" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 360px;" />
            </NFormItem>
            <NFormItem :label="$t('settings.adv.extSemanticDedupThreshold')">
              <NSlider v-model:value="config.ext_semantic_dedup_threshold" :min="0.5" :max="1" :step="0.01" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 360px;" />
            </NFormItem>
            <NFormItem :label="$t('settings.adv.extDiscardedKeepLimit')">
              <NSpace align="center">
                <NInputNumber v-model:value="config.ext_discarded_keep_limit" :min="0" :max="10000" :step="50" style="width: 180px;" />
                <NButton size="small" @click="cleanupDiscardedInbox">{{ $t('settings.adv.extDiscardedCleanup') }}</NButton>
              </NSpace>
            </NFormItem>
          </NForm>
        </div>

        <div v-else-if="advancedSection === 'scoring'">
          <div class="adv-section-header">
            <h3 class="adv-section-title">{{ $t('settings.adv.scoring') }}</h3>
            <NButton quaternary size="tiny" @click="emit('open-help', 'adv_scoring')"><span class="help-icon">?</span></NButton>
          </div>
          <p class="adv-hint">{{ $t('settings.adv.scoringHint', { total: scoringTotal.toFixed(2) }) }}</p>
          <NForm label-placement="left" label-width="220" :show-feedback="false" class="adv-form">
            <NFormItem :label="$t('settings.adv.scoreVector')"><NSlider v-model:value="config.score_vector" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 420px;" /></NFormItem>
            <NFormItem :label="$t('settings.adv.scoreImportance')"><NSlider v-model:value="config.score_importance" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 420px;" /></NFormItem>
            <NFormItem :label="$t('settings.adv.scoreRecency')"><NSlider v-model:value="config.score_recency" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 420px;" /></NFormItem>
            <NFormItem :label="$t('settings.adv.scoreScope')"><NSlider v-model:value="config.score_scope" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 420px;" /></NFormItem>
            <NFormItem :label="$t('settings.adv.scoreConfidence')"><NSlider v-model:value="config.score_confidence" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 420px;" /></NFormItem>
          </NForm>
        </div>

        <div v-else-if="advancedSection === 'gate'">
          <div class="adv-section-header">
            <h3 class="adv-section-title">{{ $t('settings.adv.retrievalGate') }}</h3>
            <NButton quaternary size="tiny" @click="emit('open-help', 'adv_gate')"><span class="help-icon">?</span></NButton>
          </div>
          <NForm label-placement="left" label-width="220" :show-feedback="false" class="adv-form">
            <NFormItem :label="$t('settings.adv.gateEnabled')"><NSwitch v-model:value="config.rg_enabled" /></NFormItem>
            <NFormItem :label="$t('settings.adv.gateMode')"><NSelect v-model:value="config.rg_mode" :options="retrievalGateModes" style="width: 220px;" /></NFormItem>
            <NFormItem :label="$t('settings.adv.gateOnNewSession')"><NSwitch v-model:value="config.rg_on_new_session" /></NFormItem>
            <NFormItem :label="$t('settings.adv.gateEveryNTurns')"><NInputNumber v-model:value="config.rg_every_n_turns" :min="0" :max="50" style="width: 160px;" /></NFormItem>
            <NFormItem :label="$t('settings.adv.gateStateConfBelow')"><NSlider v-model:value="config.rg_state_conf_below" :min="0" :max="1" :step="0.05" :format-tooltip="(v: number) => v.toFixed(2)" style="max-width: 360px;" /></NFormItem>
            <NFormItem :label="$t('settings.adv.gateTriggerKeywords')"><NDynamicTags v-model:value="config.rg_trigger_keywords" /></NFormItem>
            <NFormItem :label="$t('settings.adv.gateSkipCharsBelow')"><NInputNumber v-model:value="config.rg_skip_chars_below" :min="0" :max="200" style="width: 160px;" /></NFormItem>
            <NFormItem :label="$t('settings.adv.gateSkipWhenSufficient')"><NSwitch v-model:value="config.rg_skip_when_state_sufficient" /></NFormItem>
          </NForm>
        </div>

        <div v-else-if="advancedSection === 'hotContext'">
          <div class="adv-section-header">
            <h3 class="adv-section-title">{{ $t('settings.adv.hotContext') }}</h3>
            <NButton quaternary size="tiny" @click="emit('open-help', 'adv_hotContext')"><span class="help-icon">?</span></NButton>
          </div>
          <NForm label-placement="left" label-width="220" :show-feedback="false" class="adv-form">
            <NFormItem :label="$t('settings.adv.hcEnabled')"><NSwitch v-model:value="config.hc_enabled" /></NFormItem>
            <NFormItem :label="$t('settings.adv.hcMaxChars')"><NInputNumber v-model:value="config.hc_max_chars" :min="100" :max="10000" :step="100" style="width: 200px;" /></NFormItem>
          </NForm>
        </div>
      </div>
    </div>
  </NCard>
</template>
