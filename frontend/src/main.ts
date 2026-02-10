import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'katex/dist/katex.min.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import { createPinia } from 'pinia'
import router from './router'

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
} catch (e) {
    console.error('App Mount Error:', e)
}
