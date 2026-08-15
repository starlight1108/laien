<template>
  <div class="app">
    <header>
      <h1>App Review Insights</h1>
      <nav>
        <button v-if="store.currentRun" @click="goHome">＋ 新建分析</button>
      </nav>
    </header>
    <main>
      <HomeView v-if="!store.currentRun" />
      <RunView v-else />
    </main>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { store, loadLlmConfig } from './store'
import { getProviders } from './api'
import HomeView from './views/HomeView.vue'
import RunView from './views/RunView.vue'

onMounted(async () => {
  // 恢复持久化的模型配置（provider/base_url/model/api_key）
  const saved = loadLlmConfig()
  try {
    const data = await getProviders()
    store.providers = data.providers || []
    syncLlmDefaults(saved)
  } catch {
    // 后端不可用时也应用已保存的本地配置
    if (saved?.provider) store.llm.provider = saved.provider
    if (saved?.base_url) store.llm.base_url = saved.base_url
    if (saved?.model) store.llm.model = saved.model
    if (saved?.api_key) store.llm.api_key = saved.api_key
  }
})

function syncLlmDefaults(saved) {
  // 优先使用持久化的配置；未保存的字段才带出提供商默认值
  const p = store.providers.find((x) => x.id === (saved?.provider || store.llm.provider))
  if (saved?.provider && p) store.llm.provider = p.id
  store.llm.base_url = saved?.base_url || p?.base_url || store.llm.base_url || ''
  store.llm.model = saved?.model || ''
  store.llm.api_key = saved?.api_key || ''
  store.llm.models = []
  store.llm.modelsState = 'idle'
}

function goHome() {
  store.currentRun = null
  store.activeTab = 'progress'
  store.tcTrace = null
}
</script>
