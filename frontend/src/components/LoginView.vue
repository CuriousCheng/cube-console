<script setup>
import { reactive, ref } from 'vue'
import { api, token, me, loadMe } from '../store'

const form = reactive({ name: 'admin', password: '' })
const loading = ref(false)
const error = ref('')

async function submit() {
  loading.value = true
  error.value = ''
  try {
    const r = await api('/api/login', {
      method: 'POST',
      body: JSON.stringify({ name: form.name, password: form.password }),
    })
    token.value = r.token
    localStorage.setItem('wc_token', r.token)
    me.value = r.user
    await loadMe()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <div class="card login-card">
      <h1>Cube Console</h1>
      <p class="muted">把散落的数据库，变成 AI 能直接问的语义项目</p>

      <label class="lbl">账号</label>
      <input v-model="form.name" @keyup.enter="submit" />

      <label class="lbl">密码</label>
      <input v-model="form.password" type="password" @keyup.enter="submit" />

      <p v-if="error" class="bad">{{ error }}</p>

      <button class="primary full" :disabled="loading" @click="submit">
        {{ loading ? '登录中…' : '登录' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.login-card {
  width: 360px;
}
.login-card h1 {
  margin: 0 0 4px;
  font-size: 20px;
}
.lbl {
  display: block;
  margin: 12px 0 5px;
  font-size: 13px;
  color: #57606a;
}
.full {
  width: 100%;
  margin-top: 18px;
}
</style>
