<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, me } from '../store'
import YamlBox from './YamlBox.vue'

const cubes = ref([])
const joins = ref([])
const busy = ref(false)
const msg = ref('')
const err = ref('')
const canEdit = computed(() => ['admin', 'editor'].includes(me.value?.role))

const a = ref('')
const colA = ref('')
const b = ref('')
const colB = ref('')
const rel = ref('many_to_one')
const RELS = ['many_to_one', 'one_to_many', 'one_to_one']

const tables = computed(() => cubes.value.filter((c) => c.type !== 'view'))

function colsOf(n) {
  const c = cubes.value.find((x) => x.name === n)
  return (c?.dimensions || []).map((d) => d.name.split('.').pop())
}

const preview = computed(() =>
  a.value && colA.value && b.value && colB.value
    ? `{CUBE}.${colA.value} = {${b.value}}.${colB.value}`
    : ''
)

async function load() {
  err.value = ''
  try {
    const r = await api('/api/cube/meta')
    cubes.value = r.cubes || []
  } catch (e) {
    err.value = `读不到 Cube 元数据：${e.message}`
  }
  try {
    const j = await api('/api/cube/joins')
    joins.value = j.items || []
  } catch {
    joins.value = []
  }
}

async function save() {
  msg.value = ''
  err.value = ''
  busy.value = true
  try {
    await api('/api/cube/join', {
      method: 'POST',
      body: JSON.stringify({
        cube: a.value,
        target: b.value,
        from_column: colA.value,
        to_column: colB.value,
        relationship: rel.value,
      }),
    })
    msg.value = '已保存，Cube 会自动重载'
    colA.value = ''
    colB.value = ''
    await load()
  } catch (e) {
    err.value = e.message
  } finally {
    busy.value = false
  }
}

async function remove(j) {
  if (!confirm(`删除关系 ${j.cube} → ${j.name}？`)) return
  try {
    await api(
      `/api/cube/join?cube=${encodeURIComponent(j.cube)}&name=${encodeURIComponent(j.name)}`,
      { method: 'DELETE' }
    )
    await load()
  } catch (e) {
    alert(e.message)
  }
}

onMounted(load)
</script>

<template>
  <div class="card">
    <h3>表关系</h3>
    <p class="muted">
      两张表怎么 join。不配关系，跨表查询会报「Can't find join path」。
      表 A 是「多」的一方（一对多里的多）。
    </p>

    <p v-if="err" class="bad">{{ err }}</p>
    <p v-if="msg" class="ok">{{ msg }}</p>

    <table v-if="joins.length">
      <thead>
        <tr>
          <th style="width: 150px">从（多）</th>
          <th style="width: 150px">到（一）</th>
          <th>条件</th>
          <th style="width: 130px">类型</th>
          <th style="width: 130px"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="j in joins" :key="j.cube + j.name">
          <td><code>{{ j.cube }}</code></td>
          <td><code>{{ j.name }}</code></td>
          <td class="muted small">{{ j.sql }}</td>
          <td class="muted small">{{ j.relationship }}</td>
          <td>
            <button v-if="canEdit" @click="remove(j)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">还没有关系</p>

    <div v-if="canEdit" class="grid">
      <div>
        <label class="lbl">表 A（多的一方）</label>
        <select v-model="a" @change="colA = ''">
          <option value="">（选）</option>
          <option v-for="c in tables" :key="c.name" :value="c.name">{{ c.name }}</option>
        </select>
      </div>
      <div>
        <label class="lbl">字段 A</label>
        <select v-model="colA">
          <option value="">（选）</option>
          <option v-for="c in colsOf(a)" :key="c" :value="c">{{ c }}</option>
        </select>
      </div>
      <div>
        <label class="lbl">表 B（一的一方）</label>
        <select v-model="b" @change="colB = ''">
          <option value="">（选）</option>
          <option v-for="c in tables" :key="c.name" :value="c.name">{{ c.name }}</option>
        </select>
      </div>
      <div>
        <label class="lbl">字段 B</label>
        <select v-model="colB">
          <option value="">（选）</option>
          <option v-for="c in colsOf(b)" :key="c" :value="c">{{ c }}</option>
        </select>
      </div>
      <div>
        <label class="lbl">关系类型</label>
        <select v-model="rel">
          <option v-for="r in RELS" :key="r" :value="r">{{ r }}</option>
        </select>
      </div>
      <div class="act">
        <button class="primary" :disabled="!preview || busy" @click="save">
          {{ busy ? '保存中…' : '保存关系' }}
        </button>
      </div>
    </div>

    <p v-if="preview" class="muted small">预览：<code>{{ preview }}</code></p>

    <YamlBox kind="all" />
  </div>
</template>

<style scoped>
.lbl {
  display: block;
  margin: 10px 0 5px;
  font-size: 12.5px;
  color: #57606a;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 10px 14px;
  margin-top: 14px;
}
.act {
  display: flex;
  align-items: flex-end;
}
.small {
  font-size: 12px;
}
code {
  background: #eaeef2;
  padding: 1px 5px;
  border-radius: 4px;
}
</style>
