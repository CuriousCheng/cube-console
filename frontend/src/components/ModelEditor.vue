<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, me } from '../store'

const props = defineProps({ project: { type: String, required: true }, model: { type: String, required: true } })
const emit = defineEmits(['closed', 'saved'])

const data = ref(null)
const busy = ref(false)
const msg = ref('')
const tab = ref('form') // form | text
const text = ref('')
const canEdit = ['admin', 'editor'].includes(me.value?.role)

const TYPES = ['INTEGER', 'BIGINT', 'DOUBLE', 'DECIMAL', 'VARCHAR', 'BOOLEAN', 'DATE', 'TIMESTAMP']

const form = reactive({
  description: '',
  primary_key: '',
  columns: [],
})

async function load() {
  msg.value = ''
  try {
    const r = await api(
      `/api/projects/${encodeURIComponent(props.project)}/models/${encodeURIComponent(props.model)}/json`
    )
    data.value = r.data
    form.description = r.data?.properties?.description || ''
    form.primary_key = r.data?.primary_key || ''
    form.columns = (r.data?.columns || []).map((c) => ({
      name: c.name,
      type: c.type || 'VARCHAR',
      not_null: !!c.not_null,
      is_primary_key: !!c.is_primary_key,
      description: c.properties?.description || '',
    }))
    const t = await api(
      `/api/projects/${encodeURIComponent(props.project)}/models/${encodeURIComponent(props.model)}`
    )
    text.value = t.text
  } catch (e) {
    msg.value = e.message
  }
}

function pickPrimary(name) {
  form.primary_key = name
  form.columns.forEach((c) => {
    if (c.name === name) {
      c.is_primary_key = true
      c.not_null = true
    } else {
      c.is_primary_key = false
    }
  })
}

async function save() {
  busy.value = true
  msg.value = ''
  try {
    const columns = form.columns.map((c) => ({
      name: c.name,
      type: c.type,
      is_calculated: false,
      not_null: c.not_null,
      properties: c.description ? { description: c.description } : {},
      ...(c.is_primary_key ? { is_primary_key: true } : {}),
    }))

    const out = {
      ...(data.value || {}),
      name: props.model,
      properties: { ...(data.value?.properties || {}), description: form.description },
      columns,
      cached: data.value?.cached ?? false,
    }
    if (form.primary_key) out.primary_key = form.primary_key
    else delete out.primary_key

    await api(
      `/api/projects/${encodeURIComponent(props.project)}/models/${encodeURIComponent(props.model)}/json`,
      { method: 'PUT', body: JSON.stringify({ data: out }) }
    )
    msg.value = '已保存'
    emit('saved')
    await load()
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
      <strong>表：{{ model }}</strong>
      <span class="muted">{{ data?.table_reference?.catalog }}.{{ data?.table_reference?.schema }}.{{ data?.table_reference?.table }}</span>
      <span class="spacer"></span>
      <button :class="['t', tab === 'form' ? 'on' : '']" @click="tab = 'form'">表单</button>
      <button :class="['t', tab === 'text' ? 'on' : '']" @click="tab = 'text'">文本</button>
      <button @click="$emit('closed')">收起</button>
    </div>

    <p v-if="msg" class="muted">{{ msg }}</p>

    <template v-if="tab === 'form'">
      <div class="grid2">
        <div>
          <label class="lbl">表说明（AI 会读）</label>
          <input v-model="form.description" :disabled="!canEdit" placeholder="例如：销售订单，一行一单" />
        </div>
        <div>
          <label class="lbl">主键</label>
          <select v-model="form.primary_key" :disabled="!canEdit" @change="pickPrimary(form.primary_key)">
            <option value="">（无）</option>
            <option v-for="c in form.columns" :key="c.name" :value="c.name">{{ c.name }}</option>
          </select>
        </div>
      </div>

      <label class="lbl">列（{{ form.columns.length }}）</label>
      <table>
        <thead>
          <tr>
            <th style="width: 160px">列名</th>
            <th style="width: 130px">类型</th>
            <th style="width: 60px">主键</th>
            <th style="width: 60px">非空</th>
            <th>说明（AI 会读）</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in form.columns" :key="c.name">
            <td><code>{{ c.name }}</code></td>
            <td>
              <select v-model="c.type" :disabled="!canEdit">
                <option v-for="t in TYPES" :key="t" :value="t">{{ t }}</option>
              </select>
            </td>
            <td><input type="checkbox" :checked="c.is_primary_key" :disabled="!canEdit" @change="pickPrimary(c.name)" /></td>
            <td><input v-model="c.not_null" type="checkbox" :disabled="!canEdit" /></td>
            <td>
              <input v-model="c.description" :disabled="!canEdit" placeholder="这一列是什么，单位、口径、关联关系" />
            </td>
          </tr>
        </tbody>
      </table>

      <div class="actions">
        <button v-if="canEdit" class="primary" :disabled="busy" @click="save">
          {{ busy ? '保存中…' : '保存模型' }}
        </button>
        <span class="muted">保存后记得点上面的「编译」</span>
      </div>
    </template>

    <template v-else>
      <pre class="raw">{{ text }}</pre>
      <p class="muted">想改结构或写复杂字段，用主编辑器打开 models/{{ model }}/metadata.yml</p>
    </template>
  </div>
</template>

<style scoped>
.sub {
  border-color: #0969da;
  margin-top: 10px;
}
.head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.spacer {
  flex: 1;
}
.lbl {
  display: block;
  margin: 10px 0 5px;
  font-size: 13px;
  color: #57606a;
}
.grid2 {
  display: grid;
  grid-template-columns: 1fr 220px;
  gap: 12px;
}
.t {
  padding: 4px 12px;
  border-radius: 14px;
  font-size: 12px;
}
.t.on {
  background: #0969da;
  border-color: #0969da;
  color: #fff;
}
.actions {
  margin-top: 14px;
  display: flex;
  align-items: center;
  gap: 12px;
}
code {
  background: #eaeef2;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 12.5px;
}
.raw {
  max-height: 420px;
}
table input[type='checkbox'] {
  width: auto;
}
</style>
