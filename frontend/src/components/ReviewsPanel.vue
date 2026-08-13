<template>
  <div class="card">
    <h2>{{ title }} <span class="muted small">（{{ data?.length || 0 }} 条）</span></h2>
    <div v-if="!loaded" class="empty">加载中…</div>
    <div v-else-if="!data?.length" class="empty">暂无数据</div>
    <table v-else>
      <thead>
        <tr>
          <th>ID</th>
          <th>评分</th>
          <th>版本</th>
          <th>语言</th>
          <th style="width: 50%">内容</th>
          <th v-if="artifact === 'cleaned_reviews'">状态</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in visible" :key="r.review_id">
          <td class="small muted">{{ r.review_id }}</td>
          <td><span class="badge" :class="ratingClass(r.rating)">{{ r.rating }}★</span></td>
          <td class="small">{{ r.version || '—' }}</td>
          <td class="small">{{ r.lang || '—' }}</td>
          <td>
            <div class="small"><strong>{{ r.title }}</strong></div>
            <div class="small muted">{{ r.content }}</div>
          </td>
          <td v-if="artifact === 'cleaned_reviews'">
            <span v-if="r.is_duplicate" class="badge warn">重复 {{ r.dup_group }}</span>
            <span v-else class="badge ok">保留</span>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="data?.length > limit" class="small muted" style="margin-top: 8px">
      显示前 {{ visible.length }} 条 / 共 {{ data.length }} 条
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed, onMounted } from 'vue'
import { getArtifact } from '../api'

const props = defineProps({
  runId: { type: String, required: true },
  artifact: { type: String, required: true },
  title: { type: String, required: true }
})

const data = ref(null)
const loaded = ref(false)
const limit = 100

async function load() {
  loaded.value = false
  try {
    data.value = await getArtifact(props.runId, props.artifact)
  } catch {
    data.value = []
  }
  loaded.value = true
}

const visible = computed(() => (data.value || []).slice(0, limit))

function ratingClass(r) {
  if (r >= 4) return 'badge ok'
  if (r === 3) return 'badge info'
  return 'badge err'
}

onMounted(load)
watch(() => props.runId, load)
</script>
