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

    <div class="card">
      <h2>④ 历史分析记录</h2>
      <div class="small muted" style="margin-bottom: 10px">
        点击可重新打开以往的分析运行；标注 ⚠ 缓存 的为仓库内置演示数据。
      </div>
      <div v-if="!historyLoaded" class="empty">加载中…</div>
      <div v-else-if="!historyRuns.length" class="empty">暂无历史记录</div>
      <div v-else>
        <div v-for="r in historyRuns" :key="r.run_id" class="run-item" @click="openRun(r)">
          <strong>{{ r.app_name || '分析运行' }}</strong>
          <span class="muted small">#{{ r.run_id }}</span>
          <span class="badge" :class="statusClass(r.status)">{{ statusText(r.status) }}</span>
          <span v-if="r.cache" class="badge warn">⚠ 缓存</span>
          <span v-if="r.model" class="small muted">｜{{ r.provider }} / {{ r.model }}</span>
          <span class="small muted" style="margin-left: auto">{{ fmtTime(r.created_at) }}</span>
          <button
            v-if="!r.cache"
            class="del-btn"
            title="删除该历史记录"
            @click.stop="delRun(r)"
          >删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { store } from '../store'
import { createRun, deleteRun, listRuns } from '../api'
import ProviderPanel from '../components/ProviderPanel.vue'

const url = ref('https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684')
const historyRuns = ref([])
const historyLoaded = ref(false)

onMounted(async () => {
  try {
    const data = await listRuns()
    historyRuns.value = (data.runs || []).sort((a, b) =>
      (b.created_at || '').localeCompare(a.created_at || '')
    )
  } catch {
    /* ignore */
  }
  historyLoaded.value = true
})

function openRun(r) {
  store.currentRun = r
  store.activeTab = 'progress'
  store.tcTrace = null
}

async function delRun(r) {
  const name = r.app_name || r.run_id
  if (!window.confirm(`确定删除「${name}」的历史记录吗？产物文件将一并清除。`)) return
  try {
    await deleteRun(r.run_id)
    historyRuns.value = historyRuns.value.filter((x) => x.run_id !== r.run_id)
    if (store.currentRun?.run_id === r.run_id) store.currentRun = null
  } catch (e) {
    alert(e.message || String(e))
  }
}

function statusText(s) {
  return { pending: '待执行', running: '执行中', succeeded: '已完成', degraded: '部分降级', failed: '失败' }[s] || s || '—'
}
function statusClass(s) {
  return { pending: 'badge info', running: 'badge info', succeeded: 'badge ok', degraded: 'badge warn', failed: 'badge err' }[s] || 'badge info'
}
function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
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
.run-item {
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
.run-item:hover {
  border-color: var(--accent);
}
.del-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--muted);
  border-radius: 6px;
  padding: 2px 10px;
  font-size: 12px;
  cursor: pointer;
}
.del-btn:hover {
  color: var(--red);
  border-color: var(--red);
}
</style>
