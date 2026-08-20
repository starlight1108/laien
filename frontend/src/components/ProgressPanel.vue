<template>
  <div class="card">
    <div class="progress-header">
      <h2>工作流进度（8 个执行阶段 + UI 展示）</h2>
      <span class="small muted">{{ overallText }}</span>
    </div>

    <!-- 整体进度条 -->
    <div class="overall-bar">
      <div class="bar-fill" :style="{ width: overallPercent + '%' }"></div>
    </div>

    <div class="steps">
      <div
        v-for="s in stages"
        :key="s.stage"
        class="step"
        :class="s.status"
        :title="s.error || ''"
      >
        <span class="dot"></span>
        <div class="step-main">
          <div class="step-head">
            <span class="label">{{ s.label || s.stage }}</span>
            <span class="state">{{ stateText(s.status) }}</span>
          </div>

          <!-- 阶段内细进度条（running 或已有进度时显示） -->
          <div v-if="s.status === 'running' || s.progress > 0" class="mini-bar">
            <div class="bar-fill" :style="{ width: (s.progress || 0) + '%' }"></div>
          </div>

          <!-- 当前子步骤描述 -->
          <div v-if="s.message" class="message">{{ s.message }}</div>

          <!-- 子步骤清单（如 analyze 的批次进度） -->
          <div v-if="s.substeps?.length" class="substeps">
            <span
              v-for="(sub, i) in s.substeps"
              :key="i"
              class="substep"
              :class="sub.status"
            >
              <span class="sub-dot"></span>{{ sub.label }}
            </span>
          </div>

          <div class="meta small muted">
            <span v-if="s.started_at">开始 {{ time(s.started_at) }}</span>
            <span v-if="s.status === 'running'">已运行 {{ runningSec(s) }}s</span>
            <span v-else-if="s.finished_at">耗时 {{ duration(s) }}s</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({ stages: { type: Array, default: () => [] } })

// 每秒 tick，驱动 running 阶段的实时耗时
const now = ref(Date.now())
let timer = null
onMounted(() => {
  timer = setInterval(() => { now.value = Date.now() }, 1000)
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})

const TERMINAL = new Set(['succeeded', 'failed', 'degraded', 'revised', 'skipped'])

const total = computed(() => props.stages.length)
const completedCount = computed(() =>
  props.stages.filter((s) => TERMINAL.has(s.status)).length
)
const current = computed(() => props.stages.find((s) => s.status === 'running'))

const overallPercent = computed(() => {
  if (!total.value) return 0
  const cur = current.value?.progress || 0
  return Math.round(((completedCount.value + cur / 100) / total.value) * 100)
})

const overallText = computed(() => {
  const cur = current.value
  if (cur) {
    return `已完成 ${completedCount.value}/${total.value} · 当前：${cur.label || cur.stage}（${cur.progress || 0}%）`
  }
  return `已完成 ${completedCount.value}/${total.value}`
})

function stateText(s) {
  return {
    pending: '待执行',
    running: '执行中',
    succeeded: '✓',
    failed: '✗ 失败',
    degraded: '⚠ 降级',
    revised: '↻ 修订',
    skipped: '跳过'
  }[s] || s
}

function time(iso) {
  try {
    return new Date(iso).toLocaleTimeString()
  } catch {
    return ''
  }
}

function runningSec(s) {
  if (!s.started_at) return 0
  return Math.max(0, Math.floor((now.value - new Date(s.started_at).getTime()) / 1000))
}

function duration(s) {
  if (!s.started_at || !s.finished_at) return '—'
  const d = (new Date(s.finished_at) - new Date(s.started_at)) / 1000
  return d.toFixed(1)
}
</script>

<style scoped>
.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

/* 整体进度条 */
.overall-bar {
  height: 8px;
  border-radius: 999px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  overflow: hidden;
  margin: 10px 0 16px;
}
.overall-bar .bar-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--accent), var(--purple));
  transition: width 0.4s ease;
}

.steps {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
}

.step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
}

.step.running {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}

.step .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border);
  flex-shrink: 0;
  margin-top: 4px;
}

.step.running .dot { background: var(--accent); animation: pulse 1s infinite; }
.step.succeeded .dot { background: var(--green); }
.step.failed .dot { background: var(--red); }
.step.degraded .dot { background: var(--amber); }
.step.revised .dot { background: var(--purple); }

.step-main { flex: 1; min-width: 0; }

.step-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.step .state { margin-left: auto; color: var(--muted); font-size: 11px; flex-shrink: 0; }
.step.running .state { color: var(--accent); }
.step.failed .state { color: var(--red); }
.step.degraded .state { color: var(--amber); }

/* 阶段内细进度条 */
.mini-bar {
  height: 4px;
  border-radius: 999px;
  background: var(--panel);
  border: 1px solid var(--border);
  overflow: hidden;
  margin-top: 6px;
}
.mini-bar .bar-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--accent);
  transition: width 0.3s ease;
}
.step.succeeded .mini-bar .bar-fill { background: var(--green); }
.step.failed .mini-bar .bar-fill { background: var(--red); }
.step.degraded .mini-bar .bar-fill { background: var(--amber); }

.message {
  margin-top: 4px;
  font-size: 12px;
  color: var(--accent);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 子步骤清单 */
.substeps {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}
.substep {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid var(--border);
  color: var(--muted);
  background: var(--panel);
}
.substep .sub-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--border);
}
.substep.running { color: var(--accent); border-color: var(--accent); }
.substep.running .sub-dot { background: var(--accent); animation: pulse 1s infinite; }
.substep.succeeded { color: var(--green); border-color: var(--green); }
.substep.succeeded .sub-dot { background: var(--green); }
.substep.failed { color: var(--red); border-color: var(--red); }
.substep.failed .sub-dot { background: var(--red); }

.meta {
  margin-top: 4px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
