<script setup>
import { computed, onMounted, ref } from 'vue'
import { token, me, health, loadMe, logout } from './store'
import LoginView from './components/LoginView.vue'
import AskView from './components/AskView.vue'
import ProjectsView from './components/ProjectsView.vue'
import SourcesView from './components/SourcesView.vue'
import SettingsView from './components/SettingsView.vue'
import UsersView from './components/UsersView.vue'
import CubeBusinessView from './components/CubeBusinessView.vue'

const view = ref('ask') // ask | settings
const tab = ref('projects')

const isAdmin = computed(() => me.value?.role === 'admin')
const isEditor = computed(() => me.value?.role === 'editor')
const canSettings = computed(() => !!me.value) // 三种角色都能进；里面能看什么由 tabs 决定

const tabs = computed(() => {
  const list = [{ key: 'projects', label: '业务' }]
  if (isAdmin.value || isEditor.value) list.push({ key: 'cube', label: 'Cube 业务' })
  if (isAdmin.value || isEditor.value) list.push({ key: 'sources', label: '数据源' })
  if (isAdmin.value) list.push({ key: 'settings', label: '系统设置' })
  if (isAdmin.value) list.push({ key: 'users', label: '用户' })
  return list
})

function openSettings() {
  view.value = 'settings'
  if (!tabs.value.some((t) => t.key === tab.value)) {
    tab.value = tabs.value[0]?.key || 'projects'
  }
}

async function refresh() {
  try {
    await loadMe()
  } catch (e) {
    if (String(e.message).includes('401')) logout()
  }
}

onMounted(() => {
  if (token.value) refresh()
})
</script>

<template>
  <LoginView v-if="!token" @logged-in="refresh" />

  <div v-else class="wrap">
    <header>
      <strong>Wren Console</strong>
      <span class="muted">{{ me?.name }}（{{ me?.role }}）</span>
      <span class="spacer"></span>
      <span v-if="health" class="muted">
        Trino
        <span :class="health.trino?.ok ? 'ok' : 'bad'">
          {{ health.trino?.ok ? '已连接 ' + health.trino.version : '未连接' }}
        </span>
      </span>
      <button v-if="view === 'settings'" @click="view = 'ask'">← 返回查询</button>
      <button v-else-if="canSettings" @click="openSettings">设置</button>
      <button @click="refresh">刷新</button>
      <button @click="logout">退出</button>
    </header>

    <template v-if="view === 'ask'">
      <AskView />
    </template>

    <template v-else>
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

      <ProjectsView v-if="tab === 'projects'" />
      <CubeBusinessView v-else-if="tab === 'cube'" />
      <SourcesView v-else-if="tab === 'sources'" />
      <SettingsView v-else-if="tab === 'settings' && isAdmin" />
      <UsersView v-else-if="tab === 'users' && isAdmin" />
    </template>
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
