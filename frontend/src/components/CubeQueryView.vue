<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../store'

const cubes = ref([])
const views = ref([])
const biz = ref('')
const sel = ref('')
const measures = ref([])
const dims = ref([])
const timeDim = ref('')
const grain = ref('month')
const loading = ref(false)
const result = ref(null)
const sqlText = ref('')
const err = ref('')
const GRAINS = ['day', 'week', 'month', 'quarter', 'year']

const currentView = computed(() => views.value.find((v) => v.name === biz.value))
const scopedCubes = computed(() => {
  if (!biz.value) return cubes.value.filter((c) => c.type !== 'view')
  const names = currentView.value?.cubes || []
  return names.map((n) => cubes.value.find((c) => c.name === n)).filter(Boolean)
})
const current = computed(() => cubes.value.find((c) => c.name === sel.value))
const timeDims = computed(() => (current.value?.dimensions || []).filter((d) => d.type === 'time'))

async function load() {
  err.value = ''
  try {
    const r = await api('/api/cube/meta')
    cubes.value = r.cubes || []
  } catch (e) {
    err.value = '读不到 Cube 元数据：' + e.message
  }
  try {
    const v = await api('/api/cube/views/detail')
    views.value = v.items || []
    if (!biz.value && views.value.length) biz.value = views.value[0].name
  } catch {
    views.value = []
  }
  pickFirst()
}

function pickFirst() {
  const list = scopedCubes.value
  if (list.length && !list.some((c) => c.name === sel.value)) pick(list[0].name)
}

function pick(name) {
  sel.value = name
  measures.value = []
  dims.value = []
  timeDim.value = ''
  result.value = null
  sqlText.value = ''
  const c = cubes.value.find((x) => x.name === name)
  if (c && c.measures && c.measures.length) measures.value = [c.measures[0].name]
}

function toggle(list, name) {
  const i = list.value.indexOf(name)
  if (i >= 0) list.value.splice(i, 1)
  else list.value.push(name)
}

function body() {
  const b = { measures: [...measures.value], dimensions: [...dims.value] }
  if (timeDim.value) b.time_dimension = timeDim.value + ':' + grain.value
  return b
}

async function run() {
  err.value = ''
  sqlText.value = ''
  result.value = null
  loading.value = true
  try {
    result.value = await api('/api/cube/query', {
      method: 'POST',
      body: JSON.stringify(body()),
    })
  } catch (e) {
    err.value = e.message
  } finally {
    loading.value = false
  }
}

async function showSql() {
  try {
    const r = await api('/api/cube/sql', { method: 'POST', body: JSON.stringify(body()) })
    sqlText.value = r.ok ? r.sql : r.error || '生成失败'
  } catch (e) {
    sqlText.value = e.message
  }
}

const question = ref('')
const asking = ref(false)
const aiErr = ref('')
const aiQuery = ref(null)

const memBusy = ref(false)
const memMsg = ref('')

async function remember() {
  if (!aiQuery.value || !question.value) return
  memBusy.value = true
  memMsg.value = ''
  try {
    await api('/api/cube/memory', {
      method: 'POST',
      body: JSON.stringify({ question: question.value, query: aiQuery.value }),
    })
    memMsg.value = '已存为记忆，下次类似问题会参考'
  } catch (e) {
    memMsg.value = '保存失败：' + e.message
  } finally {
    memBusy.value = false
  }
}

async function ask() {
  if (!question.value.trim()) return
  asking.value = true
  aiErr.value = ''
  aiQuery.value = null
  result.value = null
  sqlText.value = ''
  try {
    const r = await api('/api/cube/ask', {
      method: 'POST',
      body: JSON.stringify({ question: question.value, view: biz.value }),
    })
    if (!r.ok) {
      aiErr.value = r.error || 'AI 查询失败'
      if (r.query) aiQuery.value = r.query
      return
    }
    aiQuery.value = r.query
    result.value = { ok: true, columns: r.columns, rows: r.rows }
  } catch (e) {
    aiErr.value = e.message
  } finally {
    asking.value = false
  }
}

onMounted(load)
watch(biz, pickFirst)
</script>

<template>
  <div class="card">
    <h3>业务</h3>
    <p class="muted">先选业务，后面的手工查询和 AI 提问都只在这个业务的表里进行。</p>
    <p v-if="err" class="bad">{{ err }}</p>
    <select v-model="biz">
      <option v-if="!views.length" value="">（还没有业务）</option>
      <option v-for="v in views" :key="v.name" :value="v.name">
        {{ v.title || v.name }} · {{ v.cubes.length }} 张表
      </option>
    </select>

    <h3 style="margin-top: 22px">问 AI</h3>
    <p v-if="aiErr" class="bad">{{ aiErr }}</p>
    <div class="askrow">
      <input
        v-model="question"
        :disabled="asking"
        placeholder="例如：哪个城市客户最多"
        @keyup.enter="ask"
      />
      <button class="primary" :disabled="asking || !question.trim() || !biz" @click="ask">
        {{ asking ? '思考中…' : '提问' }}
      </button>
    </div>
    <div v-if="aiQuery" class="actions">
      <button :disabled="memBusy" @click="remember">{{ memBusy ? '保存中…' : '记住这次' }}</button>
      <span v-if="memMsg" class="muted small">{{ memMsg }}</span>
    </div>
    <p v-if="aiQuery" class="muted small">
      AI 生成的查询：<code>{{ JSON.stringify(aiQuery) }}</code>
    </p>
  </div>

  <div class="card">
    <h3>手工查询</h3>

    <label class="lbl">表（当前业务里的 {{ scopedCubes.length }} 张）</label>
    <select v-model="sel" @change="pick(sel)">
      <option v-for="c in scopedCubes" :key="c.name" :value="c.name">
        {{ c.name }}<template v-if="c.title"> · {{ c.title }}</template>
      </option>
    </select>

    <label class="lbl">度量（要算的数）</label>
    <div class="chips">
      <label v-for="m in current?.measures || []" :key="m.name" class="chip">
        <input
          type="checkbox"
          :checked="measures.includes(m.name)"
          @change="toggle(measures, m.name)"
        />
        {{ m.name.split('.').pop() }}
      </label>
      <span v-if="!(current?.measures || []).length" class="muted">无</span>
    </div>

    <label class="lbl">维度（按什么分组）</label>
    <div class="chips">
      <label
        v-for="d in (current?.dimensions || []).filter((x) => x.type !== 'time')"
        :key="d.name"
        class="chip"
      >
        <input type="checkbox" :checked="dims.includes(d.name)" @change="toggle(dims, d.name)" />
        {{ d.name.split('.').pop() }}
      </label>
    </div>

    <template v-if="timeDims.length">
      <label class="lbl">时间维度（可选）</label>
      <div class="row2">
        <select v-model="timeDim">
          <option value="">（不按时间）</option>
          <option v-for="d in timeDims" :key="d.name" :value="d.name">
            {{ d.name.split('.').pop() }}
          </option>
        </select>
        <select v-model="grain" :disabled="!timeDim">
          <option v-for="g in GRAINS" :key="g" :value="g">{{ g }}</option>
        </select>
      </div>
    </template>

    <div class="actions">
      <button class="primary" :disabled="loading || !measures.length" @click="run">
        {{ loading ? '查询中…' : '查询' }}
      </button>
      <button :disabled="loading || !measures.length" @click="showSql">查看生成的 SQL</button>
    </div>
  </div>

  <div v-if="result" class="card">
    <p v-if="result.ok" class="ok">✅ {{ result.rows.length }} 行</p>
    <p v-else class="bad">{{ result.error }}</p>
    <table v-if="result.ok && result.rows.length">
      <thead>
        <tr>
          <th v-for="c in result.columns" :key="c">{{ c }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in result.rows.slice(0, 200)" :key="i">
          <td v-for="c in result.columns" :key="c">{{ r[c] }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else-if="result.ok" class="muted">没有数据</p>
  </div>

  <div v-if="sqlText" class="card">
    <label class="lbl">生成的 SQL</label>
    <pre class="raw">{{ sqlText }}</pre>
  </div>
</template>

<style scoped>
.lbl {
  display: block;
  margin: 12px 0 5px;
  font-size: 12.5px;
  color: #57606a;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid #d0d7de;
  border-radius: 16px;
  font-size: 12.5px;
  cursor: pointer;
}
.chip input {
  width: auto;
}
.row2 {
  display: grid;
  grid-template-columns: 1fr 160px;
  gap: 10px;
}
.actions {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.askrow {
  display: flex;
  gap: 10px;
  margin-top: 8px;
}
.askrow input {
  flex: 1;
}
.small {
  font-size: 12px;
  word-break: break-all;
}
.raw {
  max-height: 320px;
  white-space: pre-wrap;
}
</style>
