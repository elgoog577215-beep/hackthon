import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'katex/dist/katex.min.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import { createPinia } from 'pinia'
import router from './router'

// Error handling for startup
window.addEventListener('error', (event) => {
    document.body.innerHTML += `<div style="color: red; padding: 20px; font-family: monospace; white-space: pre-wrap; z-index: 9999; position: fixed; top: 0; left: 0; background: white; border: 2px solid red;">
        Global Error: ${event.message} at ${event.filename}:${event.lineno}
    </div>`
})

window.addEventListener('unhandledrejection', (event) => {
    document.body.innerHTML += `<div style="color: red; padding: 20px; font-family: monospace; white-space: pre-wrap; z-index: 9999; position: fixed; top: 0; left: 0; background: white; border: 2px solid red;">
        Unhandled Promise Rejection: ${event.reason}
    </div>`
})

try {
    const app = createApp(App)
    const pinia = createPinia()

    app.use(ElementPlus)
    app.use(pinia)
    app.use(router)

    for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
      app.component(key, component)
    }

    app.mount('#app')
    console.log('Vue App Mounted Successfully')
} catch (e) {
    document.body.innerHTML += `<div style="color: red; padding: 20px; font-family: monospace; white-space: pre-wrap;">
        App Mount Error: ${e}
    </div>`
    console.error(e)
}
