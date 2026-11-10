<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api, me } from '../store'

const props = defineProps({ project: { type: String, required: true } })
const emit = defineEmits(['saved'])

const rels = ref([])
const models = ref([]) // [{name, columns:[...]}]
const busy = ref(false)
const msg = ref('')
const canEdit = computed(() => ['admin', 'editor'].includes(me.value?.role))

const TYPES = ['MANY_TO_ONE', 'ONE_TO_MANY', 'ONE_TO_ONE', 'MANY_TO_MANY']

const draft = reactive({
  name: '',
  a: '',
  colA: '',
  b: '',
  colB: '',
  join_type: 'MANY_TO_ONE',
})

function colsOf(model) {
  return models.value.find((m) => m.name === model)?.columns || []
}

const condition = computed(() =>
  draft.a && draft.colA && draft.b && draft.colB
    ? `${draft.a}.${draft.colA} = ${draft.b}.${draft.colB}`
    : ''
)

async function load() {
  msg.value = ''
  try {
    const base = `/api/projects/${encodeURIComponent(props.project)}`
    const list = (await api(`${base}/models`)).items || []
    const detailed = []
    for (const m of list) {
      try {
        const j = await api(`${base}/models/${encodeURIComponent(m.name)}/json`)
        detailed.push({
          name: m.name,
          columns: (j.data?.columns || []).map((c) => c.name),
        })
      } catch {
        detailed.push({ name: m.name, columns: [] })
      }
    }
    models.value = detailed
    const r = await api(`${base}/relationships/json`)
    rels.value = r.data?.relationships || []
  } catch (e) {
    msg.value = e.message
  }
}

function add() {
  if (!condition.value) return
  const name = draft.name.trim() || `${draft.a}_${draft.b}`
  if (rels.value.some((r) => r.name === name)) {
    msg.value = `关系名 ${name} 已存在`
    return
  }
  rels.value.push({
    name,
    models: [draft.a, draft.b],
    join_type: draft.join_type,
    condition: condition.value,
  })
  Object.assign(draft, { name: '', a: '', colA: '', b: '', colB: '', join_type: 'MANY_TO_ONE' })
  msg.value = '已加入列表，记得点「保存关系」'
}

function remove(i) {
  rels.value.splice(i, 1)
}

async function save() {
  busy.value = true
  msg.value = ''
  try {
    const r = await api(
      `/api/projects/${encodeURIComponent(props.project)}/relationships/json`,
      { method: 'PUT', body: JSON.stringify({ data: { relationships: rels.value } }) }
    )
    msg.value = `已保存 ${r.count} 条关系，去点「编译」`
    emit('saved')
  } catch (e) {
    msg.value = `保存失败：${e.message}`
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="card sub">
    <div class="head">
      <strong>表关系</strong>
      <span class="muted">决定两张表怎么 join，AI 写 SQL 时靠这个</span>
    </div>

    <p v-if="msg" class="muted">{{ msg }}</p>

    <table v-if="rels.length">
      <thead>
        <tr>
          <th style="width: 180px">关系名</th>
          <th>连接条件</th>
          <th style="width: 130px">类型</th>
          <th style="width: 70px"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in rels" :key="r.name">
          <td><code>{{ r.name }}</code></td>
          <td class="mono">{{ r.condition }}</td>
          <td class="muted">{{ r.join_type }}</td>
          <td>
            <button v-if="canEdit" @click="remove(i)">删</button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">还没有关系。</p>

    <template v-if="canEdit">
      <h4>新建关系</h4>
      <div class="grid">
        <div>
          <label class="lbl">表 A</label>
          <select v-model="draft.a" @change="draft.colA = ''">
            <option value="">（选）</option>
            <option v-for="m in models" :key="m.name" :value="m.name">{{ m.name }}</option>
          </select>
        </div>
        <div>
          <label class="lbl">列 A</label>
          <select v-model="draft.colA">
            <option value="">（选）</option>
            <option v-for="c in colsOf(draft.a)" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>
        <div>
          <label class="lbl">表 B</label>
          <select v-model="draft.b" @change="draft.colB = ''">
            <option value="">（选）</option>
            <option v-for="m in models" :key="m.name" :value="m.name">{{ m.name }}</option>
          </select>
        </div>
        <div>
          <label class="lbl">列 B</label>
          <select v-model="draft.colB">
            <option value="">（选）</option>
            <option v-for="c in colsOf(draft.b)" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>
        <div>
          <label class="lbl">类型</label>
          <select v-model="draft.join_type">
            <option v-for="t in TYPES" :key="t" :value="t">{{ t }}</option>
          </select>
        </div>
        <div>
          <label class="lbl">关系名（可空，自动生成）</label>
          <input v-model="draft.name" placeholder="order_customer" />
        </div>
      </div>

      <p v-if="condition" class="preview">预览：<code>{{ condition }}</code></p>

      <div class="actions">
        <button :disabled="!condition" @click="add">加入列表</button>
        <button class="primary" :disabled="busy" @click="save">
          {{ busy ? '保存中…' : '保存关系' }}
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sub {
  border-color: #bf8700;
  margin-top: 10px;
}
.head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
h4 {
  margin: 16px 0 8px;
  font-size: 14px;
}
.lbl {
  display: block;
  margin: 8px 0 4px;
  font-size: 12.5px;
  color: #57606a;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px 14px;
}
.actions {
  margin-top: 12px;
  display: flex;
  gap: 10px;
}
.preview {
  margin: 10px 0 0;
  font-size: 12.5px;
}
code {
  background: #eaeef2;
  padding: 1px 5px;
  border-radius: 4px;
}
.mono {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12.5px;
}
</style>
