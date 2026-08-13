<template>
  <div>
    <div class="row">
      <div>
        <label>提供商</label>
        <select v-model="store.llm.provider" @change="onProviderChange">
          <option v-for="p in store.providers" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </div>
      <div>
        <label>Base URL</label>
        <input v-model="store.llm.base_url" type="text" placeholder="https://api.openai.com/v1" />
      </div>
    </div>
    <div class="row" style="margin-top: 10px">
      <div>
        <label>模型（填入 Key 后点击「获取模型」拉取）</label>
        <input
          v-model="store.llm.model"
          type="text"
          list="model-options"
          placeholder="选择或输入模型名"
        />
        <datalist id="model-options">
          <option v-for="m in modelOptions" :key="m" :value="m" />
        </datalist>
        <div class="small muted" style="margin-top: 4px">
          {{ modelHint }}
        </div>
      </div>
      <div>
        <label>API Key {{ currentProvider?.requires_key ? '' : '（本地模型可留空）' }}</label>
        <input
          v-model="store.llm.api_key"
          type="password"
          autocomplete="off"
          placeholder="仅用于本次运行，不落盘"
        />
      </div>
    </div>
    <div style="margin-top: 10px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap">
      <button class="ghost" :disabled="store.llm.modelsState === 'loading'" @click="fetchModels">
        {{ store.llm.modelsState === 'loading' ? '获取中…' : '获取模型' }}
      </button>
      <button class="ghost" :disabled="store.llm.testState === 'testing'" @click="test">
        {{ store.llm.testState === 'testing' ? '测试中…' : '测试连接' }}
      </button>
      <span v-if="store.llm.modelsState === 'ok'" class="badge ok">✓ 已拉取 {{ store.llm.models.length }} 个模型</span>
      <span v-else-if="store.llm.modelsState === 'fail'" class="badge err">{{ store.llm.modelsMsg }}</span>
      <span v-if="store.llm.testState === 'ok'" class="badge ok">✓ 连接成功</span>
      <span v-else-if="store.llm.testState === 'fail'" class="badge err">{{ store.llm.testMsg }}</span>
      <span class="small muted">Key 仅保存在浏览器与后端内存，不会写入磁盘</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { store } from '../store'
import { testLLM, fetchModels as fetchModelsApi } from '../api'

const currentProvider = computed(() =>
  store.providers.find((p) => p.id === store.llm.provider)
)

// 优先使用拉取到的模型，否则用预置模型作建议
const modelOptions = computed(() => {
  const fetched = store.llm.models
  if (fetched?.length) return fetched
  return currentProvider.value?.models || []
})

const modelHint = computed(() => {
  if (store.llm.modelsState === 'ok') return '已从提供商拉取模型列表'
  if (store.llm.modelsState === 'fail') return '自动拉取失败，可手动输入模型名'
  if (currentProvider.value?.requires_key === false)
    return '本地模型：无需 Key，可直接获取模型'
  return '填写 API Key 后点击「获取模型」拉取可用模型'
})

function onProviderChange() {
  const p = currentProvider.value
  if (!p) return
  store.llm.base_url = p.base_url
  store.llm.model = ''
  store.llm.models = []
  store.llm.modelsState = 'idle'
  store.llm.modelsMsg = ''
  store.llm.testState = 'idle'
  store.llm.testMsg = ''
}

async function fetchModels() {
  store.llm.modelsState = 'loading'
  store.llm.modelsMsg = ''
  try {
    const data = await fetchModelsApi({
      provider: store.llm.provider,
      base_url: store.llm.base_url,
      api_key: store.llm.api_key
    })
    store.llm.models = data.models || []
    if (data.source === 'fallback') {
      store.llm.modelsState = 'fail'
      store.llm.modelsMsg = `拉取失败（${data.error || '未知错误'}），已显示预置模型，可手动输入`
    } else {
      store.llm.modelsState = 'ok'
      if (!store.llm.model && store.llm.models.length) {
        store.llm.model = store.llm.models[0]
      }
    }
  } catch (e) {
    store.llm.modelsState = 'fail'
    store.llm.modelsMsg = e.message || String(e)
  }
}

async function test() {
  store.llm.testState = 'testing'
  store.llm.testMsg = ''
  try {
    await testLLM({
      provider: store.llm.provider,
      base_url: store.llm.base_url,
      model: store.llm.model,
      api_key: store.llm.api_key
    })
    store.llm.testState = 'ok'
    // 连接成功后自动拉取模型列表
    if (store.llm.modelsState !== 'ok') {
      await fetchModels()
    }
  } catch (e) {
    store.llm.testState = 'fail'
    store.llm.testMsg = e.message || String(e)
  }
}
</script>
