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
        <label>模型</label>
        <select v-if="currentProvider?.models?.length" v-model="store.llm.model">
          <option v-for="m in currentProvider.models" :key="m" :value="m">{{ m }}</option>
        </select>
        <input v-else v-model="store.llm.model" type="text" placeholder="模型名称，如 gpt-4o-mini" />
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
    <div style="margin-top: 10px; display: flex; align-items: center; gap: 10px">
      <button class="ghost" :disabled="store.llm.testState === 'testing'" @click="test">
        {{ store.llm.testState === 'testing' ? '测试中…' : '测试连接' }}
      </button>
      <span v-if="store.llm.testState === 'ok'" class="badge ok">✓ 连接成功</span>
      <span v-else-if="store.llm.testState === 'fail'" class="badge err">{{ store.llm.testMsg }}</span>
      <span class="small muted">Key 仅保存在浏览器与后端内存，不会写入磁盘</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { store } from '../store'
import { testLLM } from '../api'

const currentProvider = computed(() =>
  store.providers.find((p) => p.id === store.llm.provider)
)

function onProviderChange() {
  const p = currentProvider.value
  if (!p) return
  store.llm.base_url = p.base_url
  store.llm.model = p.models?.length ? p.models[0] : ''
  store.llm.testState = 'idle'
  store.llm.testMsg = ''
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
  } catch (e) {
    store.llm.testState = 'fail'
    store.llm.testMsg = e.message || String(e)
  }
}
</script>
