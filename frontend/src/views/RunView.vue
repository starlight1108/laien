<template>
  <div>
    <div v-if="meta?.cache" class="card" style="border-color: rgba(251,191,36,.4)">
      ⚠️ <strong>缓存演示数据</strong>
      <span class="muted small">（{{ meta.cache_note || '离线样例' }}，非实时采集结果）</span>
    </div>

    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px">
        <div>
          <strong style="font-size: 16px">{{ meta?.app_name || '分析运行' }}</strong>
          <span class="muted small"> #{{ runId }}</span>
          <div class="small muted" style="margin-top: 2px">
            目标：{{ meta?.goal || '（默认：整体用户问题）' }}
            <span v-if="meta?.model">｜模型：{{ meta?.provider }} / {{ meta?.model }}</span>
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: 8px">
          <span class="badge" :class="statusClass">{{ statusText }}</span>
          <button
            v-if="canPause"
            class="ghost"
            @click="onPause"
            title="暂停后将在下一个步骤挂起，可随时继续"
          >⏸ 暂停</button>
          <button
            v-else-if="canResume"
            class="ghost"
            @click="onResume"
          >▶ 继续</button>
        </div>
      </div>
    </div>

    <ProgressPanel :stages="meta?.stages || []" @retry="onRetry" />

    <div class="tabs">
      <button
        v-for="t in tabs"
        :key="t.id"
        :class="{ active: activeTab === t.id }"
        @click="switchTab(t.id)"
      >{{ t.label }}</button>
    </div>

    <StageDetail v-if="activeTab === 'progress'" :stages="meta?.stages || []" />
    <ReviewsPanel v-else-if="activeTab === 'reviews'" :run-id="runId" artifact="raw_reviews" title="原始评论" />
    <ReviewsPanel v-else-if="activeTab === 'cleaned'" :run-id="runId" artifact="cleaned_reviews" title="清洗·去重数据" />
    <ThemesPanel v-else-if="activeTab === 'themes'" :run-id="runId" />
    <FindingsPanel v-else-if="activeTab === 'findings'" :run-id="runId" />
    <EvidencePanel v-else-if="activeTab === 'evidence'" :run-id="runId" />
    <PrdPanel v-else-if="activeTab === 'prd'" :run-id="runId" />
    <TestsPanel v-else-if="activeTab === 'tests'" :run-id="runId" />
    <TracePanel v-else-if="activeTab === 'trace'" :run-id="runId" />
    <TcReviewsPanel v-else-if="activeTab === 'tcreviews'" :run-id="runId" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { store } from '../store'
import { getRun, streamRun, pauseRun, resumeRun } from '../api'
import ProgressPanel from '../components/ProgressPanel.vue'
import StageDetail from '../components/StageDetail.vue'
import ReviewsPanel from '../components/ReviewsPanel.vue'
import ThemesPanel from '../components/ThemesPanel.vue'
import FindingsPanel from '../components/FindingsPanel.vue'
import EvidencePanel from '../components/EvidencePanel.vue'
import PrdPanel from '../components/PrdPanel.vue'
import TestsPanel from '../components/TestsPanel.vue'
import TracePanel from '../components/TracePanel.vue'
import TcReviewsPanel from '../components/TcReviewsPanel.vue'

const runId = computed(() => store.currentRun?.run_id)
const meta = ref(store.currentRun)
const activeTab = computed(() => store.activeTab)
let es = null
let timer = null

// 终态集合：进入后停止轮询（SSE 与轮询双通道共享）
const TERMINAL_STATUSES = new Set(['succeeded', 'failed', 'degraded'])

function stopPolling() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

const tabs = [
  { id: 'progress', label: '执行进度' },
  { id: 'reviews', label: '原始评论' },
  { id: 'cleaned', label: '清洗数据' },
  { id: 'themes', label: '主题分类' },
  { id: 'findings', label: '发现' },
  { id: 'evidence', label: '证据报告' },
  { id: 'prd', label: 'PRD' },
  { id: 'tests', label: '测试用例' },
  { id: 'trace', label: '追溯报告' }
]

const statusText = computed(() => {
  const s = meta.value?.status
  return { pending: '待执行', running: '执行中', paused: '已暂停', succeeded: '已完成', degraded: '已完成(部分降级)', failed: '失败' }[s] || s || '—'
})
const statusClass = computed(() => {
  const s = meta.value?.status
  return { pending: 'badge info', running: 'badge info', paused: 'badge warn', succeeded: 'badge ok', degraded: 'badge warn', failed: 'badge err' }[s] || 'badge info'
})

// 暂停/继续：仅实时运行可操作（缓存演示数据已完结，不可暂停）
const canPause = computed(() => meta.value?.status === 'running' && !meta.value?.cache)
const canResume = computed(() => meta.value?.status === 'paused' && !meta.value?.cache)

async function onPause() {
  try {
    await pauseRun(runId.value)
    meta.value.status = 'paused'
  } catch (e) {
    alert(`暂停失败：${e.message}`)
  }
}

async function onResume() {
  try {
    await resumeRun(runId.value)
    meta.value.status = 'running'
  } catch (e) {
    alert(`继续失败：${e.message}`)
  }
}

function switchTab(id) {
  store.activeTab = id
}

function onRetry(stage) {
  // 简化：提示重新创建运行（后端支持断点重跑可后续扩展）
  alert(`阶段「${stage}」失败。当前版本支持重新创建运行，请在顶部点击「新建分析」。`)
}

onMounted(async () => {
  try {
    meta.value = await getRun(runId.value)
  } catch { /* ignore */ }
  if (meta.value?.cache) return // 缓存运行已完结，不启动 SSE/轮询
  es = streamRun(runId.value, (event) => {
    if (event.stage) {
      const list = (meta.value?.stages || []).map((s) =>
        s.stage === event.stage ? { ...s, ...event } : s
      )
      if (meta.value) meta.value.stages = list
    } else if (event.type === 'run_end') {
      meta.value.status = event.status
      stopPolling()
    } else if (event.type === 'run_paused') {
      meta.value.status = 'paused'
    } else if (event.type === 'run_resumed') {
      meta.value.status = 'running'
    }
  })
  // 轮询兜底：SSE 断开时保障状态收敛；进入终态后停止，避免无谓请求
  // 注意：progress/message/substeps 仅走 SSE 不落盘，轮询结果需与内存中的
  // 实时进度合并，否则每 3s 会把阶段内进度清空（只剩落盘的运行时间）。
  timer = setInterval(async () => {
    try {
      const m = await getRun(runId.value)
      const prev = meta.value?.stages || []
      m.stages = (m.stages || []).map((s) => {
        const p = prev.find((x) => x.stage === s.stage)
        if (p && (p.progress > 0 || p.message || p.substeps?.length)) {
          return { ...s, progress: p.progress, message: p.message, substeps: p.substeps }
        }
        return s
      })
      meta.value = m
      if (TERMINAL_STATUSES.has(m?.status)) stopPolling()
    } catch { /* ignore */ }
  }, 3000)
})

onBeforeUnmount(() => {
  es?.close()
  stopPolling()
})
</script>
