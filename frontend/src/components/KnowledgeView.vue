<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, me } from '../store'

const items = ref([])
const kind = ref('rules')
const sel = ref('')
const text = ref('')
const msg = ref('')
const err = ref('')
const busy = ref(false)
const canEdit = computed(() => ['admin', 'editor'].includes(me.value?.role))

const list = computed(() => items.value.filter((i) => i.kind === kind.value))

async function load() {
  err.value = ''
  try {
    const r = await api('/api/cube/knowledge')
    items.value = r.items || []
  } catch (e) {
    err.value = e.message
  }
}

async function open(item) {
  sel.value = item.kind + '/' + item.name
  text.value = ''
  try {
    const r = await api(`/api/cube/knowledge/${item.kind}/${encodeURIComponent(item.name)}`)
    text.value = r.text
  } catch (e) {
    err.value = e.message
  }
}

async function save() {
  if (!sel.value) return
  const [k, n] = sel.value.split('/')
  busy.value = true
  msg.value = ''
  try {
    await api(`/api/cube/knowledge/${k}/${encodeURIComponent(n)}`, {
      method: 'PUT',
      body: JSON.stringify({ text: text.value }),
    })
    msg.value = '已保存，下次提问就生效'
    await load()
  } catch (e) {
    msg.value = '保存失败：' + e.message
  } finally {
    busy.value = false
  }
}

async function create() {
  const name = prompt(kind.value === 'rules' ? '新规则文件名（如 general）' : '新记忆文件名')
  if (!name) return
  sel.value = kind.value + '/' + name
  text.value =
    kind.value === 'rules'
      ? '# 业务规则\n\n- \n'
      : '---\nnl: \nquery: {}\n---\n\n'
  await save()
  await load()
}

async function remove(item) {
  if (!confirm(`删除 ${item.kind}/${item.name}？`)) return
  try {
    await api(`/api/cube/knowledge/${item.kind}/${encodeURIComponent(item.name)}`, {
      method: 'DELETE',
    })
    if (sel.value === item.kind + '/' + item.name) {
      sel.value = ''
      text.value = ''
    }
    await load()
  } catch (e) {
    alert(e.message)
  }
}

onMounted(load)
</script>

<template>
  <div class="card">
    <h3>知识与记忆</h3>
    <p class="muted">
      「规则」每次提问都会塞进 AI 提示词；「记忆」是历史问答，按相似度召回当参考。
    </p>

    <p v-if="err" class="bad">{{ err }}</p>
    <p v-if="msg" class="ok">{{ msg }}</p>

    <div class="tabs2">
      <button :class="['m', kind === 'rules' ? 'on' : '']" @click="kind = 'rules'">规则</button>
      <button :class="['m', kind === 'sql' ? 'on' : '']" @click="kind = 'sql'">记忆</button>
      <span class="spacer"></span>
      <button v-if="canEdit" @click="create">＋ 新建</button>
    </div>

    <div class="grid">
      <div>
        <label class="lbl">{{ kind === 'rules' ? '规则文件' : '记忆文件' }}（{{ list.length }}）</label>
        <div class="list">
          <div
            v-for="i in list"
            :key="i.kind + i.name"
            :class="['item', sel === i.kind + '/' + i.name ? 'on' : '']"
            @click="open(i)"
          >
            <span class="nm">{{ i.name }}</span>
            <span class="muted small">{{ i.size }} B</span>
            <button v-if="canEdit" class="x" @click.stop="remove(i)">✕</button>
          </div>
          <p v-if="!list.length" class="muted">
            {{ kind === 'rules' ? '还没有规则' : '还没有记忆（在查询页点「记住这次」生成）' }}
          </p>
        </div>
      </div>

      <div>
        <label class="lbl">{{ sel || '（选一个文件）' }}</label>
        <textarea v-model="text" :disabled="!canEdit || !sel" spellcheck="false"></textarea>
        <div class="actions">
          <button v-if="canEdit && sel" class="primary" :disabled="busy" @click="save">
            {{ busy ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tabs2 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 10px 0;
}
.m {
  padding: 4px 14px;
  border-radius: 14px;
  font-size: 13px;
}
.m.on {
  background: #1f883d;
  border-color: #1a7f37;
  color: #fff;
}
.spacer {
  flex: 1;
}
.grid {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 14px;
}
.list {
  border: 1px solid #d0d7de;
  border-radius: 6px;
  padding: 6px;
  max-height: 420px;
  overflow: auto;
}
.item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 7px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12.5px;
}
.item:hover {
  background: #f6f8fa;
}
.item.on {
  background: #ddf4ff;
}
.nm {
  font-family: ui-monospace, Consolas, monospace;
}
.x {
  margin-left: auto;
  padding: 0 6px;
  font-size: 11px;
}
.lbl {
  display: block;
  margin: 6px 0 5px;
  font-size: 12.5px;
  color: #57606a;
}
textarea {
  width: 100%;
  min-height: 360px;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.55;
  padding: 10px;
  border: 1px solid #d0d7de;
  border-radius: 6px;
  background: #fbfcfd;
  resize: vertical;
}
.actions {
  margin-top: 8px;
}
.small {
  font-size: 11.5px;
}
</style>
