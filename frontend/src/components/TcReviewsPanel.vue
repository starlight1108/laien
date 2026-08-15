<template>
  <div class="card">
    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px">
      <h2 style="margin: 0">测试用例评论追溯</h2>
      <button class="ghost" @click="back">← 返回测试用例</button>
    </div>

    <div v-if="!loaded" class="empty">加载中…</div>

    <template v-else-if="tc">
      <div class="tc-head">
        <strong>{{ tc.id }}</strong>
        <span class="badge info">需求 {{ tc.requirement_id }}</span>
        <span class="small muted">{{ tc.verifies_issue }}</span>
      </div>

      <div class="summary-line">
        <span class="badge ok">匹配到 {{ matched.length }} 条关联评论</span>
        <span v-if="missing.length" class="badge warn">未找到 {{ missing.length }} 条</span>
      </div>

      <table v-if="matched.length">
        <thead>
          <tr>
            <th>ID</th>
            <th>评分</th>
            <th>版本</th>
            <th>语言</th>
            <th style="width: 50%">内容</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in matched" :key="r.review_id">
            <td class="small muted">{{ r.review_id }}</td>
            <td><span class="badge" :class="ratingClass(r.rating)">{{ r.rating }}★</span></td>
            <td class="small">{{ r.version || '—' }}</td>
            <td class="small">{{ r.lang || '—' }}</td>
            <td>
              <div class="small"><strong>{{ r.title }}</strong></div>
              <div class="small muted">{{ r.content }}</div>
            </td>
            <td>
              <span v-if="r.is_duplicate" class="badge warn">重复 {{ r.dup_group }}</span>
              <span v-else class="badge ok">保留</span>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">该用例暂无关联评论</div>
    </template>

    <div v-else class="empty">
      未选择测试用例，请先在「测试用例」页点击「查看关联评论」进入本页
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { getArtifact } from '../api'
import { store } from '../store'

const props = defineProps({ runId: { type: String, required: true } })

const cases = ref([])
const reviews = ref([])
const loaded = ref(false)

// 优先用最新 test_cases 产物中的用例；找不到时回退到点击时的快照
const tc = computed(() => {
  const fresh = (cases.value || []).find((c) => c.id === store.tcTrace?.id)
  return fresh || store.tcTrace || null
})

const matched = computed(() => {
  const ids = new Set(tc.value?.review_ids || [])
  return (reviews.value || []).filter((r) => ids.has(r.review_id))
})

const missing = computed(() => {
  const have = new Set((reviews.value || []).map((r) => r.review_id))
  return (tc.value?.review_ids || []).filter((id) => !have.has(id))
})

async function load() {
  loaded.value = false
  try {
    cases.value = (await getArtifact(props.runId, 'test_cases')) || []
  } catch {
    cases.value = []
  }
  try {
    reviews.value = (await getArtifact(props.runId, 'cleaned_reviews')) || []
  } catch {
    reviews.value = []
  }
  loaded.value = true
}

function back() {
  store.activeTab = 'tests'
}

function ratingClass(r) {
  if (r >= 4) return 'badge ok'
  if (r === 3) return 'badge info'
  return 'badge err'
}

onMounted(load)
watch(() => props.runId, load)
</script>

<style scoped>
.tc-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin: 12px 0 8px;
}
.summary-line { margin-bottom: 8px; }
</style>
