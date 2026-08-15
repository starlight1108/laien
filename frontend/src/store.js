import { reactive, watch } from 'vue'
import { getLlmConfig, saveLlmConfig } from './api'

// 模型配置持久化：由后端按提供商分槽写入本地 JSON 文件（data/llm_config.json，已 gitignore）。
// 每个提供商独立保存 base_url/model/api_key —— 切换提供商时互不串用（Key 不会带错家）。
// 兼容旧版：浏览器 localStorage（键 app-review-insights:llm-config）里的配置在后端无该分槽时补种。
const LEGACY_STORAGE_KEY = 'app-review-insights:llm-config'

let hydrated = false // 首次从后端读取成功后才允许回写，避免加载完成前覆盖已有配置
let saveTimer = null
const savedByProvider = reactive({}) // providerId -> {base_url, model, api_key}

function readLegacyConfig() {
  try {
    const raw = localStorage.getItem(LEGACY_STORAGE_KEY)
    if (!raw) return null
    const d = JSON.parse(raw)
    if (typeof d.provider !== 'string' || !d.provider) return null
    return {
      provider: d.provider,
      base_url: typeof d.base_url === 'string' ? d.base_url : '',
      model: typeof d.model === 'string' ? d.model : '',
      api_key: typeof d.api_key === 'string' ? d.api_key : ''
    }
  } catch {
    return null
  }
}

export async function loadLlmConfig() {
  try {
    const d = await getLlmConfig()
    hydrated = true
    const map = d.providers || {}
    // 旧版 localStorage 补种：后端没有该提供商分槽时补上并回写后端（升级不丢 Key）
    const legacy = readLegacyConfig()
    if (legacy && !map[legacy.provider]) {
      map[legacy.provider] = { base_url: legacy.base_url, model: legacy.model, api_key: legacy.api_key }
      saveLlmConfig(legacy).catch(() => { /* 后端不可用时下次加载重试 */ })
    }
    for (const id of Object.keys(map)) {
      savedByProvider[id] = {
        base_url: map[id].base_url || '',
        model: map[id].model || '',
        api_key: map[id].api_key || ''
      }
    }
    return savedFor(store.llm.provider)
  } catch {
    // 后端不可用（如仍在跑旧进程）：退回旧 localStorage，让已保存的配置至少可见可用
    const legacy = readLegacyConfig()
    if (legacy) {
      savedByProvider[legacy.provider] = {
        base_url: legacy.base_url,
        model: legacy.model,
        api_key: legacy.api_key
      }
      return legacy
    }
    return null
  }
}

// 取指定提供商的已保存配置（无则 null）；返回带 provider 字段，便于调用方区分
export function savedFor(providerId) {
  const cfg = savedByProvider[providerId]
  if (!cfg) return null
  return { provider: providerId, base_url: cfg.base_url, model: cfg.model, api_key: cfg.api_key }
}

export const store = reactive({
  providers: [],
  currentRun: null, // RunMeta
  activeTab: 'progress',
  // 测试用例追溯：从「测试用例」页点击「查看关联评论」时记录选中的用例快照
  tcTrace: null, // 测试用例对象（含 id / requirement_id / review_ids）
  llm: {
    provider: 'openai',
    base_url: '',
    model: '',
    api_key: '',
    models: [], // 从提供商拉取的模型列表
    modelsState: 'idle', // idle | loading | ok | fail
    modelsMsg: '',
    testState: 'idle', // idle | testing | ok | fail
    testMsg: ''
  }
})

function defaultBaseUrl(providerId) {
  const p = store.providers.find((x) => x.id === providerId)
  return (p && p.base_url) || ''
}

// 模型配置自动持久化（provider / base_url / model / api_key）：防抖 500ms 写入后端。
// 写入前去重：与已保存分槽一致（如切换回提供商恢复配置）或纯默认值（预置 base_url + 空 Key/模型）
// 不落盘 —— 既减少无意义写入，也保证「切换提供商」这个动作本身绝不改动任何槽位。
function saveCurrentConfig() {
  const cfg = {
    provider: store.llm.provider,
    base_url: store.llm.base_url,
    model: store.llm.model,
    api_key: store.llm.api_key
  }
  const prev = savedByProvider[cfg.provider]
  if (prev && prev.base_url === cfg.base_url && prev.model === cfg.model && prev.api_key === cfg.api_key) {
    return // 与已保存分槽一致，无需写入
  }
  if (!prev && !cfg.api_key && !cfg.model && cfg.base_url === defaultBaseUrl(cfg.provider)) {
    return // 尚无分槽且是纯默认值，不是用户意图，不落盘
  }
  savedByProvider[cfg.provider] = { base_url: cfg.base_url, model: cfg.model, api_key: cfg.api_key }
  saveLlmConfig(cfg).catch(() => { /* 后端不可用时忽略，下次变更会重试 */ })
}

watch(
  () => [store.llm.provider, store.llm.base_url, store.llm.model, store.llm.api_key],
  () => {
    if (!hydrated) return
    clearTimeout(saveTimer)
    saveTimer = setTimeout(saveCurrentConfig, 500)
  }
)
