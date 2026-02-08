<template>
  <div class="h-screen w-full flex items-center justify-center p-2 overflow-hidden bg-gradient-to-b from-slate-50 to-slate-100 relative font-sans selection:bg-primary-500/20 selection:text-primary-900 antialiased">
    <!-- Clean Background System -->
    <div class="absolute inset-0 z-0 pointer-events-none overflow-hidden bg-slate-50/50">
        <!-- 1. Subtle Base Gradient -->
        <div class="absolute inset-0 opacity-30 bg-gradient-to-br from-indigo-50/50 via-slate-50 to-blue-50/50"></div>
        
        <!-- 2. Very Subtle Ambient Light (Optional, much softer) -->
        <div class="absolute top-[-20%] right-[-10%] w-[60%] h-[60%] bg-indigo-100/20 rounded-full blur-[100px] opacity-40"></div>
        <div class="absolute bottom-[-20%] left-[-10%] w-[60%] h-[60%] bg-blue-100/20 rounded-full blur-[100px] opacity-40"></div>
    </div>

    <!-- Main Floating Container -->
    <div class="w-full h-full flex flex-col gap-3 relative z-10">
        
        <!-- Global Header - Improved contrast and hierarchy -->
        <header class="h-16 flex-shrink-0 flex items-center justify-between px-6 glass-panel-tech-floating rounded-xl z-20 relative animate-fade-in-up">
            <div class="flex items-center gap-3 cursor-pointer group" @click="router.push('/')">
                <div class="w-10 h-10 bg-primary-600 rounded-xl flex items-center justify-center text-white shadow-md transition-all duration-200 relative overflow-hidden group-hover:shadow-lg group-hover:scale-105">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-6 h-6 relative z-10">
                        <path d="M11.7 2.805a.75.75 0 01.6 0A60.65 60.65 0 0122.83 8.72a.75.75 0 01-.231 1.337 49.949 49.949 0 00-9.902 3.912l-.003.002-.34.18a.75.75 0 01-.707 0A50.009 50.009 0 002.21 10.057a.75.75 0 01-.231-1.337A60.653 60.653 0 0111.7 2.805z" />
                        <path d="M13.06 15.473a48.45 48.45 0 017.666-3.282c.134 1.438.227 2.945.227 4.53 0 5.705-3.276 10.675-8.25 13.05a.75.75 0 01-.706 0C7.026 27.478 3.75 22.508 3.75 16.8c0-1.66.103-3.235.249-4.735a48.51 48.51 0 017.76 3.42c.433.224.943.224 1.301-.012z" />
                    </svg>
                </div>
                <div>
                    <h1 class="text-lg font-semibold tracking-tight font-display text-slate-900">KnowledgeMap AI</h1>
                    <p class="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Qoder 智能引擎</p>
                </div>
            </div>
            
            <!-- Central Course Title - Improved readability -->
            <div class="absolute left-1/2 -translate-x-1/2 hidden md:flex items-center gap-2 bg-white/60 backdrop-blur-sm rounded-full px-4 py-1.5 border border-slate-200/60 shadow-sm" v-if="courseStore.currentCourseId">
                <span class="font-semibold text-slate-800 truncate max-w-[200px]">
                    {{ courseStore.courseList.find(c => c.course_id === courseStore.currentCourseId)?.course_name || '课程预览' }}
                </span>
                <span class="text-slate-300">|</span>
                <span class="text-xs text-slate-500">全书模式</span>
            </div>

            <div class="flex items-center gap-3">
                 <!-- Toolbar Controls -->
                <div class="flex items-center gap-2" v-if="courseStore.currentCourseId">
                    <!-- Global Search - Beautiful Design -->
                    <div class="relative mr-2">
                        <div class="relative transition-all duration-300 ease-out" :class="isSearchFocused ? 'w-80' : 'w-56'">
                            <!-- Glow effect -->
                            <div class="absolute -inset-[1px] bg-gradient-to-r from-primary-400/0 via-primary-500/30 to-primary-400/0 rounded-full opacity-0 blur-[2px] transition-opacity duration-300" :class="isSearchFocused ? 'opacity-100' : ''"></div>
                            
                            <div class="relative flex items-center bg-white rounded-full h-9 shadow-sm border border-slate-200/60 transition-all duration-300" :class="isSearchFocused ? 'shadow-[0_0_20px_rgba(139,92,246,0.25)] border-primary-300/50' : 'hover:shadow-md hover:border-slate-300/60'">
                                <div class="pl-3 pr-2 text-slate-400 transition-colors duration-300" :class="isSearchFocused ? 'text-primary-500' : ''">
                                    <el-icon :size="16"><Search /></el-icon>
                                </div>
                                <input 
                                    :value="courseStore.globalSearchQuery"
                                    type="text"
                                    placeholder="搜索全书内容..."
                                    class="flex-1 bg-transparent border-none outline-none focus:outline-none focus:ring-0 text-sm text-slate-700 placeholder:text-slate-400/70 h-full pr-3"
                                    @input="handleGlobalSearch"
                                    @focus="isSearchFocused = true"
                                    @blur="isSearchFocused = false"
                                />
                                <button 
                                    v-if="courseStore.globalSearchQuery"
                                    class="mr-2 text-slate-400 hover:text-slate-600 transition-colors"
                                    @click="courseStore.globalSearchQuery = ''; globalSearchResults = []"
                                >
                                    <el-icon :size="14"><CircleClose /></el-icon>
                                </button>
                            </div>
                        </div>

                        <!-- Search Results Dropdown -->
                        <div v-if="globalSearchResults.length > 0" class="absolute top-full left-0 right-0 mt-3 bg-white/95 backdrop-blur-xl rounded-xl shadow-lg border border-slate-100 p-2 z-50 max-h-80 overflow-auto">
                            <div class="flex items-center justify-between px-2 py-1.5 mb-1 border-b border-slate-100">
                                <span class="text-[11px] font-medium text-slate-500">搜索结果</span>
                                <span class="text-[10px] text-slate-400 bg-slate-100 rounded-full px-2 py-0.5">{{ globalSearchResults.length }}</span>
                            </div>
                            <div v-for="(res, idx) in globalSearchResults" :key="idx" 
                                class="px-3 py-2 hover:bg-slate-50 rounded-lg cursor-pointer transition-colors group/item"
                                @click="scrollToSearchResult(res.id)">
                                <div class="flex items-center justify-between">
                                    <span class="font-medium text-slate-700 text-sm truncate group-hover/item:text-primary-600">{{ res.title }}</span>
                                    <el-icon class="text-slate-300 group-hover/item:text-primary-400" :size="14"><ArrowRight /></el-icon>
                                </div>
                                <p class="text-xs text-slate-500 mt-0.5 line-clamp-1" v-html="res.preview"></p>
                            </div>
                        </div>
                    </div>


                    
                    <!-- Typography Settings -->
                    <el-popover placement="bottom" :width="240" trigger="click" popper-class="glass-popover">
                        <template #reference>
                            <button class="glass-icon-btn" title="外观设置">
                                <el-icon :size="18"><Setting /></el-icon>
                            </button>
                        </template>
                        <div class="p-2 space-y-4">
                            <!-- Font Size -->
                            <div class="space-y-2">
                                <div class="text-xs font-bold text-slate-500">字号</div>
                                <div class="flex items-center gap-2 bg-slate-100 rounded-lg p-1">
                                    <button class="flex-1 p-1 hover:bg-white rounded text-slate-600" @click="courseStore.uiSettings.fontSize = Math.max(8, courseStore.uiSettings.fontSize - 1)"><el-icon><Minus /></el-icon></button>
                                    <span class="text-xs font-mono w-8 text-center">{{ courseStore.uiSettings.fontSize }}</span>
                                    <button class="flex-1 p-1 hover:bg-white rounded text-slate-600" @click="courseStore.uiSettings.fontSize = Math.min(72, courseStore.uiSettings.fontSize + 1)"><el-icon><Plus /></el-icon></button>
                                </div>
                            </div>
                            <!-- Font Family -->
                            <div class="space-y-2">
                                <div class="text-xs font-bold text-slate-500">字体</div>
                                <div class="grid grid-cols-3 gap-2">
                                    <button class="px-2 py-1 text-xs border rounded hover:border-primary-500" :class="courseStore.uiSettings.fontFamily === 'sans' ? 'bg-primary-50 border-primary-500 text-primary-600' : 'bg-white border-slate-200'" @click="courseStore.uiSettings.fontFamily = 'sans'">无衬线</button>
                                    <button class="px-2 py-1 text-xs border rounded hover:border-primary-500 font-serif" :class="courseStore.uiSettings.fontFamily === 'serif' ? 'bg-primary-50 border-primary-500 text-primary-600' : 'bg-white border-slate-200'" @click="courseStore.uiSettings.fontFamily = 'serif'">衬线</button>
                                    <button class="px-2 py-1 text-xs border rounded hover:border-primary-500 font-mono" :class="courseStore.uiSettings.fontFamily === 'mono' ? 'bg-primary-50 border-primary-500 text-primary-600' : 'bg-white border-slate-200'" @click="courseStore.uiSettings.fontFamily = 'mono'">等宽</button>
                                </div>
                            </div>
                            <!-- Line Height -->
                            <div class="space-y-2">
                                <div class="text-xs font-bold text-slate-500">行高</div>
                                <div class="grid grid-cols-3 gap-2">
                                    <button class="px-2 py-1 text-xs border rounded hover:border-primary-500" :class="courseStore.uiSettings.lineHeight === 1.5 ? 'bg-primary-50 border-primary-500 text-primary-600' : 'bg-white border-slate-200'" @click="courseStore.uiSettings.lineHeight = 1.5">紧凑</button>
                                    <button class="px-2 py-1 text-xs border rounded hover:border-primary-500" :class="courseStore.uiSettings.lineHeight === 1.75 ? 'bg-primary-50 border-primary-500 text-primary-600' : 'bg-white border-slate-200'" @click="courseStore.uiSettings.lineHeight = 1.75">舒适</button>
                                    <button class="px-2 py-1 text-xs border rounded hover:border-primary-500" :class="courseStore.uiSettings.lineHeight === 2 ? 'bg-primary-50 border-primary-500 text-primary-600' : 'bg-white border-slate-200'" @click="courseStore.uiSettings.lineHeight = 2">宽松</button>
                                </div>
                            </div>
                        </div>
                    </el-popover>
                    
                    <!-- Focus Mode -->
                    <button 
                        class="glass-icon-btn"
                        :class="{'!text-primary-600 !bg-primary-50': courseStore.isFocusMode}"
                        @click="toggleFocusMode"
                        title="专注模式 (F)"
                    >
                        <el-icon :size="18"><FullScreen /></el-icon>
                    </button>

                    <div class="w-px h-5 bg-slate-200 mx-1"></div>

                    <el-dropdown trigger="click" @command="handleExport">
                        <button class="glass-icon-btn" title="导出">
                            <el-icon :size="18"><Download /></el-icon>
                        </button>
                        <template #dropdown>
                            <el-dropdown-menu>
                                <el-dropdown-item command="json">导出 JSON 备份</el-dropdown-item>
                                <el-dropdown-item command="markdown">导出 Markdown 文档</el-dropdown-item>
                            </el-dropdown-menu>
                        </template>
                    </el-dropdown>
                </div>
            </div>
        </header>

        <!-- Router View -->
        <router-view></router-view>
    </div>

    <!-- Global Status Bar -->
    <StatusBar 
        :visible="statusVisible"
        :status="statusMode"
        :current-task="statusTask"
        :logs="courseStore.generationLogs"
        :progress="statusProgress"
        :queue="courseStore.queue"
        :meta="statusMeta"
        :hint="statusHint"
        @close="courseStore.stopGeneration"
        @click="handleStatusClick"
    />
  </div>
</template>

<script setup lang="ts">
import StatusBar from './components/StatusBar.vue'
import { useCourseStore } from './stores/course'
import { useRouter } from 'vue-router'
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Setting, Minus, Plus, FullScreen, Search, Download, ArrowRight, CircleClose } from '@element-plus/icons-vue'

const courseStore = useCourseStore()
const router = useRouter()
type StatusTone = 'primary' | 'success' | 'warning' | 'danger' | 'muted'
type StatusMetaItem = { label: string; value: string; tone?: StatusTone }

const statusVisible = computed(() => {
    if (courseStore.generationStatus !== 'idle') return true
    if (courseStore.chatLoading) return true
    if (courseStore.loading) return true
    return courseStore.queue.some(i => i.status === 'running' || i.status === 'pending')
})

const statusMode = computed(() => {
    if (courseStore.generationStatus === 'error') return 'error'
    if (courseStore.isGenerating) return 'generating'
    if (courseStore.chatLoading) return 'generating'
    if (courseStore.loading) return 'paused'
    if (courseStore.queue.some(i => i.status === 'running' || i.status === 'pending')) return 'paused'
    return 'idle'
})

const statusTask = computed(() => {
    if (courseStore.isGenerating) return courseStore.currentGeneratingNode || '内容生成中'
    if (courseStore.chatLoading) return 'AI 生成中'
    if (courseStore.loading) return '数据加载中'
    if (courseStore.queue.some(i => i.status === 'running' || i.status === 'pending')) return '队列等待中'
    return null
})

const statusProgress = computed(() => {
    if (courseStore.isGenerating) return courseStore.generationProgress
    if (courseStore.chatLoading) return 35
    if (courseStore.loading) return 15
    if (courseStore.queue.some(i => i.status === 'running' || i.status === 'pending')) return 5
    return 0
})

const currentCourseName = computed(() => {
    const current = courseStore.courseList.find(c => c.course_id === courseStore.currentCourseId)
    return current?.course_name || '未选择'
})

const statusMeta = computed<StatusMetaItem[]>(() => {
    const pendingCount = courseStore.queue.filter(i => i.status === 'pending').length
    const runningCount = courseStore.queue.filter(i => i.status === 'running').length
    return [
        { label: '课程', value: currentCourseName.value, tone: 'primary' },
        { label: '章节', value: courseStore.currentNode?.node_name || '未选择', tone: 'muted' },
        { label: '节点', value: String(courseStore.nodes.length), tone: 'muted' },
        { label: '笔记', value: String(courseStore.notes.length), tone: 'success' },
        { label: '对话', value: String(courseStore.chatHistory.length), tone: courseStore.chatLoading ? 'warning' : 'muted' },
        { label: '队列', value: `${runningCount} 运行 / ${pendingCount} 等待`, tone: runningCount > 0 ? 'warning' : 'muted' },
        { label: '数据加载', value: courseStore.loading ? '进行中' : '空闲', tone: courseStore.loading ? 'warning' : 'muted' },
        { label: '生成状态', value: statusMode.value, tone: statusMode.value === 'error' ? 'danger' : (statusMode.value === 'generating' ? 'primary' : 'muted') }
    ]
})

const statusHint = computed(() => {
    const lastLog = courseStore.generationLogs[courseStore.generationLogs.length - 1]
    if (lastLog) return lastLog
    if (courseStore.chatLoading) return 'AI 正在思考与生成内容'
    if (courseStore.loading) return '正在加载课程数据'
    return ''
})

// UI State
const globalSearchResults = ref<any[]>([])
const isSearchFocused = ref(false)

// Helper: Flatten nodes for search and export order
const flatNodes = computed(() => {
    const nodes: any[] = []
    const traverse = (node: any) => {
        nodes.push(node)
        if (node.children) {
            node.children.forEach(traverse)
        }
    }
    courseStore.courseTree.forEach(traverse)
    return nodes
})

const handleGlobalSearch = (val: string | Event) => {
    // Handle both direct string and event object
    let searchValue: string
    if (typeof val === 'string') {
        searchValue = val
    } else if (val && val.target) {
        searchValue = (val.target as HTMLInputElement).value
    } else {
        searchValue = ''
    }
    
    if (!searchValue || !searchValue.trim()) {
        globalSearchResults.value = []
        courseStore.globalSearchQuery = ''
        return
    }
    
    courseStore.globalSearchQuery = searchValue
    const query = searchValue.toLowerCase().trim()
    const results: any[] = []
    
    // Search in flatNodes
    flatNodes.value.forEach(node => {
        // Skip root
        if (node.node_level === 1) return
        
        const titleMatch = node.node_name.toLowerCase().includes(query)
        const contentMatch = node.node_content && node.node_content.toLowerCase().includes(query)
        
        if (titleMatch || contentMatch) {
            // Create preview
            let preview = ''
            if (contentMatch) {
                const idx = node.node_content.toLowerCase().indexOf(query)
                const start = Math.max(0, idx - 20)
                const end = Math.min(node.node_content.length, idx + 60)
                preview = '...' + node.node_content.substring(start, end) + '...'
                // Highlight query in preview
                const safeQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
                const regex = new RegExp(`(${safeQuery})`, 'gi')
                preview = preview.replace(regex, '<span class="text-primary-600 font-bold">$1</span>')
            } else {
                preview = '标题匹配'
            }
            
            results.push({
                id: node.node_id,
                title: node.node_name,
                preview: preview
            })
        }
    })
    
    globalSearchResults.value = results.slice(0, 8) // Limit to 8 results
}

const scrollToSearchResult = (nodeId: string) => {
    courseStore.scrollToNode(nodeId)
    const node = flatNodes.value.find(n => n.node_id === nodeId)
    if (node) {
        courseStore.setCurrentNodeSilent(node)
    }
    courseStore.globalSearchQuery = ''
    globalSearchResults.value = []
}

const toggleFocusMode = () => {
    courseStore.isFocusMode = !courseStore.isFocusMode
}

const handleExport = (command: string) => {
    if (command === 'json') {
        courseStore.exportCourseJson()
    } else if (command === 'markdown') {
        courseStore.exportCourseMarkdown()
    }
}

const handleGlobalClick = (e: MouseEvent) => {
    const target = e.target as HTMLElement;
    const btn = target.closest('.copy-btn');
    if (btn) {
        const code = btn.getAttribute('data-code');
        if (code) {
            let text = ''
            try {
                text = decodeURIComponent(code)
            } catch (e) {
                text = code
            }
            navigator.clipboard.writeText(text).then(() => {
                ElMessage.success('代码已复制到剪贴板');
            }).catch(() => {
                ElMessage.error('复制失败');
            });
        }
    }
}

const handleStatusClick = () => {
    if (courseStore.currentCourseId) {
        router.push(`/course/${courseStore.currentCourseId}`)
    }
}

onMounted(() => {
    document.addEventListener('click', handleGlobalClick);
    // Restore generation state globally
    const restoredId = courseStore.restoreGenerationState()
    if (restoredId && router.currentRoute.value.path === '/') {
        router.push(`/course/${restoredId}`)
        ElMessage.success('已自动恢复上次未完成的课程生成任务')
    }
})

onUnmounted(() => {
    document.removeEventListener('click', handleGlobalClick);
})
</script>

<style>
.tech-search-input .el-input__wrapper {
    background-color: rgba(255, 255, 255, 0.6) !important;
    backdrop-filter: blur(16px) !important;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), inset 0 0 0 1px rgba(255, 255, 255, 0.6) !important;
    border-radius: 9999px !important;
    padding-left: 18px !important;
    padding-right: 18px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
}

.tech-search-input .el-input__wrapper.is-focus {
    box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.3), 0 8px 30px rgba(99, 102, 241, 0.2), inset 0 0 20px rgba(99, 102, 241, 0.05) !important;
    background-color: rgba(255, 255, 255, 0.9) !important;
    border-color: rgba(99, 102, 241, 0.5) !important;
    transform: translateY(-1px);
}

.tech-search-input .el-input__wrapper:hover:not(.is-focus) {
    background-color: rgba(255, 255, 255, 0.8) !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
}

.tech-search-input .el-input__inner {
    font-weight: 600 !important;
    color: #1e293b !important;
    font-family: 'Space Grotesk', system-ui, sans-serif !important;
}

.tech-search-input .el-input__inner::placeholder {
    color: #64748b !important;
    font-weight: 500 !important;
    letter-spacing: 0.025em !important;
}
</style>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.glass-panel-tech-floating {
    background: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(20px) saturate(180%);
    border: 1px solid rgba(255, 255, 255, 0.6);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.04);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
