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

// 开发期自动用 admin 登录，省得每次输密码；生产构建不会执行
export async function devAutoLogin() {
  if (token.value) return
  const r = await api('/api/login', {
    method: 'POST',
    body: JSON.stringify({
      name: import.meta.env.VITE_DEV_USER || 'admin',
      password: import.meta.env.VITE_DEV_PASS || 'admin123',
    }),
  })
  token.value = r.token
  localStorage.setItem('wc_token', r.token)
  me.value = r.user
  await loadMe()
}
