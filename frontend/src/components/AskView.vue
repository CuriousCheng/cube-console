<script setup>
import { onMounted, ref, watch } from 'vue'
import { api } from '../store'

const projects = ref([])
const project = ref('')
const question = ref('')
const loading = ref(false)
const result = ref(null)
const history = ref([])
const remembering = ref(false)
const remembered = ref(false)
const lastQuestion = ref('')

// ── 指标查询模式 ──────────────────────────────────────
const mode = ref('ask') // ask | cube
const cubes = ref([])
const cubeErr = ref('')
const cubeSel = ref('')
const selMeasures = ref([])
const selDims = ref([])
const useTime = ref(false)
const timeDim = ref('')
const timeGrain = ref('month')
const GRAINS = ['day', 'week', 'month', 'quarter', 'year']

function currentCube() {
  return cubes.value.find((c) => c.name === cubeSel.value)
}

async function loadCubes() {
  if (!project.value) return
  cubeErr.value = ''
  try {
    const r = await api(`/api/projects/${encodeURIComponent(project.value)}/cubes`)
    cubes.value = r.cubes || []
    if (cubes.value.length) {
      cubeSel.value = cubes.value[0].name
      pickCube(cubeSel.value)
    } else {
      cubeSel.value = ''
      selMeasures.value = []
      selDims.value = []
    }
  } catch (e) {
    cubeErr.value = e.message
    cubes.value = []
  }
}

function pickCube(name) {
  const c = cubes.value.find((x) => x.name === name)
  selMeasures.value = c?.measures?.slice(0, 1) || []
  selDims.value = []
  useTime.value = false
  timeDim.value = c?.time_dimensions?.[0] || ''
}

function toggle(list, name) {
  const i = list.value.indexOf(name)
  if (i >= 0) list.value.splice(i, 1)
  else list.value.push(name)
}

async function runCube() {
  if (!cubeSel.value || !selMeasures.value.length) return
  loading.value = true
  result.value = null
  remembered.value = false
  lastQuestion.value = `${cubeSel.value} 的 ${selMeasures.value.join(', ')}`
  const started = Date.now()
  try {
    const body = {
      cube: cubeSel.value,
      measures: [...selMeasures.value],
      dimensions: [...selDims.value],
    }
    if (useTime.value && timeDim.value) {
      body.time_dimension = `${timeDim.value}:${timeGrain.value}`
    }
    const r = await api(`/api/projects/${encodeURIComponent(project.value)}/cube`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
    result.value = r
    history.value.unshift({
      q: lastQuestion.value,
      project: project.value,
      ok: r.ok,
      ms: Date.now() - started,
    })
    if (history.value.length > 8) history.value.pop()
  } catch (e) {
    result.value = { ok: false, error: e.message }
  } finally {
    loading.value = false
  }
}

async function rememberThis() {
  if (!result.value?.sql) return
  remembering.value = true
  try {
    await api(`/api/projects/${encodeURIComponent(project.value)}/remember`, {
      method: 'POST',
      body: JSON.stringify({ question: lastQuestion.value, sql: result.value.sql }),
    })
    remembered.value = true
  } catch (e) {
    alert(e.message)
  } finally {
    remembering.value = false
  }
}

async function load() {
  try {
    projects.value = (await api('/api/projects')).items
    if (!project.value && projects.value.length) project.value = projects.value[0].name
  } catch (e) {
    console.error(e)
  }
}

async function ask() {
  if (!project.value || !question.value.trim()) return
  loading.value = true
  result.value = null
  remembered.value = false
  const q = question.value.trim()
  lastQuestion.value = q
  const started = Date.now()
  try {
    const r = await api('/api/ask', {
      method: 'POST',
      body: JSON.stringify({ project: project.value, question: q }),
    })
    result.value = r
    history.value.unshift({ q, project: project.value, ok: r.ok, ms: Date.now() - started })
    if (history.value.length > 8) history.value.pop()
  } catch (e) {
    result.value = { ok: false, error: e.message }
  } finally {
    loading.value = false
  }
}

function useHistory(h) {
  project.value = h.project
  question.value = h.q
}

onMounted(async () => {
  await load()
  await loadCubes()
})

watch(project, async () => {
  await loadCubes()
})
</script>

<template>
  <div class="card">
    <div class="row">
      <div class="proj">
        <label class="lbl">业务</label>
        <select v-model="project">
          <option v-if="!projects.length" value="">（还没有业务）</option>
          <option v-for="p in projects" :key="p.name" :value="p.name">
            {{ p.name }}<template v-if="p.mcp?.running"> · 已启用</template>
          </option>
        </select>
      </div>
      <div class="spacer"></div>
    </div>

    <div class="modes">
      <button :class="['m', mode === 'ask' ? 'on' : '']" @click="mode = 'ask'">自由提问</button>
      <button :class="['m', mode === 'cube' ? 'on' : '']" @click="mode = 'cube'">指标查询</button>
    </div>

    <template v-if="mode === 'ask'">
      <label class="lbl">问题</label>
      <div class="askrow">
        <input
          v-model="question"
          :disabled="loading || !project"
          placeholder="例如：哪个技师工单最多"
          @keyup.enter="ask"
        />
        <button class="primary" :disabled="loading || !project || !question.trim()" @click="ask">
          {{ loading ? '查询中…' : '提问' }}
        </button>
      </div>
    </template>

    <template v-else>
      <p v-if="cubeErr" class="bad">{{ cubeErr }}</p>
      <p v-else-if="!cubes.length" class="muted">
        这个业务还没有指标。到「设置 → 业务 → 编辑 → 指标」建一个。
      </p>

      <template v-else>
        <label class="lbl">指标</label>
        <select v-model="cubeSel" @change="pickCube(cubeSel)">
          <option v-for="c in cubes" :key="c.name" :value="c.name">
            {{ c.name }}（基于 {{ c.base_object }}）
          </option>
        </select>

        <label class="lbl">度量（勾一个或多个）</label>
        <div class="chips">
          <label v-for="m in currentCube()?.measures || []" :key="m" class="chip">
            <input
              type="checkbox"
              :checked="selMeasures.includes(m)"
              @change="toggle(selMeasures, m)"
            />
            {{ m }}
          </label>
        </div>

        <label class="lbl">维度（可选）</label>
        <div class="chips">
          <label v-for="d in currentCube()?.dimensions || []" :key="d" class="chip">
            <input type="checkbox" :checked="selDims.includes(d)" @change="toggle(selDims, d)" />
            {{ d }}
          </label>
          <span v-if="!(currentCube()?.dimensions || []).length" class="muted">无</span>
        </div>

        <template v-if="(currentCube()?.time_dimensions || []).length">
          <label class="lbl">
            <input v-model="useTime" type="checkbox" />
            按时间分组
          </label>
          <div v-if="useTime" class="askrow">
            <select v-model="timeDim">
              <option v-for="t in currentCube()?.time_dimensions || []" :key="t" :value="t">
                {{ t }}
              </option>
            </select>
            <select v-model="timeGrain">
              <option v-for="g in GRAINS" :key="g" :value="g">{{ g }}</option>
            </select>
          </div>
        </template>

        <div class="actions">
          <button class="primary" :disabled="loading || !selMeasures.length" @click="runCube">
            {{ loading ? '查询中…' : '查询指标' }}
          </button>
          <span class="muted">不经过 AI，直接用 cube 口径生成 SQL</span>
        </div>
      </template>
    </template>

    <p v-if="!projects.length" class="muted">
      还没有业务。先到右上角「设置 → 业务」建一个，并给它加上表。
    </p>
  </div>

  <div v-if="result" class="card">
    <p v-if="result.ok" class="ok">
      ✅ 查询成功
      <span v-if="result.recalled" class="muted">· 参考了 {{ result.recalled }} 条历史问答</span>
    </p>
    <p v-else class="bad">❌ {{ result.error }}</p>

    <div v-if="result.ok && result.sql" class="remember">
      <button :disabled="remembering || remembered" @click="rememberThis">
        {{ remembered ? '✓ 已存入记忆' : remembering ? '保存中…' : '记住这次' }}
      </button>
      <span class="muted">存进业务的 knowledge/sql/，下次问类似问题会参考</span>
    </div>

    <template v-if="result.sql">
      <label class="lbl">生成的 SQL</label>
      <pre>{{ result.sql }}</pre>
    </template>

    <template v-if="result.data">
      <label class="lbl">
        结果（{{ result.data.row_count }} 行{{ result.data.truncated ? '，已截断' : '' }}）
      </label>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th v-for="c in result.data.columns" :key="c">{{ c }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in result.data.rows" :key="i">
              <td v-for="c in result.data.columns" :key="c">{{ row[c] }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <template v-if="result.raw">
      <label class="lbl">原始输出</label>
      <pre>{{ result.raw }}</pre>
    </template>
  </div>

  <div v-if="history.length" class="card">
    <h3>最近提问</h3>
    <ul class="hist">
      <li v-for="(h, i) in history" :key="i" @click="useHistory(h)">
        <span :class="h.ok ? 'ok' : 'bad'">{{ h.ok ? '✓' : '✗' }}</span>
        {{ h.q }}
        <span class="muted">· {{ h.project }} · {{ h.ms }}ms</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.row {
  display: flex;
  align-items: flex-end;
  gap: 12px;
}
.proj {
  width: 320px;
}
.spacer {
  flex: 1;
}
.lbl {
  display: block;
  margin: 12px 0 5px;
  font-size: 13px;
  color: #57606a;
}
.askrow {
  display: flex;
  gap: 10px;
}
.askrow input {
  flex: 1;
}
.table-wrap {
  overflow: auto;
  max-height: 420px;
}
.hist {
  list-style: none;
  margin: 0;
  padding: 0;
}
.hist li {
  padding: 7px 4px;
  border-bottom: 1px solid #eaeef2;
  font-size: 13px;
  cursor: pointer;
}
.hist li:hover {
  background: #f6f8fa;
}
.remember {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 0 4px;
  font-size: 12px;
}
.modes {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}
.m {
  padding: 5px 14px;
  border-radius: 16px;
  font-size: 13px;
}
.m.on {
  background: #1f883d;
  border-color: #1a7f37;
  color: #fff;
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
  background: #fff;
  font-size: 12.5px;
  cursor: pointer;
}
.chip input {
  width: auto;
}
.actions {
  margin-top: 14px;
  display: flex;
  align-items: center;
  gap: 10px;
}
</style>
