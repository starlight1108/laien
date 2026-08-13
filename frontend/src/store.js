import { reactive } from 'vue'

export const store = reactive({
  providers: [],
  currentRun: null, // RunMeta
  activeTab: 'progress',
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
