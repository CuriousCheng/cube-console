import { ref } from 'vue'

export const token = ref(localStorage.getItem('wc_token') || '')
export const me = ref(null)
export const health = ref(null)

export async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) }
  if (token.value) headers.Authorization = `Bearer ${token.value}`
  const res = await fetch(path, { ...opts, headers })
  const text = await res.text()
  const data = text ? JSON.parse(text) : {}
  if (!res.ok) throw new Error(data.detail || data.error || `HTTP ${res.status}`)
  return data
}

export function logout() {
  token.value = ''
  me.value = null
  localStorage.removeItem('wc_token')
}

export async function loadMe() {
  me.value = await api('/api/me')
  health.value = await api('/api/health')
}
