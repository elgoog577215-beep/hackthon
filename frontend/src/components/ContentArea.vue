<template>
  <div class="h-full flex flex-col relative">
    <!-- Reading Progress Bar - Positioned below header -->
    <div class="absolute top-0 left-0 right-0 h-1 bg-slate-100/50 z-10" v-if="scrollProgress > 0">
        <div class="h-full bg-gradient-to-r from-primary-400 to-primary-600 transition-all duration-300 ease-out shadow-[0_0_10px_rgba(99,102,241,0.5)]" :style="{ width: scrollProgress + '%' }"></div>
    </div>

    <!-- Image Lightbox -->
    <Teleport to="body">
        <transition name="fade">
            <div v-if="lightboxVisible" class="fixed inset-0 z-[100] bg-black/90 backdrop-blur-md flex items-center justify-center cursor-zoom-out" @click="lightboxVisible = false">
                <img :src="lightboxImage" class="max-w-[95vw] max-h-[95vh] object-contain rounded-lg shadow-2xl transition-transform duration-300 scale-100 hover:scale-[1.02]" alt="Full screen preview" />
                <button class="absolute top-4 right-4 text-white/50 hover:text-white p-2 rounded-full hover:bg-white/10 transition-colors">
                    <el-icon :size="32"><Close /></el-icon>
                </button>
            </div>
        </transition>
    </Teleport>

    <!-- Export Dialog -->
    <Teleport to="body">
        <transition name="fade-scale">
            <div v-if="exportDialog.visible" class="fixed inset-0 z-[100] flex items-center justify-center p-4">
                <!-- Backdrop -->
                <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="closeExportDialog"></div>
                
                <!-- Dialog Content -->
                <div class="relative bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden transform transition-all">
                    <!-- Header -->
                    <div class="px-6 py-5 bg-gradient-to-r from-primary-500 to-primary-600 flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <div class="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
                                <el-icon class="text-white" :size="24"><Download /></el-icon>
                            </div>
                            <div>
                                <h3 class="text-lg font-bold text-white">{{ exportDialog.title }}</h3>
                                <p class="text-sm text-white/80">{{ exportDialog.subtitle }}</p>
                            </div>
                        </div>
                        <button @click="closeExportDialog" class="w-8 h-8 flex items-center justify-center text-white/70 hover:text-white hover:bg-white/20 rounded-lg transition-all">
                            <el-icon :size="20"><Close /></el-icon>
                        </button>
                    </div>
                    
                    <!-- Body -->
                    <div class="p-6 space-y-4">
                        <!-- Export Scope -->
                        <div class="space-y-2">
                            <label class="text-sm font-medium text-slate-700">导出范围</label>
                            <div class="grid grid-cols-3 gap-2">
                                <button 
                                    v-for="scope in exportScopes" 
                                    :key="scope.value"
                                    @click="exportDialog.scope = scope.value"
                                    class="px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 border-2"
                                    :class="exportDialog.scope === scope.value 
                                        ? 'border-primary-500 bg-primary-50 text-primary-700' 
                                        : 'border-slate-100 bg-slate-50 text-slate-600 hover:border-slate-200 hover:bg-slate-100'"
                                >
                                    <div class="flex flex-col items-center gap-1">
                                        <el-icon :size="18"><component :is="scope.icon" /></el-icon>
                                        <span>{{ scope.label }}</span>
                                    </div>
                                </button>
                            </div>
                        </div>
                        
                        <!-- Export Format -->
                        <div class="space-y-2">
                            <label class="text-sm font-medium text-slate-700">导出格式</label>
                            <div class="grid grid-cols-2 gap-3">
                                <button 
                                    v-for="fmt in exportFormats" 
                                    :key="fmt.value"
                                    @click="exportDialog.format = fmt.value"
                                    class="relative px-4 py-4 rounded-xl text-left transition-all duration-200 border-2 group"
                                    :class="exportDialog.format === fmt.value 
                                        ? 'border-primary-500 bg-primary-50/50' 
                                        : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'"
                                >
                                    <div class="flex items-start gap-3">
                                        <div class="w-10 h-10 rounded-lg flex items-center justify-center transition-colors"
                                            :class="exportDialog.format === fmt.value ? 'bg-primary-100' : 'bg-slate-100 group-hover:bg-slate-200'">
                                            <el-icon :size="20" :class="exportDialog.format === fmt.value ? 'text-primary-600' : 'text-slate-500'">
                                                <component :is="fmt.icon" />
                                            </el-icon>
                                        </div>
                                        <div class="flex-1">
                                            <div class="font-semibold text-slate-800">{{ fmt.label }}</div>
                                            <div class="text-xs text-slate-500 mt-0.5">{{ fmt.desc }}</div>
                                        </div>
                                        <div v-if="exportDialog.format === fmt.value" class="absolute top-2 right-2 w-5 h-5 rounded-full bg-primary-500 flex items-center justify-center">
                                            <el-icon class="text-white" :size="12"><Check /></el-icon>
                                        </div>
                                    </div>
                                </button>
                            </div>
                        </div>
                        
                        <!-- Export Preview -->
                        <div class="bg-slate-50 rounded-xl p-4 space-y-2">
                            <div class="flex items-center justify-between text-sm">
                                <span class="text-slate-500">预计导出</span>
                                <span class="font-semibold text-slate-800">{{ getExportCount }} 条笔记</span>
                            </div>
                            <div class="flex items-center justify-between text-sm">
                                <span class="text-slate-500">文件大小</span>
                                <span class="font-semibold text-slate-800">约 {{ getExportSize }}</span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Footer -->
                    <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-3">
                        <button @click="closeExportDialog" class="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800 hover:bg-slate-200/50 rounded-lg transition-all">
                            取消
                        </button>
                        <button 
                            @click="executeExport" 
                            :disabled="exportDialog.loading"
                            class="px-5 py-2 bg-gradient-to-r from-primary-500 to-primary-600 hover:from-primary-600 hover:to-primary-700 text-white text-sm font-medium rounded-lg shadow-lg shadow-primary-500/25 transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <el-icon v-if="exportDialog.loading" class="is-loading"><Loading /></el-icon>
                            <el-icon v-else><Download /></el-icon>
                            {{ exportDialog.loading ? '导出中...' : '开始导出' }}
                        </button>
                    </div>
                </div>
            </div>
        </transition>
    </Teleport>

    <!-- Settings Dialog -->
    <Teleport to="body">
        <transition name="fade-scale">
            <div v-if="settingsDialog.visible" class="fixed inset-0 z-[100] flex items-center justify-center p-4">
                <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="closeSettingsDialog"></div>
                <div class="relative bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden transform transition-all">
                    <div class="px-6 py-5 bg-gradient-to-r from-primary-500 to-primary-600 flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <div class="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
                                <el-icon class="text-white" :size="24"><Setting /></el-icon>
                            </div>
                            <div>
                                <h3 class="text-lg font-bold text-white">阅读设置</h3>
                                <p class="text-sm text-white/80">自定义阅读体验</p>
                            </div>
                        </div>
                        <button @click="closeSettingsDialog" class="w-8 h-8 flex items-center justify-center text-white/70 hover:text-white hover:bg-white/20 rounded-lg transition-all">
                            <el-icon :size="20"><Close /></el-icon>
                        </button>
                    </div>
                    <div class="p-6 space-y-6">
                        <!-- Font Size -->
                        <div class="space-y-3">
                            <div class="flex items-center justify-between">
                                <label class="text-sm font-medium text-slate-700">字体大小</label>
                                <span class="text-xs text-slate-500">{{ settingsDialog.fontSize }}px</span>
                            </div>
                            <el-slider v-model="settingsDialog.fontSize" :min="12" :max="24" :step="1" show-stops />
                            <div class="flex justify-between text-xs text-slate-400">
                                <span>小</span>
                                <span>中</span>
                                <span>大</span>
                            </div>
                        </div>
                        <!-- Line Height -->
                        <div class="space-y-3">
                            <div class="flex items-center justify-between">
                                <label class="text-sm font-medium text-slate-700">行高</label>
                                <span class="text-xs text-slate-500">{{ settingsDialog.lineHeight }}</span>
                            </div>
                            <el-slider v-model="settingsDialog.lineHeight" :min="1.2" :max="2.0" :step="0.1" show-stops />
                        </div>
                        <!-- Font Family -->
                        <div class="space-y-3">
                            <label class="text-sm font-medium text-slate-700">字体</label>
                            <div class="grid grid-cols-3 gap-2">
                                <button v-for="font in fontOptions" :key="font.value"
                                    @click="settingsDialog.fontFamily = font.value"
                                    class="px-3 py-2 rounded-xl text-sm transition-all border-2"
                                    :class="settingsDialog.fontFamily === font.value 
                                        ? 'border-primary-500 bg-primary-50 text-primary-700' 
                                        : 'border-slate-100 bg-slate-50 text-slate-600 hover:border-slate-200'"
                                    :style="{ fontFamily: font.value }">
                                    {{ font.label }}
                                </button>
                            </div>
                        </div>
                    </div>
                    <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex justify-end gap-3">
                        <button @click="closeSettingsDialog" class="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800 hover:bg-slate-200/50 rounded-lg transition-all">取消</button>
                        <button @click="applySettings" class="px-4 py-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-lg transition-all flex items-center gap-2">
                            <el-icon><Check /></el-icon>应用设置
                        </button>
                    </div>
                </div>
            </div>
        </transition>
    </Teleport>

    <!-- Content List (Continuous Scroll) -->
    <div class="flex-1 overflow-auto p-3 lg:p-5 xl:p-6 relative scroll-smooth custom-scrollbar" id="content-scroll-container" @mouseup="handleMouseUp" @click="handleContentClick">
      
        <!-- Note Hover Preview -->
        <Teleport to="body">
            <transition name="fade-slide">
                <div v-if="hoverPreview.visible && hoverPreview.note" 
                    class="fixed z-[60] pointer-events-none"
                    :style="{ left: hoverPreview.x + 'px', top: hoverPreview.y + 'px' }">
                    <div class="bg-white/95 backdrop-blur-xl rounded-xl shadow-[0_12px_40px_rgba(0,0,0,0.15)] border border-slate-200/60 max-w-[280px] overflow-hidden transform -translate-x-1/2 -translate-y-full mb-2">
                        <div class="px-3 py-2 border-b border-slate-100 bg-gradient-to-r from-amber-50/50 to-white">
                            <div class="flex items-center gap-1.5">
                                <div class="w-5 h-5 rounded-md bg-amber-100 flex items-center justify-center">
                                    <el-icon class="text-amber-600" :size="12"><Notebook /></el-icon>
                                </div>
                                <span class="text-[11px] font-bold text-slate-600 uppercase tracking-wide">笔记</span>
                            </div>
                        </div>
                        <div class="p-3">
                            <div v-if="hoverPreview.note.quote" class="text-[11px] text-slate-400 italic mb-2 border-l-2 border-amber-200 pl-2 line-clamp-2">
                                "{{ hoverPreview.note.quote.slice(0, 60) }}{{ hoverPreview.note.quote.length > 60 ? '...' : '' }}"
                            </div>
                            <div class="text-xs text-slate-700 leading-relaxed line-clamp-4">
                                {{ hoverPreview.note.summary || hoverPreview.note.content?.slice(0, 150) }}
                                {{ (hoverPreview.note.content?.length || 0) > 150 ? '...' : '' }}
                            </div>
                        </div>
                        <div class="px-3 py-1.5 bg-slate-50/50 border-t border-slate-100 text-[10px] text-slate-400 flex items-center gap-1">
                            <el-icon :size="10"><Timer /></el-icon>
                            {{ dayjs(hoverPreview.note.createdAt).fromNow() }}
                        </div>
                    </div>
                </div>
            </transition>
        </Teleport>

        <!-- Selection Menu -->
    <Teleport to="body">
      <transition name="scale-fade">
        <div v-if="selectionMenu.visible" 
            id="selection-menu"
            class="fixed z-50 flex flex-col p-1.5 bg-white/95 backdrop-blur-xl rounded-lg shadow-[0_12px_40px_rgba(0,0,0,0.15)] border border-white/40 ring-1 ring-black/5 min-w-[260px] select-none"
            :style="{ 
                left: selectionMenu.x + 'px', 
                top: selectionMenu.y + 'px', 
                transform: selectionMenu.placement === 'bottom' ? 'translateX(-50%)' : 'translate(-50%, -100%)' 
            }"
            @mousedown.stop>
            
            <!-- Row 1: Quick Actions -->
            <div class="flex items-center gap-1 pb-1.5 mb-1.5 border-b border-slate-100">
                <el-tooltip content="引用提问" placement="top" :show-after="500">
                    <button @click="handleAsk" class="flex-1 relative z-10 flex flex-col items-center justify-center gap-0.5 px-2 py-1.5 rounded-xl text-slate-600 hover:text-primary-600 hover:bg-primary-50 transition-all group active:scale-95">
                        <el-icon class="text-lg mb-0.5"><ChatDotRound /></el-icon> 
                        <span class="text-[10px] font-bold">提问</span>
                    </button>
                </el-tooltip>
                
                <div class="w-px h-6 bg-slate-100"></div>
                
                <el-tooltip content="添加笔记" placement="top" :show-after="500">
                    <button @click="handleAddNote" class="flex-1 relative z-10 flex flex-col items-center justify-center gap-0.5 px-2 py-1.5 rounded-xl text-slate-600 hover:text-amber-600 hover:bg-amber-50 transition-all group active:scale-95">
                        <el-icon class="text-lg mb-0.5"><ChatLineSquare /></el-icon> 
                        <span class="text-[10px] font-bold">笔记</span>
                    </button>
                </el-tooltip>
                
                <div class="w-px h-6 bg-slate-100"></div>
                
                <el-tooltip content="智能翻译" placement="top" :show-after="500">
                    <button @click="handleTranslate" class="flex-1 relative z-10 flex flex-col items-center justify-center gap-0.5 px-2 py-1.5 rounded-xl text-slate-600 hover:text-emerald-600 hover:bg-emerald-50 transition-all group active:scale-95">
                        <el-icon class="text-lg mb-0.5"><Connection /></el-icon> 
                        <span class="text-[10px] font-bold">翻译</span>
                    </button>
                </el-tooltip>
            </div>

            <!-- Row 2: Formatting -->
            <div class="flex items-center justify-between px-1">
                <!-- Colors -->
                <div class="flex gap-1.5 bg-slate-50 p-1 rounded-lg">
                    <button v-for="color in [
                            { name: 'yellow', class: 'bg-yellow-400' },
                            { name: 'green', class: 'bg-green-400' },
                            { name: 'blue', class: 'bg-blue-400' },
                            { name: 'pink', class: 'bg-pink-400' },
                            { name: 'orange', class: 'bg-orange-400' }
                            ]" :key="color.name"
                            class="w-4 h-4 rounded-full border border-black/5 hover:scale-125 hover:border-black/10 transition-transform relative cursor-pointer"
                            :class="color.class"
                            @click="applyFormat('highlight', color.name)"
                            :title="color.name">
                    </button>
                </div>
                
                <!-- Styles -->
                <div class="flex gap-1">
                    <el-tooltip content="加粗 (Ctrl+B)" placement="bottom" :show-after="500">
                        <button class="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-600 font-bold text-sm transition-colors" @click="applyFormat('bold')">B</button>
                    </el-tooltip>
                    <el-tooltip content="下划线 (Ctrl+U)" placement="bottom" :show-after="500">
                        <button class="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-600 underline text-sm transition-colors" @click="applyFormat('underline', 'solid')">U</button>
                    </el-tooltip>
                    <el-tooltip content="波浪线 (Ctrl+I)" placement="bottom" :show-after="500">
                        <button class="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-600 decoration-wavy underline text-sm transition-colors" @click="applyFormat('underline', 'wavy')">~</button>
                    </el-tooltip>
                </div>
            </div>
            
            <!-- Arrow -->
            <div v-if="selectionMenu.placement === 'bottom'" class="absolute -top-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-white border-t border-l border-white/40 rotate-45 shadow-[-2px_-2px_4px_rgba(0,0,0,0.02)]" :style="{ marginLeft: selectionMenu.arrowOffset + 'px' }"></div>
            <div v-else class="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-white border-b border-r border-white/40 rotate-45 shadow-[4px_4px_4px_rgba(0,0,0,0.05)]" :style="{ marginLeft: selectionMenu.arrowOffset + 'px' }"></div>
        </div>
      </transition>
    </Teleport>

      <div v-if="flatNodes.length > 0" class="flex w-full h-full relative">


        <!-- Main Content Column -->
        <div class="flex-1 min-w-0 px-2 sm:px-3 lg:px-4 xl:px-6 space-y-8 sm:space-y-10 lg:space-y-12 pb-24 sm:pb-28 lg:pb-32 pt-2 sm:pt-3 lg:pt-4" :class="{ 'mr-[260px] xl:mr-[300px]': !courseStore.isFocusMode && !isNotesCollapsed }">
            <CourseNode 
                    v-for="(node, index) in visibleNodes" 
                    :key="node.node_id"
                    :node="node" 
                    :index="index"
                    :font-size="fontSize"
                    :font-family="fontFamily"
                    :line-height="lineHeight"
                    :search-words="searchTokens"
                    @start-quiz="handleStartQuiz"
                />
            
            <!-- Sentinel for Lazy Loading -->
            <div ref="sentinelRef" class="h-10 w-full flex items-center justify-center">
                <div v-if="renderedCount < flatNodes.length" class="text-slate-400 text-xs flex items-center gap-2 py-2 opacity-50">
                    <el-icon class="is-loading"><Loading /></el-icon>
                </div>
            </div>
        </div>
        
        <!-- Collapsed Notes Trigger - Fixed position that follows scroll -->
        <div v-if="isNotesCollapsed && !courseStore.isFocusMode" class="fixed right-6 top-24 z-50 hidden md:block">
            <button 
                @click="isNotesCollapsed = false" 
                class="p-2.5 glass-panel-tech rounded-xl text-slate-500 hover:text-primary-600 shadow-lg hover:scale-105 transition-all bg-white/90 backdrop-blur-md border border-slate-200/60 flex items-center gap-2 group"
                title="展开笔记"
            >
                <el-icon :size="18"><Notebook /></el-icon>
                <span class="text-xs font-medium max-w-0 overflow-hidden group-hover:max-w-[80px] transition-all duration-300 whitespace-nowrap">展开笔记</span>
                <span class="absolute -top-1 -right-1 w-4 h-4 bg-primary-500 text-white text-[10px] rounded-full flex items-center justify-center font-bold" v-if="noteCounts.notes + noteCounts.mistakes > 0">
                    {{ noteCounts.notes + noteCounts.mistakes }}
                </span>
            </button>
        </div>

        <!-- Note Column (Desktop Only) - Fixed position for sticky header -->
        <div id="note-column" v-if="!courseStore.isFocusMode && !isNotesCollapsed" class="hidden md:flex flex-col fixed right-0 top-0 bottom-0 w-[260px] xl:w-[300px] bg-gradient-to-b from-slate-50/80 to-slate-100/50 transition-all duration-300 border-l border-slate-200/50 z-20" style="padding-top: 80px; padding-bottom: 70px;">
             <!-- Compact Header -->
            <div class="flex-shrink-0 px-3 py-3 bg-white/90 backdrop-blur-xl border-b border-slate-200/60">
                <!-- Header Row -->
                <div class="flex items-center justify-between mb-2">
                    <div class="flex items-center gap-2">
                        <div class="w-7 h-7 rounded-lg bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center shadow-md shadow-primary-500/20">
                            <el-icon class="text-white" :size="14"><Notebook /></el-icon>
                        </div>
                        <div>
                            <h3 class="text-xs font-bold text-slate-800">笔记</h3>
                            <p class="text-[9px] text-slate-400">{{ noteCounts.notes }} · {{ noteCounts.mistakes }} 错题</p>
                        </div>
                    </div>
                    <div class="flex items-center gap-0.5">
                        <el-tooltip content="收起" placement="bottom">
                            <button @click="isNotesCollapsed = true" class="w-7 h-7 flex items-center justify-center text-slate-400 hover:text-primary-600 hover:bg-slate-100 rounded-lg transition-all duration-200">
                                <el-icon :size="14"><ArrowRight /></el-icon>
                            </button>
                        </el-tooltip>
                        <el-dropdown trigger="click" placement="bottom-end">
                            <button class="w-7 h-7 flex items-center justify-center text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-all duration-200">
                                <el-icon :size="16"><More /></el-icon>
                            </button>
                            <template #dropdown>
                                <el-dropdown-menu>
                                    <el-dropdown-item @click="openSettingsDialog">
                                        <el-icon class="mr-2"><Setting /></el-icon>阅读设置
                                    </el-dropdown-item>
                                    <el-dropdown-item @click="openExportDialog('notes')">
                                        <el-icon class="mr-2"><Download /></el-icon>导出笔记
                                    </el-dropdown-item>
                                    <el-dropdown-item @click="openExportDialog('mistakes')" v-if="noteCounts.mistakes > 0">
                                        <el-icon class="mr-2"><Document /></el-icon>导出错题
                                    </el-dropdown-item>
                                </el-dropdown-menu>
                            </template>
                        </el-dropdown>
                    </div>
                </div>
                
                <!-- Tab Navigation -->
                <div class="flex items-center gap-1 p-0.5 bg-slate-100/80 rounded-lg">
                    <button v-for="tab in noteTabs" :key="tab.key"
                        class="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 text-[11px] font-medium rounded-md transition-all duration-200"
                        :class="activeNoteFilter === tab.key 
                            ? 'bg-white text-slate-800 shadow-sm' 
                            : 'text-slate-500 hover:text-slate-700 hover:bg-slate-200/50'"
                        @click="activeNoteFilter = tab.key"
                    >
                        <el-icon :size="12" :class="tab.color"><component :is="tab.icon" /></el-icon>
                        <span>{{ tab.label }}</span>
                        <span v-if="tab.count > 0" class="ml-0.5 px-1 py-0.5 text-[9px] rounded-full"
                              :class="activeNoteFilter === tab.key ? 'bg-slate-100 text-slate-600' : 'bg-slate-200/50 text-slate-500'">
                            {{ tab.count }}
                        </span>
                    </button>
                </div>

                <!-- Search Bar -->
                <div class="relative mt-2">
                    <div class="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400">
                        <el-icon :size="14"><Search /></el-icon>
                    </div>
                    <input 
                        v-model="noteSearchQuery" 
                        type="text"
                        placeholder="搜索..."
                        class="w-full pl-8 pr-8 py-2 bg-slate-100/50 border border-transparent rounded-lg text-xs text-slate-700 placeholder:text-slate-400 focus:bg-white focus:border-primary-300 focus:ring-2 focus:ring-primary-500/10 transition-all duration-200 outline-none"
                    >
                    <div v-if="noteSearchQuery" @click="noteSearchQuery = ''" 
                         class="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 flex items-center justify-center text-slate-400 hover:text-slate-600 hover:bg-slate-200 rounded-full cursor-pointer transition-all">
                        <el-icon :size="10"><Close /></el-icon>
                    </div>
                </div>
            </div>

            <div id="notes-container" class="relative flex-1 w-full flex flex-col">
                <!-- Mistakes View (Linear List) -->
                <div v-if="activeNoteFilter === 'mistakes'" class="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-3">
                     <div v-if="displayedNotes.length === 0" class="text-center py-8 text-xs text-slate-400 bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
                        {{ noteEmptyText }}
                    </div>
                    <div v-for="note in displayedNotes" :key="note.id"
                         class="bg-white rounded-2xl shadow-sm border border-slate-200/60 p-0 group hover:shadow-xl hover:shadow-red-500/5 hover:border-red-200 transition-all duration-300 cursor-pointer overflow-hidden relative"
                         :class="{'ring-2 ring-red-100': activeNoteId === note.id}"
                         @click="handleNoteClick(note)">
                         
                         <!-- Header -->
                        <div class="flex justify-between items-center px-4 py-3 border-b border-red-50/50 bg-gradient-to-r from-red-50/30 to-transparent">
                            <div class="flex flex-col gap-0.5">
                                <div class="text-[11px] font-black text-red-500 flex items-center gap-1.5 uppercase tracking-wide bg-red-50 px-2 py-1 rounded-md">
                                    <div class="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse"></div>
                                    错题本
                                </div>
                                <div class="text-[10px] font-bold text-slate-400 truncate max-w-[180px] mt-1 pl-1">
                                    {{ getNodeName(note.nodeId) }}
                                </div>
                            </div>
                            
                            <div class="flex gap-1">
                                <button class="p-1.5 hover:bg-white rounded-md text-slate-400 hover:text-red-500 transition-all shadow-sm border border-transparent hover:border-slate-100" @click.stop="handleDeleteNote(note.id)">
                                    <el-icon :size="14"><Delete /></el-icon>
                                </button>
                            </div>
                        </div>

                        <!-- Content -->
                        <div class="p-4">
                            <div class="text-sm text-slate-700 leading-7 font-sans tracking-normal">
                                <MarkdownRenderer :content="note.content" :search-words="searchTokens" />
                            </div>
                            <div class="mt-4 pt-3 border-t border-slate-50 flex items-center justify-between text-[11px] text-slate-400">
                                <div class="flex items-center gap-1.5 font-medium">
                                    <el-icon><Timer /></el-icon> {{ dayjs(note.createdAt).fromNow() }}
                                </div>
                                <div class="flex items-center gap-3">
                                    <button class="flex items-center gap-1 hover:text-primary-600 transition-colors px-2 py-1 rounded-full hover:bg-primary-50" @click.stop="handleNoteClick(note)">
                                        <el-icon><Position /></el-icon> 跳转原文
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Notes View (Aligned/Absolute) -->
                <div v-else class="relative flex-1 w-full">
                    <div v-if="displayedNotes.length === 0" class="absolute inset-0 flex items-center justify-center">
                        <div class="px-3 py-2 text-xs text-slate-400 bg-white/80 backdrop-blur-sm border border-white rounded-xl">
                            {{ noteEmptyText }}
                        </div>
                    </div>
                    <div class="absolute inset-0 pointer-events-none">
                        <!-- Guide Line -->
                        <div class="absolute left-[-1px] top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-primary-200 to-transparent opacity-50"></div>
                    </div>

                    <!-- Quoted Notes (Absolute Positioning) -->
                    <transition-group name="list">
                        <div v-for="note in displayedQuotedNotes" :key="note.id" :id="note.id"
                             class="absolute left-2 right-2 transition-all duration-200 ease-out will-change-[top]"
                             :style="{ top: (note.top || 0) + 'px' }">
                            
                             <!-- Connector Line -->
                             <div class="absolute -left-4 top-5 w-4 h-px transition-colors duration-200" 
                                  :class="(activeNoteId === note.id || hoveredNoteId === note.id) ? 'bg-primary-300' : 'bg-slate-200'"></div>
                             <div class="absolute -left-[18px] top-[17px] w-2 h-2 rounded-full shadow-sm ring-2 ring-white transition-all duration-200"
                                  :class="(activeNoteId === note.id || hoveredNoteId === note.id) ? 'bg-primary-500 scale-125' : (note.sourceType === 'ai' ? 'bg-purple-400' : 'bg-slate-300')"></div>

                             <!-- Note Bubble -->
                             <div class="bg-white rounded-2xl shadow-[0_2px_12px_-4px_rgba(0,0,0,0.08)] border border-slate-200/60 p-0 group hover:shadow-[0_12px_32px_-8px_rgba(0,0,0,0.12)] hover:border-primary-200/80 transition-all duration-200 cursor-pointer overflow-hidden relative"
                                  :class="[noteCardBorderClass(note), {'ring-2 ring-primary-200 ring-offset-2 shadow-lg': activeNoteId === note.id || hoveredNoteId === note.id, '!border-purple-200 !bg-purple-50/10': note.sourceType === 'ai'}]"
                                 @click="handleNoteClick(note)"
                                  @mouseenter="setHovered(note.id)"
                                  @mouseleave="setHovered(null)">
                                
                                <!-- Header -->
                                <div class="flex justify-between items-center px-4 py-3 border-b border-slate-100/50 transition-colors duration-300 bg-gradient-to-r from-slate-50/50 to-white/50 backdrop-blur-sm"
                                     :class="note.sourceType === 'ai' ? 'group-hover:border-purple-100 from-purple-50/30' : 'group-hover:border-amber-100'">
                                    
                                    <div v-if="note.sourceType === 'ai'" class="text-[11px] font-bold text-purple-600 flex items-center gap-1.5 uppercase tracking-wide bg-purple-100/50 px-2 py-1 rounded-md">
                                        <el-icon><MagicStick /></el-icon> AI 助手
                                    </div>
                                    <div v-else class="text-[11px] font-bold text-slate-500 flex items-center gap-1.5 uppercase tracking-wide bg-slate-100 px-2 py-1 rounded-md">
                                        <div class="w-1.5 h-1.5 rounded-full" :class="noteDotClass(note)"></div>
                                        笔记
                                    </div>
                                    
                                    <div class="flex gap-1.5">
                                        <button class="w-7 h-7 flex items-center justify-center rounded-lg bg-red-50/50 hover:bg-red-100 text-red-400 hover:text-red-500 transition-all duration-200 hover:scale-105" @click.stop="handleDeleteNote(note.id)" title="删除笔记">
                                            <el-icon :size="14"><Delete /></el-icon>
                                        </button>
                                    </div>
                                </div>

                                <!-- Content -->
                                <div class="p-4">
                                    <!-- Content Preview -->
                                    <div class="relative group/content">
                                        <div class="text-sm text-slate-700 leading-relaxed font-sans tracking-normal note-content-markdown note-preview-content line-clamp-4">
                                        <MarkdownRenderer :content="note.summary || note.content" :search-words="searchTokens" />
                                    </div>
                                    </div>

                                    <!-- View Full Action -->
                                    <div class="mt-4 pt-3 border-t border-slate-100/60 flex items-center justify-between">
                                        <div class="flex items-center gap-1.5 text-[11px] text-slate-400 font-medium">
                                            <el-icon><Timer /></el-icon>
                                            <span>{{ dayjs(note.createdAt).fromNow() }}</span>
                                        </div>
                                        
                                        <button @click.stop="handleNoteClick(note)" class="text-[11px] font-semibold text-primary-500 hover:text-primary-600 flex items-center gap-1 transition-all duration-200 px-2.5 py-1.5 rounded-lg hover:bg-primary-50 hover:scale-105">
                                            查看详情 <el-icon :size="12"><ArrowRight /></el-icon>
                                        </button>
                                    </div>
                                </div>
                             </div>
                        </div>
                    </transition-group>
                </div>
            </div>
        </div>
      </div>
      
      <!-- Mobile Notes Drawer moved to end -->

      <!-- Empty Selection Guide -->
      <div v-else-if="!courseStore.currentCourseId" class="flex flex-col items-center justify-center h-full text-slate-400 animate-in fade-in zoom-in duration-500">
          <div class="w-32 h-32 bg-slate-50 rounded-full flex items-center justify-center mb-6 shadow-inner relative overflow-hidden">
              <div class="absolute inset-0 bg-gradient-to-tr from-slate-100 to-transparent opacity-50"></div>
              <el-icon :size="48" class="opacity-30 text-slate-500"><Notebook /></el-icon>
          </div>
          <h3 class="text-xl font-bold text-slate-600 mb-2">开始您的学习之旅</h3>
          <p class="text-sm font-medium opacity-60">请从左侧选择一个课程或章节开始阅读</p>
      </div>
      
      <!-- Loading State -->
      <div v-else class="flex flex-col items-center justify-center h-64 gap-4">
          <div class="w-12 h-12 border-4 border-primary-200 border-t-primary-500 rounded-full animate-spin"></div>
          <p class="text-sm text-slate-500 font-medium animate-pulse">正在加载精彩内容...</p>
      </div>

    </div>


      <!-- Mobile Notes Drawer -->
      <el-drawer v-model="courseStore.isMobileNotesVisible" title="课程笔记" size="80%" direction="rtl">
        <div class="flex flex-col h-full">
            <div class="p-4 border-b border-slate-100">
                <el-input v-model="noteSearchQuery" placeholder="搜索笔记..." :prefix-icon="Search" clearable class="glass-input-clean" />
            </div>
            <div class="flex-1 overflow-auto p-4 space-y-4">
                <div v-if="displayedNotes.length === 0" class="text-center text-slate-400 py-8">
                    {{ noteEmptyText }}
                </div>
                <div v-for="note in displayedNotes" :key="'mobile-'+note.id" 
                     class="bg-white rounded-xl shadow-[0_2px_8px_-2px_rgba(0,0,0,0.05)] border border-slate-200/60 p-4 active:scale-98 transition-all duration-200"
                     :class="{'!border-purple-200 !bg-purple-50/10 shadow-purple-100': note.sourceType === 'ai'}"
                     @click="scrollToHighlight(note.highlightId, note.id); courseStore.isMobileNotesVisible = false">
                    <div class="flex justify-between items-start mb-3">
                        <div v-if="note.sourceType === 'ai'" class="text-[11px] font-bold text-purple-600 bg-purple-100/50 px-2 py-1 rounded-md flex items-center gap-1"><el-icon><MagicStick /></el-icon> AI 助手</div>
                        <div v-else class="text-[11px] font-bold px-2 py-1 rounded-md bg-slate-100 text-slate-500" :class="noteBadgeClass(note)">笔记</div>
                        <div class="flex gap-1">
                             <button class="p-1.5 text-slate-400 hover:text-primary-600 rounded-md hover:bg-slate-50" @click.stop="handleEditNote(note)"><el-icon :size="16"><Edit /></el-icon></button>
                             <button class="p-1.5 text-slate-400 hover:text-red-500 rounded-md hover:bg-slate-50" @click.stop="handleDeleteNote(note.id)"><el-icon :size="16"><Delete /></el-icon></button>
                        </div>
                    </div>
                    <div v-if="note.quote" class="text-xs text-slate-500 italic mb-3 border-l-2 border-slate-200 pl-3 py-1">"{{ note.quote }}"</div>
                    <div class="text-sm text-slate-700 leading-7 font-sans tracking-normal">
                        <MarkdownRenderer :content="note.summary || note.content" :search-words="searchTokens" />
                    </div>
                    <div class="mt-3 text-[11px] text-slate-400 flex items-center gap-1.5 font-medium">
                        <el-icon><Timer /></el-icon> {{ dayjs(note.createdAt).fromNow() }}
                    </div>
                </div>
            </div>
        </div>
      </el-drawer>

    <!-- Quiz Configuration Dialog -->
    <el-dialog
        v-model="quizConfig.visible"
        title="生成智能测验"
        width="400px"
        class="glass-dialog-clean"
        align-center
        append-to-body
    >
        <div class="flex flex-col gap-4">
             <div class="p-3 bg-primary-50 rounded-xl border border-primary-100/50">
                <div class="text-xs text-primary-500 font-bold mb-1">测试章节</div>
                <div class="text-sm font-medium text-slate-700 truncate">{{ quizConfig.nodeName }}</div>
             </div>
             
             <div class="space-y-3">
                 <div class="flex justify-between items-center">
                    <div class="text-sm font-bold text-slate-600">题目数量</div>
                    <div class="text-xs font-bold text-primary-600 bg-primary-50 px-2 py-0.5 rounded">{{ quizConfig.questionCount }} 题</div>
                 </div>
                 <el-slider v-model="quizConfig.questionCount" :min="3" :max="10" :step="1" show-stops size="small" />
             </div>

             <div class="space-y-3">
                 <div class="text-sm font-bold text-slate-600">难度选择</div>
                 <div class="grid grid-cols-3 gap-2">
                    <button v-for="diff in [DIFFICULTY_LEVELS.BEGINNER, DIFFICULTY_LEVELS.INTERMEDIATE, DIFFICULTY_LEVELS.ADVANCED]" :key="diff"
                        class="px-3 py-2 rounded-lg text-sm border transition-all"
                        :class="quizConfig.difficulty === diff ? 'bg-primary-600 text-white border-primary-600 shadow-md shadow-primary-500/30' : 'bg-white text-slate-600 border-slate-200 hover:border-primary-300'"
                        @click="quizConfig.difficulty = diff"
                    >
                       {{ diff === DIFFICULTY_LEVELS.BEGINNER ? '入门' : (diff === DIFFICULTY_LEVELS.INTERMEDIATE ? '进阶' : '精通') }}
                    </button>
                </div>
             </div>

             <div class="space-y-3">
                 <div class="text-sm font-bold text-slate-600">出题风格</div>
                 <div class="grid grid-cols-2 gap-2">
                    <button v-for="style in [TEACHING_STYLES.ACADEMIC, TEACHING_STYLES.INDUSTRIAL, TEACHING_STYLES.SOCRATIC, TEACHING_STYLES.HUMOROUS]" :key="style"
                        class="px-3 py-2 rounded-lg text-sm border transition-all"
                        :class="quizConfig.style === style ? 'bg-amber-500 text-white border-amber-500 shadow-md shadow-amber-500/30' : 'bg-white text-slate-600 border-slate-200 hover:border-amber-300'"
                        @click="quizConfig.style = style"
                    >
                       {{ style === TEACHING_STYLES.ACADEMIC ? '学术严谨' : style === TEACHING_STYLES.INDUSTRIAL ? '工业实践' : style === TEACHING_STYLES.SOCRATIC ? '苏格拉底' : '幽默风趣' }}
                    </button>
                </div>
             </div>
        </div>
        <template #footer>
            <div class="flex justify-end gap-2">
                <el-button @click="quizConfig.visible = false">取消</el-button>
                <el-button type="primary" @click="confirmQuiz">开始测验</el-button>
            </div>
        </template>
    </el-dialog>

    <!-- Quiz Dialog -->
    <el-dialog
      v-model="quizVisible"
      title="智能测验"
      width="600px"
      class="glass-dialog-clean"
      align-center
      append-to-body
    >
      <div v-if="generatingQuiz" class="flex flex-col items-center justify-center py-12">
        <div class="w-16 h-16 relative mb-4">
             <div class="absolute inset-0 border-4 border-slate-100 rounded-full"></div>
             <div class="absolute inset-0 border-4 border-primary-500 rounded-full border-t-transparent animate-spin"></div>
        </div>
        <p class="text-slate-600 font-medium">AI 正在出题中...</p>
      </div>
      <div v-else class="py-2">
        <div v-if="quizQuestions && quizQuestions.length > 0">
            <div v-for="(q, idx) in quizQuestions" :key="idx" class="mb-8 last:mb-0">
            <div class="flex gap-2 font-bold text-slate-800 mb-3 text-lg">
                <span class="shrink-0">{{ idx + 1 }}.</span>
                <MarkdownRenderer :content="q.question" />
            </div>
            <div class="space-y-2">
                <div 
                v-for="(opt, oIdx) in q.options" 
                :key="oIdx"
                class="p-3 rounded-xl border border-slate-200 cursor-pointer transition-all duration-200 hover:border-primary-300 hover:bg-primary-50/30 flex items-center gap-3"
                :class="{ 
                    '!bg-emerald-50 !border-emerald-500': quizSubmitted && opt === q.answer,
                    '!bg-red-50 !border-red-500': quizSubmitted && userAnswers[idx] === opt && opt !== q.answer,
                    'bg-primary-50 border-primary-500': userAnswers[idx] === opt && !quizSubmitted
                }"
                @click="!quizSubmitted && (userAnswers[idx] = opt)"
                >
                <div class="w-5 h-5 rounded-full border flex items-center justify-center text-xs transition-colors"
                    :class="{
                        'border-emerald-500 bg-emerald-500 text-white': quizSubmitted && opt === q.answer,
                        'border-red-500 bg-red-500 text-white': quizSubmitted && userAnswers[idx] === opt && opt !== q.answer,
                        'border-primary-500 bg-primary-500 text-white': userAnswers[idx] === opt && !quizSubmitted,
                        'border-slate-300 text-slate-400': userAnswers[idx] !== opt && !(quizSubmitted && opt === q.answer)
                    }">
                    <span v-if="quizSubmitted && opt === q.answer"><el-icon><Check /></el-icon></span>
                    <span v-else-if="quizSubmitted && userAnswers[idx] === opt && opt !== q.answer"><el-icon><Close /></el-icon></span>
                    <span v-else>{{ String.fromCharCode(65 + Number(oIdx)) }}</span>
                </div>
                <div class="text-slate-700 font-medium">
                    <MarkdownRenderer :content="opt" />
                </div>
                </div>
            </div>
            <div v-if="quizSubmitted" class="mt-3 text-sm bg-slate-50 p-3 rounded-lg text-slate-600">
                <span class="font-bold text-slate-800 block mb-1">解析：</span> 
                <MarkdownRenderer :content="q.explanation || '暂无解析'" />
            </div>
            </div>
        </div>
        <div v-else class="text-center text-slate-500 py-10">
            暂无测验题目
        </div>
      </div>
      <template #footer>
        <div class="flex items-center gap-3" v-if="!generatingQuiz">
          <div v-if="quizSubmitted" class="text-sm text-slate-500 mr-auto">得分 {{ quizScore }} 分</div>
          <el-button @click="quizVisible = false" class="!border-none !bg-slate-100 hover:!bg-slate-200 text-slate-600">关闭</el-button>
          <el-button v-if="!quizSubmitted" type="primary" @click="submitQuiz" class="bg-gradient-to-r from-primary-500 to-primary-600 border-none shadow-lg shadow-primary-500/30 hover:shadow-primary-500/40">
            提交答案
          </el-button>
          <el-button v-else type="primary" @click="quizVisible = false">
            完成
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Note Detail Dialog -->
    <el-dialog
        v-model="noteDetailVisible"
        title="笔记详情"
        width="700px"
        class="note-detail-dialog"
        align-center
        append-to-body
    >
        <div v-if="selectedNote" class="flex flex-col gap-4">
            <!-- Quote Context -->
                <div v-if="selectedNote.quote" class="p-4 bg-slate-50 rounded-xl border-l-4 italic text-slate-600 text-sm" :class="noteQuoteBorderClass(selectedNote)">
                    "{{ selectedNote.quote }}"
                </div>

                <!-- Summary Section -->
                <div v-if="selectedNote.summary" class="p-4 bg-purple-50/50 rounded-xl border border-purple-100">
                    <div class="text-[11px] font-bold text-purple-600 mb-2 uppercase tracking-wide flex items-center gap-1">
                        <el-icon><CollectionTag /></el-icon> 核心概括
                    </div>
                    <div class="text-sm text-slate-700 leading-relaxed note-content-markdown">
                        <MarkdownRenderer :content="selectedNote.summary" :search-words="searchTokens" />
                    </div>
                </div>

                <!-- Tags & Category Section -->
                <div class="flex flex-wrap items-center gap-2">
                    <!-- Category Badge -->
                    <el-select
                        v-if="isDialogEditing"
                        v-model="editingCategory"
                        placeholder="选择分类"
                        size="small"
                        class="w-32"
                        @change="updateNoteCategory"
                    >
                        <el-option
                            v-for="cat in availableCategories"
                            :key="cat"
                            :label="cat"
                            :value="cat"
                        />
                    </el-select>
                    <el-tag
                        v-else-if="selectedNote.category"
                        :type="getCategoryType(selectedNote.category)"
                        size="small"
                        effect="light"
                    >
                        <el-icon class="mr-1"><Folder /></el-icon>
                        {{ selectedNote.category }}
                    </el-tag>
                    
                    <!-- Priority Badge -->
                    <el-select
                        v-if="isDialogEditing"
                        v-model="editingPriority"
                        placeholder="优先级"
                        size="small"
                        class="w-28"
                        @change="updateNotePriority"
                    >
                        <el-option label="🔴 高" value="high" />
                        <el-option label="🟡 中" value="medium" />
                        <el-option label="🟢 低" value="low" />
                    </el-select>
                    <el-tag
                        v-else-if="selectedNote.priority"
                        :type="selectedNote.priority === 'high' ? 'danger' : selectedNote.priority === 'medium' ? 'warning' : 'info'"
                        size="small"
                        effect="light"
                    >
                        {{ getPriorityLabel(selectedNote.priority) }}
                    </el-tag>

                    <!-- Tags -->
                    <el-select
                        v-if="isDialogEditing"
                        v-model="editingTags"
                        multiple
                        filterable
                        allow-create
                        default-first-option
                        placeholder="添加标签"
                        size="small"
                        class="flex-1 min-w-[200px]"
                        @change="updateNoteTags"
                    >
                        <el-option
                            v-for="tag in availableTags"
                            :key="tag"
                            :label="tag"
                            :value="tag"
                        />
                    </el-select>
                    <template v-else>
                        <el-tag
                            v-for="tag in selectedNote.tags"
                            :key="tag"
                            size="small"
                            effect="plain"
                            class="cursor-pointer hover:bg-primary-50"
                            @click="filterByTag(tag)"
                        >
                            <el-icon class="mr-1"><PriceTag /></el-icon>
                            {{ tag }}
                        </el-tag>
                    </template>
                </div>

                <!-- Main Content / Edit Area -->
            <div v-if="isDialogEditing" class="flex flex-col gap-2">
                <!-- Editor Toolbar -->
                <div class="flex items-center gap-2 p-2 bg-slate-50 rounded-lg border border-slate-200">
                    <span class="text-xs text-slate-400">支持 Markdown 语法</span>
                </div>
                <el-input
                    v-model="editingContent"
                    type="textarea"
                    :rows="10"
                    placeholder="请输入笔记内容..."
                    class="glass-input-clean text-base"
                />
            </div>
            <div v-else class="bg-white p-6 rounded-xl border border-slate-100 shadow-sm note-content-markdown min-h-[150px]">
                <MarkdownRenderer :content="getCleanedNoteContent(selectedNote)" :search-words="searchTokens" />
            </div>

            <!-- Metadata (View Mode Only) -->
            <div v-if="!isDialogEditing" class="flex items-center justify-between pt-4 border-t border-slate-100 text-xs text-slate-400">
                <div class="flex items-center gap-2">
                    <el-icon><Timer /></el-icon>
                    创建于 {{ dayjs(selectedNote.createdAt).format('YYYY-MM-DD HH:mm') }}
                </div>
                <div class="flex items-center gap-2">
                    <el-button v-if="selectedNote.nodeId" size="small" text @click="jumpToNoteSource(selectedNote); noteDetailVisible = false">
                        <el-icon class="mr-1"><Position /></el-icon>跳转原文
                    </el-button>
                    <div v-if="selectedNote.sourceType === 'ai'" class="flex items-center gap-1 text-primary-600 font-bold bg-primary-50 px-2 py-1 rounded">
                        <el-icon><MagicStick /></el-icon> AI 助手生成
                    </div>
                </div>
            </div>
        </div>
        <template #footer>
            <div class="flex justify-end gap-2">
                <template v-if="isDialogEditing">
                    <el-button @click="cancelDialogEditing">取消</el-button>
                    <el-button type="primary" @click="saveDialogEditing">保存</el-button>
                </template>
                <template v-else>
                    <el-button @click="startEditing">编辑</el-button>
                    <el-button type="primary" @click="noteDetailVisible = false">关闭</el-button>
                </template>
            </div>
        </template>
    </el-dialog>

    <!-- Quiz Suggestion Toast - Moved to center bottom as requested -->
    <transition name="slide-up">
        <div v-if="showQuizSuggestion && suggestedQuizNode" class="fixed bottom-20 left-1/2 -translate-x-1/2 z-[100] w-72 lg:w-80 bg-white p-4 rounded-xl shadow-xl border border-slate-200 flex flex-col gap-3">
            <div class="flex items-start justify-between">
                <div class="flex items-center gap-2 text-primary-600">
                    <el-icon class="text-xl"><Trophy /></el-icon>
                    <span class="font-bold">恭喜完成阅读！</span>
                </div>
                <button @click="showQuizSuggestion = false" class="text-slate-400 hover:text-slate-600">
                    <el-icon><Close /></el-icon>
                </button>
            </div>
            <p class="text-sm text-slate-600">
                你刚刚读完了 <strong>{{ suggestedQuizNode.node_name }}</strong>，要来个小测验巩固一下知识点吗？
            </p>
            <div class="flex gap-2 mt-1">
                <button @click="showQuizSuggestion = false" class="flex-1 py-1.5 text-xs font-bold text-slate-500 hover:bg-slate-100 rounded-lg transition-colors">
                    稍后再说
                </button>
                <button @click="handleStartQuiz(suggestedQuizNode); showQuizSuggestion = false" class="flex-1 py-1.5 text-xs font-bold text-white bg-gradient-to-r from-primary-500 to-primary-600 hover:shadow-lg hover:shadow-primary-500/30 rounded-lg transition-all transform hover:-translate-y-0.5">
                    开始测验
                </button>
            </div>
        </div>
    </transition>

    <!-- Back to Top Button -->
    <Teleport to="body">
        <transition name="back-to-top">
            <button v-if="showBackToTop" 
                    class="back-to-top p-3 bg-white/90 backdrop-blur-md border border-slate-200 rounded-full shadow-lg text-slate-500 hover:text-primary-600 hover:border-primary-300 hover:shadow-xl hover:shadow-primary-100/50 transition-all active:scale-95"
                    @click="scrollToTop">
                <el-icon :size="20"><ArrowUp /></el-icon>
            </button>
        </transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch, nextTick, onUpdated, reactive } from 'vue'
import { useCourseStore } from '../stores/course'

import CourseNode from './CourseNode.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { useMermaid } from '../composables/useMermaid'
import { Download, MagicStick, Notebook, Check, Close, Edit, Delete, ChatLineSquare, Search, Timer, Connection, Trophy, ArrowUp, ChatDotRound, Position, ArrowRight, Loading, More, Document, Warning, CollectionTag, Folder, PriceTag, Setting } from '@element-plus/icons-vue'
import { DIFFICULTY_LEVELS, TEACHING_STYLES, type DifficultyLevel, type TeachingStyle } from '@/shared/prompt-config'

import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

// Lazy rendering for Mermaid diagrams
const { scanMermaidDiagrams } = useMermaid()

const isNotesCollapsed = ref(false)

onUpdated(() => {
    scanMermaidDiagrams()
})

onMounted(() => {
    scanMermaidDiagrams()
})

// Handle clicks inside content (Copy buttons, etc.)
const handleContentClick = async (e: MouseEvent) => {
    const target = e.target as HTMLElement

    // Handle Copy Button
    const btn = target.closest('.copy-btn') as HTMLElement
    if (btn) {
        const code = decodeURIComponent(btn.dataset.code || '')
        if (code) {
            try {
                await navigator.clipboard.writeText(code)
                const originalHTML = btn.innerHTML
                btn.innerHTML = '<span class="text-green-400 font-bold">OK</span>'
                btn.classList.add('bg-green-500/20')
                setTimeout(() => {
                    btn.innerHTML = originalHTML
                    btn.classList.remove('bg-green-500/20')
                }, 2000)
                ElMessage.success('代码已复制')
            } catch (err) {
                ElMessage.error('复制失败')
            }
        }
        return
    }
    
    // Handle Image Click (Lightbox)
    if (target.tagName === 'IMG' && target.closest('.content-render')) {
        lightboxImage.value = (target as HTMLImageElement).src
        lightboxVisible.value = true
    }
}

const courseStore = useCourseStore()
const selectionMenu = ref({ visible: false, x: 0, y: 0, arrowOffset: 0, placement: 'top', text: '', range: null as Range | null })
const noteSearchQuery = ref('')
const activeNoteFilter = ref('notes')

// Note filter states
const selectedTagFilter = ref('')
const selectedCategoryFilter = ref('')
const selectedPriorityFilter = ref<'low' | 'medium' | 'high' | ''>('')

// Export dialog state
const exportDialog = reactive({
    visible: false,
    title: '导出笔记',
    subtitle: '选择导出范围和格式',
    type: 'notes' as 'notes' | 'mistakes',
    scope: 'all' as 'all' | 'filtered' | 'current',
    format: 'markdown' as 'markdown' | 'json',
    loading: false
})

// Export scope options
const exportScopes: { value: 'all' | 'filtered' | 'current', label: string, icon: string }[] = [
    { value: 'all', label: '全部', icon: 'Collection' },
    { value: 'filtered', label: '已筛选', icon: 'Filter' },
    { value: 'current', label: '当前视图', icon: 'View' }
]

// Export format options
const exportFormats: { value: 'markdown' | 'json', label: string, desc: string, icon: string }[] = [
    { value: 'markdown', label: 'Markdown', desc: '适合阅读和编辑', icon: 'Document' },
    { value: 'json', label: 'JSON', desc: '结构化数据格式', icon: 'DataLine' }
]

// Computed export count
const getExportCount = computed(() => {
    let notes: any[] = []
    if (exportDialog.type === 'mistakes') {
        notes = courseStore.notes.filter((n: any) => n.sourceType === 'wrong' || n.content.includes('#错题'))
    } else {
        notes = courseStore.notes
    }
    
    if (exportDialog.scope === 'filtered') {
        notes = notes.filter((note: any) => {
            if (selectedTagFilter.value && !note.tags?.includes(selectedTagFilter.value)) return false
            if (selectedCategoryFilter.value && note.category !== selectedCategoryFilter.value) return false
            if (selectedPriorityFilter.value && note.priority !== selectedPriorityFilter.value) return false
            return true
        })
    } else if (exportDialog.scope === 'current') {
        notes = notes.filter((note: any) => {
            if (activeNoteFilter.value === 'mistakes') {
                return note.sourceType === 'wrong' || note.content.includes('#错题')
            }
            return note.sourceType !== 'wrong' && !note.content.includes('#错题')
        })
    }
    
    return notes.length
})

// Computed export size estimate
const getExportSize = computed(() => {
    const count = getExportCount.value
    if (count === 0) return '0 KB'
    const avgSize = exportDialog.format === 'markdown' ? 2 : 5 // KB per note estimate
    const totalSize = count * avgSize
    if (totalSize < 1024) return `${totalSize} KB`
    return `${(totalSize / 1024).toFixed(1)} MB`
})

// Open export dialog
const openExportDialog = (type: 'notes' | 'mistakes' = 'notes') => {
    exportDialog.type = type
    exportDialog.title = type === 'mistakes' ? '导出错题' : '导出笔记'
    exportDialog.subtitle = type === 'mistakes' ? '导出你的错题记录' : '导出你的学习笔记'
    exportDialog.scope = 'all'
    exportDialog.format = 'markdown'
    exportDialog.visible = true
}

// Close export dialog
const closeExportDialog = () => {
    exportDialog.visible = false
    exportDialog.loading = false
}

// Execute export
const executeExport = async () => {
    exportDialog.loading = true
    
    try {
        let notes: any[] = []
        
        if (exportDialog.type === 'mistakes') {
            notes = courseStore.notes.filter((n: any) => n.sourceType === 'wrong' || n.content.includes('#错题'))
        } else {
            notes = courseStore.notes
        }
        
        // Apply scope filter
        if (exportDialog.scope === 'filtered') {
            notes = notes.filter((note: any) => {
                if (selectedTagFilter.value && !note.tags?.includes(selectedTagFilter.value)) return false
                if (selectedCategoryFilter.value && note.category !== selectedCategoryFilter.value) return false
                if (selectedPriorityFilter.value && note.priority !== selectedPriorityFilter.value) return false
                return true
            })
        } else if (exportDialog.scope === 'current') {
            notes = notes.filter((note: any) => {
                if (activeNoteFilter.value === 'mistakes') {
                    return note.sourceType === 'wrong' || note.content.includes('#错题')
                }
                return note.sourceType !== 'wrong' && !note.content.includes('#错题')
            })
        }
        
        if (notes.length === 0) {
            ElMessage.warning('没有可导出的内容')
            exportDialog.loading = false
            return
        }
        
        // Simulate export delay for better UX
        await new Promise(resolve => setTimeout(resolve, 500))
        
        if (exportDialog.format === 'markdown') {
            await exportToMarkdown(notes, exportDialog.type)
            ElMessage.success(`成功导出 ${notes.length} 条笔记为 Markdown`)
        } else {
            await exportToJSON(notes, exportDialog.type)
            ElMessage.success(`成功导出 ${notes.length} 条笔记为 JSON`)
        }
        
        closeExportDialog()
    } catch (error) {
        console.error('Export failed:', error)
        ElMessage.error('导出失败，请重试')
    } finally {
        exportDialog.loading = false
    }
}

// Export to Markdown
const exportToMarkdown = async (notes: any[], type: 'notes' | 'mistakes') => {
    const title = type === 'mistakes' ? '错题本' : '学习笔记'
    let markdown = `# ${title}\n\n`
    markdown += `导出时间: ${dayjs().format('YYYY-MM-DD HH:mm')}\n\n`
    markdown += `共 ${notes.length} 条记录\n\n---\n\n`
    
    notes.forEach((note: any, index: number) => {
        if (type === 'mistakes') {
            markdown += `## 错题 ${index + 1}\n\n`
        } else {
            const noteType = note.sourceType === 'ai' ? 'AI问答' : 
                           note.sourceType === 'wrong' ? '错题' : '笔记'
            markdown += `## ${noteType} ${index + 1}\n\n`
        }
        
        if (note.category) {
            markdown += `**分类:** ${note.category}\n\n`
        }
        if (note.tags?.length) {
            markdown += `**标签:** ${note.tags.join(', ')}\n\n`
        }
        if (note.priority) {
            const priorityText: Record<string, string> = { high: '高', medium: '中', low: '低' }
            markdown += `**优先级:** ${priorityText[note.priority as string] || note.priority}\n\n`
        }
        
        markdown += `**来源章节:** ${getNodeName(note.nodeId)}\n\n`
        markdown += `**内容:**\n${note.content}\n\n`
        
        if (note.quote) {
            markdown += `**原文引用:**\n> ${note.quote}\n\n`
        }
        if (note.aiResponse) {
            markdown += `**AI回复:**\n${note.aiResponse}\n\n`
        }
        
        markdown += `**记录时间:** ${dayjs(note.createdAt).format('YYYY-MM-DD HH:mm')}\n\n`
        markdown += '---\n\n'
    })
    
    const blob = new Blob([markdown], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const fileName = type === 'mistakes' ? '错题本' : '学习笔记'
    a.download = `${fileName}_${dayjs().format('YYYYMMDD')}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
}

// Export to JSON
const exportToJSON = async (notes: any[], type: 'notes' | 'mistakes') => {
    const data = {
        exportType: type,
        exportTime: dayjs().format('YYYY-MM-DD HH:mm'),
        totalCount: notes.length,
        courseName: courseStore.currentCourse?.course_name || '未知课程',
        notes: notes.map((note: any) => ({
            id: note.id,
            type: note.sourceType || 'note',
            nodeId: note.nodeId,
            nodeName: getNodeName(note.nodeId),
            content: note.content,
            quote: note.quote,
            aiResponse: note.aiResponse,
            category: note.category,
            tags: note.tags || [],
            priority: note.priority,
            createdAt: note.createdAt,
            formattedDate: dayjs(note.createdAt).format('YYYY-MM-DD HH:mm')
        }))
    }
    
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const fileName = type === 'mistakes' ? '错题本' : '学习笔记'
    a.download = `${fileName}_${dayjs().format('YYYYMMDD')}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
}

// Settings dialog state
const settingsDialog = reactive({
    visible: false,
    fontSize: 16,
    fontFamily: 'system-ui, -apple-system, sans-serif',
    lineHeight: 1.6
})

// Font options
const fontOptions = [
    { value: 'system-ui, -apple-system, sans-serif', label: '系统默认' },
    { value: '"Noto Serif SC", "Source Han Serif SC", serif', label: '思源宋体' },
    { value: '"Noto Sans SC", "Source Han Sans SC", sans-serif', label: '思源黑体' },
    { value: '"JetBrains Mono", "Fira Code", monospace', label: '等宽字体' }
]

// Open settings dialog
const openSettingsDialog = () => {
    settingsDialog.fontSize = courseStore.uiSettings.fontSize
    settingsDialog.fontFamily = courseStore.uiSettings.fontFamily
    settingsDialog.lineHeight = courseStore.uiSettings.lineHeight
    settingsDialog.visible = true
}

// Close settings dialog
const closeSettingsDialog = () => {
    settingsDialog.visible = false
}

// Apply settings
const applySettings = () => {
    courseStore.setUiSettings({
        fontSize: settingsDialog.fontSize,
        fontFamily: settingsDialog.fontFamily,
        lineHeight: settingsDialog.lineHeight
    })
    ElMessage.success('设置已应用')
    closeSettingsDialog()
}

const scrollProgress = ref(0)
const lightboxVisible = ref(false)
const lightboxImage = ref('')
// Note tabs configuration
const noteTabs = computed(() => [
    { key: 'notes', label: '笔记', icon: Notebook, count: noteCounts.value.notes, color: 'text-primary-500' },
    { key: 'mistakes', label: '错题', icon: Warning, count: noteCounts.value.mistakes, color: 'text-red-500' }
])

const debounce = (fn: (...args: unknown[]) => void, delay: number) => {
    let timeout: ReturnType<typeof setTimeout> | null = null
    return (...args: unknown[]) => {
        if (timeout) clearTimeout(timeout)
        timeout = setTimeout(() => fn(...args), delay)
    }
}

const debouncedUpdatePositions = debounce(() => updateNotePositions(), 100)

// Watch for scroll requests from sidebar
watch(() => courseStore.scrollToNodeId, async (nodeId) => {
    if (!nodeId) return
    
    // Ensure node is rendered if it's outside the current view
    const index = flatNodes.value.findIndex(n => n.node_id === nodeId)
    if (index !== -1 && index >= renderedCount.value) {
        renderedCount.value = index + 5
        await nextTick()
    }
    
    const element = document.getElementById(`node-${nodeId}`)
    if (element) {
        isManualScrolling.value = true
        
        // Add a small offset for the sticky header
        const offset = 80
        const scrollContainer = document.getElementById('content-scroll-container')
        
        if (scrollContainer) {
            const containerRect = scrollContainer.getBoundingClientRect()
            const elementRect = element.getBoundingClientRect()
            const relativeTop = elementRect.top - containerRect.top + scrollContainer.scrollTop
            
            scrollContainer.scrollTo({
                top: relativeTop - offset,
                behavior: 'smooth'
            })
            
            // Reset flag after animation
            setTimeout(() => {
                isManualScrolling.value = false
            }, 1000)
        }
    }
})

// Watch for focus note requests (AI Teacher Mode)
watch(() => courseStore.focusNoteId, (noteId) => {
    if (noteId) {
        // Wait for DOM update (highlights to be applied)
        nextTick(() => {
            scrollToNote(noteId)
        })
    }
})

// Quiz State
const quizVisible = ref(false)
const generatingQuiz = ref(false)
const quizQuestions = ref<any[]>([])
const userAnswers = ref<string[]>([])
const quizSubmitted = ref(false)
const quizScore = computed(() => {
              if (!quizSubmitted.value || !quizQuestions.value || quizQuestions.value.length === 0) return 0
              let correct = 0
              quizQuestions.value.forEach((q, idx) => {
                  if (userAnswers.value[idx] && userAnswers.value[idx] === q.answer) {
                      correct += 1
                  }
              })
              return Math.round((correct / quizQuestions.value.length) * 100)
          })
const isManualScrolling = ref(false)
const activeNoteId = ref<string | null>(null)
const hoveredNoteId = ref<string | null>(null)
const hoverPreview = reactive({
    visible: false,
    x: 0,
    y: 0,
    note: null as any
})
const fontSize = computed(() => courseStore.uiSettings.fontSize)
const fontFamily = computed(() => courseStore.uiSettings.fontFamily)
const lineHeight = computed(() => courseStore.uiSettings.lineHeight)
const editingContent = ref('')
let observer: IntersectionObserver | null = null

const noteDetailVisible = ref(false)
const isDialogEditing = ref(false)
const selectedNote = ref<any>(null)

// Note tags, category, and priority editing
const editingTags = ref<string[]>([])
const editingCategory = ref('')
const editingPriority = ref<'low' | 'medium' | 'high'>('medium')

// Available tags and categories
const availableTags = computed(() => courseStore.getAllTags())
const availableCategories = computed(() => courseStore.getAllCategories())

watch(noteDetailVisible, (val) => {
    if (!val) {
        isDialogEditing.value = false
        editingContent.value = ''
        editingTags.value = []
        editingCategory.value = ''
        editingPriority.value = 'medium'
    }
})

// Quiz Suggestion State
const readChapters = ref<Set<string>>(new Set())
const showQuizSuggestion = ref(false)
const suggestedQuizNode = ref<any>(null)

// Check if content is long enough to collapse
const isLongContent = (content: string) => {
    // Heuristic: length > 80 or has more than 2 newlines
    return content.length > 300 || content.split('\n').length > 8
}

// Notes Logic
const flatNodes = computed(() => {
    if (!courseStore.treeData || courseStore.treeData.length === 0) return []
    const nodes: any[] = []
    const traverse = (data: any[]) => {
        for (const node of data) {
            nodes.push(node)
            if (node.children && node.children.length > 0) {
                traverse(node.children)
            }
        }
    }
    traverse(courseStore.treeData)
    return nodes
})

// --- Performance Optimization: Lazy Rendering ---
const renderedCount = ref(20)
const sentinelRef = ref<HTMLElement | null>(null)
let sentinelObserver: IntersectionObserver | null = null

const visibleNodes = computed(() => {
    if (!flatNodes.value) return []
    return flatNodes.value.slice(0, renderedCount.value)
})

const initSentinelObserver = () => {
    if (sentinelObserver) sentinelObserver.disconnect()
    
    sentinelObserver = new IntersectionObserver((entries: IntersectionObserverEntry[]) => {
        if (!entries || entries.length === 0) return
        const entry = entries[0]
        if (entry && entry.isIntersecting) {
            const allNodes = flatNodes.value || []
            if (renderedCount.value < allNodes.length) {
                renderedCount.value = Math.min(renderedCount.value + 10, allNodes.length)
            }
        }
    }, { rootMargin: '600px' }) // Load well in advance
    
    if (sentinelRef.value) {
        sentinelObserver.observe(sentinelRef.value)
    }
}

watch(sentinelRef, (el) => {
    if (el) initSentinelObserver()
})

watch(() => flatNodes.value.length, (newLen, oldLen) => {
    // If we were showing everything, keep showing everything (for new nodes generated at the end)
    if (renderedCount.value >= oldLen) {
        renderedCount.value = newLen
    }
})

// Reset when course changes significantly
watch(() => courseStore.currentCourseId, () => {
    renderedCount.value = 20
})
// ------------------------------------------------

const nodeNameMap = computed(() => new Map(flatNodes.value.map(n => [n.node_id, n.node_name])))

// Export functions have been replaced by the new export dialog

const chapterEndNodes = computed(() => {
    const triggers = new Map<string, any>()
    let currentChapter = null

    for (let i = 0; i < flatNodes.value.length; i++) {
        const node = flatNodes.value[i]
        
        if (node.node_level === 2) {
            currentChapter = node
        } else if (node.node_level > 2 && currentChapter) {
            const nextNode = flatNodes.value[i+1]
            if (!nextNode || nextNode.node_level <= 2) {
                 triggers.set(node.node_id, currentChapter)
            }
        }
    }
    return triggers
})

let chapterObserver: IntersectionObserver | null = null

const setupChapterObserver = () => {
    if (chapterObserver) chapterObserver.disconnect()
    
    chapterObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const nodeId = entry.target.id.replace('node-', '')
                const chapter = chapterEndNodes.value.get(nodeId)
                
                if (chapter && !readChapters.value.has(chapter.node_id)) {
                    suggestedQuizNode.value = chapter
                    showQuizSuggestion.value = true
                    readChapters.value.add(chapter.node_id)
                    courseStore.markNodeAsRead(chapter.node_id) // Persist read status
                    
                    // Auto-hide after 10 seconds if not interacted
                    setTimeout(() => {
                         if (showQuizSuggestion.value && suggestedQuizNode.value?.node_id === chapter.node_id) {
                             showQuizSuggestion.value = false
                         }
                    }, 10000)
                }
            }
        })
    }, { threshold: 0.1 })
    
    // Defer to ensure DOM is ready
    nextTick(() => {
        chapterEndNodes.value.forEach((_, nodeId) => {
            const el = document.getElementById(`node-${nodeId}`)
            if (el) chapterObserver?.observe(el)
        })
    })
}



const isSearching = ref(false)
const debouncedSearchQuery = ref('')
const searchTokens = computed(() => {
    const query = debouncedSearchQuery.value.toLowerCase().trim()
    if (!query) return []
    return query.split(/\s+/).filter(Boolean)
})


// Debounce logic
let searchTimeout: ReturnType<typeof setTimeout> | null = null
const handleSearchInput = (val: string) => {
    const nextVal = val || ''
    if (!nextVal.trim()) {
        debouncedSearchQuery.value = ''
        isSearching.value = false
        if (searchTimeout) clearTimeout(searchTimeout)
        return
    }
    isSearching.value = true
    if (searchTimeout) clearTimeout(searchTimeout)
    searchTimeout = setTimeout(() => {
        debouncedSearchQuery.value = nextVal
        isSearching.value = false
    }, 300)
}

watch(noteSearchQuery, (val) => {
    handleSearchInput(val)
})

watch(quizVisible, (visible) => {
    if (visible) return
    quizQuestions.value = []
    userAnswers.value = []
    quizSubmitted.value = false
    generatingQuiz.value = false
})





const isMistakeNote = (note: any) => {
    if (note.sourceType === 'wrong') return true
    return note.content.includes('**错题记录**') || note.content.includes('#错题')
}

const noteColorPalette = ['amber', 'emerald', 'sky', 'violet', 'orange', 'rose']
const defaultNoteStyle = { dot: 'bg-amber-400', highlight: 'bg-amber-200/50 border-b-2 border-amber-400 hover:bg-amber-300/50', border: 'border-amber-200/80', badge: 'text-amber-600 bg-amber-50 border-amber-100', quote: 'border-amber-400' }

const noteColorMap: Record<string, { dot: string; highlight: string; border: string; badge: string; quote: string }> = {
    amber: defaultNoteStyle,
    emerald: { dot: 'bg-emerald-400', highlight: 'bg-emerald-200/50 border-b-2 border-emerald-400 hover:bg-emerald-300/50', border: 'border-emerald-200/80', badge: 'text-emerald-600 bg-emerald-50 border-emerald-100', quote: 'border-emerald-400' },
    sky: { dot: 'bg-sky-400', highlight: 'bg-sky-200/50 border-b-2 border-sky-400 hover:bg-sky-300/50', border: 'border-sky-200/80', badge: 'text-sky-600 bg-sky-50 border-sky-100', quote: 'border-sky-400' },
    violet: { dot: 'bg-violet-400', highlight: 'bg-violet-200/50 border-b-2 border-violet-400 hover:bg-violet-300/50', border: 'border-violet-200/80', badge: 'text-violet-600 bg-violet-50 border-violet-100', quote: 'border-violet-400' },
    orange: { dot: 'bg-orange-400', highlight: 'bg-orange-200/50 border-b-2 border-orange-400 hover:bg-orange-300/50', border: 'border-orange-200/80', badge: 'text-orange-600 bg-orange-50 border-orange-100', quote: 'border-orange-400' },
    rose: { dot: 'bg-rose-400', highlight: 'bg-rose-200/50 border-b-2 border-rose-400 hover:bg-rose-300/50', border: 'border-rose-200/80', badge: 'text-rose-600 bg-rose-50 border-rose-100', quote: 'border-rose-400' },
    purple: { dot: 'bg-purple-400', highlight: 'bg-purple-200/50 border-b-2 border-purple-400 hover:bg-purple-300/50', border: 'border-purple-200/80', badge: 'text-purple-600 bg-purple-50 border-purple-100', quote: 'border-purple-400' },
    red: { dot: 'bg-red-400', highlight: 'bg-red-200/50 border-b-2 border-red-400 hover:bg-red-300/50', border: 'border-red-200/80', badge: 'text-red-600 bg-red-50 border-red-100', quote: 'border-red-400' }
}

const formatHighlightMap: Record<string, string> = {
    yellow: 'bg-yellow-200/50 hover:bg-yellow-300/50',
    green: 'bg-green-200/50 hover:bg-green-300/50',
    blue: 'bg-blue-200/50 hover:bg-blue-300/50',
    pink: 'bg-pink-200/50 hover:bg-pink-300/50',
    orange: 'bg-orange-200/50 hover:bg-orange-300/50',
    purple: 'bg-purple-200/50 hover:bg-purple-300/50'
}

const hashSeed = (value: string) => {
    let hash = 0
    for (let i = 0; i < value.length; i++) {
        hash = (hash * 31 + value.charCodeAt(i)) % 100000
    }
    return hash
}

const pickPaletteColor = (seed: string) => {
    if (noteColorPalette.length === 0) return 'amber'
    const index = hashSeed(seed) % noteColorPalette.length
    return noteColorPalette[index] ?? 'amber'
}

const resolveNoteColor = (note: any) => {
    if (!note) return 'amber'
    if (note.sourceType === 'ai') return 'purple'
    if (isMistakeNote(note)) return 'red'
    if (note.color && note.color !== 'transparent' && note.color !== 'blue') return note.color
    const seed = note.highlightId || note.id || `${note.nodeId}-${note.createdAt}`
    return pickPaletteColor(seed)
}

const noteDotClass = (note: any) => (noteColorMap[resolveNoteColor(note)] || defaultNoteStyle).dot
const noteHighlightClass = (color: string) => (noteColorMap[color] || defaultNoteStyle).highlight
const noteCardBorderClass = (note: any) => (noteColorMap[resolveNoteColor(note)] || defaultNoteStyle).border
const noteBadgeClass = (note: any) => (noteColorMap[resolveNoteColor(note)] || defaultNoteStyle).badge
const noteQuoteBorderClass = (note: any) => (noteColorMap[resolveNoteColor(note)] || defaultNoteStyle).quote

const noteSearchText = (note: any) => {
    const nodeName = nodeNameMap.value.get(note.nodeId) || ''
    const parts = [note.content, note.quote, note.anno_summary, note.title, nodeName]
    return parts.filter(Boolean).join(' ').toLowerCase()
}

const noteMatchesSearch = (note: any, tokens: string[]) => {
    if (tokens.length === 0) return true
    const text = noteSearchText(note)
    return tokens.every(token => text.includes(token))
}

const noteCounts = computed(() => {
    const nodeIds = new Set(flatNodes.value.map(n => n.node_id))
    const scoped = courseStore.notes.filter(n => nodeIds.has(n.nodeId))
    const notes = scoped.filter(n => !isMistakeNote(n) && n.sourceType !== 'format').length
    const mistakes = scoped.filter(n => isMistakeNote(n) && n.sourceType !== 'format').length
    return { notes, mistakes }
})

const visibleNotes = computed(() => {
    const nodeIds = new Set(flatNodes.value.map(n => n.node_id))
    let notes = courseStore.notes.filter(n => nodeIds.has(n.nodeId))
    
    // Filter by Type
    if (activeNoteFilter.value === 'mistakes') {
        notes = notes.filter(n => isMistakeNote(n))
    } else {
        // 'notes' tab: Exclude mistakes
        notes = notes.filter(n => !isMistakeNote(n))
    }

    // Filter by Tag
    if (selectedTagFilter.value) {
        notes = notes.filter(n => n.tags?.includes(selectedTagFilter.value))
    }

    // Filter by Category
    if (selectedCategoryFilter.value) {
        notes = notes.filter(n => n.category === selectedCategoryFilter.value)
    }

    // Filter by Priority
    if (selectedPriorityFilter.value) {
        notes = notes.filter(n => n.priority === selectedPriorityFilter.value)
    }

    if (searchTokens.value.length > 0) {
        notes = notes.filter(n => noteMatchesSearch(n, searchTokens.value))
    }
    
    // Sort by Chapter Order then Time
    const nodeOrder = new Map(flatNodes.value.map((n, i) => [n.node_id, i]))
    notes.sort((a, b) => {
        const orderA = nodeOrder.get(a.nodeId) ?? -1
        const orderB = nodeOrder.get(b.nodeId) ?? -1
        if (orderA !== orderB) return orderA - orderB
        return a.createdAt - b.createdAt
    })
    
    return notes
})

const quotedNotes = computed(() => visibleNotes.value.filter(n => n.quote && n.quote.trim().length > 0))
const displayedNotes = computed(() => {
    let notes = visibleNotes.value.filter(n => n.sourceType !== 'format')
    
    return notes
})
const displayedQuotedNotes = computed(() => quotedNotes.value.filter(n => n.sourceType !== 'format'))
const noteEmptyText = computed(() => {
    if (debouncedSearchQuery.value) return '无匹配结果'
    return activeNoteFilter.value === 'mistakes' ? '暂无错题记录' : '暂无笔记'
})

watch(() => [visibleNotes.value.length, flatNodes.value], () => {
    nextTick(() => {
        reapplyHighlights()
        debouncedUpdatePositions()
        setupChapterObserver()
    })
}, { deep: true })

watch(() => courseStore.uiSettings.fontSize, () => {
    nextTick(() => {
        debouncedUpdatePositions()
    })
})

const reapplyHighlights = () => {
    // 1. Cleanup orphans
    // Identify active highlight IDs from quotedNotes
    const activeIds = new Set(quotedNotes.value.map(n => n.highlightId))
    
    document.querySelectorAll('.highlight-marker').forEach(el => {
        // ID format: highlightId or highlightId-part-*
        const id = el.id ? el.id.split('-part-')[0] : ''
        
        if (!id || !activeIds.has(id)) {
             // Unwrap orphan highlight
             const parent = el.parentNode
             while (el.firstChild) parent?.insertBefore(el.firstChild, el)
             parent?.removeChild(el)
        }
    })

    // 2. Group notes by nodeId to minimize DOM traversal
    const notesByNode = new Map<string, any[]>()
    quotedNotes.value.forEach(note => {
        if (document.getElementById(note.highlightId)) return // Skip already highlighted
        
        if (!notesByNode.has(note.nodeId)) {
            notesByNode.set(note.nodeId, [])
        }
        notesByNode.get(note.nodeId)?.push(note)
    })

    // 3. Process each node (chapter) once
    notesByNode.forEach((notes, nodeId) => {
        const nodeEl = document.getElementById('node-' + nodeId)
        if (!nodeEl) return
        
        // Advanced Text Search & Highlight Strategy (Robust "Strip Whitespace" Match)
        // 1. Get all text nodes and build a map ONCE per chapter
        const textNodes: { node: Node, text: string, length: number }[] = []
        let fullTextStripped = ''
        const mapIndices: { index: number, node: Node, offset: number }[] = []
        
        const walker = document.createTreeWalker(nodeEl, NodeFilter.SHOW_TEXT)
        let currentNode
        while (currentNode = walker.nextNode()) {
            const text = currentNode.textContent || ''
            if (!text) continue 
            
            // Build map: for every character in stripped text, record where it came from
            for (let i = 0; i < text.length; i++) {
                const char = text[i]
                if (!char || /\s/.test(char)) {
                    continue
                }
                    mapIndices.push({
                        index: fullTextStripped.length,
                        node: currentNode,
                        offset: i
                    })
                    fullTextStripped += char
            }
            
            textNodes.push({
                node: currentNode,
                text: text,
                length: text.length
            })
        }
        
        // 2. Apply all notes for this chapter
        notes.forEach(note => {
            // Normalize quote (Strip all whitespace)
            const normalize = (str: string) => str.replace(/\s+/g, '')
            const quoteStripped = normalize(note.quote)
            
            if (!quoteStripped) return
    
            // Find matches
            const matchIndex = fullTextStripped.indexOf(quoteStripped)
            
            if (matchIndex !== -1) {
                 const startIndex = matchIndex
                 const endIndex = matchIndex + quoteStripped.length - 1 // Inclusive for map lookup
                 
                if (startIndex < mapIndices.length && endIndex < mapIndices.length) {
                    const startMap = mapIndices[startIndex]
                    const endMap = mapIndices[endIndex]
                    if (!startMap || !endMap) return
                    
                    const startNode = startMap.node
                    const startOffset = startMap.offset
                    const endNode = endMap.node
                    const endOffset = endMap.offset + 1 // Exclusive end offset
                     
                     try {
                         // Create Range
                         const startNodeIdx = textNodes.findIndex(t => t.node === startNode)
                         const endNodeIdx = textNodes.findIndex(t => t.node === endNode)
                        if (startNodeIdx === -1 || endNodeIdx === -1) return
                         
                         if (startNode === endNode) {
                             const range = document.createRange()
                             range.setStart(startNode, startOffset)
                             range.setEnd(endNode, endOffset)
                             wrapRange(range, note.highlightId, note.id)
                         } else {
                             // Start Node Part
                             const range1 = document.createRange()
                             range1.setStart(startNode, startOffset)
                            const startNodeText = textNodes[startNodeIdx]
                            if (!startNodeText) return
                            range1.setEnd(startNode, startNodeText.text.length)
                             wrapRange(range1, note.highlightId + '-part-start', note.id)
                             
                             // Middle Nodes
                             for (let i = startNodeIdx + 1; i < endNodeIdx; i++) {
                                const nodeEntry = textNodes[i]
                                if (!nodeEntry) continue
                                const rangeM = document.createRange()
                                rangeM.selectNodeContents(nodeEntry.node)
                                 // Only wrap if it contains non-whitespace
                                if (nodeEntry.text.trim().length > 0) {
                                     wrapRange(rangeM, note.highlightId + '-part-' + i, note.id)
                                 }
                             }
                             
                             // End Node Part
                             const range2 = document.createRange()
                             range2.setStart(endNode, 0)
                             range2.setEnd(endNode, endOffset)
                             wrapRange(range2, note.highlightId, note.id)
                             
                             // Ensure main ID is on the first part for positioning
                             const firstWrapper = document.getElementById(note.highlightId + '-part-start')
                             if (firstWrapper) firstWrapper.id = note.highlightId
                         }
                     } catch (e) {
                         console.warn('Highlight range creation failed', e)
                     }
                 }
            }
        })
    })
}



const applyFormat = (style: string, value?: string) => {
    if (!selectionMenu.value.range || !selectionMenu.value.text) return
    
    const highlightId = 'highlight-' + Math.random().toString(36).substr(2, 9)
    
    // Determine color based on style
    let color = 'transparent'
    if (style === 'highlight') color = value || 'yellow'
    
    // Determine Note Style
    let noteStyle = style
    if (style === 'underline') noteStyle = value || 'solid'
    
    // Find Node ID
    let nodeId = ''
    let curr: Node | null = selectionMenu.value.range.startContainer
    while(curr && !nodeId) {
        if (curr.nodeType === 1 && (curr as Element).id.startsWith('node-')) {
            nodeId = (curr as Element).id.replace('node-', '')
        }
        curr = curr.parentNode
    }
    
    if (nodeId) {
        courseStore.createNote({
            id: 'note-' + Math.random().toString(36).substr(2, 9),
            nodeId,
            highlightId,
            quote: selectionMenu.value.text,
            content: '', // Empty content implies annotation only
            color,
            createdAt: Date.now(),
            sourceType: 'format',
            style: noteStyle as any
        })
        
        selectionMenu.value.visible = false
        window.getSelection()?.removeAllRanges()
    }
}

const setHovered = (noteId: string | null, event?: MouseEvent) => {
    hoveredNoteId.value = noteId
    // 1. Clean up old highlights
    document.querySelectorAll('.pulse-highlight').forEach(el => el.classList.remove('pulse-highlight'))
    
    // 2. Add new highlights and show preview
    if (noteId) {
        const note = courseStore.notes.find(n => n.id === noteId)
        if (note && note.highlightId) {
            const els = document.querySelectorAll(`[id^="${note.highlightId}"]`)
            els.forEach(el => el.classList.add('pulse-highlight'))
        }
        
        // Show hover preview
        if (note && event) {
            hoverPreview.visible = true
            hoverPreview.x = event.clientX
            hoverPreview.y = event.clientY - 10
            hoverPreview.note = note
        }
    } else {
        hoverPreview.visible = false
        hoverPreview.note = null
    }
}

const wrapRange = (range: Range, id: string, noteId: string) => {
    try {
        // Skip empty ranges
        if (range.toString().length === 0) return
        
        const note = courseStore.notes.find(n => n.id === noteId)
        const span = document.createElement('span')
        span.id = id
        
        // Dynamic Class based on Note Type/Style
        let className = 'highlight-marker transition-colors cursor-pointer '
        
        if (note?.sourceType === 'format') {
            if (note.style === 'bold') {
                className += 'font-bold '
            } else if (note.style === 'solid') { // Underline solid
                className += 'border-b-2 border-slate-800 '
            } else if (note.style === 'wavy') {
                className += 'underline decoration-wavy decoration-slate-800 '
            } else if (note.color && note.color !== 'transparent') {
                // Highlight
                const colorClass = formatHighlightMap[note.color] || 'bg-yellow-200/50 hover:bg-yellow-300/50'
                className += colorClass + ' '
            }
        } else if (note?.sourceType === 'ai') {
            // AI Teacher Style
            className += noteHighlightClass('purple') + ' '
        } else {
            // Default Note Style
            const resolvedColor = resolveNoteColor(note)
            className += noteHighlightClass(resolvedColor) + ' '
        }
        
        span.className = className
        
        span.onclick = (e) => {
            e.stopPropagation()
            // Only scroll to note if it has content (regular note)
            if (note && note.sourceType !== 'format') {
                scrollToNote(noteId)
            }
        }
        // Add hover effects with preview
        span.onmouseenter = (e) => setHovered(noteId, e as MouseEvent)
        span.onmouseleave = () => setHovered(null)
        
        range.surroundContents(span)
    } catch (e) {
        // Ignore
    }
}

const scrollToNote = (noteId: string) => {
    const note = courseStore.notes.find(n => n.id === noteId)
    if (!note) {
        console.warn('Note not found:', noteId)
        return
    }

    activeNoteId.value = note.id

    // First, try to scroll to the highlight in content area (preferred)
    if (note.highlightId) {
        const highlightEl = document.getElementById(note.highlightId)
        if (highlightEl) {
            highlightEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
            highlightEl.classList.add('pulse-highlight')
            setTimeout(() => highlightEl.classList.remove('pulse-highlight'), 1500)

            // Also scroll the note card in sidebar
            const noteEl = document.getElementById(note.id)
            if (noteEl) {
                noteEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
                noteEl.classList.add('flash-card', 'ring-4', 'ring-primary-200')
                setTimeout(() => {
                    noteEl.classList.remove('flash-card', 'ring-4', 'ring-primary-200')
                }, 1000)
            }
            return
        }
    }

    // If no highlight or highlight not found, scroll to the node
    if (note.nodeId) {
        // First ensure the node is rendered
        const nodeEl = document.getElementById(`node-${note.nodeId}`)
        if (nodeEl) {
            nodeEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
            nodeEl.classList.add('pulse-highlight')
            setTimeout(() => nodeEl.classList.remove('pulse-highlight'), 1500)
        } else {
            // Node not rendered, use store method to scroll
            courseStore.scrollToNode(note.nodeId)
        }
    }

    // Scroll note card in sidebar
    nextTick(() => {
        const noteEl = document.getElementById(note.id)
        if (noteEl) {
            noteEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
            noteEl.classList.add('flash-card', 'ring-4', 'ring-primary-200')
            setTimeout(() => {
                noteEl.classList.remove('flash-card', 'ring-4', 'ring-primary-200')
            }, 1000)
        }
    })
}

const updateNotePositions = () => {
    const notes = [...displayedQuotedNotes.value]
    const container = document.getElementById('notes-container')
    if (!container) return

    // --- Phase 1: Batch Read (DOM Measurements) ---
    // Read container metrics once
    const containerRect = container.getBoundingClientRect()
    const containerTop = containerRect.top
    
    // Detect Scale Factor (User might be using transform: scale())
    // If container is scaled, getBoundingClientRect() returns scaled values,
    // but style.top expects unscaled values (internal coordinate system).
    let scaleY = 1
    if (container.offsetHeight > 0) {
        scaleY = containerRect.height / container.offsetHeight
    }
    // Safety clamp for scale to avoid division by zero or extreme values
    if (scaleY < 0.1 || scaleY > 10) scaleY = 1
    
    // Create a map of element IDs to search to avoid repeated getElementById
    const elementIds = new Set<string>()
    notes.forEach(note => {
        if (note.highlightId) elementIds.add(note.highlightId)
        if (note.nodeId) elementIds.add('node-' + note.nodeId)
    })

    // Batch query elements
    // Note: getElementById is fast, but boundingClientRect causes reflow.
    // We want to minimize interleaved read/write.
    
    // Store measurements
    const measurements = new Map<string, number>() // id -> relativeTop
    const noteHeights = new Map<string, number>() // noteId -> height

    // Measure Targets (Highlights/Nodes)
    notes.forEach(note => {
        let el = document.getElementById(note.highlightId)
        let isFallback = false
        if (!el) {
            el = document.getElementById('node-' + note.nodeId)
            isFallback = true
        }

        if (el) {
            const rects = el.getClientRects()
            const rect = rects.length > 0 ? rects[0] : el.getBoundingClientRect()
            if (!rect) {
                measurements.set(note.id, -9999)
                return
            }
            // Calculate unscaled relative top
            // (Visual Difference) / Scale = Internal Difference
            const relativeTop = (rect.top - containerTop) / scaleY
            
            // Dynamic Offset for Alignment:
            // Goal: Align the card connector (dot center at ~21px from card top) with the text center.
            // rect.height is scaled height. We need unscaled height to calculate internal offset.
            const unscaledTextHeight = rect.height / scaleY
            const textCenter = unscaledTextHeight / 2
            
            // Connector position is fixed in CSS (21px from top of card)
            const connectorPos = 21 
            const offset = textCenter - connectorPos
            
            measurements.set(note.id, relativeTop + (isFallback ? 10 : offset))
        } else {
            measurements.set(note.id, -9999)
        }
    })

    // Measure Note Card Heights
    // We need to know how tall each note IS to stack them.
    // This is tricky because if we change 'top', it doesn't affect height, 
    // but if we caused a reflow above, it might. 
    // Since notes are absolute positioned, reading their height is safe-ish 
    // IF we haven't written to the DOM yet in this frame.
    notes.forEach(note => {
        const el = document.getElementById(note.id)
        if (el) {
            noteHeights.set(note.id, el.offsetHeight)
        } else {
            // Estimate if not rendered yet
            const estimated = 100 + (isLongContent(note.content) ? 120 : Math.min(note.content.length, 100))
            noteHeights.set(note.id, estimated)
        }
    })

    // --- Phase 2: Calculation (Pure JS) ---
    // 1. Assign Natural Positions
    const positionedNotes = notes.map(note => ({
        note,
        top: measurements.get(note.id) || 0,
        height: noteHeights.get(note.id) || 100
    }))

    // 2. Sort by Natural Top
    positionedNotes.sort((a, b) => a.top - b.top)

    // 3. Collision Resolution (Stacking)
    let lastBottom = 0 
    
    // Increased gap to prevent visual overlap of shadows/borders
    const GAP = 24 

    positionedNotes.forEach(item => {
        // If natural position is above the valid floor (lastBottom + GAP), push it down
        if (item.top < lastBottom + GAP) {
            item.top = lastBottom + GAP
        }
        
        // Update floor for next item
        // Use a slightly larger buffer for height to account for varying font rendering
        lastBottom = item.top + item.height + 4
    })

    // --- Phase 3: Batch Write (DOM Updates) ---
    // Apply calculated tops
    positionedNotes.forEach(item => {
        // We update the reactive object. Vue will batch the DOM updates.
        // If we were manipulating DOM directly, we would do style.top here.
        // Since we bind :style="{ top: note.top + 'px' }", updating the prop is enough.
        // However, we must ensure we are updating the SAME object reference in the array
        // that Vue is rendering.
        if (item.note.top !== item.top) {
            item.note.top = item.top
        }
    })
}

// Add ResizeObserver to monitor note height changes
let resizeObserver: ResizeObserver | null = null

const handleGlobalKeydown = (e: KeyboardEvent) => {
    // Only handle if Ctrl or Meta is pressed
    if (!(e.ctrlKey || e.metaKey)) return

    const key = e.key.toLowerCase()
    
    // Formatting Shortcuts
    if (['b', 'i', 'u'].includes(key)) {
        e.preventDefault()
        const selection = window.getSelection()
        if (selection && selection.toString().trim()) {
            // Show menu if not visible, or just apply directly
            if (!selectionMenu.value.visible) {
                 const range = selection.getRangeAt(0)
                 selectionMenu.value = {
                     visible: false,
                     x: 0, y: 0,
                     arrowOffset: 0,
                     placement: 'top',
                     text: selection.toString(),
                     range: range
                 }
            }
            
            if (key === 'b') applyFormat('bold')
            else if (key === 'i') applyFormat('underline', 'wavy') // Use wavy for italic/emphasis
            else if (key === 'u') applyFormat('underline', 'solid')
        }
    }
}

const getNodeName = (nodeId: string) => {
    const node = flatNodes.value.find(n => n.node_id === nodeId)
    return node ? node.node_name : '未知章节'
}

onMounted(() => {
    window.addEventListener('keydown', handleGlobalKeydown)
    
    // Initialize ResizeObserver
    resizeObserver = new ResizeObserver(() => {
        debouncedUpdatePositions()
    })
    
    // Observe the note column to catch general layout changes
    const noteColumn = document.getElementById('note-column')
    if (noteColumn) {
        resizeObserver.observe(noteColumn)
    }
    
    setupChapterObserver()
})

onUnmounted(() => {
    window.removeEventListener('keydown', handleGlobalKeydown)
    if (resizeObserver) resizeObserver.disconnect()
    if (chapterObserver) chapterObserver.disconnect()
})

// Watch for DOM updates to re-attach observer to new note elements
watch(() => visibleNotes.value, () => {
    nextTick(() => {
        reapplyHighlights()
        updateNotePositions()
        
        // Observe each note element
        visibleNotes.value.forEach(note => {
            const el = document.getElementById(note.id)
            if (el && resizeObserver) {
                resizeObserver.observe(el)
            }
        })
    })
}, { deep: true })





const getCleanedNoteContent = (note: any) => {
    let content = note.content || ''
    
    // Auto-remove quote from content if it matches the explicit quote context
    if (note.quote) {
        // Normalize strings for comparison (ignore whitespace, markdown markers)
        const normalize = (s: string) => s.replace(/[>\s#*]/g, '').trim().toLowerCase()
        const normQuote = normalize(note.quote)
        
        // Check if content starts with the quote
        // We look for the quote at the beginning, possibly wrapped in blockquotes
        
        // Heuristic: If the first few non-empty lines match the quote, remove them.
        
        // Simpler approach: Check if normalized content *starts with* normalized quote
        // But the content usually has extra stuff.
        // Let's rely on standard markdown blockquote structure: "> quote"
        
        // Remove blockquotes at the start that match the quote context
        // Pattern: (> text \n)+
        
        // Actually, many AI models output: 
        // > Quote
        // 
        // Answer...
        
        // Let's try to strip the first blockquote if it looks similar to note.quote
        const blockquoteMatch = content.match(/^((?:> ?.*\n?)+)/)
        if (blockquoteMatch) {
            const blockContent = blockquoteMatch[1].replace(/^> ?/gm, '')
            if (normalize(blockContent).includes(normQuote) || normQuote.includes(normalize(blockContent).substring(0, 50))) {
                 // Remove the blockquote
                 content = content.replace(blockquoteMatch[0], '').trim()
            }
        }
    }
    
    return content
}



// Selection Handling
const handleMouseUp = (_e: MouseEvent) => {
    // Check if clicked on image
    const target = _e.target as HTMLElement
    if (target.tagName === 'IMG' && target.closest('.prose')) {
        lightboxImage.value = (target as HTMLImageElement).src
        lightboxVisible.value = true
        return
    }

    // Prevent selection menu during scroll
    if (isManualScrolling.value) return
    
    const selection = window.getSelection()
    if (selection && selection.toString().trim().length > 0) {
        const range = selection.getRangeAt(0)
        const rect = range.getBoundingClientRect()
        
        // Detect Scale of the Teleport Target (Body)
        // Similar to note positioning, we must account for global scaling (e.g. transform on body/app)
        const body = document.body
        const bodyRect = body.getBoundingClientRect()
        let scaleX = 1
        let scaleY = 1
        if (body.offsetWidth > 0) scaleX = bodyRect.width / body.offsetWidth
        if (body.offsetHeight > 0) scaleY = bodyRect.height / body.offsetHeight
        
        // Safety clamp
        if (scaleX < 0.1 || scaleX > 10) scaleX = 1
        if (scaleY < 0.1 || scaleY > 10) scaleY = 1
        
        const isScaled = Math.abs(scaleX - 1) > 0.005 || Math.abs(scaleY - 1) > 0.005

        // Initial Calculation
        let effectiveViewportWidth = window.innerWidth
        let x = 0
        let y = 0
        
        if (isScaled) {
            // Context is scaled (likely transform on body), fixed positioning is relative to body
            effectiveViewportWidth = window.innerWidth / scaleX
            x = (rect.left - bodyRect.left) / scaleX + (rect.width / scaleX) / 2
            y = (rect.top - bodyRect.top) / scaleY - 12
        } else {
            // Standard Viewport (No scale)
            x = rect.left + rect.width / 2
            y = rect.top - 12
        }
        
        const originalX = x
        let placement = 'top'

        // Initial estimate (safe default to avoid large jumps)
        const ESTIMATED_WIDTH = 280
        if (x + (ESTIMATED_WIDTH / 2) > effectiveViewportWidth - 20) x = effectiveViewportWidth - (ESTIMATED_WIDTH / 2) - 20
        if (x - (ESTIMATED_WIDTH / 2) < 20) x = (ESTIMATED_WIDTH / 2) + 20

        selectionMenu.value = {
            visible: true,
            x: x, 
            y: y, 
            arrowOffset: originalX - x,
            placement: placement,
            text: selection.toString(),
            range: range
        }

        // Precise Adjustment after Render (Fix for P1: Scaling/Overflow Alignment)
        nextTick(() => {
            const menuEl = document.getElementById('selection-menu')
            if (menuEl) {
                // Use offsetWidth/Height to get the "layout" size, ignoring the scale-in animation
                // getBoundingClientRect() would return the scaled-down size during the transition
                const actualWidth = menuEl.offsetWidth
                const actualHeight = menuEl.offsetHeight
                
                // Re-calculate X based on ACTUAL width
                let newX = originalX
                
                // Prevent overflow right (allow closer to edge: 5px)
                if (newX + (actualWidth / 2) > effectiveViewportWidth - 5) {
                    newX = effectiveViewportWidth - (actualWidth / 2) - 5
                }
                // Prevent overflow left (allow closer to edge: 5px)
                if (newX - (actualWidth / 2) < 5) {
                    newX = (actualWidth / 2) + 5
                }
                
                // Re-calculate Arrow Offset
                let newArrowOffset = originalX - newX
                
                // Clamp arrow (allow closer to edge, e.g. 6px from edge)
                const maxOffset = (actualWidth / 2) - 6 
                if (newArrowOffset > maxOffset) newArrowOffset = maxOffset
                if (newArrowOffset < -maxOffset) newArrowOffset = -maxOffset
                
                // Re-calculate Y (Placement)
                // Need to recalculate base Y/Bottom in correct coordinate space
                let newY = isScaled ? ((rect.top - bodyRect.top) / scaleY - 12) : (rect.top - 12)
                let newPlacement = 'top'
                
                // Check top overflow with ACTUAL height
                if (newY - actualHeight < 60) {
                     newY = isScaled ? ((rect.bottom - bodyRect.top) / scaleY + 12) : (rect.bottom + 12)
                     newPlacement = 'bottom'
                }
                
                // Update State
                selectionMenu.value.x = newX
                selectionMenu.value.y = newY
                selectionMenu.value.arrowOffset = newArrowOffset
                selectionMenu.value.placement = newPlacement
            }
        })
    } else {
        selectionMenu.value.visible = false
    }
}

const handleAsk = () => {
    if (!selectionMenu.value.text) return
    
    const selection = selectionMenu.value.text
    // Format as a quote
    const quote = `> ${selection}\n\n`
    
    // Set to store to trigger ChatPanel update
    courseStore.setPendingChatInput(quote)
    
    // Hide menu
    selectionMenu.value.visible = false
}

const handleTranslate = async () => {
    if (!selectionMenu.value.text) return
    
    const selection = selectionMenu.value.text
    const prompt = `请将以下内容翻译为中文（如果是中文则翻译为英文），并保持专业术语的准确性：\n> "${selection}"`
    
    // 1. Add User Message
    courseStore.addMessage('user', prompt)
    
    // 2. Find Context Node
    let nodeId = undefined
    if (selectionMenu.value.range) {
         const nodeEl = selectionMenu.value.range.startContainer.parentElement?.closest('[id^="node-"]')
         if (nodeEl) nodeId = nodeEl.id.replace('node-', '')
    }
    
    // 3. Trigger AI
    selectionMenu.value.visible = false
    
    ElMessage.success('正在翻译，请查看右侧助手')
    
    await courseStore.askQuestion(prompt, selection, nodeId)
}

const handleAddNote = () => {
    if (!selectionMenu.value.range || !selectionMenu.value.text) return
    
    ElMessageBox.prompt('请输入笔记内容', '添加笔记', {
        confirmButtonText: '保存',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '内容不能为空'
    }).then((data: any) => {
        const { value } = data
        // Create Highlight
        const highlightId = 'highlight-' + Math.random().toString(36).substr(2, 9)
        const noteId = 'note-' + Math.random().toString(36).substr(2, 9)
        const color = pickPaletteColor(`${noteId}-${highlightId}`)
        const span = document.createElement('span')
        span.id = highlightId
        span.className = `highlight-marker ${noteHighlightClass(color)} cursor-pointer transition-colors`
        span.onclick = (e) => {
            e.stopPropagation()
            scrollToHighlight(highlightId)
        }
        
        if (selectionMenu.value.range) {
            const range = selectionMenu.value.range
            try {
                // Try surroundContents first (works for simple selections)
                range.surroundContents(span)
            } catch (e) {
                // For cross-paragraph selections, extract contents and wrap them
                try {
                    const contents = range.extractContents()
                    span.appendChild(contents)
                    range.insertNode(span)
                } catch (e2) {
                    // If still fails, try to find common ancestor and wrap
                    try {
                        const commonAncestor = range.commonAncestorContainer
                        if (commonAncestor.nodeType === Node.TEXT_NODE) {
                            // Split the text node and wrap
                            const parent = commonAncestor.parentNode
                            if (parent) {
                                const startOffset = range.startOffset
                                const endOffset = range.endOffset
                                const text = commonAncestor.textContent || ''
                                const beforeText = text.substring(0, startOffset)
                                const selectedText = text.substring(startOffset, endOffset)
                                const afterText = text.substring(endOffset)
                                
                                span.textContent = selectedText
                                
                                if (beforeText) {
                                    parent.insertBefore(document.createTextNode(beforeText), commonAncestor)
                                }
                                parent.insertBefore(span, commonAncestor)
                                if (afterText) {
                                    parent.insertBefore(document.createTextNode(afterText), commonAncestor)
                                }
                                parent.removeChild(commonAncestor)
                            }
                        } else {
                            ElMessage.warning('选择区域包含复杂内容，已创建笔记但高亮可能不完整')
                            // Continue without highlight but create the note
                        }
                    } catch (e3) {
                        ElMessage.error('无法在此处创建笔记，请尝试选择更小的范围')
                        return
                    }
                }
            }
        }
        
        // Find Node ID - use the range's start container if span wasn't inserted
        let nodeId = ''
        if (span.parentNode) {
            const nodeEl = span.closest('[id^="node-"]')
            nodeId = nodeEl ? nodeEl.id.replace('node-', '') : ''
        } else {
            // Fallback: find node from range
            let container = selectionMenu.value.range?.startContainer
            if (container) {
                if (container.nodeType === Node.TEXT_NODE) {
                    container = container.parentElement
                }
                const nodeEl = (container as Element)?.closest('[id^="node-"]')
                nodeId = nodeEl ? nodeEl.id.replace('node-', '') : ''
            }
        }
        
        if (nodeId) {
            courseStore.createNote({
                id: noteId,
                nodeId,
                highlightId: span.parentNode ? highlightId : undefined, // Only save highlightId if span was inserted
                quote: selectionMenu.value.text,
                content: value,
                color,
                createdAt: Date.now(),
                sourceType: 'user'
            })
            selectionMenu.value.visible = false
            window.getSelection()?.removeAllRanges()
            const lastNote = courseStore.notes[courseStore.notes.length - 1]
            if (lastNote) activeNoteId.value = lastNote.id
        }
    }).catch(() => {})
}



const handleNoteClick = (note: any) => {
    // Open note detail dialog instead of jumping
    selectedNote.value = note
    noteDetailVisible.value = true
    activeNoteId.value = note.id
    isDialogEditing.value = false
}

const handleEditNote = (note: any) => {
    selectedNote.value = note
    noteDetailVisible.value = true
    activeNoteId.value = note.id
    isDialogEditing.value = true
    // Initialize editing values
    editingContent.value = note.content || ''
    editingTags.value = note.tags || []
    editingCategory.value = note.category || ''
    editingPriority.value = note.priority || 'medium'
}

// Start editing from view mode
const startEditing = () => {
    if (selectedNote.value) {
        editingContent.value = selectedNote.value.content || ''
        editingTags.value = selectedNote.value.tags || []
        editingCategory.value = selectedNote.value.category || ''
        editingPriority.value = selectedNote.value.priority || 'medium'
        isDialogEditing.value = true
    }
}

// Helper functions for tags and categories
const getCategoryType = (category: string): string => {
    const typeMap: Record<string, string> = {
        '重点': 'danger',
        '难点': 'warning',
        '疑问': 'info',
        '总结': 'success',
        '错题': 'danger'
    }
    return typeMap[category] || 'info'
}

const getPriorityLabel = (priority: string): string => {
    const labelMap: Record<string, string> = {
        'high': '高优先级',
        'medium': '中优先级',
        'low': '低优先级'
    }
    return labelMap[priority] || priority
}

// Update note metadata
const updateNoteTags = async () => {
    if (selectedNote.value) {
        await courseStore.updateNoteTags(selectedNote.value.id, editingTags.value)
        selectedNote.value.tags = [...editingTags.value]
    }
}

const updateNoteCategory = async () => {
    if (selectedNote.value) {
        await courseStore.updateNoteCategory(selectedNote.value.id, editingCategory.value)
        selectedNote.value.category = editingCategory.value
    }
}

const updateNotePriority = async () => {
    if (selectedNote.value) {
        await courseStore.updateNotePriority(selectedNote.value.id, editingPriority.value)
        selectedNote.value.priority = editingPriority.value
    }
}

// Filter notes by tag
const filterByTag = (tag: string) => {
    const filteredNotes = courseStore.getNotesByTag(tag)
    ElMessage.info(`标签 "${tag}" 共有 ${filteredNotes.length} 条笔记`)
}

const jumpToNoteSource = (note: any) => {
    // Priority 1: Jump to specific highlight if it exists in DOM
    if (note.highlightId) {
        scrollToHighlight(note.highlightId, note.id)
        return
    }

    // Priority 2: Jump to Node (Chapter/Section)
    if (note.nodeId) {
        courseStore.scrollToNode(note.nodeId)
        activeNoteId.value = note.id
    }
}

const cancelDialogEditing = () => {
    isDialogEditing.value = false
    editingContent.value = ''
}

const saveDialogEditing = async () => {
    if (!editingContent.value.trim()) {
        ElMessage.warning('笔记内容不能为空')
        return
    }
    if (selectedNote.value) {
        await courseStore.updateNote(selectedNote.value.id, editingContent.value)
        selectedNote.value.content = editingContent.value
    }
    isDialogEditing.value = false
    ElMessage.success('笔记已更新')
}

const handleDeleteNote = (noteId: string) => {
    const note = courseStore.notes.find(n => n.id === noteId)
    if (!note) return

    ElMessageBox.confirm('确定删除这条笔记吗？将会同时移除关联的划线。', '删除确认', {
        type: 'warning',
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger'
    }).then(() => {
        // State update triggers watcher -> reapplyHighlights -> cleanup orphans
        courseStore.deleteNote(noteId)
        
        showUndoToast(note)
    }).catch(() => {})
}

const showUndoToast = (note: any) => {
    // We can't easily add a button to ElMessage. 
    // Let's add a fixed "Undo" alert at bottom of screen.
    undoNote.value = note
    undoVisible.value = true
    setTimeout(() => { undoVisible.value = false }, 5000)
}

const undoNote = ref(null)
const undoVisible = ref(false)

const scrollToHighlight = (highlightId: string, noteId?: string) => {
    if (!highlightId) {
        if (noteId) {
            scrollToNote(noteId)
        }
        return
    }
    const el = document.getElementById(highlightId)
    if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        el.classList.add('pulse-highlight')
        setTimeout(() => el.classList.remove('pulse-highlight'), 1500)
        
        const note = courseStore.notes.find(n => n.highlightId === highlightId)
        if (note) {
            activeNoteId.value = note.id
            const noteCard = document.getElementById(note.id)
            if (noteCard) {
                noteCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
                noteCard.classList.add('flash-card', 'ring-4', 'ring-primary-200')
                setTimeout(() => noteCard.classList.remove('flash-card', 'ring-4', 'ring-primary-200'), 1000)
            }
        }
        return
    }
    reapplyHighlights()
    nextTick(() => {
        const retryEl = document.getElementById(highlightId)
        if (retryEl) {
            retryEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
            retryEl.classList.add('pulse-highlight')
            setTimeout(() => retryEl.classList.remove('pulse-highlight'), 1500)
            return
        }
        if (noteId) {
            scrollToNote(noteId)
        }
        const note = courseStore.notes.find(n => n.highlightId === highlightId)
        if (note?.nodeId) {
            courseStore.scrollToNode(note.nodeId)
        }
    })
}



const quizConfig = ref({
    visible: false,
    nodeId: '',
    nodeName: '',
    difficulty: DIFFICULTY_LEVELS.INTERMEDIATE as DifficultyLevel,
    style: TEACHING_STYLES.ACADEMIC as TeachingStyle,
    questionCount: 3
})

// Quiz Handling
const handleStartQuiz = (node: any) => {
    quizConfig.value.nodeId = node.node_id
    quizConfig.value.nodeName = node.node_name
    quizConfig.value.visible = true
}



// Dialog Quiz Logic
const submitQuiz = () => {
    if (!quizConfig.value.nodeId) return

    const total = quizQuestions.value.length
    if (total === 0) {
        ElMessage.warning('暂无可提交的题目')
        return
    }
    
    const normalizedAnswers = quizQuestions.value.map((_, idx) => userAnswers.value[idx] || '')
    if (normalizedAnswers.some(a => !a)) {
        ElMessage.warning('请完成所有题目后再提交')
        return
    }
    
    let correctCount = 0
    
    quizQuestions.value.forEach((q, idx) => {
        if (normalizedAnswers[idx] === q.answer) {
            correctCount++
        } else {
            // Auto-save wrong question
            const userAnswer = normalizedAnswers[idx]
            const noteContent = `**错题记录**\n\n**题目**：${q.question}\n\n**你的答案**：${userAnswer} ❌\n**正确答案**：${q.answer} ✅\n\n**解析**：${q.explanation || '暂无解析'}\n\n#错题`
            
            // Check if this wrong question already exists (avoid duplicates)
            const exists = courseStore.notes.some(n => 
                n.nodeId === quizConfig.value.nodeId && 
                n.sourceType === 'wrong' &&
                n.content.includes(q.question)
            )
            
            if (!exists) {
                courseStore.createNote({
                    id: `wrong-${Date.now()}-${idx}`,
                    nodeId: quizConfig.value.nodeId,
                    highlightId: '', // No highlight for quiz
                    quote: '', 
                    content: noteContent,
                    color: 'red',
                    createdAt: Date.now(),
                    sourceType: 'wrong', // Mark as wrong question for UI handling
                    style: 'highlight' // Visual indicator
                })
            }
        }
    })
    
    const score = Math.round((correctCount / total) * 100)
    
    // Persist Score
    courseStore.updateNodeScore(quizConfig.value.nodeId, score)
    
    quizSubmitted.value = true
    
    if (score === 100) {
        ElMessage.success(`太棒了！满分通过！`)
    } else {
        ElMessage.info(`测验完成，得分：${score}分`)
    }
}

const confirmQuiz = async () => {
    quizConfig.value.visible = false
    
    const nodeContent = nodeContentForQuiz(quizConfig.value.nodeId)
    if (!nodeContent || !nodeContent.trim()) {
        ElMessage.warning('当前章节暂无内容，无法生成测验')
        return
    }
    
    // Reset state
    quizVisible.value = true
    generatingQuiz.value = true
    quizQuestions.value = []
    userAnswers.value = []
    quizSubmitted.value = false
    
    try {
        // Use generateQuiz but we want QUESTIONS, not chat history.
        // The store.generateQuiz adds to chat history. 
        // We need a method that returns questions directly for the DIALOG.
        // I will modify store.generateQuiz to return data, which it already does.
        // But store.generateQuiz also adds to chat history.
        // Let's suppress chat history addition if we are in "Dialog Mode"?
        // Or just let it be in chat too? "Dual mode".
        // Let's keep it simple: generateQuiz returns data. We use data for Dialog.
        
        const res = await courseStore.generateQuiz(
            quizConfig.value.nodeId, 
            nodeContent, 
            quizConfig.value.style,
            quizConfig.value.difficulty,
            { silent: true, questionCount: quizConfig.value.questionCount }
        )
        
        if (res && Array.isArray(res)) {
            quizQuestions.value = res
            userAnswers.value = new Array(res.length).fill('')
        } else {
            quizVisible.value = false
            ElMessage.warning('生成题目失败，请重试')
        }
    } catch (e) {
        console.error(e)
        quizVisible.value = false
    } finally {
        generatingQuiz.value = false
    }
}

// Helper to find content
const nodeContentForQuiz = (nodeId: string) => {
    const node = courseStore.nodes.find(n => n.node_id === nodeId)
    return node ? node.node_content : ''
}

// Deprecated old quiz logic (kept for reference if needed, but unused by new flow)
/*
const handleStartQuiz_OLD = async (node: any) => {
    quizVisible.value = true
    generatingQuiz.value = true
    quizSubmitted.value = false
    userAnswers.value = []
    
    try {
        const questions = await courseStore.generateQuiz(node.node_id, node.node_content)
        quizQuestions.value = questions
        userAnswers.value = new Array(questions.length).fill('')
    } catch (error) {
        ElMessage.error('生成题目失败，请重试')
        quizVisible.value = false
    } finally {
        generatingQuiz.value = false
    }
}
*/



// Watch visible notes to re-apply highlights and update positions
watch(visibleNotes, () => {
    // Wait for DOM update
    nextTick(() => {
        reapplyHighlights()
        debouncedUpdatePositions()
    })
}, { deep: true })

// Watch for focus mode changes to recalculate note positions
watch(() => courseStore.isFocusMode, (newVal, oldVal) => {
    if (oldVal && !newVal) {
        // Exiting focus mode - wait for layout to settle then update positions
        nextTick(() => {
            setTimeout(() => {
                reapplyHighlights()
                updateNotePositions()
            }, 300) // Wait for transition to complete
        })
    }
})

const showBackToTop = ref(false)

const handleScroll = (e: Event) => {
    const target = e.target as HTMLElement
    showBackToTop.value = target.scrollTop > 500
    
    // Update Progress
    if (target.scrollHeight > target.clientHeight) {
        scrollProgress.value = (target.scrollTop / (target.scrollHeight - target.clientHeight)) * 100
    }
    
    // Save position (Debounce manually or just save)
    // We use a simple throttle or just save every scroll? Too frequent.
    // Let's debounce the save action.
    saveScrollPosition(target.scrollTop)
}

const saveScrollPosition = debounce((scrollTop: unknown) => {
    if (courseStore.currentCourseId && typeof scrollTop === 'number') {
        localStorage.setItem(`scroll-pos-${courseStore.currentCourseId}`, scrollTop.toString())
    }
}, 500)

const scrollToTop = () => {
    const container = document.getElementById('content-scroll-container')
    if (container) {
        container.scrollTo({ top: 0, behavior: 'smooth' })
    }
}

const restoreScrollPosition = () => {
    if (!courseStore.currentCourseId) return
    const savedPos = localStorage.getItem(`scroll-pos-${courseStore.currentCourseId}`)
    if (!savedPos) return
    const container = document.getElementById('content-scroll-container')
    if (!container) return
    let attempts = 0
    const tryRestore = () => {
        if (!container) return
        const maxTop = Math.max(0, container.scrollHeight - container.clientHeight)
        const target = Math.min(parseInt(savedPos), maxTop)
        if (maxTop > 0 || attempts >= 5) {
            container.scrollTop = target
            return
        }
        attempts += 1
        setTimeout(tryRestore, 200)
    }
    tryRestore()
}

onMounted(() => {
    document.addEventListener('mousedown', (e) => {
        if (selectionMenu.value.visible && !(e.target as HTMLElement).closest('#content-scroll-container')) {
            selectionMenu.value.visible = false
        }
    })

    const container = document.getElementById('content-scroll-container')
    if (container) {
        container.addEventListener('scroll', handleScroll)
        
        observer = new IntersectionObserver((entries: IntersectionObserverEntry[]) => {
            if (isManualScrolling.value) return 

            // Find the intersecting entry that is closest to the top of viewport
            let bestCandidate: any = null
            let maxRatio = -1

            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    if (entry.intersectionRatio > maxRatio) {
                        maxRatio = entry.intersectionRatio
                        bestCandidate = entry
                    }
                }
            })
            
            if (bestCandidate) {
                const target = bestCandidate.target as HTMLElement | null
                const nodeId = target ? target.id.replace('node-', '') : ''
                if (nodeId && courseStore.currentNode?.node_id !== nodeId) {
                    const node = flatNodes.value.find(n => n.node_id === nodeId)
                    if (node) {
                        courseStore.setCurrentNodeSilent(node)
                    }
                }
            }
        }, {
            root: container,
            threshold: [0.1, 0.3, 0.6], // More triggers
            rootMargin: '-10% 0px -60% 0px' // Focus on top area
        })
    }
    
    // Listen for resize to update note positions
    window.addEventListener('resize', debouncedUpdatePositions)
    
    // Initial highlight
    setTimeout(() => {
        reapplyHighlights()
        updateNotePositions()
        restoreScrollPosition()
    }, 1000)
})

// Helper to re-observe nodes when data changes
watch(() => flatNodes.value, () => {
    nextTick(() => {
        if (!observer) return
        observer.disconnect()
        flatNodes.value.forEach(node => {
            const el = document.getElementById(`node-${node.node_id}`)
            if (el) observer?.observe(el)
        })
    })
}, { immediate: true })

onUnmounted(() => {
    window.removeEventListener('resize', debouncedUpdatePositions)
    if (observer) observer.disconnect()
})

defineExpose({
    startQuiz: handleStartQuiz
})
</script>

<style scoped>
/* ContentArea Styles */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.2s ease;
}

.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.scale-fade-enter-active,
.scale-fade-leave-active {
  transition: all 0.2s ease;
}

.scale-fade-enter-from,
.scale-fade-leave-to {
  opacity: 0;
  transform: scale(0.9);
}

:deep(.glass-dialog-clean) {
    background: rgba(255, 255, 255, 0.9) !important;
    backdrop-filter: blur(24px) saturate(180%);
    border-radius: 24px;
    box-shadow: 
        0 0 0 1px rgba(255, 255, 255, 0.2),
        0 20px 40px -12px rgba(0, 0, 0, 0.12), 
        0 0 0 1px rgba(0,0,0,0.02);
    border: none;
    overflow: hidden;
}

:deep(.glass-dialog-clean .el-dialog__header) {
    margin-right: 0;
    padding: 24px 28px 16px;
    border-bottom: 1px solid rgba(0,0,0,0.03);
}

:deep(.glass-dialog-clean .el-dialog__title) {
    font-weight: 800;
    color: #1e293b;
    font-size: 1.25rem;
    letter-spacing: -0.02em;
}

:deep(.glass-dialog-clean .el-dialog__body) {
    padding: 24px 28px;
}

:deep(.glass-dialog-clean .el-dialog__footer) {
    padding: 16px 28px 24px;
    border-top: 1px solid rgba(0,0,0,0.03);
    background: rgba(250, 250, 255, 0.5);
}

:deep(.glass-dialog) {
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(20px);
    border-radius: 20px;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
    border: 1px solid rgba(255, 255, 255, 0.5);
}

:deep(.el-dialog__header) {
    margin-right: 0;
    padding: 20px 24px;
    border-bottom: 1px solid rgba(0,0,0,0.05);
}

:deep(.el-dialog__title) {
    font-weight: 800;
    color: #1e293b;
    font-size: 1.125rem;
}

:deep(.el-dialog__body) {
    padding: 24px;
}

.dashed-line {
    background-image: linear-gradient(to right, #cbd5e1 50%, rgba(255,255,255,0) 0%);
    background-position: bottom;
    background-size: 6px 1px;
    background-repeat: repeat-x;
    background-color: transparent !important;
}

.highlight-marker {
    mix-blend-mode: multiply;
    border-radius: 2px;
    background-color: rgba(251, 191, 36, 0.3);
    border-bottom: 2px solid #f59e0b;
    transition: all 0.2s ease;
    /* 统一高亮高度，模拟荧光笔效果 */
    line-height: 1.4em;
    padding: 0.1em 0;
    box-decoration-clone: clone;
    -webkit-box-decoration-clone: clone;
}

.highlight-marker:hover {
    background-color: rgba(251, 191, 36, 0.5);
    box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.2);
}

.pulse-highlight {
    animation: pulse-glow 1.5s infinite ease-in-out;
    background-color: rgba(251, 191, 36, 0.6) !important;
    box-shadow: 0 0 8px rgba(245, 158, 11, 0.4);
}

.flash-card {
    animation: card-flash 1s ease;
}

@keyframes pulse-glow {
    0% { background-color: rgba(251, 191, 36, 0.4); box-shadow: 0 0 0px rgba(245, 158, 11, 0.2); }
    50% { background-color: rgba(251, 191, 36, 0.7); box-shadow: 0 0 12px rgba(245, 158, 11, 0.6); }
    100% { background-color: rgba(251, 191, 36, 0.4); box-shadow: 0 0 0px rgba(245, 158, 11, 0.2); }
}

@keyframes card-flash {
    0% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0); }
    30% { box-shadow: 0 0 0 6px rgba(99, 102, 241, 0.3); border-color: #818cf8; transform: scale(1.02); }
    100% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0); transform: scale(1); }
}

.flash-highlight {
    animation: flash 1s ease;
}

@keyframes flash {
    0%, 100% { background-color: rgba(251, 191, 36, 0.3); }
    50% { background-color: rgba(251, 191, 36, 0.8); box-shadow: 0 0 10px rgba(245, 158, 11, 0.5); }
}

.back-to-top {
    position: fixed;
    bottom: 1.5rem;
    right: 1.5rem;
    z-index: 50;
    transition: all 0.3s ease;
}

/* Adjust position when notes panel is open */
@media (min-width: 768px) {
    .back-to-top {
        right: 300px;
    }
}

@media (min-width: 1280px) {
    .back-to-top {
        right: 320px;
    }
}

.back-to-top-enter-active,
.back-to-top-leave-active {
    transition: all 0.3s ease;
}

.back-to-top-enter-from,
.back-to-top-leave-to {
    opacity: 0;
    transform: translateY(20px);
}

.note-underline {
    position: relative;
}

.note-underline::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    bottom: -6px;
    height: 6px;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='6' viewBox='0 0 120 6'><polyline points='0,4 20,4 20,1 40,1 40,4 60,4 60,1 80,1 80,4 100,4 100,1 120,1' fill='none' stroke='%2394a3b8' stroke-width='1.5' stroke-linejoin='miter' stroke-linecap='square'/></svg>");
    background-repeat: repeat-x;
    background-size: 120px 6px;
    opacity: 0;
    transition: opacity 0.2s ease;
    pointer-events: none;
}

.group:hover .note-underline::after {
    opacity: 0.8;
}

:deep(.glass-input-clean .el-input__wrapper) {
    background-color: rgba(255, 255, 255, 0.6) !important;
    box-shadow: none !important;
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-radius: 12px;
    padding: 8px 12px;
    transition: all 0.3s ease;
}

:deep(.glass-input-clean .el-input__wrapper:hover) {
    background-color: rgba(255, 255, 255, 0.8) !important;
    border-color: rgba(255, 255, 255, 0.8);
}

:deep(.glass-input-clean .el-input__wrapper.is-focus) {
    background-color: white !important;
    border-color: #cbd5e1;
    box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.08) !important;
}

.glass-panel-floating {
    background: rgba(255, 255, 255, 0.75);
    backdrop-filter: blur(20px) saturate(180%);
    border: 1px solid rgba(255, 255, 255, 0.6);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.04);
}

.glass-panel-floating:hover {
    background: rgba(255, 255, 255, 0.85);
    border-color: rgba(255, 255, 255, 0.8);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.06);
}


:deep(.glass-input-clean .el-input__inner) {
    color: #334155;
    font-weight: 500;
}

/* Content Render Styles */
.content-render :deep(h1),
.content-render :deep(h2),
.content-render :deep(h3),
.content-render :deep(h4) {
    font-weight: 600;
    color: #1e293b;
    margin-top: 2rem;
    margin-bottom: 1rem;
}

.content-render :deep(h2) {
    font-size: 1.25rem;
    font-weight: 700;
    letter-spacing: -0.02em;
}

.content-render :deep(h3) {
    font-size: 1.125rem;
    font-weight: 600;
}

.content-render :deep(p) {
    color: #475569;
    line-height: 1.8;
    margin-bottom: 1.25rem;
    font-size: 15px;
}

.content-render :deep(a) {
    color: #4f46e5;
    text-decoration: none;
    font-weight: 500;
}

.content-render :deep(a:hover) {
    text-decoration: underline;
}

.content-render :deep(strong) {
    color: #334155;
    font-weight: 600;
}

.content-render :deep(code) {
    color: #4f46e5;
    background: rgba(79, 70, 229, 0.08);
    padding: 0.125rem 0.375rem;
    border-radius: 0.375rem;
    font-size: 13px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.content-render :deep(pre) {
    background: #1e293b;
    border-radius: 0.75rem;
    padding: 1rem;
    margin: 1.25rem 0;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    overflow-x: auto;
}

.content-render :deep(pre code) {
    background: transparent;
    color: #e2e8f0;
    padding: 0;
}

.content-render :deep(ul),
.content-render :deep(ol) {
    margin: 1rem 0;
    padding-left: 1.5rem;
}

.content-render :deep(li) {
    color: #475569;
    font-size: 15px;
    line-height: 1.8;
    margin: 0.375rem 0;
}

.content-render :deep(blockquote) {
    border-left: 3px solid #818cf8;
    background: linear-gradient(to right, rgba(79, 70, 229, 0.05), transparent);
    padding-left: 1.25rem;
    padding-top: 0.5rem;
    padding-bottom: 0.5rem;
    margin: 1.25rem 0;
    font-style: normal;
    color: #475569;
    font-weight: 500;
}

/* Note Detail Dialog Markdown Styles */
:deep(.note-detail-dialog) {
    background: rgba(255, 255, 255, 0.95) !important;
    backdrop-filter: blur(24px) saturate(180%);
    border-radius: 20px;
    box-shadow:
        0 0 0 1px rgba(255, 255, 255, 0.2),
        0 20px 40px -12px rgba(0, 0, 0, 0.12),
        0 0 0 1px rgba(0,0,0,0.02);
    border: none;
    overflow: hidden;
}

:deep(.note-detail-dialog .el-dialog__header) {
    margin-right: 0;
    padding: 20px 24px 16px;
    border-bottom: 1px solid rgba(0,0,0,0.05);
}

:deep(.note-detail-dialog .el-dialog__title) {
    font-weight: 700;
    color: #1e293b;
    font-size: 1.125rem;
}

:deep(.note-detail-dialog .el-dialog__body) {
    padding: 20px 24px;
    max-height: 60vh;
    overflow-y: auto;
}

:deep(.note-detail-dialog .el-dialog__footer) {
    padding: 16px 24px 20px;
    border-top: 1px solid rgba(0,0,0,0.05);
}

.note-content-markdown {
    color: #334155;
    line-height: 1.8;
    font-size: 15px;
}

.note-content-markdown :deep(h1),
.note-content-markdown :deep(h2),
.note-content-markdown :deep(h3),
.note-content-markdown :deep(h4),
.note-content-markdown :deep(h5),
.note-content-markdown :deep(h6) {
    font-weight: 600;
    color: #1e293b;
    margin-top: 1.5rem;
    margin-bottom: 0.75rem;
    line-height: 1.4;
}

.note-content-markdown :deep(h1) {
    font-size: 1.5rem;
    font-weight: 700;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 0.5rem;
}

.note-content-markdown :deep(h2) {
    font-size: 1.25rem;
    font-weight: 600;
}

.note-content-markdown :deep(h3) {
    font-size: 1.125rem;
    font-weight: 600;
}

.note-content-markdown :deep(h4) {
    font-size: 1rem;
    font-weight: 600;
}

.note-content-markdown :deep(p) {
    margin-bottom: 1rem;
    color: #475569;
}

.note-content-markdown :deep(strong) {
    color: #1e293b;
    font-weight: 600;
}

.note-content-markdown :deep(em) {
    color: #64748b;
    font-style: italic;
}

.note-content-markdown :deep(code) {
    color: #4f46e5;
    background: rgba(79, 70, 229, 0.08);
    padding: 0.125rem 0.375rem;
    border-radius: 0.375rem;
    font-size: 13px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.note-content-markdown :deep(pre) {
    background: #1e293b;
    border-radius: 0.75rem;
    padding: 1rem;
    margin: 1rem 0;
    overflow-x: auto;
}

.note-content-markdown :deep(pre code) {
    background: transparent;
    color: #e2e8f0;
    padding: 0;
}

.note-content-markdown :deep(ul),
.note-content-markdown :deep(ol) {
    margin: 1rem 0;
    padding-left: 1.5rem;
}

.note-content-markdown :deep(li) {
    margin: 0.375rem 0;
}

.note-content-markdown :deep(blockquote) {
    border-left: 3px solid #818cf8;
    background: linear-gradient(to right, rgba(79, 70, 229, 0.05), transparent);
    padding: 0.75rem 1rem;
    margin: 1rem 0;
    border-radius: 0 0.5rem 0.5rem 0;
}

/* Table Styles */
.note-content-markdown :deep(table) {
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
    font-size: 14px;
    border-radius: 0.5rem;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.note-content-markdown :deep(thead) {
    background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
}

.note-content-markdown :deep(th) {
    padding: 0.75rem 1rem;
    text-align: left;
    font-weight: 600;
    color: #1e293b;
    border-bottom: 2px solid #cbd5e1;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.note-content-markdown :deep(td) {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid #e2e8f0;
    color: #475569;
}

.note-content-markdown :deep(tr:hover) {
    background: rgba(79, 70, 229, 0.03);
}

.note-content-markdown :deep(tr:last-child td) {
    border-bottom: none;
}

.note-content-markdown :deep(a) {
    color: #4f46e5;
    text-decoration: none;
    font-weight: 500;
}

.note-content-markdown :deep(a:hover) {
    text-decoration: underline;
}

.note-content-markdown :deep(hr) {
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 1.5rem 0;
}

.note-content-markdown :deep(img) {
    max-width: 100%;
    border-radius: 0.5rem;
    margin: 1rem 0;
}

/* Preview Card Markdown Overrides */
.note-preview-content :deep(h1),
.note-preview-content :deep(h2),
.note-preview-content :deep(h3),
.note-preview-content :deep(h4),
.note-preview-content :deep(h5),
.note-preview-content :deep(h6) {
    font-size: 0.95rem !important;
    font-weight: 700 !important;
    margin: 0.25rem 0 !important;
    line-height: 1.4 !important;
    color: #334155;
}

.note-preview-content :deep(p) {
    margin-bottom: 0.25rem !important;
    font-size: 0.875rem !important;
}

.note-preview-content :deep(ul),
.note-preview-content :deep(ol) {
    margin: 0.25rem 0 !important;
    padding-left: 1rem !important;
}

.note-preview-content :deep(pre),
.note-preview-content :deep(blockquote),
.note-preview-content :deep(table) {
    margin: 0.5rem 0 !important;
    font-size: 0.75rem !important;
}

.note-preview-content :deep(.katex) {
    font-size: 1em !important;
}
</style>
