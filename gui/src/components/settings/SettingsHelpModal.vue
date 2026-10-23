<script setup lang="ts">
import { NModal } from 'naive-ui'

const help = defineModel<string>('help', { required: true })
</script>

<template>
  <NModal
    :show="!!help"
    preset="card"
    :title="$t('settings.helpTitle')"
    style="width: min(600px, 96vw); background: #18181b;"
    :mask-closable="true"
    @update:show="(visible: boolean) => { if (!visible) help = '' }"
  >
    <div v-if="help === 'llm'" class="help-content">
      <p><strong>{{ $t('settings.forwardMode') }}</strong>: {{ $t('settings.forwardModeHelp') }}</p>
      <p><strong>{{ $t('settings.provider') }}</strong>: {{ $t('settings.providerHelp') }}</p>
      <p><strong>Base URL</strong>: {{ $t('settings.baseUrlHelp') }}</p>
      <p><strong>API Key</strong>: {{ $t('settings.apiKeyHelp') }}</p>
      <p><strong>{{ $t('settings.modelName') }}</strong>: {{ $t('settings.modelNameHelp') }}</p>
    </div>
    <div v-else-if="help === 'embedding'" class="help-content">
      <p>{{ $t('settings.embeddingHelp') }}</p>
      <p><strong>{{ $t('settings.dimension') }}</strong>: {{ $t('settings.dimensionHelp') }}</p>
    </div>
    <div v-else-if="help === 'rerank'" class="help-content">
      <p>{{ $t('settings.rerankHelp') }}</p>
      <p><strong>{{ $t('settings.maxDocsPerBatch') }}</strong>: {{ $t('settings.maxDocsHelp') }}</p>
    </div>
    <div v-else-if="help === 'stateFiller'" class="help-content">
      <p>{{ $t('settings.stateFillerHelp') }}</p>
      <p><strong>{{ $t('settings.fillMode') }}</strong>: {{ $t('settings.fillModeHelp') }}</p>
      <p><strong>{{ $t('settings.minConfidence') }}</strong>: {{ $t('settings.minConfidenceHelp') }}</p>
      <p><strong>{{ $t('settings.timeout') }}</strong>: {{ $t('settings.timeoutHelp') }}</p>
      <p><strong>{{ $t('settings.temperature') }}</strong>: {{ $t('settings.temperatureHelp') }}</p>
      <p><strong>{{ $t('settings.customPrompt') }}</strong>: {{ $t('settings.customPromptHelp') }}</p>
    </div>
    <div v-else-if="help === 'memory'" class="help-content">
      <p>{{ $t('settings.memoryHelp') }}</p>
      <p><strong>{{ $t('settings.maxInjectChars') }}</strong>: {{ $t('settings.maxInjectCharsHelp') }}</p>
      <p><strong>{{ $t('settings.memoryJudge') }}</strong>: {{ $t('settings.memoryJudgeHelp') }}</p>
      <p><strong>{{ $t('settings.judgeMode') }}</strong>: {{ $t('settings.judgeModeHelp') }}</p>
      <p><strong>{{ $t('settings.userRules') }}</strong>: {{ $t('settings.userRulesHelp') }}</p>
    </div>
    <div v-else-if="help === 'server'" class="help-content">
      <p><strong>{{ $t('settings.openaiBaseUrl') }}</strong>: {{ $t('settings.openaiBaseUrlHelp') }}</p>
      <p><strong>{{ $t('settings.localPort') }}</strong>: {{ $t('settings.localPortHelp') }}</p>
      <p><strong>{{ $t('settings.storageDir') }}</strong>: {{ $t('settings.storageDirHelp') }}</p>
      <p><strong>{{ $t('settings.timezone') }}</strong>: {{ $t('settings.timezoneHelp') }}</p>
      <p><strong>{{ $t('settings.language') }}</strong>: {{ $t('settings.languageHelp') }}</p>
      <p><strong>{{ $t('settings.closeToTray') }}</strong>: {{ $t('settings.closeToTrayHelp') }}</p>
      <p><strong>{{ $t('settings.updateCheck') }}</strong>: {{ $t('settings.updateCheckHelp') }}</p>
    </div>
    <div v-else-if="help === 'adv_memoryTop'" class="help-content">
      <p>{{ $t('settings.adv.helpDetail.memoryTop.intro') }}</p>
      <p><strong>{{ $t('settings.adv.injectEnabled') }}</strong>: {{ $t('settings.adv.helpDetail.memoryTop.inject') }}</p>
      <p><strong>{{ $t('settings.adv.extractionEnabled') }}</strong>: {{ $t('settings.adv.helpDetail.memoryTop.extraction') }}</p>
      <p><strong>{{ $t('settings.adv.maxRecentTurns') }}</strong>: {{ $t('settings.adv.helpDetail.memoryTop.recentTurns') }}</p>
      <p><strong>{{ $t('settings.adv.vectorTopK') }}</strong>: {{ $t('settings.adv.helpDetail.memoryTop.topK') }}</p>
    </div>
    <div v-else-if="help === 'adv_conversation'" class="help-content">
      <p>{{ $t('settings.adv.helpDetail.conversation.intro') }}</p>
      <p><strong>{{ $t('settings.adv.convIdentityMode') }}</strong>: {{ $t('settings.adv.helpDetail.conversation.identityMode') }}</p>
      <p><strong>{{ $t('settings.adv.convAutoGap') }}</strong>: {{ $t('settings.adv.helpDetail.conversation.gap') }}</p>
      <p><strong>{{ $t('settings.adv.convDetectCount') }}</strong>: {{ $t('settings.adv.helpDetail.conversation.count') }}</p>
    </div>
    <div v-else-if="help === 'adv_scopes'" class="help-content">
      <p>{{ $t('settings.adv.helpDetail.scopes.intro') }}</p>
      <p><strong>{{ $t('settings.adv.scopeGlobal') }}</strong>: {{ $t('settings.adv.helpDetail.scopes.global') }}</p>
      <p><strong>{{ $t('settings.adv.scopeCharacter') }}</strong>: {{ $t('settings.adv.helpDetail.scopes.character') }}</p>
      <p><strong>{{ $t('settings.adv.scopeConversation') }}</strong>: {{ $t('settings.adv.helpDetail.scopes.conversation') }}</p>
    </div>
    <div v-else-if="help === 'adv_extraction'" class="help-content">
      <p>{{ $t('settings.adv.helpDetail.extraction.intro') }}</p>
      <p><strong>{{ $t('settings.adv.extMinImportance') }}</strong>: {{ $t('settings.adv.helpDetail.extraction.importance') }}</p>
      <p><strong>{{ $t('settings.adv.extMinConfidence') }}</strong>: {{ $t('settings.adv.helpDetail.extraction.confidence') }}</p>
      <p><strong>{{ $t('settings.adv.extSemanticDedupThreshold') }}</strong>: {{ $t('settings.adv.helpDetail.extraction.semanticDedup') }}</p>
    </div>
    <div v-else-if="help === 'adv_scoring'" class="help-content">
      <p>{{ $t('settings.adv.helpDetail.scoring.intro') }}</p>
      <p><strong>{{ $t('settings.adv.scoreVector') }}</strong>: {{ $t('settings.adv.helpDetail.scoring.vector') }}</p>
      <p><strong>{{ $t('settings.adv.scoreImportance') }}</strong>: {{ $t('settings.adv.helpDetail.scoring.importance') }}</p>
      <p><strong>{{ $t('settings.adv.scoreRecency') }}</strong>: {{ $t('settings.adv.helpDetail.scoring.recency') }}</p>
      <p><strong>{{ $t('settings.adv.scoreScope') }}</strong>: {{ $t('settings.adv.helpDetail.scoring.scope') }}</p>
      <p><strong>{{ $t('settings.adv.scoreConfidence') }}</strong>: {{ $t('settings.adv.helpDetail.scoring.confidence') }}</p>
    </div>
    <div v-else-if="help === 'adv_gate'" class="help-content">
      <p>{{ $t('settings.adv.helpDetail.gate.intro') }}</p>
      <p><strong>{{ $t('settings.adv.gateMode') }}</strong>: {{ $t('settings.adv.helpDetail.gate.mode') }}</p>
      <p><strong>{{ $t('settings.adv.gateOnNewSession') }}</strong>: {{ $t('settings.adv.helpDetail.gate.newSession') }}</p>
      <p><strong>{{ $t('settings.adv.gateEveryNTurns') }}</strong>: {{ $t('settings.adv.helpDetail.gate.everyN') }}</p>
      <p><strong>{{ $t('settings.adv.gateStateConfBelow') }}</strong>: {{ $t('settings.adv.helpDetail.gate.confBelow') }}</p>
      <p><strong>{{ $t('settings.adv.gateTriggerKeywords') }}</strong>: {{ $t('settings.adv.helpDetail.gate.keywords') }}</p>
      <p><strong>{{ $t('settings.adv.gateSkipCharsBelow') }}</strong>: {{ $t('settings.adv.helpDetail.gate.skipChars') }}</p>
      <p><strong>{{ $t('settings.adv.gateSkipWhenSufficient') }}</strong>: {{ $t('settings.adv.helpDetail.gate.skipSufficient') }}</p>
    </div>
    <div v-else-if="help === 'adv_hotContext'" class="help-content">
      <p>{{ $t('settings.adv.helpDetail.hotContext.intro') }}</p>
      <p><strong>{{ $t('settings.adv.hcMaxChars') }}</strong>: {{ $t('settings.adv.helpDetail.hotContext.maxChars') }}</p>
      <p><strong>{{ $t('settings.adv.hcSections') }}</strong>: {{ $t('settings.adv.helpDetail.hotContext.sections') }}</p>
    </div>
    <div v-else-if="help === 'vectorMaintenance'" class="help-content">
      <p>{{ $t('settings.vectorHelp.intro') }}</p>
      <p><strong>{{ $t('settings.rebuildIndex') }}</strong>: {{ $t('settings.vectorHelp.rebuild') }}</p>
      <p><strong>{{ $t('settings.startMigration') }}</strong>: {{ $t('settings.vectorHelp.migration') }}</p>
      <p><strong>{{ $t('settings.retryVectorSync') }}</strong>: {{ $t('settings.vectorHelp.retry') }}</p>
    </div>
  </NModal>
</template>
