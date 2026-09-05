import './assets/main.css'
import './assets/range-slider.css'
import './assets/route-slide.css'
import 'md-editor-v3/lib/style.css'
import 'katex/dist/katex.min.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import MdEditor from 'md-editor-v3'

import App from './App.vue'
import router from './router'
import { installCustomScrollbar } from './plugins/customScrollbar'

// md-editor-v3 默认把预览渲染用 500ms debounce 包住：流式生成时每个增量都会 reset
// 这个定时器，直到整段流结束 500ms 后预览才出现一次——这正是「右侧预览在生成时一直空白」
// 的根因（lib/md-editor-v3.mjs 第 2797 行）。
// 把 renderDelay 调到 0 表示每次 modelValue 变化都立即重渲染预览，让流式写入的
// 内容可以实时显示；非生成场景下用户手敲也不会因此明显变卡。
MdEditor.config({
  editorConfig: {
    renderDelay: 0,
  },
})

const app = createApp(App)

app.use(createPinia())
app.use(router)
installCustomScrollbar(router)

// 接口返回鉴权失败（401 或「无效的 token」等）时，request 会清除 token 并派发此事件。
// 线下排查/联调阶段：不要在全局自动跳转到任何外站（避免误跳转）。
let oauthRedirecting = false
window.addEventListener('auth:unauthorized', () => {
  // 仅本机开发：不因 401 强制跳 /auth，便于无有效 token 时仍浏览页面
  try {
    const h = window.location.hostname
    if (h === 'localhost' || h === '127.0.0.1') {
      if (import.meta.env.DEV && typeof console !== 'undefined') {
        console.warn('[auth] 收到 401（auth:unauthorized），本机开发模式下不跳转登录页')
      }
      return
    }
  } catch {
    // ignore
  }
  if (oauthRedirecting) return
  oauthRedirecting = true
  router.replace('/auth')
})

app.mount('#app')
