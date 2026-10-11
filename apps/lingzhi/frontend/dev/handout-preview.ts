import { createApp } from 'vue'
import { createPinia } from 'pinia'
import '../src/style.css'
import 'katex/dist/katex.min.css'
import { initializeI18n } from '../src/shared/i18n'
import HandoutPreview from './HandoutPreview.vue'

await initializeI18n()
createApp(HandoutPreview).use(createPinia()).mount('#app')
