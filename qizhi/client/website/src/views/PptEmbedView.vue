<template>
  <div class="ppt-embed-view">
    <div class="toolbar">
      <div class="toolbar-left">
        <a href="#" class="back-btn" @click.prevent="goBack">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span>返回</span>
        </a>
        <h2 class="page-title">PPT 生成</h2>
      </div>
    </div>

    <div class="embed-area">
      <iframe
        :src="embedUrl"
        class="embed-iframe"
        title="PPT 生成"
        frameborder="0"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const embedUrl = computed(() => 'http://aiassistant-cx.zju.edu.cn/cassso/tozju?refer=https%3A%2F%2F5vqb341f.mh.chaoxing.com')

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/my-courses')
}
</script>

<style scoped>
.ppt-embed-view {
  width: 100%;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: transparent;
}

.toolbar {
  background-color: transparent;
  padding: 16px 24px;
  padding-left: var(--toolbar-pad-left, 102px);
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: none;
  flex-shrink: 0;
}

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

.back-btn:hover {
  color: #C5D9FF;
}

.embed-area {
  flex: 1;
  min-height: 0;
  padding: 0;
  background-color: transparent;
}

@media (max-width: 640px) {
  .toolbar {
    padding: 12px 16px;
    gap: 12px;
  }
}

.embed-iframe {
  width: 100%;
  height: 100%;
  border: none;
  display: block;
}
</style>
