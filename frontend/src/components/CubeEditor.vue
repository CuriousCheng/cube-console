<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api, me } from '../store'

const props = defineProps({ project: { type: String, required: true } })
const emit = defineEmits(['saved'])

const cubes = ref([])
const models = ref([])
const sel = ref('')
const data = ref(null)
const busy = ref(false)
const msg = ref('')
const canEdit = computed(() => ['admin', 'editor'].includes(me.value?.role))

const TYPES = ['BIGINT', 'DOUBLE', 'DECIMAL', 'INTEGER', 'VARCHAR']
const newCube = reactive({ name: '', base_object: '' })

function baseCols() {
  return models.value.find((m) => m.name === data.value?.base_object)?.columns || []
}

async function load() {
  msg.value = ''
  try {
    const base = `/api/projects/${encodeURIComponent(props.project)}`
    const cs = await api(`${base}/cubes`)
    cubes.value = cs.cubes || []
    const ms = (await api(`${base}/models`)).items || []
    const detailed = []
    for (const m of ms) {
      try {
        const j = await api(`${base}/models/${encodeURIComponent(m.name)}/json`)
        detailed.push({ name: m.name, columns: (j.data?.columns || []).map((c) => c.name) })
      } catch {
        detailed.push({ name: m.name, columns: [] })
      }
    }
    models.value = detailed
    if (!newCube.base_object && detailed.length) newCube.base_object = detailed[0].name

    if (cubes.value.length) {
      sel.value = sel.value || cubes.value[0].name
      await open(sel.value)
    } else {
      sel.value = ''
      data.value = null
    }
  } catch (e) {
    msg.value = e.message
  }
}

async function open(name) {
  if (!name) return
  sel.value = name
  msg.value = ''
  try {
    const r = await api(
      `/api/projects/${encodeURIComponent(props.project)}/cubes/${encodeURIComponent(name)}/json`
    )
    data.value = r.data
    data.value.measures = data.value.measures || []
    data.value.dimensions = data.value.dimensions || []
    data.value.time_dimensions = data.value.time_dimensions || []
    data.value.properties = data.value.properties || {}
  } catch (e) {
    msg.value = e.message
  }
}

async function create() {
  busy.value = true
  msg.value = ''
  try {
    const r = await api(`/api/projects/${encodeURIComponent(props.project)}/cubes`, {
      method: 'POST',
      body: JSON.stringify(newCube),
    })
    newCube.name = ''
    await load()
    await open(r.cube)
    msg.value = `已创建指标 ${r.cube}`
    emit('saved')
  } catch (e) {
    msg.value = `创建失败：${e.message}`
  } finally {
    busy.value = false
  }
}

async function save() {
  busy.value = true
  msg.value = ''
  try {
    await api(
      `/api/projects/${encodeURIComponent(props.project)}/cubes/${encodeURIComponent(sel.value)}/json`,
      { method: 'PUT', body: JSON.stringify({ data: data.value }) }
    )
    msg.value = '已保存，去点「编译」'
    emit('saved')
  } catch (e) {
    msg.value = `保存失败：${e.message}`
  } finally {
    busy.value = false
  }
}

async function remove(name) {
  if (!confirm(`删除指标 ${name}？`)) return
  try {
    await api(
      `/api/projects/${encodeURIComponent(props.project)}/cubes/${encodeURIComponent(name)}`,
      { method: 'DELETE' }
    )
    if (sel.value === name) sel.value = ''
    await load()
    emit('saved')
  } catch (e) {
    alert(e.message)
  }
}

function addRow(kind) {
  if (kind === 'measures') data.value.measures.push({ name: '', expression: '', type: 'DOUBLE' })
  else if (kind === 'dimensions')
    data.value.dimensions.push({ name: '', expression: '', type: 'VARCHAR' })
  else data.value.time_dimensions.push({ name: '', expression: '', type: 'TIMESTAMP' })
}

function delRow(kind, i) {
  data.value[kind].splice(i, 1)
}

onMounted(load)
</script>

<template>
  <div class="card sub">
    <div class="head">
      <strong>指标</strong>
      <span class="muted">固定计算口径，AI 和指标查询都用它</span>
      <span class="spacer"></span>
      <select v-if="cubes.length" v-model="sel" @change="open(sel)">
        <option v-for="c in cubes" :key="c.name" :value="c.name">{{ c.name }}</option>
      </select>
      <button v-if="sel && canEdit" @click="remove(sel)">删除指标</button>
    </div>

    <p v-if="msg" class="muted">{{ msg }}</p>

    <div v-if="canEdit" class="newrow">
      <input v-model="newCube.name" placeholder="新指标名（小写英文，如 sales_order）" />
      <select v-model="newCube.base_object">
        <option v-for="m in models" :key="m.name" :value="m.name">{{ m.name }}</option>
      </select>
      <button :disabled="!newCube.name || busy" @click="create">新建指标</button>
    </div>

    <template v-if="data">
      <div class="grid2">
        <div>
          <label class="lbl">指标名</label>
          <input :value="data.name" disabled />
        </div>
        <div>
          <label class="lbl">基础表</label>
          <select v-model="data.base_object" :disabled="!canEdit">
            <option v-for="m in models" :key="m.name" :value="m.name">{{ m.name }}</option>
          </select>
        </div>
        <div class="span2">
          <label class="lbl">说明（AI 会读）</label>
          <input v-model="data.properties.description" :disabled="!canEdit" />
        </div>
      </div>

      <div v-for="(label, kind) in { measures: '度量（要算的数）', dimensions: '维度（按什么切）', time_dimensions: '时间维度' }" :key="kind">
        <h4>
          {{ label }}
          <button v-if="canEdit" class="mini" @click="addRow(kind)">＋</button>
        </h4>
        <table v-if="data[kind].length">
          <thead>
            <tr>
              <th style="width: 190px">名称</th>
              <th>表达式</th>
              <th style="width: 130px">类型</th>
              <th style="width: 50px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in data[kind]" :key="i">
              <td><input v-model="row.name" :disabled="!canEdit" /></td>
              <td>
                <input
                  v-model="row.expression"
                  :disabled="!canEdit"
                  :placeholder="kind === 'measures' ? 'SUM(price) / COUNT(*)' : '列名'"
                />
              </td>
              <td>
                <select v-model="row.type" :disabled="!canEdit">
                  <option v-for="t in TYPES" :key="t" :value="t">{{ t }}</option>
                  <option v-if="kind === 'time_dimensions'" value="TIMESTAMP">TIMESTAMP</option>
                </select>
              </td>
              <td><button v-if="canEdit" @click="delRow(kind, i)">✕</button></td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">（空）</p>
      </div>

      <p class="muted hint">
        基础表的列：{{ baseCols().join(', ') || '—' }}
        · 度量名不能和列同名，否则 Wren 报 circular dependency
      </p>

      <div class="actions">
        <button v-if="canEdit" class="primary" :disabled="busy" @click="save">
          {{ busy ? '保存中…' : '保存指标' }}
        </button>
        <span class="muted">保存后点上面的「编译」</span>
      </div>
    </template>

    <p v-else-if="!cubes.length" class="muted">还没有指标，上面新建一个。</p>
  </div>
</template>

<style scoped>
.sub {
  border-color: #8250df;
  margin-top: 10px;
}
.head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.spacer {
  flex: 1;
}
.newrow {
  display: grid;
  grid-template-columns: 1fr 220px 120px;
  gap: 10px;
  margin: 10px 0 16px;
}
h4 {
  margin: 16px 0 8px;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.mini {
  padding: 0 8px;
  font-size: 12px;
  border-radius: 10px;
}
.lbl {
  display: block;
  margin: 8px 0 4px;
  font-size: 12.5px;
  color: #57606a;
}
.grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 14px;
}
.span2 {
  grid-column: span 2;
}
.actions {
  margin-top: 14px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.hint {
  font-size: 12px;
  margin-top: 6px;
}
</style>
