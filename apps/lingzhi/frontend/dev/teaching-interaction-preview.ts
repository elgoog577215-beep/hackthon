import { createApp } from 'vue'
import '../src/style.css'
import { initializeI18n } from '../src/shared/i18n'
import TeachingInteractionPreview from './TeachingInteractionPreview.vue'
await initializeI18n()
createApp(TeachingInteractionPreview).mount('#app')
