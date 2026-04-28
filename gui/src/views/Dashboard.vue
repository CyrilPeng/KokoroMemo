<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NCard, NGrid, NGridItem, NTag, NSpin, NSpace, NButton } from 'naive-ui'
import { apiFetch, getServerUrl } from '../api'

const health = ref<any>(null)
const loading = ref(true)
const serverUrl = ref(getServerUrl())

async function fetchHealth() {
  loading.value = true
  try {
    serverUrl.value = getServerUrl()
    const resp = await apiFetch('/health')
    health.value = await resp.json()
  } catch (e) {
    health.value = null
  }
  loading.value = false
}

onMounted(fetchHealth)
</script>

<template>
  <div>
    <div style="margin-bottom: 28px;">
      <h1 style="font-size: 24px; font-weight: 600; color: #e4e4e7; margin-bottom: 4px;">仪表盘</h1>
      <p style="color: #71717a; font-size: 14px;">KokoroMemo 服务状态概览</p>
    </div>

    <NSpin :show="loading">
      <div v-if="health">
        <NGrid :cols="3" :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
          <NGridItem span="3 m:1">
            <NCard style="background: #18181b; border: 1px solid #27272a;">
              <div style="display: flex; align-items: center; justify-content: space-between;">
                <div>
                  <div style="color: #71717a; font-size: 13px; margin-bottom: 8px;">服务状态</div>
                  <NTag :type="health.status === 'ok' ? 'success' : 'error'" size="medium" round>
                    {{ health.status === 'ok' ? '● 运行中' : '● 异常' }}
                  </NTag>
                </div>
                <NButton size="small" quaternary @click="fetchHealth" style="color: #71717a;">
                  刷新
                </NButton>
              </div>
              <div style="margin-top: 12px; font-size: 13px; color: #52525b;">
                监听端口: {{ health.server_port || 14514 }}
              </div>
            </NCard>
          </NGridItem>

          <NGridItem span="3 m:1">
            <NCard style="background: #18181b; border: 1px solid #27272a;">
              <div style="color: #71717a; font-size: 13px; margin-bottom: 8px;">Embedding 模型</div>
              <div style="font-size: 15px; font-weight: 500; color: #e4e4e7; margin-bottom: 8px;">
                {{ health.embedding?.model || '未配置' }}
              </div>
              <NSpace>
                <NTag :type="health.embedding?.enabled ? 'success' : 'warning'" size="small" round>
                  {{ health.embedding?.enabled ? '已启用' : '未启用' }}
                </NTag>
                <span style="color: #52525b; font-size: 12px;">
                  维度: {{ health.embedding?.dimension || '-' }}
                </span>
              </NSpace>
            </NCard>
          </NGridItem>

          <NGridItem span="3 m:1">
            <NCard style="background: #18181b; border: 1px solid #27272a;">
              <div style="color: #71717a; font-size: 13px; margin-bottom: 8px;">Rerank 模型</div>
              <div style="font-size: 15px; font-weight: 500; color: #e4e4e7; margin-bottom: 8px;">
                {{ health.rerank?.model || '未配置' }}
              </div>
              <NTag :type="health.rerank?.enabled ? 'success' : 'info'" size="small" round>
                {{ health.rerank?.enabled ? '已启用' : '未启用' }}
              </NTag>
            </NCard>
          </NGridItem>
        </NGrid>

        <NCard style="background: #18181b; border: 1px solid #27272a; margin-top: 16px;">
          <div style="color: #71717a; font-size: 13px; margin-bottom: 8px;">LLM 配置</div>
          <div style="font-size: 15px; font-weight: 500; color: #e4e4e7;">
            {{ health.llm?.model || '未配置' }}
          </div>
        </NCard>
      </div>

      <NCard v-else style="background: #18181b; border: 1px solid #27272a;">
        <div style="text-align: center; padding: 40px 0;">
          <div style="font-size: 40px; margin-bottom: 16px;">⚠️</div>
          <div style="font-size: 16px; color: #e4e4e7; margin-bottom: 8px;">无法连接到后端服务</div>
          <div style="color: #71717a; font-size: 14px;">请确保后端服务已启动在 {{ serverUrl }}</div>
          <NButton style="margin-top: 16px;" type="primary" @click="fetchHealth">重试连接</NButton>
        </div>
      </NCard>
    </NSpin>
  </div>
</template>
