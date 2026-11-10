<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, me } from '../store'
import YamlBox from './YamlBox.vue'

const cubes = ref([])
const sel = ref('')
const data = ref(null)
const busy = ref(false)
const msg = ref('')
const canEdit = computed(() => ['admin', 'editor'].includes(me.value?.role))

const MEASURE_TYPES = ['count', 'count_distinct', 'sum', 'avg', 'min', 'max', 'number']
const DIM_TYPES = ['string', 'number', 'time', 'boolean']

async function loadCubes() {
  try {
    const r = await api('/api/cube/meta')
    cubes.value = (r.cubes || []).filter((c) => c.type !== 'view')
    if (!sel.value && cubes.value.length) sel.value = cubes.value[0].name
  } catch (e) {
    msg.value = e.message
  }
}

async function open(name) {
  if (!name) return
  msg.value = ''
  data.value = null
  try {
    const r = await api(`/api/cube/cube/${encodeURIComponent(name)}/fields`)
    data.value = r.data
  } catch (e) {
    msg.value = e.message
  }
}

async function save() {
  if (!data.value) return
  busy.value = true
  msg.value = ''
  try {
    await api(`/api/cube/cube/${encodeURIComponent(sel.value)}/fields`, {
      method: 'PUT',
      body: JSON.stringify({
        description: data.value.description,
        measures: data.value.measures,
        dimensions: data.value.dimensions,
      }),
    })
    msg.value = '已保存，Cube 会自动重载'
  } catch (e) {
    msg.value = `保存失败：${e.message}`
  } finally {
    busy.value = false
  }
}

function pickPrimary(name) {
  data.value.dimensions.forEach((d) => {
    d.primary_key = d.name === name
  })
}

function addMeasure() {
  data.value.measures.push({
    name: '',
    title: '',
    description: '',
    type: 'sum',
    sql: '',
    isNew: true,
  })
}

function delMeasure(m) {
  if (m.isNew) {
    data.value.measures = data.value.measures.filter((x) => x !== m)
  } else {
    m.deleted = !m.deleted
  }
}

onMounted(async () => {
  await loadCubes()
  if (sel.value) await open(sel.value)
})
</script>

<template>
  <div class="card">
    <h3>字段定义</h3>
    <p class="muted">
      显示名和说明是给 AI 读的。写清楚「这一列是什么、单位、跟哪张表关联」，AI 生成的查询才准。
    </p>

    <p v-if="msg" class="muted">{{ msg }}</p>

    <label class="lbl">表</label>
    <select v-model="sel" @change="open(sel)">
      <option v-for="c in cubes" :key="c.name" :value="c.name">{{ c.name }}</option>
    </select>

    <template v-if="data">
      <p class="muted small">物理表：{{ data.sql_table }}</p>

      <label class="lbl">表说明（AI 会读）</label>
      <input
        v-model="data.description"
        :disabled="!canEdit"
        placeholder="例如：销售订单，一行一单"
      />

      <label class="lbl">
        度量（{{ data.measures.filter((m) => !m.deleted).length }}）
        <button v-if="canEdit" class="mini" @click="addMeasure">＋ 新建度量</button>
      </label>
      <table>
        <thead>
          <tr>
            <th style="width: 130px">名称</th>
            <th style="width: 110px">类型</th>
            <th>表达式（如 SUM(total_amount)）</th>
            <th style="width: 150px">显示名</th>
            <th>说明（AI 会读）</th>
            <th style="width: 50px"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in data.measures" :key="m.name || m._k" :class="{ del: m.deleted }">
            <td>
              <input
                v-if="m.isNew"
                v-model="m.name"
                :disabled="!canEdit"
                placeholder="sales_amount"
                style="width: 100%"
              />
              <code v-else>{{ m.name }}</code>
            </td>
            <td>
              <select v-model="m.type" :disabled="!canEdit">
                <option v-for="t in MEASURE_TYPES" :key="t" :value="t">{{ t }}</option>
              </select>
            </td>
            <td>
              <input
                v-model="m.sql"
                :disabled="!canEdit || m.type === 'count'"
                :placeholder="m.type === 'count' ? '（count 不需要表达式）' : 'SUM(total_amount)'"
              />
            </td>
            <td><input v-model="m.title" :disabled="!canEdit" placeholder="订单数" /></td>
            <td><input v-model="m.description" :disabled="!canEdit" placeholder="这个度量算的是什么" /></td>
            <td>
              <button v-if="canEdit" @click="delMeasure(m)">{{ m.deleted ? '↺' : '✕' }}</button>
            </td>
          </tr>
        </tbody>
      </table>

      <label class="lbl">维度（{{ data.dimensions.length }}）</label>
      <table>
        <thead>
          <tr>
            <th style="width: 150px">名称</th>
            <th style="width: 120px">类型</th>
            <th style="width: 60px">主键</th>
            <th style="width: 170px">显示名</th>
            <th>说明（AI 会读）</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in data.dimensions" :key="d.name">
            <td><code>{{ d.name }}</code></td>
            <td>
              <select v-model="d.type" :disabled="!canEdit">
                <option v-for="t in DIM_TYPES" :key="t" :value="t">{{ t }}</option>
              </select>
            </td>
            <td>
              <input
                type="checkbox"
                :checked="d.primary_key"
                :disabled="!canEdit"
                @change="pickPrimary(d.name)"
              />
            </td>
            <td><input v-model="d.title" :disabled="!canEdit" placeholder="订单号" /></td>
            <td>
              <input
                v-model="d.description"
                :disabled="!canEdit"
                placeholder="这一列是什么，单位、口径、关联关系"
              />
            </td>
          </tr>
        </tbody>
      </table>

      <div class="actions">
        <button v-if="canEdit" class="primary" :disabled="busy" @click="save">
          {{ busy ? '保存中…' : '保存字段定义' }}
        </button>
        <span class="muted">保存后 Cube 自动重载，改动立即生效</span>
      </div>

            <YamlBox kind="cube" :name="sel" />
      <YamlBox kind="preagg" :name="sel" />
    </template>
  </div>
</template>

<style scoped>
.lbl {
  display: block;
  margin: 12px 0 5px;
  font-size: 12.5px;
  color: #57606a;
}
.small {
  font-size: 12px;
}
.actions {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}
code {
  background: #eaeef2;
  padding: 1px 5px;
  border-radius: 4px;
}
.mini {
  margin-left: 10px;
  padding: 0 8px;
  font-size: 12px;
  border-radius: 10px;
}
tr.del td {
  opacity: 0.45;
  text-decoration: line-through;
}
table input[type='checkbox'] {
  width: auto;
}
</style>
