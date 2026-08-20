<template>
  <div class="card">
    <h2>阶段详情与修订记录</h2>
    <div v-for="s in stages" :key="s.stage" style="margin-bottom: 14px">
      <div style="display: flex; align-items: center; gap: 8px">
        <strong>{{ s.label || s.stage }}</strong>
        <span class="badge" :class="badgeClass(s.status)">{{ stateText(s.status) }}</span>
        <span class="small muted" v-if="s.finished_at">耗时 {{ duration(s) }}s</span>
      </div>
      <div v-if="s.progress > 0 || s.status === 'running'" class="detail-progress">
        <div class="bar-fill" :style="{ width: (s.progress || 0) + '%' }"></div>
        <span class="small muted">{{ s.progress || 0 }}%</span>
      </div>
      <div v-if="s.message" class="small" style="margin-top: 4px; color: var(--accent)">
        {{ s.message }}
      </div>
      <div v-if="s.error" class="error-box">{{ s.error }}</div>
      <div v-if="s.revisions?.length" class="small" style="margin-top: 4px">
        <span class="badge warn">修订</span>
        <ul style="margin: 4px 0 0; padding-left: 18px; color: var(--amber)">
          <li v-for="(r, i) in s.revisions" :key="i">{{ r }}</li>
        </ul>
      </div>
      <pre v-if="summaryText(s)" class="summary">{{ summaryText(s) }}</pre>
    </div>
  </div>
</template>

<script setup>
defineProps({ stages: { type: Array, default: () => [] } })

function stateText(s) {
  return { pending: '待执行', running: '执行中', succeeded: '完成', failed: '失败', degraded: '降级', revised: '修订' }[s] || s
}
function badgeClass(s) {
  return { succeeded: 'badge ok', failed: 'badge err', degraded: 'badge warn', running: 'badge info', revised: 'badge warn' }[s] || 'badge info'
}
function duration(s) {
  if (!s.started_at || !s.finished_at) return '—'
  const d = (new Date(s.finished_at) - new Date(s.started_at)) / 1000
  return d.toFixed(1)
}
function summaryText(s) {
  if (!s.summary || !Object.keys(s.summary).length) return ''
  return JSON.stringify(s.summary, null, 2)
}
</script>

<style scoped>
.detail-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.detail-progress .bar-fill {
  flex: 1;
  height: 4px;
  border-radius: 999px;
  background: var(--accent);
  border: 1px solid var(--border);
  transition: width 0.3s ease;
}
.summary {
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  font-size: 11px;
  max-height: 220px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
