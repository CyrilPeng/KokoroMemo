<script setup lang="ts">
import { NCollapse, NCollapseItem, NSpace, NTag } from 'naive-ui'
import type { StateDiagnostic } from './types'

defineProps<{
  issues: StateDiagnostic[]
  rowCount: number
  previewChars: number
}>()
</script>

<template>
  <NCollapse>
    <NCollapseItem title="健康诊断" name="diag">
      <NSpace align="center" :wrap="true">
        <NTag v-for="item in issues" :key="item.label" :type="item.type">{{ item.label }}</NTag>
        <span style="color: #a1a1aa; font-size: 13px;">当前状态行 {{ rowCount }} 条，注入预览 {{ previewChars || 0 }} 字符。</span>
      </NSpace>
    </NCollapseItem>
  </NCollapse>
</template>
