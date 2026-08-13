<template>
  <div class="card">
    <h2>重大发现（区分确定性统计 / 模型结论）</h2>
    <div v-if="!loaded" class="empty">加载中…</div>
    <div v-else-if="!findings?.length" class="empty">暂无发现（需要模型阶段或统计数据）</div>
    <template v-else>
      <div class="legend">
        <span class="badge ok">📊 确定性统计</span> —— 代码计算，精确可复现
        <span class="badge info" style="margin-left: 14px">🤖 模型结论</span> —— LLM 基于证据推断，已复核
      </div>
      <div class="finding" v-for="f in findings" :key="f.id">
        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap">
          <strong>{{ f.id }} · {{ f.title }}</strong>
          <span class="badge" :class="f.kind === 'deterministic_stat' ? 'badge ok' : 'badge info'">
            {{ f.kind === 'deterministic_stat' ? '📊 统计' : '🤖 模型' }}
          </span>
          <span class="badge" :class="confidenceClass(f.confidence)">置信度 {{ confidenceText(f.confidence) }}</span>
          <span v-if="f.assumption" class="badge warn">假设</span>
        </div>
        <p class="small">{{ f.summary }}</p>
        <div class="meta">
          <span>支持样本：<strong>{{ f.supporting_count }}</strong></span>
          <span v-if="f.conflicting_review_ids?.length" class="warn-text">
            冲突证据：{{ f.conflicting_review_ids.length }} 条
          </span>
          <span v-if="f.uncertainty" class="muted">不确定性：{{ f.uncertainty }}</span>
        </div>
        <div class="evidence">
          <button class="ghost small-btn" @click="toggle(f.id)">证据评论（{{ f.evidence_review_ids?.length || 0 }}）</button>
          <div v-if="expanded === f.id" class="ids-box">
            <code>{{ (f.evidence_review_ids || []).join(', ') }}</code>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getArtifact } from '../api'

const props = defineProps({ runId: { type: String, required: true } })
const findings = ref(null)
const loaded = ref(false)
const expanded = ref(null)

onMounted(async () => {
  try {
    findings.value = await getArtifact(props.runId, 'findings')
  } catch {
    findings.value = []
  }
  loaded.value = true
})

function toggle(id) {
  expanded.value = expanded.value === id ? null : id
}
function confidenceText(c) {
  return { high: '高', medium: '中', low: '低' }[c] || c
}
function confidenceClass(c) {
  return { high: 'badge ok', medium: 'badge info', low: 'badge warn' }[c] || 'badge info'
}
</script>

<style scoped>
.legend { margin-bottom: 12px; color: var(--muted); font-size: 12px; }
.finding {
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 10px;
}
.finding p { margin: 6px 0; }
.meta { display: flex; gap: 16px; font-size: 12px; color: var(--muted); flex-wrap: wrap; }
.warn-text { color: var(--amber); }
.small-btn { padding: 3px 10px; font-size: 12px; }
.evidence { margin-top: 6px; }
.ids-box {
  background: #0b1220;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 10px;
  margin-top: 6px;
  font-size: 11px;
  color: var(--accent);
  word-break: break-all;
}
</style>
