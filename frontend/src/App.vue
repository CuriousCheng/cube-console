<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, token, me, health, loadMe, logout, devAutoLogin } from './store'
import LoginView from './components/LoginView.vue'
import SettingsView from './components/SettingsView.vue'
import UsersView from './components/UsersView.vue'
import CubeBusinessView from './components/CubeBusinessView.vue'
import CubeQueryView from './components/CubeQueryView.vue'
import CubeFieldEditor from './components/CubeFieldEditor.vue'
import CubeJoinView from './components/CubeJoinView.vue'
import SourcesView from './components/SourcesView.vue'
import KnowledgeView from './components/KnowledgeView.vue'

const tab = ref('cubequery')
const compiling = ref(false)
const compileMsg = ref('')

async function compile() {
  compiling.value = true
  compileMsg.value = ''
  try {
    const r = await api('/api/cube/compile', { method: 'POST' })
    if (!r.ok) {
      compileMsg.value = '编译失败'
    } else {
      const b = r.rebuild || {}
      compileMsg.value =
        '已编译 ' + (b.cubes || 0) + ' 个表' +
        (b.added ? '，新增 ' + b.added : '') +
        (b.removed ? '，移除 ' + b.removed : '') +
        (r.ready ? '，Cube 就绪' : '，Cube 未就绪')
    }
  } catch (e) {
    compileMsg.value = e.message
  } finally {
    compiling.value = false
  }
}

const isAdmin = computed(() => me.value?.role === 'admin')
const isEditor = computed(() => me.value?.role === 'editor')

const tabs = computed(() => {
  const list = [
    { key: 'cubequery', label: '查询' },
    { key: 'cube', label: '业务' },
    { key: 'fields', label: '字段定义' },
    { key: 'joins', label: '表关系' },
    { key: 'knowledge', label: '知识记忆' },
    { key: 'sources', label: '数据源' },
  ]
  if (isAdmin.value) list.push({ key: 'settings', label: '系统设置' })
  if (isAdmin.value) list.push({ key: 'users', label: '用户' })
  return list
})

async function refresh() {
  try {
    await loadMe()
  } catch (e) {
    if (String(e.message).includes('401')) logout()
  }
}

onMounted(async () => {
  if (!token.value && import.meta.env.DEV) {
    try {
      await devAutoLogin()
    } catch {}
  }
  if (token.value) refresh()
})
</script>

<template>
  <LoginView v-if="!token" @logged-in="refresh" />

  <div v-else class="wrap">
    <header>
      <strong>Cube Console</strong>
      <span class="muted">{{ me?.name }}（{{ me?.role }}）</span>
      <span class="spacer"></span>
      <span v-if="health" class="muted">
        Trino
        <span :class="health.trino?.ok ? 'ok' : 'bad'">
          {{ health.trino?.ok ? '已连接 ' + health.trino.version : '未连接' }}
        </span>
      </span>
      <button :disabled="compiling" @click="compile">
        {{ compiling ? '编译中…' : '编译' }}
      </button>
      <span v-if="compileMsg" class="muted small">{{ compileMsg }}</span>
      <button @click="refresh">刷新</button>
      <button @click="logout">退出</button>
    </header>

    <nav class="tabs">
      <button
        v-for="t in tabs"
        :key="t.key"
        :class="['tab', tab === t.key ? 'on' : '']"
        @click="tab = t.key"
      >
        {{ t.label }}
      </button>
    </nav>

    <CubeQueryView v-if="tab === 'cubequery'" />
    <CubeBusinessView v-else-if="tab === 'cube'" />
    <CubeFieldEditor v-else-if="tab === 'fields'" />
    <CubeJoinView v-else-if="tab === 'joins'" />
    <KnowledgeView v-else-if="tab === 'knowledge'" />
    <SourcesView v-else-if="tab === 'sources'" />
    <SettingsView v-else-if="tab === 'settings' && isAdmin" />
    <UsersView v-else-if="tab === 'users' && isAdmin" />
  </div>
</template>

<style scoped>
.wrap {
  max-width: 1080px;
  margin: 0 auto;
  padding: 18px;
}
header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}
.spacer {
  flex: 1;
}
.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.tab {
  padding: 7px 16px;
  border-radius: 20px;
}
.tab.on {
  background: #1f883d;
  border-color: #1a7f37;
  color: #fff;
}
</style>
