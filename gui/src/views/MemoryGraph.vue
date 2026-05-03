<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, triggerRef, watch } from 'vue'
import {
  NButton, NCard, NEmpty, NIcon, NInputNumber, NModal, NSelect, NSpace,
  NSpin, NTag, useMessage,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { HelpCircleOutline, RefreshOutline } from '@vicons/ionicons5'
import { apiFetch } from '../api'

const message = useMessage()
const { t } = useI18n()

const libraries = ref<any[]>([])
const selectedLibraryId = ref<string | null>(null)
const limit = ref(100)
const loading = ref(false)
const helpModal = ref(false)
const nodes = ref<any[]>([])
const edges = ref<any[]>([])
const hoveredNode = ref<any | null>(null)

interface SimNode { id: string; x: number; y: number; vx: number; vy: number; data: any }
const simNodes = ref<SimNode[]>([])
const simEdges = ref<{ source: SimNode; target: SimNode; data: any }[]>([])
const SVG_W = 880
const SVG_H = 560

const libraryOptions = computed(() => [
  { label: t('graph.allLibraries'), value: null as any },
  ...libraries.value.map((l) => ({ label: l.name, value: l.library_id })),
])

const typeColor: Record<string, string> = {
  preference: '#a78bfa',
  boundary: '#f87171',
  relationship: '#34d399',
  event: '#60a5fa',
  promise: '#fbbf24',
  correction: '#f472b6',
  world_state: '#a3e635',
  summary: '#9ca3af',
}

function nodeColor(type: string) {
  return typeColor[type] || '#71717a'
}

function typeLabel(type: string): string {
  const key = `memories.typeLabels.${type}`
  const translated = t(key)
  return translated === key ? type : translated
}

function scopeLabel(scope: string): string {
  if (!scope) return ''
  const key = `memories.scopeLabels.${scope}`
  const translated = t(key)
  return translated === key ? scope : translated
}

function nodeRadius(importance: number) {
  return 6 + Math.max(0, Math.min(1, importance || 0.5)) * 8
}

async function fetchLibraries() {
  try {
    const resp = await apiFetch('/admin/memory-libraries')
    if (resp.ok) libraries.value = (await resp.json()).items || []
  } catch {}
}

async function fetchGraph() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (selectedLibraryId.value) params.set('library_id', selectedLibraryId.value)
    params.set('limit', String(limit.value))
    const resp = await apiFetch(`/admin/memory-graph?${params.toString()}`)
    if (resp.ok) {
      const data = await resp.json()
      nodes.value = data.nodes || []
      edges.value = data.edges || []
      initSimulation()
    }
  } catch (e: any) {
    message.error(t('graph.loadFailed', { error: e.message || e }))
  }
  loading.value = false
}

let rafId: number | null = null

function initSimulation() {
  const cx = SVG_W / 2
  const cy = SVG_H / 2
  // 随机初始散布：纯圆形布局容易让模拟陷入局部最小值。
  simNodes.value = nodes.value.map((n) => ({
    id: n.id,
    x: cx + (Math.random() - 0.5) * SVG_W * 0.6,
    y: cy + (Math.random() - 0.5) * SVG_H * 0.6,
    vx: 0, vy: 0,
    data: n,
  }))
  const idMap: Record<string, SimNode> = {}
  for (const n of simNodes.value) idMap[n.id] = n
  simEdges.value = edges.value
    .filter((e) => idMap[e.source] && idMap[e.target])
    .map((e) => ({ source: idMap[e.source], target: idMap[e.target], data: e }))
  if (rafId) cancelAnimationFrame(rafId)
  let iter = 0
  const step = () => {
    if (iter > 600) { rafId = null; return }
    iter++
    tick()
    triggerRef(simNodes)
    rafId = requestAnimationFrame(step)
  }
  rafId = requestAnimationFrame(step)
}

function tick() {
  const cx = SVG_W / 2
  const cy = SVG_H / 2
  const repel = 1500
  const linkDist = 90
  const center = 0.008
  // 每对节点之间的类库仑斥力
  for (const a of simNodes.value) {
    let fx = (cx - a.x) * center
    let fy = (cy - a.y) * center
    for (const b of simNodes.value) {
      if (a === b) continue
      const dx = a.x - b.x
      const dy = a.y - b.y
      const d2 = dx * dx + dy * dy + 0.01
      const dist = Math.sqrt(d2)
      const f = repel / d2
      fx += (dx / dist) * f
      fy += (dy / dist) * f
    }
    a.vx = (a.vx + fx) * 0.82
    a.vy = (a.vy + fy) * 0.82
  }
  // 每条边的弹簧力：权重越高目标距离越短（拉力越强）
  for (const e of simEdges.value) {
    const dx = e.target.x - e.source.x
    const dy = e.target.y - e.source.y
    const dist = Math.sqrt(dx * dx + dy * dy) + 0.01
    const weight = Math.max(0.2, Math.min(2, e.data.weight || 1))
    const desired = linkDist / weight
    const k = (dist - desired) * 0.08
    const fx = (dx / dist) * k
    const fy = (dy / dist) * k
    e.source.vx += fx
    e.source.vy += fy
    e.target.vx -= fx
    e.target.vy -= fy
  }
  for (const n of simNodes.value) {
    n.x = Math.max(20, Math.min(SVG_W - 20, n.x + n.vx))
    n.y = Math.max(20, Math.min(SVG_H - 20, n.y + n.vy))
  }
}

function onNodeHover(node: SimNode | null) {
  hoveredNode.value = node?.data || null
}

onMounted(async () => {
  await fetchLibraries()
  await fetchGraph()
})

onBeforeUnmount(() => {
  if (rafId) cancelAnimationFrame(rafId)
})

watch([selectedLibraryId, limit], () => fetchGraph())
</script>

<template>
  <div>
    <div style="margin-bottom: 28px; display: flex; justify-content: space-between; align-items: flex-start;">
      <div>
        <h1 style="font-size: 24px; font-weight: 600; color: #e4e4e7; margin-bottom: 4px;">{{ $t('graph.title') }}</h1>
        <p style="color: #71717a; font-size: 14px; margin: 0;">{{ $t('graph.subtitle') }}</p>
      </div>
      <NButton quaternary @click="helpModal = true">
        <template #icon><NIcon><HelpCircleOutline /></NIcon></template>
        {{ $t('graph.helpButton') }}
      </NButton>
    </div>

    <NCard style="background: #18181b; border: 1px solid #27272a;">
      <NSpace align="center" justify="space-between" style="margin-bottom: 12px;" wrap>
        <NSpace align="center" wrap>
          <NSelect v-model:value="selectedLibraryId" :options="libraryOptions" :placeholder="$t('graph.selectLibrary')" style="width: 220px;" size="small" />
          <span style="color: #a1a1aa; font-size: 13px;">{{ $t('graph.limit') }}</span>
          <NInputNumber v-model:value="limit" :min="10" :max="500" :step="10" size="small" style="width: 110px;" />
          <NButton size="small" quaternary @click="fetchGraph">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ $t('common.refresh') }}
          </NButton>
        </NSpace>
        <NSpace align="center" :size="14">
          <NTag size="small">{{ $t('graph.nodesCount', { count: nodes.length }) }}</NTag>
          <NTag size="small">{{ $t('graph.edgesCount', { count: edges.length }) }}</NTag>
        </NSpace>
      </NSpace>

      <NSpin :show="loading">
        <NEmpty v-if="!nodes.length && !loading" :description="$t('graph.empty')" style="padding: 40px 0;" />
        <div v-else style="display: flex; gap: 16px;">
          <svg
            :viewBox="`0 0 ${SVG_W} ${SVG_H}`"
            style="flex: 1; background: #09090b; border-radius: 6px; min-height: 560px;"
          >
            <line
              v-for="(e, i) in simEdges"
              :key="`edge-${i}`"
              :x1="e.source.x" :y1="e.source.y"
              :x2="e.target.x" :y2="e.target.y"
              stroke="#3f3f46"
              :stroke-width="1 + (e.data.weight || 0.5)"
              opacity="0.7"
            />
            <g v-for="n in simNodes" :key="n.id">
              <circle
                :cx="n.x" :cy="n.y"
                :r="nodeRadius(n.data.importance)"
                :fill="nodeColor(n.data.type)"
                stroke="#18181b" stroke-width="1.5"
                style="cursor: pointer;"
                @mouseenter="onNodeHover(n)"
                @mouseleave="onNodeHover(null)"
              />
            </g>
          </svg>
          <div style="width: 280px; flex-shrink: 0;">
            <NCard style="background: #09090b; border: 1px solid #27272a; height: 100%;">
              <template #header>
                <span style="font-size: 14px;">{{ hoveredNode ? $t('graph.nodeDetails') : $t('graph.legend') }}</span>
              </template>
              <div v-if="hoveredNode">
                <p style="color: #d4d4d8; font-size: 13px; line-height: 1.6; margin: 0 0 10px;">{{ hoveredNode.label }}</p>
                <div style="font-size: 12px; color: #a1a1aa; line-height: 1.8;">
                  <div><span style="color: #71717a;">{{ $t('graph.type') }}：</span><NTag size="tiny" :color="{ color: nodeColor(hoveredNode.type), textColor: '#fff' }">{{ typeLabel(hoveredNode.type) }}</NTag></div>
                  <div><span style="color: #71717a;">{{ $t('graph.importance') }}：</span>{{ (hoveredNode.importance || 0).toFixed(2) }}</div>
                  <div><span style="color: #71717a;">{{ $t('graph.confidence') }}：</span>{{ (hoveredNode.confidence || 0).toFixed(2) }}</div>
                  <div><span style="color: #71717a;">{{ $t('graph.scope') }}：</span>{{ scopeLabel(hoveredNode.scope) }}</div>
                </div>
              </div>
              <div v-else>
                <div v-for="(color, type) in typeColor" :key="type" style="display: flex; align-items: center; gap: 8px; margin: 6px 0; font-size: 12px; color: #d4d4d8;">
                  <span :style="{ width: '10px', height: '10px', borderRadius: '50%', background: color }"></span>
                  <span>{{ typeLabel(String(type)) }}</span>
                </div>
              </div>
            </NCard>
          </div>
        </div>
      </NSpin>
    </NCard>

    <NModal v-model:show="helpModal" preset="card" :title="$t('graph.helpTitle')" style="width: 600px; background: #18181b;" :mask-closable="true">
      <div class="help-content">
        <p>{{ $t('graph.help.intro') }}</p>
        <p><strong>{{ $t('graph.help.nodesTitle') }}</strong>: {{ $t('graph.help.nodes') }}</p>
        <p><strong>{{ $t('graph.help.edgesTitle') }}</strong>: {{ $t('graph.help.edges') }}</p>
        <p><strong>{{ $t('graph.help.colorsTitle') }}</strong>: {{ $t('graph.help.colors') }}</p>
        <p><strong>{{ $t('graph.help.limitTitle') }}</strong>: {{ $t('graph.help.limit') }}</p>
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
