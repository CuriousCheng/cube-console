<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../store'

const ai = reactive({ protocol: 'openai', base_url: '', model: '', api_key: '', has_key: false })
const aiBusy = ref(false)
const aiResult = ref(null)
const aiMsg = ref('')

const sys = reactive({
  pool_size: 3,
  ask_concurrency: 1,
  viewer_can_see_sql: false,
  idle_stop_minutes: 10,
})
const sysBusy = ref(false)
const sysMsg = ref('')

async function load() {
  Object.assign(ai, await api('/api/ai'))
  const c = await api('/api/config')
  Object.assign(sys, {
    pool_size: c.pool_size,
    ask_concurrency: c.ask_concurrency,
    viewer_can_see_sql: c.viewer_can_see_sql,
    idle_stop_minutes: c.idle_stop_minutes,
  })
}

async function testAi() {
  aiBusy.value = true
  aiResult.value = null
  try {
    aiResult.value = await api('/api/ai/test', {
      method: 'POST',
      body: JSON.stringify({ protocol: ai.protocol, base_url: ai.base_url, api_key: ai.api_key }),
    })
  } catch (e) {
    aiResult.value = { ok: false, error: e.message }
  } finally {
    aiBusy.value = false
  }
}

async function saveAi() {
  aiBusy.value = true
  aiMsg.value = ''
  try {
    await api('/api/ai', {
      method: 'PUT',
      body: JSON.stringify({
        protocol: ai.protocol,
        base_url: ai.base_url,
        model: ai.model,
        api_key: ai.api_key || '',
      }),
    })
    ai.api_key = ''
    aiMsg.value = '已保存'
    await load()
  } catch (e) {
    aiMsg.value = `保存失败：${e.message}`
  } finally {
    aiBusy.value = false
  }
}

async function saveSys() {
  sysBusy.value = true
  sysMsg.value = ''
  try {
    await api('/api/config', { method: 'PUT', body: JSON.stringify(sys) })
    sysMsg.value = '已保存'
  } catch (e) {
    sysMsg.value = `保存失败：${e.message}`
  } finally {
    sysBusy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="card">
    <h3>AI 接口</h3>
    <p class="muted">本地 Ollama 或云端 API 都填这里。key 加密存在 config.json。</p>

    <div class="grid2">
      <div>
        <label class="lbl">协议</label>
        <select v-model="ai.protocol">
          <option value="openai">OpenAI 兼容（/v1/chat/completions）</option>
          <option value="anthropic">Anthropic（/v1/messages）</option>
        </select>
      </div>
      <div>
        <label class="lbl">模型名</label>
        <input v-model="ai.model" placeholder="qwen2.5:3b 或 deepseek-v4.1-flash" />
      </div>
      <div class="span2">
        <label class="lbl">接口地址</label>
        <input
          v-model="ai.base_url"
          placeholder="本地 http://127.0.0.1:11434/v1 ，云端 https://api.xxx.com/v1"
        />
      </div>
      <div class="span2">
        <label class="lbl">API Key（本地服务留空）</label>
        <input
          v-model="ai.api_key"
          type="password"
          :placeholder="ai.has_key ? '已保存，留空表示不修改' : 'sk-...'"
        />
      </div>
    </div>

    <div class="actions">
      <button :disabled="aiBusy" @click="testAi">{{ aiBusy ? '…' : '测试连接' }}</button>
      <button class="primary" :disabled="aiBusy" @click="saveAi">保存</button>
      <span v-if="aiMsg" class="muted">{{ aiMsg }}</span>
    </div>

    <div v-if="aiResult" class="result">
      <p v-if="aiResult.ok" class="ok">
        ✅ 通了（{{ aiResult.endpoint }}），可用模型 {{ aiResult.models?.length || 0 }} 个
      </p>
      <p v-else class="bad">❌ {{ aiResult.error }}</p>
      <p v-if="aiResult.models?.length" class="muted">
        {{ aiResult.models.slice(0, 12).join(', ') }}{{ aiResult.models.length > 12 ? ' …' : '' }}
      </p>
      <template v-if="aiResult.ok && !aiResult.models?.length">
        <p class="bad">响应里没有模型列表，地址可能不是 API 入口。原始响应：</p>
        <pre>{{ aiResult.raw }}</pre>
      </template>
    </div>
  </div>

  <div class="card">
    <h3>查询参数</h3>
    <p class="muted">控制一次查询最多返回多少行、viewer 能不能看到生成的 SQL。</p>

    <div class="grid2">
      <div>
        <label class="lbl">viewer 能否看 SQL</label>
        <label class="switch">
          <input v-model="sys.viewer_can_see_sql" type="checkbox" />
          <span>{{ sys.viewer_can_see_sql ? '可以看' : '不看（默认）' }}</span>
        </label>
      </div>
    </div>

    <div class="actions">
      <button class="primary" :disabled="sysBusy" @click="saveSys">保存</button>
      <span v-if="sysMsg" class="muted">{{ sysMsg }}</span>
    </div>
  </div>
</template>

<style scoped>
.lbl {
  display: block;
  margin: 12px 0 5px;
  font-size: 13px;
  color: #57606a;
}
.grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 18px;
}
.span2 {
  grid-column: span 2;
}
.actions {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.result {
  margin-top: 12px;
  padding: 10px 12px;
  background: #f6f8fa;
  border-radius: 6px;
}
.switch {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #24292f;
}
.switch input {
  width: auto;
}
</style>
