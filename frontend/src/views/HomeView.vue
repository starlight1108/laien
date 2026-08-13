<template>
  <div>
    <div class="card">
      <h2>① 应用链接</h2>
      <input
        v-model="url"
        type="text"
        placeholder="https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"
      />
      <div class="row" style="margin-top: 14px">
        <div>
          <label>数据来源</label>
          <select v-model="source">
            <option value="url">在线采集（Apple 官方 RSS Feed）</option>
            <option value="import">导入评论数据（JSON / CSV）</option>
          </select>
        </div>
        <div v-if="source === 'import'">
          <label>选择文件（.json / .csv，UTF-8）</label>
          <input type="file" accept=".json,.csv,.txt" @change="onFile" />
          <div v-if="importText" class="small muted" style="margin-top: 4px">
            ✓ 已读取 {{ importPreview }} 字符
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>② 分析目标 / 约束</h2>
      <textarea v-model="goal" rows="2" placeholder="例如：聚焦订阅转化；或：只看低分评论；或：关注 8.x 版本的用户反馈"></textarea>
      <div style="margin-top: 8px">
        <span
          v-for="g in goalPresets"
          :key="g"
          class="tag"
          :class="{ active: goal === g }"
          @click="toggleGoal(g)"
        >{{ g }}</span>
      </div>
    </div>

    <div class="card">
      <h2>③ 模型（模型驱动语义分析）</h2>
      <ProviderPanel />
    </div>

    <div style="display: flex; align-items: center; gap: 12px">
      <button class="primary" :disabled="starting || !canStart" @click="start">
        {{ starting ? '正在启动…' : '开始' }}
      </button>
      <span v-if="error" class="error-box" style="margin: 0; flex: 1">{{ error }}</span>
    </div>

    <div v-if="cacheRuns.length" class="card">
      <h2>④ 离线缓存示例（无网 / 无 Key 评审）</h2>
      <div class="small muted" style="margin-bottom: 10px">
        以下为仓库内置缓存运行：评论数据真实采集自 Apple RSS Feed，语义产物为演示用途，不替代联网+Key 的实时分析。
      </div>
      <div v-for="r in cacheRuns" :key="r.run_id" class="cache-run" @click="openCache(r)">
        <strong>{{ r.app_name || '缓存示例' }}</strong>
        <span class="muted small">#{{ r.run_id }}</span>
        <span class="badge warn">⚠ 缓存</span>
        <div class="small muted">{{ r.cache_note }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { store } from '../store'
import { createRun, listRuns } from '../api'
import ProviderPanel from '../components/ProviderPanel.vue'

const url = ref('https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684')
const cacheRuns = ref([])

onMounted(async () => {
  try {
    const data = await listRuns()
    cacheRuns.value = (data.runs || []).filter((r) => r.cache)
  } catch {
    /* ignore */
  }
})

function openCache(r) {
  store.currentRun = r
  store.activeTab = 'progress'
}
const goal = ref('')
const source = ref('url')
const importText = ref('')
const starting = ref(false)
const error = ref('')

const goalPresets = ['订阅转化', '可用性', '低分评论', '特定版本']

function toggleGoal(g) {
  goal.value = goal.value === g ? '' : g
}

function onFile(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    importText.value = reader.result || ''
  }
  reader.readAsText(file, 'utf-8')
}

const importPreview = computed(() => String(importText.value || '').length)


const canStart = computed(() => {
  if (source.value === 'import') return !!importText.value
  return !!url.value
})

async function start() {
  starting.value = true
  error.value = ''
  try {
    const payload = {
      url: source.value === 'url' ? url.value : null,
      goal: goal.value,
      provider: store.llm.provider,
      model: store.llm.model,
      base_url: store.llm.base_url,
      api_key: store.llm.api_key,
      import_text: source.value === 'import' ? importText.value : null
    }
    const meta = await createRun(payload)
    store.currentRun = meta
    store.activeTab = 'progress'
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    starting.value = false
  }
}
</script>

<style scoped>
.cache-run {
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cache-run:hover {
  border-color: var(--amber);
}
</style>
