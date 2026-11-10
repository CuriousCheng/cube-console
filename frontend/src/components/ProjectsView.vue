<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, me } from '../store'
import BusinessView from './BusinessView.vue'

const projects = ref([])
const sources = ref([])
const busy = ref('')
const msg = ref('')
const form = reactive({ name: '', datasource_id: '' })
const opened = ref('')

const canManage = () => ['admin', 'editor'].includes(me.value?.role)
const canDelete = () => me.value?.role === 'admin'
const canRun = () => ['admin', 'editor'].includes(me.value?.role)

async function load() {
  try {
    projects.value = (await api('/api/projects')).items
    sources.value = (await api('/api/datasources')).items
  } catch (e) {
    msg.value = e.message
  }
}

async function create() {
  busy.value = 'create'
  msg.value = ''
  try {
    await api('/api/projects', { method: 'POST', body: JSON.stringify(form) })
    form.name = ''
    await load()
    msg.value = '已创建'
  } catch (e) {
    msg.value = `失败：${e.message}`
  } finally {
    busy.value = ''
  }
}

async function start(p) {
  busy.value = p.name
  msg.value = ''
  try {
    const r = await api(`/api/projects/${encodeURIComponent(p.name)}/start`, { method: 'POST' })
    msg.value = `${p.name} 已启动 → :${r.port}${r.evicted ? `（踢掉了 ${r.evicted}）` : ''}`
    await load()
  } catch (e) {
    msg.value = `启动失败：${e.message}`
  } finally {
    busy.value = ''
  }
}

async function stop(p) {
  busy.value = p.name
  try {
    await api(`/api/projects/${encodeURIComponent(p.name)}/stop`, { method: 'POST' })
    await load()
  } catch (e) {
    msg.value = e.message
  } finally {
    busy.value = ''
  }
}

async function remove(p) {
  if (!confirm(`删除项目「${p.name}」？目录会被删掉。`)) return
  busy.value = p.name
  try {
    await api(`/api/projects/${encodeURIComponent(p.name)}`, { method: 'DELETE' })
    await load()
  } catch (e) {
    msg.value = e.message
  } finally {
    busy.value = ''
  }
}

onMounted(load)
</script>

<template>
  <div class="card">
    <h3>项目</h3>
    <p class="muted">
      一个项目 = 一个 Wren 语义模型集 = 一个 MCP 进程。池容量默认 3，超了会踢最久没用的。
    </p>

    <table v-if="projects.length">
      <thead>
        <tr>
          <th>业务</th>
          <th>数据源</th>
          <th>表数</th>
          <th style="width: 170px">MCP</th>
          <th style="width: 240px">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in projects" :key="p.name">
          <td><strong>{{ p.name }}</strong></td>
          <td>{{ p.datasource || '—' }}</td>
          <td>{{ p.models }}</td>
          <td>
            <span v-if="p.mcp.running" class="ok">运行中 :{{ p.mcp.port }}</span>
            <span v-else class="muted">已停止</span>
          </td>
          <td>
            <button @click="opened = opened === p.name ? '' : p.name">
              {{ opened === p.name ? '收起' : '编辑' }}
            </button>
            <button v-if="canRun() && !p.mcp.running" :disabled="busy === p.name" @click="start(p)">
              启动
            </button>
            <button v-if="canRun() && p.mcp.running" :disabled="busy === p.name" @click="stop(p)">
              停止
            </button>
            <button v-if="canDelete()" :disabled="busy === p.name" @click="remove(p)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">还没有业务。</p>

    <p v-if="msg" class="muted">{{ msg }}</p>
  </div>

  <BusinessView
    v-if="opened"
    :project="opened"
    @closed="opened = ''"
    @changed="load"
  />

  <div v-if="canManage()" class="card">
    <h3>新建业务</h3>
    <p class="muted">
      建好后会得到一个空的 Wren 项目目录；下一步从这里挑表生成模型。
    </p>

    <div class="grid2">
      <div>
        <label class="lbl">项目名</label>
        <input v-model="form.name" placeholder="例如：销售分析" />
      </div>
      <div>
        <label class="lbl">主数据源</label>
        <select v-model="form.datasource_id">
          <option value="">（不绑定）</option>
          <option v-for="s in sources" :key="s.id" :value="s.id">
            {{ s.name }}（{{ s.type }}）
          </option>
        </select>
      </div>
    </div>

    <div class="actions">
      <button class="primary" :disabled="busy === 'create' || !form.name" @click="create">
        {{ busy === 'create' ? '创建中…' : '创建项目' }}
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
