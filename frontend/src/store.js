import { reactive, watch } from 'vue'

// 模型配置持久化键（provider/base_url/model/api_key；用户明确要求 Key 一并保存）
const LLM_CONFIG_KEY = 'app-review-insights:llm-config'

export function loadLlmConfig() {
  try {
    const raw = localStorage.getItem(LLM_CONFIG_KEY)
    if (!raw) return null
    const d = JSON.parse(raw)
    return {
      provider: typeof d.provider === 'string' ? d.provider : null,
      base_url: typeof d.base_url === 'string' ? d.base_url : null,
      model: typeof d.model === 'string' ? d.model : null,
      api_key: typeof d.api_key === 'string' ? d.api_key : null
    }
  } catch {
    return null
  }
}

export const store = reactive({
  providers: [],
  currentRun: null, // RunMeta
  activeTab: 'progress',
  // 测试用例追溯：从「测试用例」页点击「查看关联评论」时记录选中的用例快照
  tcTrace: null, // 测试用例对象（含 id / requirement_id / review_ids）
  llm: {
    provider: 'openai',
    base_url: '',
    model: '',
    api_key: '',
    models: [], // 从提供商拉取的模型列表
    modelsState: 'idle', // idle | loading | ok | fail
    modelsMsg: '',
    testState: 'idle', // idle | testing | ok | fail
    testMsg: ''
  }
})

// 模型配置自动持久化（provider / base_url / model / api_key）
watch(
  () => [store.llm.provider, store.llm.base_url, store.llm.model, store.llm.api_key],
  () => {
    try {
      localStorage.setItem(
        LLM_CONFIG_KEY,
        JSON.stringify({
          provider: store.llm.provider,
          base_url: store.llm.base_url,
          model: store.llm.model,
          api_key: store.llm.api_key
        })
      )
    } catch {
      /* 隐私模式等无法写入时忽略 */
    }
  }
)
