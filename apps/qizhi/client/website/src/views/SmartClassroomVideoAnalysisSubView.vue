<template>
  <div class="sc-sub-view">
    <div class="toolbar">
      <div class="toolbar-left">
        <a href="#" class="back-btn" @click.prevent="goBack">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span>返回</span>
        </a>
        <h2 class="page-title">课堂视频</h2>
      </div>
      <div class="toolbar-right">
        <button type="button" class="action-btn" :disabled="streaming" @click="handleFetch(false)">
          {{ streaming ? '拉取中...' : '拉取详情' }}
        </button>
        <button type="button" class="action-btn primary" :disabled="streaming || applying" @click="handleApply">
          {{ applying ? '申请中...' : '视频分析申请' }}
        </button>
      </div>
    </div>

    <div class="content-area">
      <section class="panel">
        <div class="kv">
          <div class="k">sub_id</div>
          <div class="v mono">{{ subId }}</div>
        </div>
        <div class="kv">
          <div class="k">tenant_code</div>
          <div class="v">
            <input v-model.trim="tenantCode" class="form-input" placeholder="可选：不填则用服务端默认" />
          </div>
        </div>
        <div class="kv">
          <div class="k">下载到本地</div>
          <div class="v">
            <label class="checkbox">
              <input v-model="downloadVideo" type="checkbox" />
              <span>download_video = true</span>
            </label>
          </div>
        </div>

        <div v-if="progressVisible" class="progress">
          <div class="progress-bar">
            <div class="progress-inner" :style="{ width: `${progressPercent}%` }"></div>
          </div>
          <div class="progress-text">
            <span v-if="progressTotal != null">下载中 {{ progressPercent }}%</span>
            <span v-else>下载中（已接收 {{ progressReceived }} bytes）</span>
          </div>
        </div>

        <p v-if="error" class="error">操作失败，请稍后重试</p>
      </section>

      <section class="panel">
        <h3 class="panel-title">视频预览</h3>
        <div class="video-wrap">
          <div v-if="!playableUrl" class="video-placeholder">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="2" y="4" width="20" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
              <path d="M10 9l5 3-5 3V9z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <p>请先点击「拉取详情」获取播放地址</p>
          </div>
          <video v-else :src="playableUrl" controls class="video-player" />
        </div>

        <div class="urls">
          <div class="kv small">
            <div class="k">video_local_url</div>
            <div class="v mono">{{ videoLocalUrl || '—' }}</div>
          </div>
          <div class="kv small">
            <div class="k">video_play_url</div>
            <div class="v mono">{{ videoPlayUrl || '—' }}</div>
          </div>
        </div>
      </section>

      <section class="panel">
        <h3 class="panel-title">分析结果</h3>
        <p class="muted">分析申请后将跳转到报告页展示视频及分析结果。</p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchSmartClassroomSubDetailStream } from '../api/smartClassroom'

const route = useRoute()
const router = useRouter()

const isMockMode = computed(() => import.meta.env.DEV && route.query?.mock === '1')

const subId = computed(() => {
  const raw = String(route.params.subId || '')
  try { return decodeURIComponent(raw) } catch { return raw }
})

const tenantCode = ref<string>('')
const downloadVideo = ref<boolean>(true)

const streaming = ref(false)
const applying = ref(false)
const error = ref<string | null>(null)

const videoLocalUrl = ref<string | null>(null)
const videoPlayUrl = ref<string | null>(null)

const progressReceived = ref(0)
const progressTotal = ref<number | null>(null)

const progressVisible = computed(() => streaming.value && (progressReceived.value > 0 || progressTotal.value != null))
const progressPercent = computed(() => {
  if (!progressTotal.value || progressTotal.value <= 0) return 0
  return Math.min(100, Math.round((progressReceived.value / progressTotal.value) * 100))
})

const playableUrl = computed(() => {
  // 优先本地视频（可长期播放），否则用上游短链接
  return videoLocalUrl.value || videoPlayUrl.value || ''
})

let abortCtrl: AbortController | null = null

onMounted(() => {
  const q = route.query?.tenant_code
  if (typeof q === 'string' && q.trim()) {
    tenantCode.value = q.trim()
  }
})

function resetProgress() {
  progressReceived.value = 0
  progressTotal.value = null
}

async function handleFetch(forceDownload: boolean) {
  if (streaming.value) return
  streaming.value = true
  error.value = null
  resetProgress()
  abortCtrl = new AbortController()
  try {
    if (isMockMode.value) {
      // 纯前端 mock：模拟 detail/progress/done
      const total = 80 * 1024 * 1024
      progressTotal.value = total
      progressReceived.value = 0
      videoPlayUrl.value = 'https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4'
      for (let i = 0; i <= 10; i++) {
        await new Promise((r) => setTimeout(r, 120))
        progressReceived.value = Math.round((total * i) / 10)
      }
      videoLocalUrl.value = null
      return
    }
    await fetchSmartClassroomSubDetailStream(
      {
        sub_id: subId.value,
        tenant_code: tenantCode.value ? tenantCode.value : null,
        download_video: forceDownload ? true : downloadVideo.value,
      },
      (ev) => {
        if (ev.type === 'detail') {
          videoPlayUrl.value = (ev.data as any)?.video_play_url ?? videoPlayUrl.value
        } else if (ev.type === 'progress') {
          progressReceived.value = ev.data.received || 0
          progressTotal.value = ev.data.total ?? null
        } else if (ev.type === 'done') {
          videoLocalUrl.value = ev.data.video_local_url ?? videoLocalUrl.value
          videoPlayUrl.value = ev.data.video_play_url ?? videoPlayUrl.value
        } else if (ev.type === 'error') {
          console.error('[SmartClassroom] 拉取详情失败', ev.data)
          error.value = 'failed'
        }
      },
      abortCtrl.signal
    )
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return
    console.error('[SmartClassroom] 拉取详情失败', e)
    error.value = 'failed'
  } finally {
    streaming.value = false
    abortCtrl = null
  }
}

async function handleApply() {
  if (applying.value || streaming.value) return
  applying.value = true
  error.value = null
  try {
    if (isMockMode.value) {
      // mock：不调用后端，直接进入 mock 报告页（meta.public）
      router.push('/resource-analysis/report-mock?mock=1')
      return
    }
    // 确保下载本地视频（更稳定的播放与后端可复用路径）
    await handleFetch(true)
    const id = (videoLocalUrl.value || videoPlayUrl.value || '').trim()
    if (!id) throw new Error('未获取到可用视频地址，无法发起分析')
    // 跳转到报告/预览页；分析改为在报告页手动触发
    router.push(`/resource-analysis/report/${encodeURIComponent(id)}`)
  } catch (e) {
    console.error('[SmartClassroom] 申请失败', e)
    error.value = 'failed'
  } finally {
    applying.value = false
  }
}

function goBack() {
  router.back()
}

onBeforeUnmount(() => {
  try { abortCtrl?.abort() } catch { /* ignore */ }
})
</script>

<style scoped>
.sc-sub-view {
  width: 100%;
  min-height: calc(100vh - 64px);
  background-color: transparent;
  display: flex;
  flex-direction: column;
}
.toolbar {
  background-color: rgba(0, 0, 0, 0);
  padding: 16px 24px;
  padding-left: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  margin: 12px 24px 0;
  flex-shrink: 0;
}
.toolbar-right { margin-left: auto; display: flex; gap: 12px; flex-wrap: wrap; }
.back-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  color: #333;
  font-size: 14px;
  text-decoration: none;
  transition: color 0.2s;
  border-radius: 4px;
}
.back-btn:hover { color: #C5D9FF; }
.action-btn {
  padding: 8px 16px;
  background-color: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  transition: all 0.2s;
}
.action-btn:hover:not(:disabled) { border-color: #C5D9FF; background-color: #f8f9ff; }
.action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.action-btn.primary { background: #C5D9FF; border-color: transparent; }
.action-btn.primary:hover:not(:disabled) { background: #b0caff; }

.content-area {
  flex: 1;
  padding: 16px 24px 20px;
  padding-left: calc(24px + 20px);
  max-width: 100%;
  margin: 0 auto;
  width: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.panel {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  padding: 18px 18px 20px;
}
.panel-title { margin: 0 0 12px; font-size: 16px; font-weight: 700; color: #333; }
.muted { margin: 0; font-size: 13px; color: #666; }

.kv {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 12px;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #f2f2f2;
}
.kv:last-child { border-bottom: none; }
.kv.small { grid-template-columns: 140px 1fr; }
.k { font-size: 13px; color: #666; }
.v { font-size: 14px; color: #333; min-width: 0; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 12px; word-break: break-all; }

.form-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #e6e6e6;
  border-radius: 10px;
  outline: none;
  font-size: 14px;
  box-sizing: border-box;
}
.form-input:focus { border-color: #C5D9FF; }

.checkbox { display: inline-flex; align-items: center; gap: 8px; font-size: 14px; color: #333; }

.progress { margin-top: 14px; }
.progress-bar {
  width: 100%;
  height: 8px;
  border-radius: 999px;
  background: #f0f0f0;
  overflow: hidden;
}
.progress-inner {
  height: 100%;
  background: #C5D9FF;
  transition: width 0.2s ease;
}
.progress-text { margin-top: 6px; font-size: 12px; color: #666; }

.error { margin: 12px 0 0; font-size: 13px; color: #c62828; }

.video-wrap {
  background: #000;
  border-radius: 20px;
  width: 100%;
  height: auto;
  aspect-ratio: 16 / 9;
  overflow: hidden;
}
.video-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #ddd;
  gap: 12px;
  text-align: center;
  padding: 12px;
  box-sizing: border-box;
}
.video-placeholder p { margin: 0; font-size: 14px; }
.video-player { width: 100%; height: 100%; object-fit: contain; }

.urls { margin-top: 14px; display: flex; flex-direction: column; gap: 6px; }

@media (max-width: 768px) {
  .toolbar { margin: 8px 12px 0; }
  .content-area { padding-left: calc(12px + 24px); }
  .kv { grid-template-columns: 96px 1fr; }
}

@media (max-width: 640px) {
  .content-area { padding-left: 12px; padding-right: 12px; }
  .kv { grid-template-columns: 1fr; gap: 4px; }
}
</style>
