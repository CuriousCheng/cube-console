<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, me } from '../store'

const users = ref([])
const msg = ref('')
const busy = ref(false)
const form = reactive({ name: '', password: '', role: 'viewer' })

async function load() {
  try {
    users.value = (await api('/api/users')).items
  } catch (e) {
    msg.value = e.message
  }
}

async function create() {
  busy.value = true
  msg.value = ''
  try {
    await api('/api/users', { method: 'POST', body: JSON.stringify(form) })
    Object.assign(form, { name: '', password: '', role: 'viewer' })
    await load()
    msg.value = '已创建'
  } catch (e) {
    msg.value = `失败：${e.message}`
  } finally {
    busy.value = false
  }
}

async function resetPwd(u) {
  const pwd = prompt(`给「${u.name}」设置新密码（至少 4 位）`)
  if (!pwd) return
  try {
    await api(`/api/users/${u.id}/password`, {
      method: 'PUT',
      body: JSON.stringify({ password: pwd }),
    })
    alert('密码已重置')
  } catch (e) {
    alert(e.message)
  }
}

async function setRole(u, role) {
  try {
    await api(`/api/users/${u.id}/role`, { method: 'PUT', body: JSON.stringify({ role }) })
    await load()
  } catch (e) {
    alert(e.message)
    await load()
  }
}

async function remove(u) {
  if (!confirm(`确定删除用户「${u.name}」？`)) return
  try {
    await api(`/api/users/${u.id}`, { method: 'DELETE' })
    await load()
  } catch (e) {
    alert(e.message)
  }
}

onMounted(load)
</script>

<template>
  <div class="card">
    <h3>用户</h3>
    <p class="muted">
      admin 管配置和建项目；editor 在项目里建模和提问；viewer 只能提问看结果。
    </p>

    <table v-if="users.length">
      <thead>
        <tr>
          <th>用户名</th>
          <th style="width: 150px">角色</th>
          <th style="width: 200px">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="u in users" :key="u.id">
          <td>
            {{ u.name }}
            <span v-if="u.id === me?.id" class="muted">（我）</span>
          </td>
          <td>
            <select :value="u.role" @change="setRole(u, $event.target.value)">
              <option value="admin">admin</option>
              <option value="editor">editor</option>
              <option value="viewer">viewer</option>
            </select>
          </td>
          <td>
            <button @click="resetPwd(u)">重置密码</button>
            <button :disabled="u.id === me?.id" @click="remove(u)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

    <p v-if="msg" class="muted">{{ msg }}</p>
  </div>

  <div class="card">
    <h3>新建用户</h3>
    <div class="grid2">
      <div>
        <label class="lbl">用户名</label>
        <input v-model="form.name" />
      </div>
      <div>
        <label class="lbl">初始密码</label>
        <input v-model="form.password" />
      </div>
      <div>
        <label class="lbl">角色</label>
        <select v-model="form.role">
          <option value="viewer">viewer（只看）</option>
          <option value="editor">editor（建模+提问）</option>
          <option value="admin">admin（全部）</option>
        </select>
      </div>
    </div>
    <div class="actions">
      <button class="primary" :disabled="busy || !form.name" @click="create">
        {{ busy ? '创建中…' : '创建账号' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.lbl {
  display: block;
  margin: 12px 0 5px;
  font-size: 13px;
  color: #57606a;
}
.grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 18px;
}
.actions {
  margin-top: 16px;
}
</style>
