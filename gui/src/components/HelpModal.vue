<script setup lang="ts">
import { computed } from 'vue'
import { NModal, NSpace } from 'naive-ui'

export interface HelpSection {
  title: string
  body?: string
  bullets?: string[]
}

const props = defineProps<{
  show: boolean
  title: string
  sections: HelpSection[]
  width?: string
}>()
const emit = defineEmits<{ (e: 'update:show', value: boolean): void }>()

const internalShow = computed({
  get: () => props.show,
  set: (value) => emit('update:show', value),
})
const modalWidth = computed(() => {
  const base = props.width || '720px'
  return base.startsWith('min(') || base.endsWith('vw') ? base : `min(${base}, 96vw)`
})
</script>

<template>
  <NModal v-model:show="internalShow" preset="card" :title="title" :style="{ width: modalWidth }" class="help-modal">
    <NSpace vertical size="medium" class="help-modal__body">
      <div v-for="(section, index) in sections" :key="index">
        <b>{{ section.title }}</b>
        <p v-if="section.body" class="help-body">{{ section.body }}</p>
        <ul v-if="section.bullets && section.bullets.length" class="help-bullets">
          <li v-for="(item, idx) in section.bullets" :key="idx">{{ item }}</li>
        </ul>
      </div>
    </NSpace>
  </NModal>
</template>

<style scoped>
.help-modal__body {
  max-height: calc(80vh - 80px);
  overflow-y: auto;
}

.help-body {
  color: #a1a1aa;
  font-size: 13px;
  line-height: 1.7;
  margin: 4px 0 0 0;
}

.help-bullets {
  color: #a1a1aa;
  font-size: 13px;
  line-height: 1.7;
  margin: 4px 0 0 0;
  padding-left: 20px;
}

.help-bullets li {
  margin-bottom: 2px;
}
</style>
