<template>
  <div class="card">
    <h2>测试用例（可追溯到需求与评论）</h2>
    <div v-if="!loaded" class="empty">加载中…</div>
    <div v-else-if="!cases?.length" class="empty">暂无测试用例（需要 PRD 与模型阶段支持）</div>
    <div v-else>
      <div v-for="tc in cases" :key="tc.id" class="tc">
        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap">
          <strong>{{ tc.id }}</strong>
          <span class="badge info">需求 {{ tc.requirement_id }}</span>
          <span class="small muted">关联评论 {{ tc.review_ids?.length || 0 }} 条</span>
          <button
            class="ghost small-btn"
            :disabled="!tc.review_ids?.length"
            @click="viewReviews(tc)"
          >查看关联评论</button>
        </div>
        <div class="small" style="margin-top: 6px">
          <strong class="muted">验证问题：</strong>{{ tc.verifies_issue }}
        </div>
        <div class="small" style="margin-top: 4px">
          <span class="muted">前置条件：</span>{{ tc.preconditions }}
        </div>
        <ol class="small" style="margin: 6px 0 0; padding-left: 18px">
          <li v-for="(s, i) in tc.steps" :key="i">{{ s }}</li>
        </ol>
        <div class="small" style="margin-top: 4px">
          <span class="muted">预期结果：</span><span style="color: var(--green)">{{ tc.expected }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getArtifact } from '../api'
import { store } from '../store'

const props = defineProps({ runId: { type: String, required: true } })
const cases = ref(null)
const loaded = ref(false)

onMounted(async () => {
  try {
    cases.value = await getArtifact(props.runId, 'test_cases')
  } catch {
    cases.value = []
  }
  loaded.value = true
})

function viewReviews(tc) {
  store.tcTrace = tc
  store.activeTab = 'tcreviews'
}
</script>

<style scoped>
.tc {
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 10px;
}
.small-btn { padding: 3px 10px; font-size: 12px; }
.small-btn:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
