<script setup>
import { computed, ref, watch } from 'vue'
import { api, me } from '../store'

const props = defineProps({
  kind: { type: String, required: true }, // cube | joins | all | view
  name: { type: String, default: '' },
})

const open = ref(false)
const text = ref('')
const msg = ref('')
const busy = ref(false)
const canEdit = computed(() => ['admin', 'editor'].includes(me.value?.role))

const needName = computed(
  () =>
    props.kind === 'cube' || props.kind === 'joins' || props.kind === 'view' || props.kind === 'preagg'
)
const visible = computed(() => (needName.value ? !!props.name : true))
const label = computed(() => {
  if (props.kind === 'all') return '全部关系'
  if (props.kind === 'preagg') return props.name + ' 的预聚合'
  if (props.kind === 'joins') return props.name + ' 的 joins'
  if (props.kind === 'cube') return props.name
  return 'views/' + props.name + '.yml'
})

const url = computed(() => {
  const n = encodeURIComponent(props.name)
  if (props.kind === 'preagg') return '/api/cube/preagg/' + n
  if (props.kind === 'all') return '/api/cube/all-joins/yaml'
  if (props.kind === 'joins') return '/api/cube/joins/' + n + '/yaml'
  if (props.kind === 'cube') return '/api/cube/cube/' + n + '/yaml'
  return '/api/cube/view/' + n + '/yaml'
})

async function load() {
  text.value = ''
  msg.value = ''
  if (!visible.value) return
  try {
    const r = await api(url.value)
    text.value = r.text
  } catch (e) {
    msg.value = e.message
  }
}

async function save() {
  busy.value = true
  msg.value = ''
  try {
    await api(url.value, { method: 'PUT', body: JSON.stringify({ text: text.value }) })
    msg.value = '已保存，Cube 会自动重载'
  } catch (e) {
    msg.value = `保存失败：${e.message}`
  } finally {
    busy.value = false
  }
}

watch(
  () => props.name,
  async () => {
    if (open.value) await load()
  }
)

async function toggle() {
  open.value = !open.value
  if (open.value) await load()
}
</script>

<template>
  <div v-if="visible" class="yaml-box">
    <div class="head">
      <button @click="toggle">{{ open ? '收起 YAML' : '编辑 YAML' }}</button>
      <span class="muted small">{{ label }}</span>
      <span class="spacer"></span>
      <span v-if="msg" class="muted small">{{ msg }}</span>
    </div>

    <template v-if="open">
      <textarea v-model="text" :disabled="!canEdit" spellcheck="false"></textarea>
      <div class="actions">
        <button v-if="canEdit" class="primary" :disabled="busy || !text" @click="save">
          {{ busy ? '保存中…' : '保存 YAML' }}
        </button>
        <button :disabled="busy" @click="load">重新读取</button>
        <span class="muted small">直接改这里也行，跟上面的表单是同一份数据</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.yaml-box {
  margin-top: 16px;
  border-top: 1px dashed #d0d7de;
  padding-top: 10px;
}
.head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.spacer {
  flex: 1;
}
textarea {
  width: 100%;
  min-height: 320px;
  margin-top: 8px;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.55;
  padding: 10px;
  border: 1px solid #d0d7de;
  border-radius: 6px;
  background: #fbfcfd;
  resize: vertical;
  white-space: pre;
  overflow: auto;
}
.actions {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.small {
  font-size: 12px;
}
</style>
