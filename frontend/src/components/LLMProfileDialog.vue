<template>
  <MorphingDialog ariaLabel="模型配置" size="medium" @close="$emit('close')">
    <section class="profile-dialog">
      <header>
        <div>
          <p>本机模型服务</p>
          <h2>模型配置</h2>
        </div>
        <button class="icon-button" type="button" aria-label="关闭" @click="$emit('close')"><X :size="18" /></button>
      </header>

      <div class="profile-dialog__body">
        <p class="hint">密钥只保存到本机后端，不会再次返回到浏览器。</p>
        <div v-if="loading" class="empty">正在读取配置…</div>
        <div v-else-if="profiles.length" class="profile-list">
          <article v-for="profile in profiles" :key="profile.id" class="profile-item" :class="{ active: profile.is_active }">
            <button type="button" class="profile-select" :disabled="switching === profile.id" @click="activate(profile.id)">
              <span><strong>{{ profile.name }}</strong><small>{{ profile.smart_model || '使用服务默认模型' }}</small></span>
              <Check v-if="profile.is_active" :size="17" />
              <span v-else class="activate">切换</span>
            </button>
            <button type="button" class="test-button" :disabled="testing === profile.id" @click="testConnection(profile.id)">{{ testing === profile.id ? '测试中…' : '测试连接' }}</button>
          </article>
        </div>
        <div v-else class="empty">还没有模型配置。添加一个即可开始生成课程。</div>

        <form class="profile-form" @submit.prevent="save">
          <h3>添加模型配置</h3>
          <label>名称<input v-model.trim="form.name" required maxlength="80" placeholder="例如：ModelScope 主力" /></label>
          <label>API Base URL<input v-model.trim="form.api_base" required type="url" placeholder="https://api-inference.modelscope.cn/v1" /></label>
          <label>API Key<input v-model="form.api_key" required type="password" autocomplete="new-password" placeholder="仅保存至本机" /></label>
          <label>主模型（可选）<input v-model.trim="form.smart_model" placeholder="例如：Qwen/Qwen3-32B" /></label>
          <label>快速模型（可选）<input v-model.trim="form.fast_model" placeholder="例如：Qwen/Qwen3-Next-80B-A3B-Instruct" /></label>
          <button class="save-button" type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存并切换到此配置' }}</button>
        </form>
      </div>
    </section>
  </MorphingDialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Check, X } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import MorphingDialog from './MorphingDialog.vue'
import http from '@/utils/http'

type Profile = { id: string; name: string; api_base: string; smart_model: string; fast_model: string; has_api_key: boolean; is_active: boolean }
defineEmits<{ close: [] }>()

const profiles = ref<Profile[]>([])
const loading = ref(true)
const saving = ref(false)
const switching = ref('')
const testing = ref('')
const form = reactive({ name: '', api_base: 'https://api-inference.modelscope.cn/v1', api_key: '', smart_model: '', fast_model: '' })

async function load() {
  loading.value = true
  try {
    const { data } = await http.get<{ profiles: Profile[] }>('/api/llm-profiles')
    profiles.value = data.profiles
  } catch {
    ElMessage.error('读取模型配置失败')
  } finally {
    loading.value = false
  }
}

async function activate(id: string) {
  switching.value = id
  try {
    await http.post(`/api/llm-profiles/${id}/activate`)
    await load()
    ElMessage.success('已切换模型配置，下一次 AI 请求将使用它')
  } finally {
    switching.value = ''
  }
}

async function save() {
  saving.value = true
  try {
    await http.post('/api/llm-profiles', { ...form, activate: true })
    form.name = ''; form.api_key = ''; form.smart_model = ''; form.fast_model = ''
    await load()
    ElMessage.success('模型配置已保存并启用')
  } finally {
    saving.value = false
  }
}

async function testConnection(id: string) {
  testing.value = id
  try {
    const { data } = await http.post<{ ok: boolean; model_count: number }>(`/api/llm-profiles/${id}/test`)
    ElMessage.success(`连接成功，可读取 ${data.model_count} 个模型`)
  } finally {
    testing.value = ''
  }
}

onMounted(load)
</script>

<style scoped>
.profile-dialog { width:min(560px, calc(100vw - 32px)); background:#fff; border-radius:16px; overflow:hidden; color:var(--lz-text); }
header { display:flex; justify-content:space-between; align-items:center; padding:18px 20px; border-bottom:1px solid var(--lz-border); }
header p { margin:0 0 2px; color:var(--lz-text-muted); font-size:11px; font-weight:700; } h2 { margin:0; font-size:18px; } h3 { margin:0 0 12px; font-size:13px; }
.icon-button { width:34px; height:34px; border:0; border-radius:9px; background:transparent; color:var(--lz-text-secondary); cursor:pointer; }.icon-button:hover { background:var(--lz-surface-muted); }
.profile-dialog__body { max-height:72vh; overflow:auto; padding:18px 20px 22px; }.hint { margin:0 0 14px; color:var(--lz-text-muted); font-size:12px; line-height:1.5; }
.profile-list { display:grid; gap:8px; margin-bottom:18px; }.profile-item { display:flex; align-items:center; gap:10px; padding:7px 8px 7px 12px; border:1px solid var(--lz-border); border-radius:10px; color:var(--lz-text-secondary); background:#fff; }.profile-item:hover,.profile-item.active { border-color:var(--lz-brand); background:var(--lz-brand-soft); }.profile-select { min-width:0; flex:1; display:flex; align-items:center; justify-content:space-between; gap:12px; border:0; color:inherit; background:transparent; text-align:left; cursor:pointer; }.profile-item strong,.profile-item small { display:block; }.profile-item small { margin-top:2px; color:var(--lz-text-muted); font-size:11px; }.profile-item.active { color:var(--lz-brand-strong); }.activate { font-size:12px; font-weight:700; }.test-button { flex:0 0 auto; min-height:30px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text-secondary); background:#fff; font-size:11px; font-weight:700; cursor:pointer; }.test-button:hover { border-color:var(--lz-brand); color:var(--lz-brand-strong); }.test-button:disabled { opacity:.6; cursor:not-allowed; }.empty { margin-bottom:16px; padding:13px; border-radius:9px; color:var(--lz-text-muted); background:var(--lz-surface-muted); font-size:12px; }
.profile-form { display:grid; gap:11px; padding-top:18px; border-top:1px solid var(--lz-border); }.profile-form label { display:grid; gap:6px; color:var(--lz-text-secondary); font-size:12px; font-weight:700; }.profile-form input { height:38px; box-sizing:border-box; border:1px solid var(--lz-border); border-radius:8px; padding:0 10px; color:var(--lz-text); font:inherit; font-weight:400; }.profile-form input:focus { outline:0; border-color:var(--lz-brand); box-shadow:0 0 0 3px rgba(99,102,241,.1); }.save-button { min-height:40px; margin-top:3px; border:1px solid var(--lz-brand-strong); border-radius:8px; color:#fff; background:var(--lz-brand-strong); font-weight:700; cursor:pointer; }.save-button:disabled { opacity:.6; cursor:not-allowed; }
</style>
