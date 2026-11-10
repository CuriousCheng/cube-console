<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, me } from '../store'
import YamlBox from './YamlBox.vue'

const cubes = ref([])
const views = ref([])
const picked = ref([])
const name = ref('')
const title = ref('')
const busy = ref(false)
const msg = ref('')
const err = ref('')
const canEdit = computed(() => ['admin', 'editor'].includes(me.value?.role))

const yamlName = ref('')

const pickedCubes = computed(() => cubes.value.filter((c) => picked.value.includes(c.name)))
const tableCubes = computed(() => cubes.value.filter((c) => c.type !== 'view'))

function toggle(n) {
  const i = picked.value.indexOf(n)
  if (i >= 0) picked.value.splice(i, 1)
  else picked.value.push(n)
}

async function load() {
  err.value = ''
  try {
    const r = await api('/api/cube/meta')
    cubes.value = r.cubes || []
  } catch (e) {
    err.value = `读不到 Cube 元数据：${e.message}`
  }
  try {
    const v = await api('/api/cube/views')
    views.value = v.items || []
  } catch {
    views.value = []
  }
}

function autoName() {
  if (!name.value && picked.value.length) {
    name.value = 'biz_' + picked.value.slice(0, 2).join('_').replace(/[^a-z0-9_]/g, '')
  }
}

async function create() {
  msg.value = ''
  err.value = ''
  busy.value = true
  try {
    await api('/api/cube/view', {
      method: 'POST',
      body: JSON.stringify({
        name: name.value,
        title: title.value,
        cubes: picked.value,
      }),
    })
    msg.value = `已创建业务 ${title.value || name.value}，Cube 已自动重载`
    picked.value = []
    name.value = ''
    title.value = ''
    await load()
  } catch (e) {
    err.value = e.message
  } finally {
    busy.value = false
  }
}

async function remove(v) {
  if (!confirm(`删除业务 ${v.name}？`)) return
  try {
    await api(`/api/cube/views/${encodeURIComponent(v.name)}`, { method: 'DELETE' })
    await load()
  } catch (e) {
    alert(e.message)
  }
}

onMounted(load)
</script>

<template>
  <div class="card">
    <h3>业务</h3>
    <p class="muted">
      勾选要放进这个业务的表，Cube 会生成一个 <b>view</b>（一组字段的视图）。选表就是业务边界。
    </p>

    <p v-if="err" class="bad">{{ err }}</p>
    <p v-if="msg" class="ok">{{ msg }}</p>

    <div class="grid2">
      <div>
        <label class="lbl">表（{{ tableCubes.length }}）</label>
        <div class="list">
          <label v-for="c in tableCubes" :key="c.name" class="item">
            <input
              type="checkbox"
              :checked="picked.includes(c.name)"
              :disabled="!canEdit"
              @change="toggle(c.name)"
            />
            <span class="nm">{{ c.name }}</span>
            <span class="muted small">{{ c.title }}</span>
          </label>
          <p v-if="!tableCubes.length" class="muted">没有表</p>
        </div>
      </div>

      <div>
        <label class="lbl">已选（{{ pickedCubes.length }}）</label>
        <div class="list">
          <div v-for="c in pickedCubes" :key="c.name" class="item">
            <span class="nm">{{ c.name }}</span>
            <span class="muted small">
              度量 {{ c.measures.length }} · 维度 {{ c.dimensions.length }}
            </span>
          </div>
          <p v-if="!pickedCubes.length" class="muted">还没选</p>
        </div>
      </div>
    </div>

    <div class="form">
      <div>
        <label class="lbl">业务标识（英文，a-z 0-9 _）</label>
        <input v-model="name" :disabled="!canEdit" placeholder="auto_sales" @focus="autoName" />
      </div>
      <div>
        <label class="lbl">业务名称（中文，显示用）</label>
        <input v-model="title" :disabled="!canEdit" placeholder="汽车销售分析" />
      </div>
      <div class="act">
        <button
          class="primary"
          :disabled="!canEdit || busy || !picked.length || !name"
          @click="create"
        >
          {{ busy ? '创建中…' : '创建业务' }}
        </button>
      </div>
    </div>

    <h3 style="margin-top: 24px">已有业务</h3>
    <table v-if="views.length">
      <thead>
        <tr>
          <th>标识</th>
          <th>文件</th>
          <th style="width: 160px"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="v in views" :key="v.name">
          <td><code>{{ v.name }}</code></td>
          <td class="muted small">{{ v.file }}</td>
          <td>
            <button @click="yamlName = yamlName === v.name ? '' : v.name">
              {{ yamlName === v.name ? '收起' : 'YAML' }}
            </button>
            <button v-if="canEdit" @click="remove(v)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">还没有业务</p>

    <YamlBox kind="view" :name="yamlName" />
  </div>
</template>

<style scoped>
.grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 12px;
}
.list {
  border: 1px solid #d0d7de;
  border-radius: 6px;
  max-height: 320px;
  overflow: auto;
  padding: 6px;
}
.item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  border-radius: 4px;
  font-size: 13px;
}
.item:hover {
  background: #f6f8fa;
}
.item input {
  width: auto;
}
.nm {
  font-family: ui-monospace, Consolas, monospace;
}
.small {
  font-size: 12px;
}
.lbl {
  display: block;
  margin: 10px 0 5px;
  font-size: 12.5px;
  color: #57606a;
}
.form {
  display: grid;
  grid-template-columns: 1fr 1fr 140px;
  gap: 12px;
  align-items: end;
  margin-top: 16px;
}
.act {
  padding-bottom: 1px;
}
code {
  background: #eaeef2;
  padding: 1px 5px;
  border-radius: 4px;
}
</style>
