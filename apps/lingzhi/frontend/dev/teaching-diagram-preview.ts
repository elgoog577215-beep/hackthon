import { createApp } from 'vue'
import '../src/style.css'
import { initializeI18n } from '../src/shared/i18n'
import TeachingDiagramPreview from './TeachingDiagramPreview.vue'
await initializeI18n()
createApp(TeachingDiagramPreview).mount('#app')
