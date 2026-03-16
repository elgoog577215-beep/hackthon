import { createApp } from 'vue'
import './style.css'
import './styles/design-system.css'
import App from './App.vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'katex/dist/katex.min.css'
import { createPinia } from 'pinia'
import router from './router'
import logger from './utils/logger'

try {
    const app = createApp(App)
    const pinia = createPinia()

    app.use(ElementPlus)
    app.use(pinia)
    app.use(router)

    app.mount('#app')
} catch (e) {
    logger.error('App Mount Error:', e)
}
