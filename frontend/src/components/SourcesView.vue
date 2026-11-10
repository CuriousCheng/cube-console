<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, me } from '../store'

const sources = ref([])
const testResult = ref(null)
const testLoading = ref(false)
const saving = ref(false)
const rebuildLoading = ref(false)
const rebuildMsg = ref('')
const error = ref('')

const form = reactive({
  name: '',
  type: 'mysql',
  host: '127.0.0.1',
  port: 3306,
  database: '',
  user: '',
  password: '',
})

const PORT_HINT = { mysql: 3306, mariadb: 3306, postgresql: 5432, sqlserver: 1433 }
const canEdit = () => me.value?.role === 'admin'

const dbs = ref([])

const TYPE_HINT = {
  mysql: 'MySQL 一个数据源覆盖整台服务器，所有库都会变成 Trino 的 schema。',
  mariadb: 'MariaDB 同 MySQL，一个数据源覆盖整台服务器。',
  postgresql: 'PostgreSQL 一个数据源只能连一个库，要多个库就建多个数据源。',
  sqlserver: 'SQL Server 一个数据源连一个库。',
}

function setType(t) {
  form.type = t
  form.port = PORT_HINT[t] || 3306
  form.database = ''
  dbs.value = []
}

async function load() {
  sources.value = (await api('/api/datasources')).items
}

async function testForm() {
  testLoading.value = true
  testResult.value = null
  dbs.value = []
  try {
    testResult.value = await api('/api/datasources/test', {
      method: 'POST',
      body: JSON.stringify(form),
    })
    if (testResult.value?.ok && Array.isArray(testResult.value.databases)) {
      dbs.value = testResult.value.databases.filter(
        (x) => !['information_schema', 'performance_schema', 'mysql', 'sys', 'pg_catalog'].includes(x)
      )
    }
  } catch (e) {
    testResult.value = { ok: false, error: e.message }
  } finally {
    testLoading.value = false
  }
}

async function rebuild() {
  rebuildLoading.value = true
  rebuildMsg.value = ''
  try {
    const r = await api('/api/cube/rebuild', { method: 'POST' })
    rebuildMsg.value = r.ok
      ? `已重建 ${r.cubes} 个 cube（新增 ${r.added}，保留 ${r.kept}，移除 ${r.removed}）`
      : `重建失败：${r.error}`
  } catch (e) {
    rebuildMsg.value = e.message
  } finally {
    rebuildLoading.value = false
  }
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    await api('/api/datasources', { method: 'POST', body: JSON.stringify(form) })
    await load()
    Object.assign(form, { name: '', database: '', user: '', password: '' })
    testResult.value = null
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

async function testSaved(ds) {
  try {
    const r = await api(`/api/datasources/${ds.id}/test`, { method: 'POST' })
    alert(r.ok ? `连接成功：${r.version}\n可见库：${(r.databases || []).join(', ')}` : `失败：${r.error}`)
    await load()
  } catch (e) {
    alert(e.message)
  }
}

async function remove(ds) {
  if (!confirm(`确定删除数据源「${ds.name}」？`)) return
  try {
    await api(`/api/datasources/${ds.id}`, { method: 'DELETE' })
    await load()
  } catch (e) {
    alert(e.message)
  }
}

onMounted(load)
</script>

<template>
  <div class="card">
    <h3>数据源</h3>
    <p class="muted">这里写的是「别人的数据库」，保存后会注册成 Trino 的 catalog。</p>

    <table v-if="sources.length">
      <thead>
        <tr>
          <th>名称</th>
          <th>类型</th>
          <th>地址</th>
          <th>库</th>
          <th>Catalog</th>
          <th style="width: 170px">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="d in sources" :key="d.id">
          <td>{{ d.name }}</td>
          <td>{{ d.type }}</td>
          <td>{{ d.host }}:{{ d.port }}</td>
          <td>{{ d.database || '—' }}</td>
          <td><code>{{ d.catalog }}</code></td>
          <td>
            <button @click="testSaved(d)">测试</button>
            <button v-if="canEdit()" @click="remove(d)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">还没有数据源。</p>

    <div class="actions">
      <button :disabled="rebuildLoading" @click="rebuild">
        {{ rebuildLoading ? '重建中…' : '重新生成模型' }}
      </button>
      <span v-if="rebuildMsg" class="muted">{{ rebuildMsg }}</span>
      <span v-else class="muted">数据源增删后会自动重建，也可以手动点这里</span>
    </div>
  </div>

  <div v-if="canEdit()" class="card">
    <h3>添加数据源</h3>

    <div class="grid2">
      <div>
        <label class="lbl">名称</label>
        <input v-model="form.name" placeholder="例如：销售库" />
      </div>
      <div>
        <label class="lbl">类型</label>
        <select :value="form.type" @change="setType($event.target.value)">
          <option value="mysql">MySQL</option>
          <option value="mariadb">MariaDB</option>
          <option value="postgresql">PostgreSQL</option>
          <option value="sqlserver">SQL Server</option>
        </select>
        <p class="hint">{{ TYPE_HINT[form.type] }}</p>
      </div>
      <div>
        <label class="lbl">主机</label>
        <input v-model="form.host" />
      </div>
      <div>
        <label class="lbl">端口</label>
        <input v-model.number="form.port" type="number" />
      </div>
      <div>
        <label class="lbl">数据库</label>
        <select v-if="dbs.length" v-model="form.database">
          <option value="">（服务器上的库，测试连接后可选）</option>
          <option v-for="d in dbs" :key="d" :value="d">{{ d }}</option>
        </select>
        <input v-else v-model="form.database" placeholder="先点下面的「测试连接」拉取库列表" />
      </div>
      <div>
        <label class="lbl">用户名</label>
        <input v-model="form.user" />
      </div>
      <div>
        <label class="lbl">密码</label>
        <input v-model="form.password" type="password" />
      </div>
    </div>

    <div class="actions">
      <button :disabled="testLoading" @click="testForm">
        {{ testLoading ? '测试中…' : '测试连接' }}
      </button>
      <button class="primary" :disabled="saving || !form.name" @click="save">
        {{ saving ? '保存中（重启 Trino 约 10 秒）…' : '保存并注册到 Trino' }}
      </button>
    </div>

    <p v-if="error" class="bad">{{ error }}</p>

    <div v-if="testResult" class="result">
      <p v-if="testResult.ok" class="ok">✅ 连接成功，版本 {{ testResult.version }}</p>
      <p v-else class="bad">❌ {{ testResult.error }}</p>
      <p v-if="testResult.databases?.length" class="muted">
        可见的库：{{ testResult.databases.join(', ') }}
      </p>
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
  display: flex;
  gap: 10px;
}
.result {
  margin-top: 12px;
  padding: 10px 12px;
  background: #f6f8fa;
  border-radius: 6px;
}
.hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: #57606a;
  line-height: 1.5;
}
code {
  background: #eaeef2;
  padding: 1px 5px;
  border-radius: 4px;
}
</style>
