<template>
  <div class="card">
    <h2>产品需求文档（PRD）</h2>
    <div v-if="!loaded" class="empty">加载中…</div>
    <template v-else-if="prd">
      <div v-if="prd.update_plan?.summary" class="plan">
        <strong>更新计划：</strong>{{ prd.update_plan.summary }}
      </div>
      <div v-if="prd.update_plan?.versions?.length" class="versions">
        <div v-for="v in prd.update_plan.versions" :key="v.version" class="version">
          <span class="badge info">{{ v.version }}</span>
          <strong>{{ v.title }}</strong>
          <span class="small muted">{{ v.scope }}</span>
          <span v-if="v.rationale" class="small muted">｜拆分理由：{{ v.rationale }}</span>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>标题</th>
            <th style="width: 35%">描述</th>
            <th>优先级</th>
            <th>版本</th>
            <th>证据</th>
            <th>边界</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in prd.requirements" :key="r.id">
            <td>{{ r.id }}</td>
            <td>
              {{ r.title }}
              <span v-if="r.assumption" class="badge warn">假设</span>
            </td>
            <td class="small muted">{{ r.description }}</td>
            <td><span class="badge" :class="prioClass(r.priority)">{{ r.priority }}</span></td>
            <td>{{ r.version }}</td>
            <td class="small">
              <div>发现：<code class="ids">{{ r.finding_ids?.join(', ') }}</code></div>
              <div>评论：<code class="ids">{{ (r.review_ids || []).slice(0, 6).join(', ') }}</code></div>
            </td>
            <td class="small muted">{{ r.boundaries }}</td>
          </tr>
        </tbody>
      </table>
    </template>
    <div v-else class="empty">暂无 PRD（需要模型阶段支持）</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getArtifact } from '../api'

const props = defineProps({ runId: { type: String, required: true } })
const prd = ref(null)
const loaded = ref(false)

onMounted(async () => {
  try {
    prd.value = await getArtifact(props.runId, 'prd')
  } catch {
    prd.value = null
  }
  loaded.value = true
})

function prioClass(p) {
  return { P0: 'badge err', P1: 'badge warn', P2: 'badge info' }[p] || 'badge info'
}
</script>

<style scoped>
.plan {
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
}
.versions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}
.version {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  flex-wrap: wrap;
}
.ids {
  font-size: 11px;
  color: var(--accent);
}
</style>
