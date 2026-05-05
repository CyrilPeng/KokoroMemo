<script setup lang="ts">
import { NButton, NIcon } from 'naive-ui'
import { HelpCircleOutline } from '@vicons/ionicons5'
import { useI18n } from 'vue-i18n'

defineProps<{
  title: string
  subtitle?: string
  showHelp?: boolean
}>()
const emit = defineEmits<{ (e: 'help'): void }>()
const { t } = useI18n()
</script>

<template>
  <div class="page-header">
    <div class="page-header__title-block">
      <h1 class="page-header__title">{{ title }}</h1>
      <p v-if="subtitle" class="page-header__subtitle">{{ subtitle }}</p>
    </div>
    <NButton v-if="showHelp" quaternary class="page-header__help-btn" @click="emit('help')">
      <template #icon><NIcon :component="HelpCircleOutline" /></template>
      {{ t('common.help') }}
    </NButton>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.page-header__title-block {
  flex: 1 1 auto;
  min-width: 0;
}

.page-header__title {
  font-size: 22px;
  font-weight: 600;
  color: #e4e4e7;
  margin: 0 0 4px 0;
  line-height: 1.3;
}

.page-header__subtitle {
  color: #71717a;
  font-size: 13px;
  margin: 0;
  line-height: 1.5;
}

.page-header__help-btn {
  flex-shrink: 0;
}
</style>
