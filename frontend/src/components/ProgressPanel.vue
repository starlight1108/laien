<template>
  <div class="card">
    <h2>工作流进度（10 阶段）</h2>
    <div class="steps">
      <div
        v-for="s in stages"
        :key="s.stage"
        class="step"
        :class="s.status"
        :title="s.error || ''"
      >
        <span class="dot"></span>
        <span class="label">{{ s.label || s.stage }}</span>
        <span class="state">{{ stateText(s.status) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({ stages: { type: Array, default: () => [] } })

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
</script>

<style scoped>
.steps {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.step {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
}

.step .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border);
  flex-shrink: 0;
}

.step.running .dot { background: var(--accent); animation: pulse 1s infinite; }
.step.succeeded .dot { background: var(--green); }
.step.failed .dot { background: var(--red); }
.step.degraded .dot { background: var(--amber); }
.step.revised .dot { background: var(--purple); }

.step .state { margin-left: auto; color: var(--muted); font-size: 11px; }
.step.running .state { color: var(--accent); }
.step.failed .state { color: var(--red); }
.step.degraded .state { color: var(--amber); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
