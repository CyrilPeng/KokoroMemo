import { ref, type Ref } from 'vue'
import type { useMessage } from 'naive-ui'
import { apiFetch } from '../api'

export function useModelFetching(
  config: Ref<any>,
  message: ReturnType<typeof useMessage>,
  t: (key: string, params?: Record<string, any>) => string,
) {
  const llmModels = ref<{label: string, value: string}[]>([])
  const embeddingModels = ref<{label: string, value: string}[]>([])
  const rerankModels = ref<{label: string, value: string}[]>([])
  const judgeModels = ref<{label: string, value: string}[]>([])
  const stateFillerModels = ref<{label: string, value: string}[]>([])
  const fetchingLlm = ref(false)
  const fetchingEmbedding = ref(false)
  const fetchingRerank = ref(false)
  const fetchingJudge = ref(false)
  const fetchingStateFiller = ref(false)

  async function fetchModelList(baseUrl: string, apiKey: string, target: 'llm' | 'embedding' | 'rerank' | 'judge' | 'state_filler') {
    if (!baseUrl) {
      message.warning(t('settings.inputBaseUrl'))
      return
    }
    if (!apiKey) {
      message.warning(t('settings.inputApiKey'))
      return
    }
    const flagRef = target === 'llm' ? fetchingLlm : target === 'embedding' ? fetchingEmbedding : target === 'rerank' ? fetchingRerank : target === 'judge' ? fetchingJudge : fetchingStateFiller
    flagRef.value = true
    const provider = target === 'llm' ? config.value.llm_provider : undefined
    try {
      const resp = await apiFetch('/admin/fetch-models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ base_url: baseUrl, api_key: apiKey, provider }),
      })
      const data = await resp.json()
      if (data.status === 'ok' && data.models.length > 0) {
        const options = data.models.map((m: string) => ({ label: m, value: m }))
        if (target === 'llm') llmModels.value = options
        else if (target === 'embedding') embeddingModels.value = options
        else if (target === 'rerank') rerankModels.value = options
        else if (target === 'judge') judgeModels.value = options
        else stateFillerModels.value = options
        message.success(t('settings.fetchModelsSuccess', { count: data.models.length }))
      } else {
        message.error(data.message || t('settings.fetchModelsEmpty'))
      }
    } catch (e) {
      message.error(t('settings.fetchModelsFailed'))
    }
    flagRef.value = false
  }

  return {
    llmModels,
    embeddingModels,
    rerankModels,
    judgeModels,
    stateFillerModels,
    fetchingLlm,
    fetchingEmbedding,
    fetchingRerank,
    fetchingJudge,
    fetchingStateFiller,
    fetchModelList,
  }
}
