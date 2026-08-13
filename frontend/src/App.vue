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
import { store } from './store'
import { getProviders } from './api'
import HomeView from './views/HomeView.vue'
import RunView from './views/RunView.vue'

onMounted(async () => {
  try {
    const data = await getProviders()
    store.providers = data.providers || []
    syncLlmDefaults()
  } catch {
    /* 后端不可用时忽略 */
  }
})

function syncLlmDefaults() {
  const p = store.providers.find((x) => x.id === store.llm.provider)
  if (p) {
    store.llm.base_url = p.base_url
    if (!store.llm.model && p.models?.length) store.llm.model = p.models[0]
  }
}

function goHome() {
  store.currentRun = null
  store.activeTab = 'progress'
}
</script>
