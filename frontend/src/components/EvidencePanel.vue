<template>
  <div class="card">
    <h2>证据充分性评估</h2>
    <div v-if="!loaded" class="empty">加载中…</div>
    <template v-else-if="report">
      <p class="small">{{ report.overall }}</p>
      <table v-if="report.items?.length">
        <thead>
          <tr>
            <th>发现</th>
            <th>状态</th>
            <th>样本数</th>
            <th>版本覆盖</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="it in report.items" :key="it.finding_id">
            <td>{{ it.finding_id }}</td>
            <td>
              <span class="badge" :class="statusClass(it.status)">
                {{ statusText(it.status) }}
              </span>
            </td>
            <td>{{ it.supporting_count }}</td>
            <td class="small muted">{{ it.coverage }}</td>
            <td class="small muted">{{ it.note }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="report.data_limitations?.length" style="margin-top: 12px">
        <strong class="small">数据局限（如实声明，不伪造数据）</strong>
        <ul class="small muted">
          <li v-for="(l, i) in report.data_limitations" :key="i">{{ l }}</li>
        </ul>
      </div>
    </template>
    <div v-else class="empty">暂无证据报告</div>
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
    report.value = await getArtifact(props.runId, 'evidence_report')
  } catch {
    report.value = null
  }
  loaded.value = true
})

function statusText(s) {
  return { sufficient: '证据充分', insufficient: '证据不足', conflicting: '存在冲突' }[s] || s
}
function statusClass(s) {
  return { sufficient: 'badge ok', insufficient: 'badge warn', conflicting: 'badge err' }[s] || 'badge info'
}
</script>
