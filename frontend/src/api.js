const BASE = ''

async function request(path, options = {}) {
  const resp = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  })
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
export const getArtifact = (id, name) => request(`/api/runs/${id}/artifacts/${name}`)
export const listArtifacts = (id) => request(`/api/runs/${id}/artifacts`)
export const testLLM = (payload) =>
  request('/api/llm/test', { method: 'POST', body: JSON.stringify(payload) })

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
