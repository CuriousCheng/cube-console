<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, me } from '../store'
import ModelEditor from './ModelEditor.vue'
import RelationshipEditor from './RelationshipEditor.vue'
import CubeEditor from './CubeEditor.vue'

const props = defineProps({ project: { type: String, required: true } })
const emit = defineEmits(['closed', 'changed'])

const models = ref([])
const editing = ref('')
const files = ref([])
const current = ref('') // 当前编辑的文件相对路径
const text = ref('')
const dirty = ref(false)

const sources = ref([])
const schemas = ref([])
const tables = ref([])
const pick = reactive({ datasource_id: '', schema_name: '', table: '', description: '' })

const msg = ref('')
const busy = ref('')

const canEdit = computed(() => ['admin', 'editor'].includes(me.value?.role))

const GROUPS = [
  { key: 'relationships.yml', label: '关系' },
  { key: 'knowledge/rules/', label: '知识' },
  { key: 'knowledge/sql/', label: '记忆' },
  { key: 'cubes/', label: '指标' },
]

const lastGroup = ref('cubes/')

async function newFile() {
  if (!canEdit.value) return
  const DEF = {
    'relationships.yml': 'relationships.yml',
    'knowledge/rules/': 'knowledge/rules/rule2.md',
    'knowledge/sql/': 'knowledge/sql/q2.md',
    'cubes/': 'cubes/' + (prompt('新指标名（英文小写，用作目录名）', 'sales_model') || '') +
      '/metadata.yml',
  }
  let def = DEF[lastGroup.value] || 'knowledge/rules/new.md'
  if (def.includes('//')) return
  const path = prompt('新建文件路径（相对业务目录）：', def)
  if (!path) return
  await saveAs(path, '')
}

async function loadModels() {
  models.value = (await api(`/api/projects/${encodeURIComponent(props.project)}/models`)).items
}

async function loadFiles() {
  files.value = (await api(`/api/projects/${encodeURIComponent(props.project)}/files`)).items
}

async function loadSources() {
  if (!canEdit.value) return
  sources.value = (await api('/api/datasources')).items
  if (!pick.datasource_id && sources.value.length) pick.datasource_id = sources.value[0].id
}

async function loadSchemas() {
  if (!pick.datasource_id) return
  pick.schema_name = ''
  pick.table = ''
  tables.value = []
  try {
    schemas.value = (await api(`/api/datasources/${pick.datasource_id}/schemas`)).items
  } catch (e) {
    msg.value = e.message
  }
}

async function loadTables() {
  if (!pick.datasource_id || !pick.schema_name) return
  pick.table = ''
  try {
    tables.value = (
      await api(
        `/api/datasources/${pick.datasource_id}/tables?schema_name=${encodeURIComponent(pick.schema_name)}`
      )
    ).items
  } catch (e) {
    msg.value = e.message
  }
}

async function addModel() {
  if (!pick.table) return
  busy.value = 'add'
  msg.value = ''
  try {
    const r = await api(`/api/projects/${encodeURIComponent(props.project)}/models`, {
      method: 'POST',
      body: JSON.stringify({
        datasource_id: pick.datasource_id,
        schema_name: pick.schema_name,
        table: pick.table,
        description: pick.description,
        model_name: pick.table,
      }),
    })
    msg.value = `已加入表 ${r.model}（${r.columns} 列）`
    pick.description = ''
    await loadModels()
    await loadFiles()
    emit('changed')
  } catch (e) {
    msg.value = `失败：${e.message}`
  } finally {
    busy.value = ''
  }
}

async function removeModel(m) {
  if (!confirm(`从业务里移除表 ${m.name}？`)) return
  try {
    await api(`/api/projects/${encodeURIComponent(props.project)}/models/${m.name}`, {
      method: 'DELETE',
    })
    await loadModels()
    await loadFiles()
    emit('changed')
  } catch (e) {
    alert(e.message)
  }
}

async function openFile(path) {
  if (dirty.value && !confirm('当前文件有未保存修改，放弃？')) return
  current.value = path
  const r = await api(
    `/api/projects/${encodeURIComponent(props.project)}/file?path=${encodeURIComponent(path)}`
  )
  text.value = r.text
  dirty.value = false
}

async function openGroup(g) {
  lastGroup.value = g.key
  const hit = files.value.find((f) => f.path === g.key || f.path.startsWith(g.key))
  if (hit) return openFile(hit.path)
  if (!canEdit.value) return

  const DEFAULTS = {
    'relationships.yml': 'relationships.yml',
    'knowledge/rules/': 'knowledge/rules/rule1.md',
    'knowledge/sql/': 'knowledge/sql/q1.md',
    'cubes/': 'cubes/sales_order/metadata.yml',
  }
  const STARTER = {
    'cubes/': `name: sales_order
base_object: sales_orders

measures:
  - name: total_amount
    expression: SUM(total_amount)
    type: DOUBLE

dimensions:
  - name: status
    expression: status
    type: VARCHAR

properties:
  description: 指标说明
`,
  }

  const name = prompt('新建文件，路径（相对业务目录）：', DEFAULTS[g.key] || g.key)
  if (!name) return
  await saveAs(name, STARTER[g.key] || '')
}

async function saveAs(path, content) {
  try {
    await api(`/api/projects/${encodeURIComponent(props.project)}/file`, {
      method: 'PUT',
      body: JSON.stringify({ path, text: content }),
    })
    await loadFiles()
    await openFile(path)
  } catch (e) {
    msg.value = e.message
  }
}

async function saveFile() {
  if (!current.value) return
  busy.value = 'save'
  try {
    await api(`/api/projects/${encodeURIComponent(props.project)}/file`, {
      method: 'PUT',
      body: JSON.stringify({ path: current.value, text: text.value }),
    })
    dirty.value = false
    msg.value = '已保存'
    emit('changed')
  } catch (e) {
    msg.value = `保存失败：${e.message}`
  } finally {
    busy.value = ''
  }
}

async function build() {
  busy.value = 'build'
  msg.value = ''
  try {
    const r = await api(`/api/projects/${encodeURIComponent(props.project)}/build`, {
      method: 'POST',
    })
    msg.value = r.ok ? `编译成功：${r.output.split('\n')[0]}` : `编译失败：${r.output}`
    emit('changed')
  } catch (e) {
    msg.value = e.message
  } finally {
    busy.value = ''
  }
}

async function indexMemory() {
  busy.value = 'index'
  msg.value = ''
  try {
    const r = await api(`/api/projects/${encodeURIComponent(props.project)}/index`, {
      method: 'POST',
    })
    msg.value = r.ok
      ? `索引完成：${(r.output || '').split('\n').slice(-2).join(' ').slice(0, 160)}`
      : `索引失败：${r.output}`
  } catch (e) {
    msg.value = `索引失败：${e.message}`
  } finally {
    busy.value = ''
  }
}

watch(
  () => props.project,
  async () => {
    await loadModels()
    await loadFiles()
  },
  { immediate: true }
)

onMounted(async () => {
  await loadSources()
  if (pick.datasource_id) await loadSchemas()
})
</script>

<template>
  <div class="card panel">
    <div class="head">
      <h3>业务：{{ project }}</h3>
      <span class="spacer"></span>
      <button :disabled="busy === 'build'" @click="build">
        {{ busy === 'build' ? '编译中…' : '编译' }}
      </button>
      <button :disabled="busy === 'index'" @click="indexMemory">
        {{ busy === 'index' ? '建索引中…' : '建记忆索引' }}
      </button>
      <button @click="$emit('closed')">收起</button>
    </div>

    <p v-if="msg" class="muted">{{ msg }}</p>

    <h4>表（{{ models.length }}）</h4>
    <table v-if="models.length">
      <thead>
        <tr>
          <th>表名</th>
          <th>来源</th>
          <th>列</th>
          <th>说明</th>
          <th style="width: 80px"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="m in models" :key="m.name">
          <td><strong>{{ m.name }}</strong></td>
          <td class="muted">{{ m.catalog }}.{{ m.schema }}.{{ m.table }}</td>
          <td>{{ m.columns }}</td>
          <td class="muted">{{ m.description }}</td>
          <td>
            <button @click="editing = editing === m.name ? '' : m.name">
              {{ editing === m.name ? '收起' : '编辑' }}
            </button>
            <button v-if="canEdit" @click="removeModel(m)">移除</button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">还没有表。下面从数据源里挑一张加进来。</p>

    <ModelEditor
      v-if="editing"
      :project="project"
      :model="editing"
      @closed="editing = ''"
      @saved="loadModels"
    />

    <RelationshipEditor
      v-if="models.length"
      :project="project"
      @saved="loadFiles"
    />

    <CubeEditor
      v-if="models.length"
      :project="project"
      @saved="loadFiles"
    />

    <template v-if="canEdit">
      <h4>加入表</h4>
      <div class="grid3">
        <div>
          <label class="lbl">数据源</label>
          <select v-model="pick.datasource_id" @change="loadSchemas">
            <option v-for="s in sources" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </div>
        <div>
          <label class="lbl">库 / schema</label>
          <select v-model="pick.schema_name" @change="loadTables">
            <option value="">（选）</option>
            <option v-for="s in schemas" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
        <div>
          <label class="lbl">表</label>
          <select v-model="pick.table">
            <option value="">（选）</option>
            <option v-for="t in tables" :key="t" :value="t">{{ t }}</option>
          </select>
        </div>
        <div class="span3">
          <label class="lbl">表说明（可空）</label>
          <input v-model="pick.description" placeholder="例如：名人名言，一行一条" />
        </div>
      </div>
      <div class="actions">
        <button class="primary" :disabled="!pick.table || busy === 'add'" @click="addModel">
          {{ busy === 'add' ? '加入中…' : '加入这个业务' }}
        </button>
      </div>
    </template>

    <h4>业务文件</h4>
    <div class="quick">
      <button v-for="g in GROUPS" :key="g.key" class="ghost" @click="openGroup(g)">
        {{ g.label }}
      </button>
      <button v-if="canEdit" class="ghost" @click="newFile">＋ 新建文件</button>
    </div>

    <div class="editor">
      <div class="tree">
        <div
          v-for="f in files"
          :key="f.path"
          :class="['fitem', current === f.path ? 'on' : '']"
          @click="openFile(f.path)"
        >
          {{ f.path }}
        </div>
        <p v-if="!files.length" class="muted">还没有文件</p>
      </div>
      <div class="pane">
        <p v-if="!current" class="muted">左边选一个文件</p>
        <template v-else>
          <div class="fileref">
            <code>{{ current }}</code>
            <span v-if="dirty" class="muted">· 未保存</span>
            <span class="spacer"></span>
            <button v-if="canEdit" class="primary" :disabled="busy === 'save'" @click="saveFile">
              {{ busy === 'save' ? '保存中…' : '保存' }}
            </button>
          </div>
          <textarea v-model="text" rows="16" @input="dirty = true"></textarea>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.panel {
  border-color: #1f883d;
}
.head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.head h3 {
  margin: 0;
}
.spacer {
  flex: 1;
}
h4 {
  margin: 18px 0 8px;
  font-size: 14px;
}
.lbl {
  display: block;
  margin: 8px 0 5px;
  font-size: 13px;
  color: #57606a;
}
.grid3 {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 10px 14px;
}
.span3 {
  grid-column: span 3;
}
.actions {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.quick {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.ghost {
  background: #f6f8fa;
}
.editor {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 12px;
}
.tree {
  border: 1px solid #d0d7de;
  border-radius: 6px;
  background: #fff;
  max-height: 340px;
  overflow: auto;
  padding: 6px;
  font-size: 12px;
}
.fitem {
  padding: 5px 7px;
  border-radius: 4px;
  cursor: pointer;
  word-break: break-all;
}
.fitem:hover {
  background: #f6f8fa;
}
.fitem.on {
  background: #dafbe1;
  font-weight: 600;
}
.pane {
  min-width: 0;
}
.fileref {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
}
textarea {
  width: 100%;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  padding: 10px;
  border: 1px solid #d0d7de;
  border-radius: 6px;
  resize: vertical;
}
</style>
