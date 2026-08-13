<template>
  <div class="card">
    <h2>动态主题分类（模型归纳，无预设分类）</h2>
    <div v-if="!loaded" class="empty">加载中…</div>
    <div v-else-if="!themes?.length" class="empty">暂无主题（可能需要模型阶段支持）</div>
    <div v-else class="grid">
      <div v-for="t in themes" :key="t.id" class="theme">
        <div style="display: flex; align-items: center; gap: 8px">
          <strong>{{ t.title }}</strong>
          <span class="badge" :class="sentimentClass(t.sentiment)">{{ sentimentText(t.sentiment) }}</span>
          <span class="badge info">{{ t.confidence }}</span>
        </div>
        <div class="small muted" style="margin-top: 4px">{{ t.description }}</div>
        <div class="small" style="margin-top: 6px">
          <span class="muted">{{ t.review_ids?.length || 0 }} 条评论：</span>
          <code class="ids">{{ (t.review_ids || []).slice(0, 8).join(', ') }}</code>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getArtifact } from '../api'

const props = defineProps({ runId: { type: String, required: true } })
const themes = ref(null)
const loaded = ref(false)

onMounted(async () => {
  try {
    themes.value = await getArtifact(props.runId, 'themes')
  } catch {
    themes.value = []
  }
  loaded.value = true
})

function sentimentText(s) {
  return { negative: '负面', positive: '正面', mixed: '混合' }[s] || s
}
function sentimentClass(s) {
  return { negative: 'badge err', positive: 'badge ok', mixed: 'badge warn' }[s] || 'badge info'
}
</script>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.theme {
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
}
.ids {
  font-size: 11px;
  color: var(--accent);
  word-break: break-all;
}
</style>
