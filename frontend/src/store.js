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
    testState: 'idle', // idle | testing | ok | fail
    testMsg: ''
  }
})
