<template>
  <div class="card">
    <h2>可追溯性验证报告</h2>
    <div v-if="!loaded" class="empty">加载中…</div>
    <template v-else-if="report">
      <div class="summary-line">
        <span class="badge ok">通过 {{ report.summary?.ok || 0 }}</span>
        <span class="badge err">问题 {{ report.summary?.issues || 0 }}</span>
        <span class="muted small">｜评论 → 发现 → 需求 → 测试用例 全链路校验</span>
      </div>
      <div v-if="report.revisions?.length" class="revisions">
        <strong class="small">修订记录：</strong>
        <ul class="small" style="margin: 4px 0 0; padding-left: 18px; color: var(--amber)">
          <li v-for="(r, i) in report.revisions" :key="i">{{ r }}</li>
        </ul>
      </div>
      <table v-if="report.checks?.length" style="margin-top: 10px">
        <thead>
          <tr>
            <th>类型</th>
            <th>ID</th>
            <th>结果</th>
            <th>处理</th>
            <th>问题</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(c, i) in report.checks" :key="i">
            <td class="small">{{ typeText(c.item_type) }}</td>
            <td><code>{{ c.item_id }}</code></td>
            <td>
              <span class="badge" :class="c.ok ? 'badge ok' : 'badge err'">{{ c.ok ? '通过' : '问题' }}</span>
            </td>
            <td class="small">{{ actionText(c.action) }}</td>
            <td class="small muted">{{ c.issues?.join('；') }}</td>
          </tr>
        </tbody>
      </table>
    </template>
    <div v-else class="empty">暂无追溯报告</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getArtifact } from '../api'

const props = defineProps({ runId: { type: String, required: true } })
const report = ref(null)
const loaded = ref(false)

onMounted(async () => {
  try {
    report.value = await getArtifact(props.runId, 'traceability_report')
  } catch {
    report.value = null
  }
  loaded.value = true
})

function typeText(t) {
  return { finding: '发现', requirement: '需求', test_case: '测试用例' }[t] || t
}
function actionText(a) {
  return { keep: '保留', revised: '修订', removed: '删除', assumption: '标注假设' }[a] || a
}
</script>

<style scoped>
.summary-line { margin-bottom: 8px; }
.revisions {
  background: rgba(251, 191, 36, 0.08);
  border: 1px solid rgba(251, 191, 36, 0.3);
  border-radius: 8px;
  padding: 8px 12px;
  margin-top: 8px;
}
</style>
