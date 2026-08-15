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
        <label>模型（共 {{ modelOptions.length }} 个可选）</label>
        <select v-model="selectValue">
          <option value="">选择模型…</option>
          <option v-for="m in modelOptions" :key="m" :value="m">{{ m }}</option>
          <option value="__custom__">✏️ 自定义（手动输入）</option>
        </select>
        <input
          v-if="selectValue === '__custom__'"
          v-model="store.llm.model"
          type="text"
          placeholder="输入自定义模型名"
          style="margin-top: 6px"
        />
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
          placeholder="填写 API Key（自动保存到服务器本地）"
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
      <span class="small muted">Key 已保存到服务器本地 data/llm_config.json（已 gitignore），仅本机可见；请勿在公共/共享设备上使用</span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { store, savedFor } from '../store'
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
  if (store.llm.modelsState === 'ok') return `已从提供商拉取 ${store.llm.models.length} 个模型，下拉可查看完整列表`
  if (store.llm.modelsState === 'fail') return '自动拉取失败，可下拉选择或选「自定义」手动输入模型名'
  if (currentProvider.value?.requires_key === false)
    return '本地模型：无需 Key，可直接获取模型'
  return '填写 API Key 后点击「获取模型」拉取可用模型'
})

// 自定义模式为独立 UI 状态：选中「自定义」后保持输入框显示，不受 model 值影响
const customMode = ref(false)

// 模型下拉的选中态：当前模型在列表内则选中该项；自定义模式或模型不在列表内则归入「自定义」
const selectValue = computed({
  get() {
    const m = store.llm.model
    if (customMode.value || (m && !modelOptions.value.includes(m))) return '__custom__'
    if (m) return m
    return ''
  },
  set(v) {
    customMode.value = v === '__custom__'
    store.llm.model = v === '__custom__' ? '' : v
  }
})

function onProviderChange() {
  const p = currentProvider.value
  if (!p) return
  // 载入该提供商已保存的配置：base_url 优先已保存值，其次提供商默认值；
  // 不带入上一家提供商的 Key / 中转地址（各提供商独立持久化）
  const saved = savedFor(p.id)
  store.llm.base_url = saved?.base_url || p.base_url || ''
  store.llm.model = saved?.model || ''
  store.llm.api_key = saved?.api_key || ''
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
