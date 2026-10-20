import { createApp } from 'vue'
import { createPinia } from 'pinia'
import '../src/style.css'
import { initializeI18n } from '../src/shared/i18n'
import CourseChangePreview from './CourseChangePreview.vue'

await initializeI18n()
createApp(CourseChangePreview).use(createPinia()).mount('#app')
