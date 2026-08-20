const BASE = ''

async function request(path, options = {}, timeoutMs = 0) {
  const controller = timeoutMs ? new AbortController() : null
  const timer = timeoutMs ? setTimeout(() => controller.abort(), timeoutMs) : null
  let resp
  try {
    resp = await fetch(BASE + path, {
      headers: { 'Content-Type': 'application/json' },
      signal: controller?.signal,
      ...options
    })
  } catch (e) {
    if (e?.name === 'AbortError') throw new Error('请求超时，请检查网络或服务配置')
    throw e
  } finally {
    if (timer) clearTimeout(timer)
  }
  let data = null
  try {
    data = await resp.json()
  } catch {
    data = null
  }
  if (!resp.ok) {
    const detail = data?.detail || data?.error || resp.statusText
    const msg = typeof detail === 'string' ? detail : JSON.stringify(detail)
    throw new Error(msg)
  }
  return data
}

export const getProviders = () => request('/api/providers')
export const createRun = (payload) =>
  request('/api/runs', { method: 'POST', body: JSON.stringify(payload) })
export const getRun = (id) => request(`/api/runs/${id}`)
export const listRuns = () => request('/api/runs')
export const deleteRun = (id) => request(`/api/runs/${id}`, { method: 'DELETE' })
export const pauseRun = (id) => request(`/api/runs/${id}/pause`, { method: 'POST' })
export const resumeRun = (id) => request(`/api/runs/${id}/resume`, { method: 'POST' })
export const getArtifact = (id, name) => request(`/api/runs/${id}/artifacts/${name}`)
export const listArtifacts = (id) => request(`/api/runs/${id}/artifacts`)
export const testLLM = (payload) =>
  request('/api/llm/test', { method: 'POST', body: JSON.stringify(payload) }, 30000)
export const fetchModels = (payload) =>
  request('/api/llm/models', { method: 'POST', body: JSON.stringify(payload) }, 20000)
export const getLlmConfig = () => request('/api/llm/config')
export const saveLlmConfig = (cfg) =>
  request('/api/llm/config', { method: 'PUT', body: JSON.stringify(cfg) })

export function streamRun(id, onEvent) {
  const es = new EventSource(`/api/runs/${id}/events`)
  es.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data))
    } catch {
      /* ignore */
    }
  }
  return es
}
