<template>
  <div class="h-screen w-full flex items-center justify-center p-2 overflow-hidden bg-slate-50 relative font-sans selection:bg-primary-500/20 selection:text-primary-900">
    <!-- Exquisite Background System -->
    <div class="absolute inset-0 z-0 pointer-events-none overflow-hidden">
        <!-- 1. Base Mesh Gradient (Subtle & Rich) -->
        <div class="absolute inset-0 opacity-60 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-primary-100/40 via-slate-50 to-primary-100/40"></div>
        
        <!-- 2. Animated Orbs (Deep Depth) -->
        <div class="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-primary-200/20 rounded-full mix-blend-multiply filter blur-3xl animate-blob"></div>
        <div class="absolute top-[-10%] right-[-10%] w-[40%] h-[40%] bg-primary-200/20 rounded-full mix-blend-multiply filter blur-3xl animate-blob animation-delay-2000"></div>
        <div class="absolute bottom-[-20%] left-[20%] w-[50%] h-[50%] bg-pink-200/20 rounded-full mix-blend-multiply filter blur-3xl animate-blob animation-delay-4000"></div>
        
        <!-- 3. Fine Grain Noise (Texture) -->
        <div class="absolute inset-0 opacity-[0.02]" style="background-image: url(&quot;data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E&quot;);"></div>
    </div>

    <!-- Main Floating Container -->
    <div class="w-full h-full flex flex-col gap-3 relative z-10">
        
        <!-- Global Header -->
        <header class="h-16 flex-shrink-0 flex items-center px-6 glass-panel-tech rounded-2xl z-20 relative animate-fade-in-up">
            <div class="flex items-center gap-3 cursor-pointer" @click="router.push('/')">
                <div class="w-10 h-10 bg-primary-600 rounded-xl flex items-center justify-center text-white shadow-sm transition-transform duration-300 relative overflow-hidden group hover:scale-105">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-6 h-6 relative z-10">
                        <path d="M11.7 2.805a.75.75 0 01.6 0A60.65 60.65 0 0122.83 8.72a.75.75 0 01-.231 1.337 49.949 49.949 0 00-9.902 3.912l-.003.002-.34.18a.75.75 0 01-.707 0A50.009 50.009 0 002.21 10.057a.75.75 0 01-.231-1.337A60.653 60.653 0 0111.7 2.805z" />
                        <path d="M13.06 15.473a48.45 48.45 0 017.666-3.282c.134 1.438.227 2.945.227 4.53 0 5.705-3.276 10.675-8.25 13.05a.75.75 0 01-.706 0C7.026 27.478 3.75 22.508 3.75 16.8c0-1.66.103-3.235.249-4.735a48.51 48.51 0 017.76 3.42c.433.224.943.224 1.301-.012z" />
                    </svg>
                </div>
                <div>
                    <h1 class="text-xl font-bold tracking-tight font-display text-slate-800">KnowledgeMap AI</h1>
                    <p class="text-xxs uppercase tracking-widest text-slate-500 font-bold opacity-90">Qoder 智能引擎</p>
                </div>
            </div>
            
            <div class="ml-auto flex items-center gap-4">
                 <div class="hidden md:flex items-center gap-2 px-3 py-1.5 bg-white/50 rounded-full border border-white/60 shadow-sm text-xs font-medium text-gray-600 backdrop-blur-md">
                    <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                    系统在线
                </div>
                <div class="w-9 h-9 rounded-full bg-gradient-to-tr from-gray-50 to-gray-100 border border-white shadow-inner flex items-center justify-center text-xs font-bold text-gray-600 cursor-pointer hover:scale-105 hover:shadow-lg transition-all duration-300">
                    U
                </div>
            </div>
        </header>

        <!-- Router View -->
        <router-view></router-view>
    </div>

    <!-- Global Status Bar -->
    <StatusBar 
        :visible="courseStore.generationStatus !== 'idle'"
        :status="courseStore.generationStatus"
        :current-task="courseStore.currentGeneratingNode"
        :logs="courseStore.generationLogs"
        :progress="courseStore.generationProgress"
        :queue="courseStore.queue"
        @close="courseStore.stopGeneration"
    />
  </div>
</template>

<script setup lang="ts">
import StatusBar from './components/StatusBar.vue'
import { useCourseStore } from './stores/course'
import { useRouter } from 'vue-router'
import { onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'

const courseStore = useCourseStore()
const router = useRouter()

const handleGlobalClick = (e: MouseEvent) => {
    const target = e.target as HTMLElement;
    const btn = target.closest('.copy-btn');
    if (btn) {
        const code = btn.getAttribute('data-code');
        if (code) {
            navigator.clipboard.writeText(code).then(() => {
                ElMessage.success('代码已复制到剪贴板');
            }).catch(() => {
                ElMessage.error('复制失败');
            });
        }
    }
}

onMounted(() => {
    document.addEventListener('click', handleGlobalClick);
})

onUnmounted(() => {
    document.removeEventListener('click', handleGlobalClick);
})
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
