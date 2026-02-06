<template>
  <div class="h-full flex flex-col">
    <!-- Reading Progress Bar -->
    <div class="fixed top-0 left-0 right-0 h-1 bg-slate-100 z-50" v-if="scrollProgress > 0">
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

    <!-- Toolbar -->
    <div class="h-16 flex items-center justify-between px-4 lg:px-6 mx-2 lg:mx-6 mt-4 mb-2 sticky top-4 z-30 transition-all duration-300 glass-panel rounded-2xl">
      <div class="bg-white/50 backdrop-blur-sm rounded-full px-4 py-1.5 border border-white/40 shadow-sm flex items-center gap-2">
        <span class="font-bold text-slate-700 truncate max-w-[200px]">
            {{ courseStore.courseList.find(c => c.course_id === courseStore.currentCourseId)?.course_name || '课程预览' }}
        </span>
        <span class="text-slate-300">|</span>
        <span class="text-xs text-slate-500">全书模式</span>
      </div>
      
      <div class="flex gap-3">
        <button class="lg:hidden px-3 py-1.5 rounded-lg bg-white/40 hover:bg-white/80 border border-white/50 text-slate-600 flex items-center gap-2" @click="showMobileNotes = true">
            <el-icon><Notebook /></el-icon>
        </button>
        
        <!-- Typography Settings -->
        <el-popover placement="bottom" :width="240" trigger="click" popper-class="glass-popover">
            <template #reference>
                <button class="px-3 py-1.5 rounded-lg bg-white/40 hover:bg-white/80 border border-white/50 text-slate-600 hover:text-primary-600 flex items-center gap-2 transition-all shadow-sm hover:shadow-md text-xs font-bold">
                    <el-icon><Setting /></el-icon>
                    <span class="hidden lg:inline">外观</span>
                </button>
            </template>
            <div class="p-2 space-y-4">
                <!-- Font Size -->
                <div class="space-y-2">
                    <div class="text-xs font-bold text-slate-500">字号</div>
                    <div class="flex items-center gap-2 bg-slate-100 rounded-lg p-1">
                        <button class="flex-1 p-1 hover:bg-white rounded text-slate-600" @click="fontSize = Math.max(8, fontSize - 1)"><el-icon><Minus /></el-icon></button>
                        <span class="text-xs font-mono w-8 text-center">{{ fontSize }}</span>
                        <button class="flex-1 p-1 hover:bg-white rounded text-slate-600" @click="fontSize = Math.min(72, fontSize + 1)"><el-icon><Plus /></el-icon></button>
                    </div>
                </div>
                <!-- Font Family -->
                <div class="space-y-2">
                    <div class="text-xs font-bold text-slate-500">字体</div>
                    <div class="grid grid-cols-3 gap-2">
                        <button class="px-2 py-1 text-xs border rounded hover:border-primary-500" :class="fontFamily === 'sans' ? 'bg-primary-50 border-primary-500 text-primary-600' : 'bg-white border-slate-200'" @click="fontFamily = 'sans'">无衬线</button>
                        <button class="px-2 py-1 text-xs border rounded hover:border-primary-500 font-serif" :class="fontFamily === 'serif' ? 'bg-primary-50 border-primary-500 text-primary-600' : 'bg-white border-slate-200'" @click="fontFamily = 'serif'">衬线</button>
                        <button class="px-2 py-1 text-xs border rounded hover:border-primary-500 font-mono" :class="fontFamily === 'mono' ? 'bg-primary-50 border-primary-500 text-primary-600' : 'bg-white border-slate-200'" @click="fontFamily = 'mono'">等宽</button>
                    </div>
                </div>
                <!-- Line Height -->
                <div class="space-y-2">
                    <div class="text-xs font-bold text-slate-500">行高</div>
                    <div class="grid grid-cols-3 gap-2">
                        <button class="px-2 py-1 text-xs border rounded hover:border-primary-500" :class="lineHeight === 1.5 ? 'bg-primary-50 border-primary-500 text-primary-600' : 'bg-white border-slate-200'" @click="lineHeight = 1.5">紧凑</button>
                        <button class="px-2 py-1 text-xs border rounded hover:border-primary-500" :class="lineHeight === 1.75 ? 'bg-primary-50 border-primary-500 text-primary-600' : 'bg-white border-slate-200'" @click="lineHeight = 1.75">舒适</button>
                        <button class="px-2 py-1 text-xs border rounded hover:border-primary-500" :class="lineHeight === 2 ? 'bg-primary-50 border-primary-500 text-primary-600' : 'bg-white border-slate-200'" @click="lineHeight = 2">宽松</button>
                    </div>
                </div>
            </div>
        </el-popover>
        
        <!-- Focus Mode -->
        <button 
            class="px-3 py-1.5 rounded-lg bg-white/40 hover:bg-white/80 border border-white/50 text-slate-600 hover:text-primary-600 flex items-center gap-2 transition-all shadow-sm hover:shadow-md text-xs font-bold"
            @click="toggleFocusMode"
            :class="{'!text-primary-600 !bg-white': courseStore.isFocusMode}"
            title="专注模式"
        >
            <el-icon><FullScreen /></el-icon>
            <span class="hidden lg:inline">{{ courseStore.isFocusMode ? '退出专注' : '专注模式' }}</span>
        </button>

        <!-- TTS Control -->
        <button 
            class="px-3 py-1.5 rounded-lg bg-white/40 hover:bg-white/80 border border-white/50 text-slate-600 hover:text-primary-600 flex items-center gap-2 transition-all shadow-sm hover:shadow-md text-xs font-bold"
            @click="toggleTTS"
            :class="{'!text-primary-600 !bg-white': isSpeaking}"
        >
            <el-icon><Microphone /></el-icon>
            <span class="hidden lg:inline">{{ isSpeaking ? '停止朗读' : '朗读全书' }}</span>
        </button>

        <div class="w-px h-6 bg-slate-300 mx-1"></div>

        <!-- Global Search -->
        <div class="relative group">
            <el-input 
                v-model="globalSearchQuery" 
                placeholder="搜索内容..." 
                :prefix-icon="Search" 
                size="small" 
                clearable 
                class="!w-40 focus:!w-64 transition-all duration-300 glass-input"
                @input="handleGlobalSearch"
            />
            <div v-if="globalSearchResults.length > 0" class="absolute top-full left-0 right-0 mt-2 bg-white rounded-xl shadow-xl border border-slate-100 p-2 z-50 max-h-60 overflow-auto">
                <div v-for="(res, idx) in globalSearchResults" :key="idx" 
                     class="p-2 hover:bg-slate-50 rounded-lg cursor-pointer text-xs flex flex-col gap-1"
                     @click="scrollToSearchResult(res.id)">
                    <span class="font-bold text-slate-700 truncate">{{ res.title }}</span>
                    <span class="text-slate-500 truncate" v-html="res.preview"></span>
                </div>
            </div>
        </div>

        <el-dropdown trigger="click" @command="handleExport">
            <button 
                class="px-3 py-1.5 rounded-lg bg-white/40 hover:bg-white/80 border border-white/50 text-slate-600 hover:text-primary-600 flex items-center gap-2 transition-all shadow-sm hover:shadow-md text-xs font-bold" 
            >
                <el-icon><Download /></el-icon>
                <span>导出</span>
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

    <!-- Content List (Continuous Scroll) -->
    <div class="flex-1 overflow-auto p-4 lg:p-10 relative scroll-smooth custom-scrollbar" id="content-scroll-container" @mouseup="handleMouseUp" @dblclick="handleDoubleClick">
      
        <!-- Selection Menu -->
    <Teleport to="body">
      <transition name="scale-fade">
        <div v-if="selectionMenu.visible" 
            class="fixed z-50 flex flex-col p-1.5 bg-white/95 backdrop-blur-xl rounded-2xl shadow-[0_12px_40px_rgba(0,0,0,0.15)] border border-white/40 ring-1 ring-black/5 min-w-[260px] select-none"
            :style="{ left: selectionMenu.x + 'px', top: selectionMenu.y + 'px', transform: 'translateX(-50%)' }"
            @mousedown.stop>
            
            <!-- Row 1: Quick Actions -->
            <div class="flex items-center gap-1 pb-1.5 mb-1.5 border-b border-slate-100">
                <el-tooltip content="AI 智能解析" placement="top" :show-after="500">
                    <button @click="handleExplain" class="flex-1 relative z-10 flex flex-col items-center justify-center gap-0.5 px-2 py-1.5 rounded-xl text-slate-600 hover:text-primary-600 hover:bg-primary-50 transition-all group active:scale-95">
                        <el-icon class="text-lg mb-0.5"><MagicStick /></el-icon> 
                        <span class="text-[10px] font-bold">解析</span>
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
            <div class="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-white border-b border-r border-white/40 rotate-45 shadow-[4px_4px_4px_rgba(0,0,0,0.05)]"></div>
        </div>
      </transition>
    </Teleport>

      <div v-if="flatNodes.length > 0" class="flex w-full h-full relative">


        <!-- Main Content Column -->
        <div class="flex-1 min-w-0 px-4 lg:px-12 space-y-12 pb-32 pt-4">
            <div v-for="(node, index) in flatNodes" :key="node.node_id" :id="'node-' + node.node_id" 
                class="scroll-mt-24 transition-all duration-500 animate-fade-in-up"
                :style="{ animationDelay: (index * 100) + 'ms' }">
                
                <!-- Level 1: Course Title / Part -->
                <div v-if="node.node_level === 1" class="relative overflow-hidden rounded-[2.5rem] bg-white/60 backdrop-blur-2xl border border-white/60 shadow-xl shadow-primary-500/5 mb-24 group hover:shadow-2xl hover:shadow-primary-500/10 transition-shadow duration-500">
                    <!-- Background Decor -->
                    <div class="absolute inset-0 bg-gradient-to-br from-white/60 via-transparent to-white/20 pointer-events-none"></div>
                    <div class="absolute -top-[40%] -right-[20%] w-[80%] h-[120%] bg-gradient-to-b from-primary-100/40 to-transparent rounded-full blur-[100px] pointer-events-none opacity-60 mix-blend-multiply"></div>
                    <div class="absolute -bottom-[40%] -left-[20%] w-[80%] h-[120%] bg-gradient-to-t from-pink-100/40 to-transparent rounded-full blur-[100px] pointer-events-none opacity-60 mix-blend-multiply"></div>
                    
                    <div class="relative z-10 p-16 lg:p-24 flex flex-col items-center text-center">
                        <!-- Badge -->
                        <div class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/80 border border-slate-200/60 shadow-sm backdrop-blur-md mb-10 group-hover:-translate-y-1 transition-transform duration-500">
                            <span class="relative flex h-2 w-2">
                            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-400 opacity-75"></span>
                            <span class="relative inline-flex rounded-full h-2 w-2 bg-primary-500"></span>
                            </span>
                            <span class="text-[10px] font-bold tracking-widest text-slate-500 uppercase font-sans">Interactive Course</span>
                        </div>

                        <!-- Title -->
                        <h1 class="text-5xl lg:text-7xl font-black text-slate-800 mb-8 tracking-tighter drop-shadow-sm font-display leading-[1.1] max-w-6xl bg-clip-text text-transparent bg-gradient-to-br from-slate-900 via-slate-800 to-slate-700">
                            {{ node.node_name.replace(/《|》/g, '') }}
                        </h1>

                        <!-- Divider -->
                        <div class="flex items-center gap-6 mb-10 opacity-40">
                            <div class="w-16 h-px bg-gradient-to-r from-transparent via-slate-400 to-transparent"></div>
                            <div class="w-1.5 h-1.5 rounded-full bg-slate-400"></div>
                            <div class="w-16 h-px bg-gradient-to-r from-transparent via-slate-400 to-transparent"></div>
                        </div>

                        <!-- Description -->
                        <div class="prose prose-lg prose-slate text-slate-600 max-w-5xl mx-auto font-sans leading-relaxed mix-blend-multiply text-center font-medium" v-html="renderMarkdown(node.node_content)"></div>
                    </div>
                </div>

                <!-- Level 2: Chapter -->
                <div v-else-if="node.node_level === 2" class="mt-24 mb-10 relative group">
                    <div class="absolute -left-4 -top-4 w-20 h-20 bg-gradient-to-br from-slate-100 to-transparent rounded-full opacity-50 blur-xl group-hover:opacity-100 transition-opacity"></div>
                    <div class="flex items-baseline gap-4 mb-6 border-b-2 border-slate-100 pb-4">
                        <span class="text-4xl font-black text-slate-200 font-display select-none">CHAPTER</span>
                        <h2 class="text-3xl font-bold text-slate-800 relative z-10">{{ node.node_name }}</h2>
                        <!-- TTS Button -->
                        <button class="ml-2 p-1.5 rounded-full text-slate-300 hover:text-primary-500 hover:bg-primary-50 transition-all opacity-0 group-hover:opacity-100"
                                @click="toggleTTS(node.node_content)"
                                :class="{'text-primary-500 bg-primary-50 !opacity-100 animate-pulse': isSpeaking && currentSpeakingContent === node.node_content}"
                                title="朗读本章">
                             <el-icon><Microphone /></el-icon>
                        </button>
                    </div>
                    
                    <!-- Chapter Metadata -->
                    <div class="flex items-center gap-4 mb-4 text-xs font-bold text-slate-400">
                        <div v-if="node.is_read" class="flex items-center gap-1 text-emerald-500 bg-emerald-50 px-2 py-1 rounded-full">
                            <el-icon><Check /></el-icon> 已读
                        </div>
                        <div v-if="node.quiz_score !== undefined" class="flex items-center gap-1 text-amber-500 bg-amber-50 px-2 py-1 rounded-full">
                            <el-icon><Trophy /></el-icon> 最高分: {{ node.quiz_score }}%
                        </div>
                        <div class="flex items-center gap-1 text-indigo-500 bg-indigo-50 px-2 py-1 rounded-full">
                            <el-icon><Timer /></el-icon> 预计阅读: {{ Math.ceil((node.node_content?.length || 0) / 500) }} 分钟
                        </div>
                    </div>

                    <!-- Quiz Button -->
                    <div class="absolute right-0 top-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                        <button 
                        class="glass-icon-btn !w-auto !px-3 !h-8 !rounded-full bg-white/50 hover:bg-white/90 text-xs gap-2"
                        @click="handleStartQuiz(node)" 
                        title="智能测验"
                        >
                        <el-icon><VideoPlay /></el-icon>
                        <span>本章测验</span>
                        </button>
                    </div>
                </div>

                <!-- Level 3+: Content Card -->
                <div v-else class="group relative pl-8 border-l-2 border-slate-100 hover:border-primary-300 transition-colors duration-300">
                    <div class="absolute -left-[9px] top-0 w-4 h-4 rounded-full bg-slate-50 border-2 border-slate-200 group-hover:border-primary-500 group-hover:bg-primary-50 transition-all duration-300"></div>
                    
                    <h3 class="text-xl font-bold text-slate-800 mb-4 flex items-center gap-3">
                        {{ node.node_name }}
                        <div class="opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex gap-2">
                            <button class="p-1 text-slate-400 hover:text-primary-500 rounded-md hover:bg-slate-100 transition-colors" @click="handleStartQuiz(node)" title="小节测验">
                                <el-icon><VideoPlay /></el-icon>
                            </button>
                            <button class="p-1 text-slate-400 hover:text-primary-500 rounded-md hover:bg-slate-100 transition-colors" @click="showSummary(node)" title="内容摘要">
                                <el-icon><Notebook /></el-icon>
                            </button>
                        </div>
                    </h3>
                    
                    <div class="glass-panel p-6 lg:p-8 rounded-2xl relative overflow-hidden group-hover:shadow-lg transition-shadow duration-300">
                        <div class="prose prose-slate max-w-none prose-headings:font-display prose-headings:text-slate-800 prose-p:text-slate-600 prose-a:text-primary-600 hover:prose-a:text-primary-500 prose-strong:text-slate-700 prose-code:text-primary-600 prose-code:bg-primary-50 prose-pre:bg-slate-800 prose-pre:shadow-lg" 
                            :style="{ 
                                fontSize: fontSize + 'px',
                                fontFamily: fontFamily === 'mono' ? 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' : (fontFamily === 'serif' ? 'ui-serif, Georgia, Cambria, Times New Roman, Times, serif' : 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif'),
                                lineHeight: lineHeight 
                            }"
                            v-html="renderMarkdown(node.node_content)">
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Note Column (Desktop Only) -->
        <div id="note-column" v-if="!courseStore.isFocusMode" class="hidden lg:flex flex-col w-[260px] flex-shrink-0 relative border-l border-slate-100 bg-slate-50/30 transition-all duration-300">
             <!-- Search Header -->
            <div class="sticky top-0 z-10 p-3 bg-slate-50/95 backdrop-blur border-b border-slate-100 flex flex-col gap-2">
                <div class="flex items-center gap-2">
                    <h3 class="text-sm font-bold text-slate-700">我的笔记</h3>
                    <div class="flex-1"></div>
                    <el-tooltip content="导出笔记" placement="bottom">
                        <button class="p-1.5 text-slate-400 hover:text-primary-600 hover:bg-white rounded-md transition-colors" @click="exportContent">
                            <el-icon><Download /></el-icon>
                        </button>
                    </el-tooltip>
                </div>
                
                <!-- Note Filters -->
                <div class="relative flex bg-slate-100 p-1 rounded-xl mb-2 select-none">
                    <!-- Animated Background -->
                    <div class="absolute top-1 bottom-1 rounded-lg bg-white shadow-sm transition-all duration-300 ease-out"
                         :style="activeTabStyle"></div>
                         
                    <button v-for="tab in ['all', 'ai', 'user', 'wrong']" :key="tab"
                        class="relative flex-1 py-1.5 text-xs font-bold rounded-lg transition-colors z-10 text-center"
                        :class="activeNoteFilter === tab ? 'text-primary-600' : 'text-slate-500 hover:text-slate-700'"
                        @click="activeNoteFilter = tab"
                    >
                        {{ tab === 'all' ? '全部' : (tab === 'ai' ? 'AI' : (tab === 'user' ? '手记' : '错题')) }}
                    </button>
                </div>

                <el-input v-model="noteSearchQuery" placeholder="搜索笔记..." :prefix-icon="Search" size="small" clearable class="!w-full glass-input">
                    <template #suffix>
                        <el-icon v-if="isSearching" class="is-loading text-primary-500"><Loading /></el-icon>
                    </template>
                </el-input>
            </div>

            <div id="notes-container" class="relative flex-1 w-full">
                <div class="absolute inset-0 pointer-events-none">
                    <!-- Guide Line -->
                    <div class="absolute left-[-1px] top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-primary-200 to-transparent opacity-50"></div>
                </div>
                
                <!-- Loading Skeleton -->
                <div v-if="isSearching" class="absolute inset-0 z-20 bg-white/80 backdrop-blur-sm p-4 space-y-4">
                    <div v-for="i in 3" :key="i" class="animate-pulse flex flex-col gap-2">
                         <div class="h-20 bg-slate-100 rounded-xl"></div>
                    </div>
                </div>
                
                <!-- Empty State for Search -->
                <div v-if="!isSearching && displayedNotes.length === 0 && debouncedSearchQuery" class="flex flex-col items-center justify-center py-10 text-slate-400">
                    <el-icon :size="24" class="mb-2 opacity-50"><Search /></el-icon>
                    <p class="text-xs">未找到相关笔记</p>
                </div>

                <!-- Unquoted/Global Notes (Static Flow) -->
                <div id="global-notes-section" class="flex flex-col gap-3 p-2 pb-4 mb-2 border-b border-slate-100/50 relative z-10">
                    <div class="flex justify-between items-center px-1">
                        <div class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">全局笔记</div>
                        <el-button link size="small" type="primary" @click="addGlobalNote">
                            <el-icon class="mr-1"><Plus /></el-icon>添加
                        </el-button>
                    </div>
                    <div v-if="unquotedNotes.length === 0" class="text-center py-4 text-xs text-slate-400 bg-slate-50/50 rounded-lg border border-dashed border-slate-200">
                        暂无全局笔记
                    </div>
                    <div v-for="note in unquotedNotes" :key="note.id" 
                         class="bg-white rounded-xl shadow-sm border border-slate-200 p-3 group hover:shadow-md hover:border-primary-200 transition-all cursor-pointer relative"
                         :class="{'ring-2 ring-primary-100': activeNoteId === note.id, '!border-purple-200 !bg-purple-50/30': note.sourceType === 'ai'}"
                         @click="handleEditNote(note)">
                        
                        <!-- Connector (Hidden for global) -->
                        
                        <div class="flex justify-between items-start mb-1">
                            <div v-if="note.sourceType === 'ai'" class="text-[10px] font-bold text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded border border-purple-100 flex items-center gap-1">
                                <el-icon><MagicStick /></el-icon> AI 助手
                            </div>
                            <div v-else class="text-[10px] font-bold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-100">笔记</div>
                            
                            <div class="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button class="p-1 hover:bg-slate-100 rounded text-slate-400 hover:text-primary-600" @click.stop="handleEditNote(note)">
                                    <el-icon :size="12"><Edit /></el-icon>
                                </button>
                                <button class="p-1 hover:bg-slate-100 rounded text-slate-400 hover:text-red-500" @click.stop="handleDeleteNote(note.id)">
                                    <el-icon :size="12"><Delete /></el-icon>
                                </button>
                            </div>
                        </div>
                        <div v-if="editingNoteId === note.id" class="mt-2" @click.stop>
                            <el-input 
                                v-model="editingContent" 
                                type="textarea" 
                                :rows="3" 
                                resize="none"
                                class="mb-2"
                                placeholder="输入笔记内容..."
                            />
                            <div class="flex justify-end gap-2 mt-2">
                                <el-button size="small" text bg @click.stop="cancelEditing">取消</el-button>
                                <el-button size="small" type="primary" round @click.stop="saveEditing(note)">保存修改</el-button>
                            </div>
                        </div>
                        <template v-else>
                            <div class="text-sm text-slate-700 font-medium leading-relaxed whitespace-pre-wrap" 
                                 v-html="formatNoteContent(note.content)"
                                 :style="noteContentStyle(note)"></div>
                                <div v-if="shouldCollapse(note)" 
                                      class="text-primary-500 text-xs cursor-pointer hover:underline mt-1 select-none block"
                                      @click.stop="toggleExpand(note.id)">
                                    {{ expandedNoteIds.includes(note.id) ? '收起' : '展开' }}
                                </div>
                                <div class="mt-2 flex items-center justify-between">
                                    <div class="flex items-center gap-1 text-[10px] text-slate-400">
                                        <el-icon><Timer /></el-icon>
                                        <span>{{ dayjs(note.createdAt).fromNow() }}</span>
                                    </div>
                                    <el-tag v-if="note.sourceType === 'ai'" size="small" type="success" effect="plain" round class="!h-5 !text-[10px] !px-1.5 border-none bg-green-50 text-green-600">
                                        AI 生成
                                    </el-tag>
                                </div>
                            </template>
                    </div>
                </div>

                <!-- Quoted Notes (Absolute Positioning) -->
                <transition-group name="list">
                    <div v-for="note in displayedQuotedNotes" :key="note.id" :id="note.id"
                         class="absolute left-2 right-2 transition-all duration-500 ease-out"
                         :style="{ top: (note.top || 0) + 'px' }">
                        
                         <!-- Connector Line -->
                         <div class="absolute -left-4 top-5 w-4 h-px transition-colors duration-300" 
                              :class="(activeNoteId === note.id || hoveredNoteId === note.id) ? 'bg-primary-300' : 'bg-slate-200'"></div>
                         <div class="absolute -left-[18px] top-[17px] w-2 h-2 rounded-full shadow-sm ring-2 ring-white transition-all duration-300"
                              :class="(activeNoteId === note.id || hoveredNoteId === note.id) ? 'bg-primary-500 scale-125' : (note.sourceType === 'ai' ? 'bg-purple-400' : 'bg-slate-300')"></div>

                         <!-- Note Bubble -->
                         <div class="bg-white rounded-xl shadow-md border border-slate-100 p-0 group hover:shadow-lg hover:-translate-y-0.5 transition-all duration-300 cursor-pointer overflow-hidden"
                              :class="{'ring-2 ring-primary-200': activeNoteId === note.id || hoveredNoteId === note.id, '!border-purple-200 !shadow-purple-100': note.sourceType === 'ai'}"
                              @click="scrollToHighlight(note.highlightId)"
                              @mouseenter="setHovered(note.id)"
                              @mouseleave="setHovered(null)">
                            
                            <!-- Header -->
                            <div class="flex justify-between items-center px-3 py-2 border-b border-slate-50"
                                 :class="note.sourceType === 'ai' ? 'bg-purple-50/50' : 'bg-slate-50/50'">
                                <div v-if="note.sourceType === 'ai'" class="text-[10px] font-bold text-purple-600 flex items-center gap-1">
                                    <el-icon><MagicStick /></el-icon> AI 助手
                                </div>
                                <div v-else class="text-[10px] font-bold text-slate-500 flex items-center gap-1">
                                    <div class="w-1.5 h-1.5 rounded-full" :class="note.color && note.color !== 'transparent' ? `bg-${note.color}-400` : 'bg-amber-400'"></div>
                                    笔记
                                </div>
                                
                                <div class="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button class="p-1 hover:bg-white rounded text-slate-400 hover:text-primary-600 transition-colors shadow-sm" @click.stop="handleEditNote(note)">
                                        <el-icon :size="12"><Edit /></el-icon>
                                    </button>
                                    <button class="p-1 hover:bg-white rounded text-slate-400 hover:text-red-500 transition-colors shadow-sm" @click.stop="handleDeleteNote(note.id)">
                                        <el-icon :size="12"><Delete /></el-icon>
                                    </button>
                                </div>
                            </div>

                            <!-- Content -->
                            <div class="p-3">
                                <div v-if="note.quote" class="text-xs text-slate-400 italic mb-2 line-clamp-2 pl-2 border-l-2" :class="note.sourceType === 'ai' ? 'border-purple-200' : 'border-slate-200'">
                                    "{{ note.quote }}"
                                </div>
                                <div v-if="editingNoteId === note.id" class="mt-2" @click.stop>
                                    <el-input 
                                        v-model="editingContent" 
                                        type="textarea" 
                                        :rows="3" 
                                        resize="none"
                                        class="mb-2 !text-xs"
                                        placeholder="输入笔记内容..."
                                        ref="editInputRef"
                                    />
                                    <div class="flex justify-end gap-2 mt-2">
                                        <el-button size="small" text bg @click.stop="cancelEditing">取消</el-button>
                                        <el-button size="small" type="primary" round @click.stop="saveEditing(note)">保存修改</el-button>
                                    </div>
                                </div>
                                <template v-else>
                                    <!-- Content with auto-collapse -->
                                    <div class="relative group/content transition-all duration-300"
                                         :class="{'max-h-[120px] overflow-hidden': shouldCollapse(note) && !isAccordionMode, 'max-h-[60px] overflow-hidden': shouldCollapse(note) && isAccordionMode}">
                                        <div class="text-sm text-slate-700 font-medium leading-relaxed whitespace-pre-wrap" v-html="formatNoteContent(note.content)"></div>
                                        
                                        <!-- Gradient Mask -->
                                        <div v-if="shouldCollapse(note)" 
                                             class="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-white to-transparent pointer-events-none">
                                        </div>
                                    </div>

                                    <!-- Expand/Collapse Action -->
                                    <div v-if="shouldCollapse(note) || expandedNoteIds.includes(note.id)" class="mt-2 flex justify-center">
                                        <button @click.stop="toggleExpand(note.id)" class="text-[10px] font-bold text-slate-400 hover:text-primary-600 flex items-center gap-1 transition-colors bg-slate-50 hover:bg-primary-50 px-2 py-0.5 rounded-full">
                                            {{ expandedNoteIds.includes(note.id) ? '收起' : '展开' }} <el-icon><ArrowDown v-if="!expandedNoteIds.includes(note.id)" /><ArrowUp v-else /></el-icon>
                                        </button>
                                    </div>

                                    <div class="mt-3 pt-2 border-t border-slate-50 flex items-center justify-between text-[10px] text-slate-300">
                                        <div class="flex items-center gap-1">
                                            <el-icon><Timer /></el-icon>
                                            <span>{{ dayjs(note.createdAt).fromNow() }}</span>
                                        </div>
                                    </div>
                                </template>
                            </div>
                         </div>
                    </div>
                </transition-group>
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
      <el-drawer v-model="showMobileNotes" title="课程笔记" size="80%" direction="rtl">
        <div class="flex flex-col h-full">
            <div class="p-4 border-b border-slate-100">
                <el-input v-model="noteSearchQuery" placeholder="搜索笔记..." :prefix-icon="Search" clearable />
            </div>
            <div class="flex-1 overflow-auto p-4 space-y-4">
                <div v-if="displayedNotes.length === 0" class="text-center text-slate-400 py-8">
                    暂无笔记
                </div>
                <div v-for="note in displayedNotes" :key="'mobile-'+note.id" 
                     class="bg-white rounded-xl shadow-sm border border-slate-200 p-4"
                     :class="{'!border-purple-200 !bg-purple-50/30': note.sourceType === 'ai'}"
                     @click="scrollToHighlight(note.highlightId); showMobileNotes = false">
                    <div class="flex justify-between items-start mb-2">
                        <div v-if="note.sourceType === 'ai'" class="text-xs font-bold text-purple-600 bg-purple-50 px-2 py-0.5 rounded border border-purple-100">AI 助手</div>
                        <div v-else class="text-xs font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded border border-amber-100">笔记</div>
                        <div class="flex gap-2">
                             <button class="p-1 text-slate-400 hover:text-primary-600" @click.stop="handleEditNote(note)"><el-icon><Edit /></el-icon></button>
                             <button class="p-1 text-slate-400 hover:text-red-500" @click.stop="handleDeleteNote(note.id)"><el-icon><Delete /></el-icon></button>
                        </div>
                    </div>
                    <div v-if="note.quote" class="text-xs text-slate-500 italic mb-2 border-l-2 border-slate-200 pl-2">"{{ note.quote }}"</div>
                    <div class="text-sm text-slate-700 font-medium whitespace-pre-wrap" v-html="formatNoteContent(note.content)"></div>
                    <div class="mt-2 text-xs text-slate-400 flex items-center gap-1">
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
        class="glass-dialog"
        align-center
        append-to-body
    >
        <div class="flex flex-col gap-4">
             <div class="p-3 bg-primary-50 rounded-xl border border-primary-100/50">
                <div class="text-xs text-primary-500 font-bold mb-1">测试章节</div>
                <div class="text-sm font-medium text-slate-700 truncate">{{ quizConfig.nodeName }}</div>
             </div>
             
             <div class="space-y-3">
                 <div class="text-sm font-bold text-slate-600">难度选择</div>
                 <div class="grid grid-cols-3 gap-2">
                     <button v-for="diff in ['easy', 'medium', 'hard']" :key="diff"
                         class="px-3 py-2 rounded-lg text-sm border transition-all"
                         :class="quizConfig.difficulty === diff ? 'bg-primary-600 text-white border-primary-600 shadow-md shadow-primary-500/30' : 'bg-white text-slate-600 border-slate-200 hover:border-primary-300'"
                         @click="quizConfig.difficulty = diff"
                     >
                        {{ diff === 'easy' ? '简单' : (diff === 'medium' ? '中等' : '困难') }}
                     </button>
                 </div>
             </div>

             <div class="space-y-3">
                 <div class="text-sm font-bold text-slate-600">出题风格</div>
                 <div class="grid grid-cols-3 gap-2">
                     <button v-for="style in ['standard', 'practical', 'creative']" :key="style"
                         class="px-3 py-2 rounded-lg text-sm border transition-all"
                         :class="quizConfig.style === style ? 'bg-amber-500 text-white border-amber-500 shadow-md shadow-amber-500/30' : 'bg-white text-slate-600 border-slate-200 hover:border-amber-300'"
                         @click="quizConfig.style = style"
                     >
                        {{ style === 'standard' ? '标准' : (style === 'practical' ? '实战' : '创意') }}
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
      class="glass-dialog"
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
        <div v-for="(q, idx) in quizQuestions" :key="idx" class="mb-8 last:mb-0">
          <p class="font-bold text-slate-800 mb-3 text-lg">{{ idx + 1 }}. {{ q.question }}</p>
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
              <span class="text-slate-700 font-medium">{{ opt }}</span>
            </div>
          </div>
          <div v-if="quizSubmitted" class="mt-3 text-sm bg-slate-50 p-3 rounded-lg text-slate-600">
             <span class="font-bold text-slate-800">解析：</span> {{ q.explanation }}
          </div>
        </div>
      </div>
      <template #footer>
        <div class="flex justify-end gap-3" v-if="!generatingQuiz">
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
        width="600px"
        class="glass-dialog"
        align-center
        append-to-body
    >
        <div v-if="selectedNote" class="flex flex-col gap-4">
            <!-- Quote Context -->
            <div v-if="selectedNote.quote" class="p-4 bg-slate-50 rounded-xl border-l-4 border-primary-400 italic text-slate-600 text-sm">
                "{{ selectedNote.quote }}"
            </div>
            
            <!-- Main Content -->
            <div class="prose prose-slate max-w-none text-slate-800 leading-relaxed" v-html="formatNoteContent(selectedNote.content)"></div>
            
            <!-- Metadata -->
            <div class="flex items-center justify-between pt-4 border-t border-slate-100 text-xs text-slate-400">
                <div class="flex items-center gap-2">
                    <el-icon><Timer /></el-icon>
                    创建于 {{ dayjs(selectedNote.createdAt).format('YYYY-MM-DD HH:mm') }}
                </div>
                <div v-if="selectedNote.sourceType === 'ai'" class="flex items-center gap-1 text-primary-600 font-bold bg-primary-50 px-2 py-1 rounded">
                    <el-icon><MagicStick /></el-icon> AI 助手生成
                </div>
            </div>
        </div>
        <template #footer>
            <div class="flex justify-end gap-2">
                <el-button @click="handleEditNote(selectedNote); noteDetailVisible = false">编辑</el-button>
                <el-button type="primary" @click="noteDetailVisible = false">关闭</el-button>
            </div>
        </template>
    </el-dialog>

    <!-- Quiz Suggestion Toast -->
    <transition name="slide-up">
        <div v-if="showQuizSuggestion && suggestedQuizNode" class="fixed bottom-8 right-8 z-50 w-80 bg-white/90 backdrop-blur-xl p-4 rounded-2xl shadow-2xl border border-primary-100 flex flex-col gap-3 animate-bounce-in">
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
    <transition name="back-to-top">
        <button v-if="showBackToTop" 
                class="back-to-top p-3 bg-white/80 backdrop-blur border border-slate-200 rounded-full shadow-lg text-slate-500 hover:text-primary-600 hover:border-primary-200 hover:shadow-primary-100 transition-all active:scale-95"
                @click="scrollToTop">
            <el-icon :size="20"><ArrowUp /></el-icon>
        </button>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useCourseStore } from '../stores/course'
import MarkdownIt from 'markdown-it'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import hljs from 'highlight.js'
import DOMPurify from 'dompurify'
import { Minus, Plus, Download, MagicStick, VideoPlay, Notebook, Check, Close, Edit, Delete, ChatLineSquare, Search, Timer, CircleCheckFilled, FullScreen, Microphone, Setting, Connection, Trophy, ArrowDown, ArrowUp, Loading } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const courseStore = useCourseStore()
const fontSize = ref(16)
const fontFamily = ref('sans')
const lineHeight = ref(1.75)
const selectionMenu = ref({ visible: false, x: 0, y: 0, text: '', range: null as Range | null })
const noteSearchQuery = ref('')
const globalSearchQuery = ref('')
const globalSearchResults = ref<any[]>([])
const activeNoteFilter = ref('all')
const showMobileNotes = ref(false)
const isSpeaking = ref(false)
const currentSpeakingContent = ref('')
const isAccordionMode = ref(true) // Default to true or false? Let's say false initially or true for better UX
const expandedNoteIds = ref<string[]>([])
const scrollProgress = ref(0)
const lightboxVisible = ref(false)
const lightboxImage = ref('')

// TTS Logic - Merged
const toggleTTS = (content?: string) => {
    // If called without content (e.g. from Toolbar button), read full content
    if (!content || typeof content !== 'string') {
        if (isSpeaking.value) {
            window.speechSynthesis.cancel()
            isSpeaking.value = false
            currentSpeakingContent.value = ''
            return
        }
        
        // Generate text content from flatNodes
        const text = flatNodes.value.map(n => {
            const c = n.node_content || ''
            // Simple markdown stripping
            const stripped = c
                .replace(/[#*`>]/g, '') 
                .replace(/\[.*?\]\(.*?\)/g, '') 
                .replace(/!\[.*?\]\(.*?\)/g, '')
            return `${n.node_name}。\n${stripped}`
        }).join('\n\n')
        
        // Start full reading (Node by Node for better control)
        speakNodesRecursively(0)
        isSpeaking.value = true
        currentSpeakingContent.value = 'FULL_BOOK'
        return
    }

    // If called with content (Chapter button)
    if (isSpeaking.value && currentSpeakingContent.value === content) {
        window.speechSynthesis.cancel()
        isSpeaking.value = false
        currentSpeakingContent.value = ''
    } else {
        window.speechSynthesis.cancel()
        const utterance = new SpeechSynthesisUtterance(content)
        utterance.lang = 'zh-CN'
        utterance.rate = 1.0
        utterance.onend = () => {
            isSpeaking.value = false
            currentSpeakingContent.value = ''
        }
        window.speechSynthesis.speak(utterance)
        isSpeaking.value = true
        currentSpeakingContent.value = content
    }
}

const speakNodesRecursively = (index: number) => {
    if (index >= flatNodes.value.length || !isSpeaking.value) {
        isSpeaking.value = false
        return
    }
    
    const node = flatNodes.value[index]
    const content = node.node_content.replace(/[#*`>]/g, '').replace(/\[.*?\]\(.*?\)/g, '')
    const text = `${node.node_name}。\n${content}`
    
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'zh-CN'
    
    utterance.onstart = () => {
        courseStore.scrollToNode(node.node_id)
        // Add visual highlight class
        const el = document.getElementById(`node-${node.node_id}`)
        if (el) el.classList.add('ring-4', 'ring-primary-200', 'bg-primary-50/30')
    }
    
    utterance.onend = () => {
        const el = document.getElementById(`node-${node.node_id}`)
        if (el) el.classList.remove('ring-4', 'ring-primary-200', 'bg-primary-50/30')
        if (isSpeaking.value) speakNodesRecursively(index + 1)
    }
    
    utterance.onerror = () => {
        isSpeaking.value = false
    }
    
    window.speechSynthesis.speak(utterance)
}

const toggleFocusMode = () => {
    courseStore.isFocusMode = !courseStore.isFocusMode
}

// Custom Math Plugin using installed katex
const customMathPlugin = (md: MarkdownIt) => {
    // Inline math $...$
    md.inline.ruler.before('escape', 'math_inline', (state, silent) => {
        if (state.src[state.pos] !== '$') return false;
        
        // Block math check (double dollar)
        if (state.src.slice(state.pos, state.pos + 2) === '$$') return false; // Handled by block rule
        
        const start = state.pos + 1;
        let match = start;
        let pos = start;
        
        while ((match = state.src.indexOf('$', pos)) !== -1) {
            // Check for escaped dollar
            if (state.src[match - 1] === '\\') {
                pos = match + 1;
                continue;
            }
            break;
        }
        
        if (match === -1) return false;
        if (match - start === 0) return false;
        
        if (!silent) {
            const token = state.push('math_inline', 'math', 0);
            token.markup = '$';
            token.content = state.src.slice(start, match);
        }
        
        state.pos = match + 1;
        return true;
    });

    // Block math $$...$$
    md.block.ruler.after('blockquote', 'math_block', (state, startLine, endLine, silent) => {
        const startPos = state.bMarks[startLine] + state.tShift[startLine];
        const max = state.eMarks[startLine];
        
        if (state.src.slice(startPos, startPos + 2) !== '$$') return false;
        
        let pos = startPos + 2;
        let content = '';
        let found = false;
        let nextLine = startLine;
        
        // Single line case $$...$$
        if (state.src.indexOf('$$', pos) !== -1) {
             const end = state.src.indexOf('$$', pos);
             content = state.src.slice(pos, end);
             nextLine = startLine + 1;
             found = true;
        } else {
            // Multi line case
            content = state.src.slice(pos);
            nextLine++;
            while (nextLine < endLine) {
                const lineStart = state.bMarks[nextLine] + state.tShift[nextLine];
                const lineEnd = state.eMarks[nextLine];
                const lineText = state.src.slice(lineStart, lineEnd);
                
                if (lineText.trim().endsWith('$$')) {
                    content += '\n' + lineText.trim().slice(0, -2);
                    found = true;
                    nextLine++;
                    break;
                }
                content += '\n' + lineText;
                nextLine++;
            }
        }
        
        if (!found) return false;
        if (silent) return true;
        
        const token = state.push('math_block', 'math', 0);
        token.block = true;
        token.content = content;
        token.map = [startLine, nextLine];
        token.markup = '$$';
        
        state.line = nextLine;
        return true;
    });

    // Renderers
    md.renderer.rules.math_inline = (tokens, idx) => {
        try {
            return katex.renderToString(tokens[idx].content, { throwOnError: false, displayMode: false });
        } catch (e) {
            return tokens[idx].content;
        }
    };
    
    md.renderer.rules.math_block = (tokens, idx) => {
        try {
            return '<div class="katex-display">' + katex.renderToString(tokens[idx].content, { throwOnError: false, displayMode: true }) + '</div>';
        } catch (e) {
            return '<pre>' + tokens[idx].content + '</pre>';
        }
    };
};

// Markdown Configuration
const md = new MarkdownIt({
    html: true,
    linkify: true,
    typographer: true,
    highlight: function (str, lang) {
        if (lang && hljs.getLanguage(lang)) {
            try {
                return hljs.highlight(str, { language: lang }).value;
            } catch (__) {}
        }
        return ''; // use external default escaping
    }
}).use(customMathPlugin);

// Custom Fence Renderer for Code Blocks
md.renderer.rules.fence = function (tokens, idx, options, _env, _self) {
  const token = tokens[idx];
  if (!token) return '';
  
  const info = token.info ? md.utils.unescapeAll(token.info).trim() : '';
  let langName = '';
  let highlighted = '';

  if (info) {
    langName = info.split(/\s+/g)[0] || '';
  }

  if (options.highlight) {
    highlighted = options.highlight(token.content, langName, '') || md.utils.escapeHtml(token.content);
  } else {
    highlighted = md.utils.escapeHtml(token.content);
  }

  const validLang = langName || 'plaintext';
  
  return `<div class="relative group my-4 rounded-xl overflow-hidden shadow-sm border border-slate-200/60 bg-[#1e293b]">
      <div class="flex items-center justify-between px-4 py-2 bg-slate-800/50 border-b border-white/5">
          <div class="flex gap-1.5">
              <div class="w-3 h-3 rounded-full bg-red-400/80"></div>
              <div class="w-3 h-3 rounded-full bg-amber-400/80"></div>
              <div class="w-3 h-3 rounded-full bg-emerald-400/80"></div>
          </div>
          <span class="text-xs text-slate-400 font-mono">${validLang}</span>
      </div>
      <button class="copy-btn absolute top-2 right-2 p-1.5 text-slate-400 hover:text-white rounded-lg opacity-0 group-hover:opacity-100 transition-opacity bg-white/10 hover:bg-white/20" onclick="navigator.clipboard.writeText(decodeURIComponent('${encodeURIComponent(token.content)}'))">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
      </button>
      <pre class="!m-0 !p-4 !bg-transparent overflow-x-auto text-sm font-mono leading-relaxed"><code class="hljs ${validLang}">${highlighted}</code></pre>
    </div>`;
};


// Watch for scroll requests from sidebar
watch(() => courseStore.scrollToNodeId, (nodeId) => {
    if (!nodeId) return
    
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
const isManualScrolling = ref(false)
const activeNoteId = ref<string | null>(null)
const editingNoteId = ref<string | null>(null)
const editingContent = ref('')
let observer: IntersectionObserver | null = null

const noteDetailVisible = ref(false)
const selectedNote = ref<any>(null)

// Quiz Suggestion State
const readChapters = ref<Set<string>>(new Set())
const showQuizSuggestion = ref(false)
const suggestedQuizNode = ref<any>(null)

// Check if content is long enough to collapse
const isLongContent = (content: string) => {
    // Heuristic: length > 80 or has more than 2 newlines
    return content.length > 80 || content.split('\n').length > 2
}

const openNoteDetail = (note: any) => {
    selectedNote.value = note
    noteDetailVisible.value = true
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

// Debounce logic
let searchTimeout: any = null
const handleSearchInput = (val: string) => {
    isSearching.value = true
    if (searchTimeout) clearTimeout(searchTimeout)
    searchTimeout = setTimeout(() => {
        debouncedSearchQuery.value = val
        isSearching.value = false
    }, 300)
}

watch(noteSearchQuery, (val) => {
    handleSearchInput(val)
})

const handleGlobalSearch = (val: string) => {
    if (!val || !val.trim()) {
        globalSearchResults.value = []
        return
    }
    
    const query = val.toLowerCase().trim()
    const results: any[] = []
    
    // Search in flatNodes
    flatNodes.value.forEach(node => {
        // Skip root
        if (node.node_level === 1) return
        
        const titleMatch = node.node_name.toLowerCase().includes(query)
        const contentMatch = node.node_content.toLowerCase().includes(query)
        
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
    // Implement scroll to search result
    const el = document.getElementById('node-' + nodeId)
    if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        // Highlight logic
        courseStore.setCurrentNodeSilent(flatNodes.value.find(n => n.node_id === nodeId))
        globalSearchQuery.value = ''
        globalSearchResults.value = []
    }
}


// Tab Animation Style
const activeTabStyle = computed(() => {
    const tabs = ['all', 'ai', 'user', 'wrong']
    const idx = tabs.indexOf(activeNoteFilter.value)
    if (idx === -1) return {}
    return {
        left: `${idx * 25}%`,
        width: '25%'
    }
})

const visibleNotes = computed(() => {
    const nodeIds = new Set(flatNodes.value.map(n => n.node_id))
    let notes = courseStore.notes.filter(n => nodeIds.has(n.nodeId))
    
    // Filter by Type
    if (activeNoteFilter.value !== 'all') {
        if (activeNoteFilter.value === 'ai') {
            notes = notes.filter(n => n.sourceType === 'ai')
        } else if (activeNoteFilter.value === 'user') {
            notes = notes.filter(n => n.sourceType === 'user')
        } else if (activeNoteFilter.value === 'wrong') {
            notes = notes.filter(n => n.content.includes('**错题记录**') || n.content.includes('#错题'))
        }
    }

    if (debouncedSearchQuery.value) {
        const query = debouncedSearchQuery.value.toLowerCase()
        notes = notes.filter(n => n.content.toLowerCase().includes(query) || (n.quote && n.quote.toLowerCase().includes(query)))
    }
    
    return notes
})

const quotedNotes = computed(() => visibleNotes.value.filter(n => n.quote && n.quote.trim().length > 0))
const displayedNotes = computed(() => visibleNotes.value.filter(n => n.sourceType !== 'format'))
const displayedQuotedNotes = computed(() => quotedNotes.value.filter(n => n.sourceType !== 'format'))
const unquotedNotes = computed(() => visibleNotes.value.filter(n => (!n.quote || n.quote.trim().length === 0) && n.sourceType !== 'format'))

watch(() => [visibleNotes.value.length, flatNodes.value], () => {
    nextTick(() => {
        reapplyHighlights()
        debouncedUpdatePositions()
        setupChapterObserver()
    })
}, { deep: true })

watch(fontSize, () => {
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
        const id = el.id.split('-part-')[0]
        
        if (!activeIds.has(id)) {
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
                if (!/\s/.test(text[i])) {
                    mapIndices.push({
                        index: fullTextStripped.length,
                        node: currentNode,
                        offset: i
                    })
                    fullTextStripped += text[i]
                }
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
                     
                     const startNode = startMap.node
                     const startOffset = startMap.offset
                     const endNode = endMap.node
                     const endOffset = endMap.offset + 1 // Exclusive end offset
                     
                     try {
                         // Create Range
                         const startNodeIdx = textNodes.findIndex(t => t.node === startNode)
                         const endNodeIdx = textNodes.findIndex(t => t.node === endNode)
                         
                         if (startNode === endNode) {
                             const range = document.createRange()
                             range.setStart(startNode, startOffset)
                             range.setEnd(endNode, endOffset)
                             wrapRange(range, note.highlightId, note.id)
                         } else {
                             // Start Node Part
                             const range1 = document.createRange()
                             range1.setStart(startNode, startOffset)
                             range1.setEnd(startNode, textNodes[startNodeIdx].text.length)
                             wrapRange(range1, note.highlightId + '-part-start', note.id)
                             
                             // Middle Nodes
                             for (let i = startNodeIdx + 1; i < endNodeIdx; i++) {
                                 const rangeM = document.createRange()
                                 rangeM.selectNodeContents(textNodes[i].node)
                                 // Only wrap if it contains non-whitespace
                                 if (textNodes[i].text.trim().length > 0) {
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

const setHovered = (noteId: string | null) => {
    // 1. Clean up old highlights
    document.querySelectorAll('.pulse-highlight').forEach(el => el.classList.remove('pulse-highlight'))
    
    // 2. Add new highlights
    if (noteId) {
        const note = courseStore.notes.find(n => n.id === noteId)
        if (note && note.highlightId) {
            const els = document.querySelectorAll(`[id^="${note.highlightId}"]`)
            els.forEach(el => el.classList.add('pulse-highlight'))
        }
    }
}

const wrapRange = (range: Range, id: string, noteId: string) => {
    try {
        // Skip empty ranges
        if (range.toString().length === 0) return
        
        const note = courseStore.notes.find(n => n.id === noteId)
        const span = document.createElement('span')
        span.id = id
        
        // Define color map for safe class usage (prevents Tailwind purging)
        const colorMap: Record<string, string> = {
            yellow: 'bg-yellow-200/50 hover:bg-yellow-300/50',
            green: 'bg-green-200/50 hover:bg-green-300/50',
            blue: 'bg-blue-200/50 hover:bg-blue-300/50',
            pink: 'bg-pink-200/50 hover:bg-pink-300/50',
            orange: 'bg-orange-200/50 hover:bg-orange-300/50',
            purple: 'bg-purple-200/50 hover:bg-purple-300/50',
        }
        
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
                const colorClass = colorMap[note.color] || `bg-${note.color}-200/50 hover:bg-${note.color}-300/50`
                className += colorClass + ' '
            }
        } else if (note?.sourceType === 'ai') {
            // AI Teacher Style
            className += 'bg-purple-200/50 border-b-2 border-purple-400 hover:bg-purple-300/50 '
        } else {
            // Default Note Style
            className += 'bg-amber-200/50 border-b-2 border-amber-400 hover:bg-amber-300/50 '
        }
        
        span.className = className
        
        span.onclick = (e) => {
            e.stopPropagation()
            // Only scroll to note if it has content (regular note)
            if (note && note.sourceType !== 'format') {
                scrollToNote(noteId)
            }
        }
        // Add hover effects
        span.onmouseenter = () => setHovered(noteId)
        span.onmouseleave = () => setHovered(null)
        
        range.surroundContents(span)
    } catch (e) {
        // Ignore
    }
}

const scrollToNote = (noteId: string) => {
    const note = courseStore.notes.find(n => n.id === noteId)
    if (note) {
        activeNoteId.value = note.id
        // Scroll note into view if needed
        const noteEl = document.getElementById(note.id)
        if (noteEl) {
            noteEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
            // Add flash effect to card
            noteEl.classList.add('flash-card', 'ring-4', 'ring-primary-200')
            setTimeout(() => {
                noteEl.classList.remove('flash-card', 'ring-4', 'ring-primary-200')
            }, 1000)
        }

        // Also flash the text highlight in content area
        if (note.highlightId) {
            // IDs can be multiple (split parts), find all starting with highlightId
            const highlights = document.querySelectorAll(`[id^="${note.highlightId}"]`)
            highlights.forEach(el => {
                el.classList.add('flash-highlight')
                // Scroll the first highlight into view if it's the target
                // Actually, let's prefer scrolling to the highlight if possible?
                // The prompt says "finger pointing", so scrolling to text is better.
                if (el.id === note.highlightId || el.id === `${note.highlightId}-part-start`) {
                     el.scrollIntoView({ behavior: 'smooth', block: 'center' })
                }
            })
            
            setTimeout(() => {
                highlights.forEach(el => el.classList.remove('flash-highlight'))
            }, 1500)
        }
    }
}

const updateNotePositions = () => {
    const notes = [...displayedQuotedNotes.value]
    const container = document.getElementById('notes-container')
    if (!container) return

    // --- Phase 1: Batch Read (DOM Measurements) ---
    // Read container metrics once
    const containerRect = container.getBoundingClientRect()
    const containerTop = containerRect.top
    
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
            const rect = el.getBoundingClientRect()
            const relativeTop = rect.top - containerTop
            // Store the "natural" top position for this note
            measurements.set(note.id, relativeTop + (isFallback ? 10 : 0))
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
    
    // Get Global Section Bottom (Read once)
    const globalSection = document.getElementById('global-notes-section')
    if (globalSection) {
        lastBottom = globalSection.offsetTop + globalSection.offsetHeight
    }

    const GAP = 16 

    positionedNotes.forEach(item => {
        // If natural position is above the valid floor (lastBottom + GAP), push it down
        if (item.top < lastBottom + GAP) {
            item.top = lastBottom + GAP
        }
        
        // Update floor for next item
        lastBottom = item.top + item.height
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

onMounted(() => {
    window.addEventListener('keydown', handleGlobalKeydown)
    
    // Initialize ResizeObserver
    resizeObserver = new ResizeObserver((entries) => {
        // Debounce update
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

watch(editingNoteId, () => {
    nextTick(() => {
        updateNotePositions()
    })
})

// Add image lazy loading support
md.renderer.rules.image = function (tokens, idx, options, env, self) {
  const token = tokens[idx];
  token.attrSet('loading', 'lazy'); // Add lazy loading
  token.attrSet('class', 'rounded-xl shadow-sm border border-slate-100 my-4 max-w-full h-auto'); // Default styling
  return self.renderToken(tokens, idx, options);
};

// Memoization cache
const markdownCache = new Map<string, string>()

const renderMarkdown = (content: string) => {
    if (!content) return ''
    
    // Check cache
    if (markdownCache.has(content)) {
        return markdownCache.get(content) || ''
    }
    
    // Pre-process LaTeX formula fixes
    let fixedContent = content
        // Fix \[ ... \] block formulas to $$ ... $$
        .replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$')
        // Fix \( ... \) inline formulas to $ ... $
        .replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$')
        // Fix spaces in inline math $ ... $ -> $...$ to ensure markdown-it-katex parses it
        .replace(/(\$\$[\s\S]*?\$\$)|(\$\s+(.+?)\s+\$)/g, (match, block, inline, content) => {
            if (block) return block
            if (inline) return `$${content}$`
            return match
        })
        // Fix non-standard prime notation
        .replace(/(\w+)'\s+\((.+?)\)/g, "$1'($2)")
        .replace(/(\w+)\s+'/g, "$1'")
        // Fix trailing dollar sign issue
        .replace(/(\$\$[\s\S]*?)[^$]\$$/gm, "$1$$")
    
    try {
        const rawHtml = md.render(fixedContent)
        // Allow class and style attributes for styling
        const sanitized = DOMPurify.sanitize(rawHtml, {
            ADD_TAGS: ['span'],
            ADD_ATTR: ['class', 'style', 'loading']
        })
        
        // Cache result (limit cache size?)
        if (markdownCache.size > 500) {
            const firstKey = markdownCache.keys().next().value
            if (firstKey) markdownCache.delete(firstKey)
        }
        markdownCache.set(content, sanitized)
        
        return sanitized
    } catch (e) {
        console.error('Markdown render error:', e)
        return content
    }
}

const handleExport = (command: string) => {
    if (command === 'json') {
        exportJson()
    } else if (command === 'markdown') {
        downloadMarkdown()
    }
}

// exportContent was duplicate or conflicting.
// The template uses @click="exportContent" on the button.
// And handleExport on the dropdown.
// Let's keep exportContent as an alias to downloadMarkdown for the button.

const exportContent = () => {
    downloadMarkdown()
}

const exportJson = () => {
    if (visibleNotes.value.length === 0) {
        ElMessage.warning('当前没有可导出的笔记')
        return
    }
    
    const data = JSON.stringify(visibleNotes.value, null, 2)
    const blob = new Blob([data], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    
    const a = document.createElement('a')
    a.href = url
    a.download = `notes_export_${dayjs().format('YYYYMMDD_HHmmss')}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    
    ElMessage.success('笔记导出成功')
}

const downloadMarkdown = () => {
    if (visibleNotes.value.length === 0) {
        ElMessage.warning('当前没有可导出的笔记')
        return
    }
    
    let md = `# ${courseStore.courseList.find(c => c.course_id === courseStore.currentCourseId)?.course_name || 'My Notes'}\n\n`
    
    // Group notes by Node (Chapter) to avoid repeated headers
    const groupedNotes = new Map<string, any[]>()
    
    // Maintain order from visibleNotes
    visibleNotes.value.forEach(note => {
        const nodeId = note.nodeId
        if (!groupedNotes.has(nodeId)) {
            groupedNotes.set(nodeId, [])
        }
        groupedNotes.get(nodeId)?.push(note)
    })
    
    // Iterate groups
    groupedNotes.forEach((notes, nodeId) => {
        const node = courseStore.nodes.find(n => n.node_id === nodeId)
        md += `## ${node?.node_name || '未知章节'}\n\n`
        
        notes.forEach(note => {
             // Skip pure formatting notes for better readability in export
             if (note.sourceType === 'format') return 

             if (note.quote) {
                 md += `> ${note.quote}\n\n`
             }
             md += `${note.content}\n\n`
            
            const typeLabel = note.sourceType === 'ai' ? 'AI 助手' : '笔记'
            md += `> — *${typeLabel} · ${dayjs(note.createdAt).format('YYYY-MM-DD HH:mm')}*\n\n---\n\n`
        })
    })
    
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `notes_export_${dayjs().format('YYYYMMDD_HHmmss')}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('Markdown 导出成功')
}

const formatNoteContent = (content: string) => {
    if (!content) return ''
    
    // 1. Tag Highlight (Source level replacement to preserve through markdown render)
    // Matches #tag at start or after space
    let processed = content.replace(/(?<=^|\s)(#[\w\u4e00-\u9fa5]+)/g, '<span class="text-primary-600 font-bold">$1</span>')
    
    // 2. Search Highlight (Source level)
    if (noteSearchQuery.value && noteSearchQuery.value.trim()) {
        const query = noteSearchQuery.value.trim()
        const safeQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
        const regex = new RegExp(`(${safeQuery})`, 'gi')
        processed = processed.replace(regex, '<span class="bg-yellow-200 text-slate-900 rounded px-0.5 box-decoration-clone">$1</span>')
    }
    
    // 3. Render Markdown & LaTeX
    return renderMarkdown(processed)
}

// Selection Handling
const handleDoubleClick = () => {
    courseStore.isFocusMode = !courseStore.isFocusMode
}

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
        
        // Boundary Detection
        const MENU_WIDTH = 280
        const MENU_HEIGHT = 80
        const VIEWPORT_WIDTH = window.innerWidth
        
        let x = rect.left + (rect.width / 2)
        let y = rect.top - 60 // Default top
        
        // Prevent overflow right
        if (x + (MENU_WIDTH / 2) > VIEWPORT_WIDTH - 20) {
            x = VIEWPORT_WIDTH - (MENU_WIDTH / 2) - 20
        }
        // Prevent overflow left
        if (x - (MENU_WIDTH / 2) < 20) {
            x = (MENU_WIDTH / 2) + 20
        }
        
        // Prevent overflow top (flip to bottom if not enough space)
        if (y - MENU_HEIGHT < 60) { // 60px for toolbar
            y = rect.bottom + 20
        }
        
        selectionMenu.value = {
            visible: true,
            x: x, 
            y: y, 
            text: selection.toString(),
            range: range
        }
    } else {
        selectionMenu.value.visible = false
    }
}

const handleExplain = async () => {
    if (!selectionMenu.value.text) return
    
    const selection = selectionMenu.value.text
    const prompt = `请对以下选中内容进行深度解析：\n> "${selection}"\n\n请从以下几个维度进行分析：\n1. 🔍 **核心概念**：解释其中的关键术语。\n2. 💡 **原理阐述**：用通俗易懂的语言说明其背后的逻辑。\n3. 🌟 **举例说明**：给出一个具体的应用场景或案例。\n4. 🔗 **关联思考**：这段内容与课程其他部分的联系。`
    
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
    
    // Open Chat Panel if possible? (Optional, maybe just a toast)
    ElMessage.success('正在进行深度解析，请查看右侧助手')
    
    await courseStore.askQuestion(prompt, selection, nodeId)
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
        const span = document.createElement('span')
        span.id = highlightId
        span.className = 'highlight-marker bg-amber-200/50 border-b-2 border-amber-400 cursor-pointer transition-colors hover:bg-amber-300/50'
        span.onclick = (e) => {
            e.stopPropagation()
            scrollToHighlight(highlightId)
        }
        
        if (selectionMenu.value.range) {
            try {
                selectionMenu.value.range.surroundContents(span)
            } catch (e) {
                ElMessage.error('无法在此处创建笔记（跨段落选择暂不支持）')
                return
            }
        }
        
        // Find Node ID
        const nodeEl = span.closest('[id^="node-"]')
        const nodeId = nodeEl ? nodeEl.id.replace('node-', '') : ''
        
        if (nodeId) {
            courseStore.createNote({
                id: 'note-' + Math.random().toString(36).substr(2, 9),
                nodeId,
                highlightId,
                quote: selectionMenu.value.text,
                content: value,
                color: 'blue',
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

const shouldCollapse = (note: any) => {
    // If it's already expanded, we show the toggle button if it's long or we are in accordion mode
    // But if expanded, we don't collapse. Wait, the v-if is for the BUTTON.
    // The content truncation logic should be in the template or a computed property for display content.
    // Actually, the template uses `formatNoteContent(note.content)`, which renders FULL content.
    // We need to truncate the content display if not expanded.
    
    // Correction: The v-if="shouldCollapse(note)" controls the "Expand/Collapse" button visibility.
    // So if content is short and not in accordion mode, no button.
    if (isAccordionMode.value) return true
    return isLongContent(note.content)
}

// Override formatNoteContent to support truncation? 
// No, formatNoteContent returns HTML string. Truncating HTML is risky.
// Better to use CSS line-clamp for collapsed state.

const noteContentStyle = (note: any) => {
    if (expandedNoteIds.value.includes(note.id)) return {}
    if (isAccordionMode.value || isLongContent(note.content)) {
        return {
            display: '-webkit-box',
            '-webkit-line-clamp': '3',
            '-webkit-box-orient': 'vertical',
            overflow: 'hidden'
        }
    }
    return {}
}

const toggleExpand = (noteId: string) => {
    const index = expandedNoteIds.value.indexOf(noteId)
    if (index === -1) {
        if (isAccordionMode.value) {
            expandedNoteIds.value = [noteId]
        } else {
            expandedNoteIds.value.push(noteId)
        }
    } else {
        expandedNoteIds.value.splice(index, 1)
    }
    // Update positions after expand/collapse
    nextTick(() => updateNotePositions())
}

const handleEditNote = (note: any) => {
    if (showMobileNotes.value) {
        ElMessageBox.prompt('编辑笔记', '修改笔记', {
            inputValue: note.content,
            confirmButtonText: '保存',
            cancelButtonText: '取消',
            inputType: 'textarea'
        }).then((data: any) => {
            const { value } = data
            courseStore.updateNote(note.id, value)
        }).catch(() => {})
    } else {
        editingNoteId.value = note.id
        editingContent.value = note.content
    }
}

const cancelEditing = () => {
    editingNoteId.value = null
    editingContent.value = ''
}

const saveEditing = async (note: any) => {
    if (!editingContent.value.trim()) {
        ElMessage.warning('笔记内容不能为空')
        return
    }
    await courseStore.updateNote(note.id, editingContent.value)
    editingNoteId.value = null
    editingContent.value = ''
    ElMessage.success('笔记已更新')
}

const addGlobalNote = () => {
    ElMessageBox.prompt('请输入笔记内容', '添加全局笔记', {
        confirmButtonText: '添加',
        cancelButtonText: '取消',
        inputType: 'textarea',
        inputPlaceholder: '记录您的想法...'
    }).then(({ value }) => {
        if (!value || !value.trim()) return
        
        const noteId = `note-${Date.now()}`
        courseStore.createNote({
            id: noteId,
            nodeId: courseStore.treeData[0]?.node_id || 'root', // Default to first node or root if no context
            highlightId: '',
            quote: '',
            content: value,
            color: 'yellow',
            createdAt: Date.now(),
            sourceType: 'user'
        })
        ElMessage.success('笔记已添加')
    }).catch(() => {})
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

const handleUndoDelete = () => {
    if (undoNote.value) {
        // Just call createNote, which handles addition and persistence.
        // We use the same ID so backend should update or create if missing?
        // Actually backend saveAnnotation might expect new ID if it was truly deleted?
        // But we kept the ID in undoNote.value.
        courseStore.createNote(undoNote.value)
        undoVisible.value = false
        undoNote.value = null
        ElMessage.success('撤销成功')
        
        // Re-apply highlight happens automatically via watcher on notes/visibleNotes?
        // visibleNotes is computed from courseStore.notes. 
        // So adding to store updates visibleNotes, which triggers watcher to reapply highlights.
    }
}

const scrollToHighlight = (highlightId: string) => {
    const el = document.getElementById(highlightId)
    if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        // Flash effect
        el.classList.add('pulse-highlight')
        setTimeout(() => el.classList.remove('pulse-highlight'), 1500)
        
        const note = courseStore.notes.find(n => n.highlightId === highlightId)
        if (note) {
            activeNoteId.value = note.id
            // Scroll note column to this note
            const noteCard = document.getElementById(note.id)
            if (noteCard) {
                noteCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
                noteCard.classList.add('flash-card', 'ring-4', 'ring-primary-200')
                setTimeout(() => noteCard.classList.remove('flash-card', 'ring-4', 'ring-primary-200'), 1000)
            }
        }
    }
}

const debounce = (fn: Function, delay: number) => {
    let timeout: any
    return (...args: any[]) => {
        clearTimeout(timeout)
        timeout = setTimeout(() => fn(...args), delay)
    }
}

const debouncedUpdatePositions = debounce(updateNotePositions, 100)

const quizConfig = ref({
    visible: false,
    nodeId: '',
    nodeName: '',
    difficulty: 'medium',
    style: 'standard'
})

// Quiz Handling
const handleStartQuiz = (node: any) => {
    quizConfig.value.nodeId = node.node_id
    quizConfig.value.nodeName = node.node_name
    quizConfig.value.visible = true
}

const showSummary = async (node: any) => {
    // 1. Try to use AI Summary if available (from metadata or generate on fly?)
    // For now, let's use a smarter truncation or prompt AI
    
    // Check if we already have an AI summary note for this node
    const aiNote = courseStore.notes.find(n => n.nodeId === node.node_id && n.sourceType === 'ai' && n.content.includes('摘要'))
    
    if (aiNote) {
        ElMessageBox.alert(formatNoteContent(aiNote.content), `${node.node_name} - 智能摘要`, {
            confirmButtonText: '确定',
            customClass: 'glass-panel !rounded-2xl',
            dangerouslyUseHTMLString: true
        })
        return
    }

    // Fallback to simple preview with option to generate
    const summary = node.node_content.slice(0, 300) + '...'
    
    try {
        await ElMessageBox.confirm(
            `<div>${summary}</div><div class="mt-4 text-primary-600 font-bold cursor-pointer hover:underline">点击生成 AI 深度摘要</div>`, 
            `${node.node_name} - 内容预览`, 
            {
                confirmButtonText: '生成 AI 摘要',
                cancelButtonText: '关闭',
                customClass: 'glass-panel !rounded-2xl',
                dangerouslyUseHTMLString: true,
                distinguishCancelAndClose: true
            }
        )
        
        // If confirmed, trigger AI summary generation
        generateAiSummary(node)
        
    } catch (action) {
        // Cancelled
    }
}

const generateAiSummary = async (node: any) => {
    ElMessage.success('正在生成摘要，请稍候...')
    // Simulate or call AI
    const prompt = `请为章节《${node.node_name}》生成一份精简的摘要，包含核心概念和主要结论。`
    
    // Add to chat history
    courseStore.addMessage('user', prompt)
    
    // Call askQuestion but we might want the result to be a NOTE?
    // Let's use askQuestion and let the user save it, or auto-save.
    // Ideally we want to call a specific summary endpoint.
    // For now, reuse askQuestion flow which streams response to chat.
    await courseStore.askQuestion(prompt, node.node_content, node.node_id)
}

// Dialog Quiz Logic
const submitQuiz = () => {
    if (!quizConfig.value.nodeId) return

    if (userAnswers.value.some(a => !a)) {
        ElMessage.warning('请完成所有题目后再提交')
        return
    }
    
    // Calculate score
    let correctCount = 0
    let total = quizQuestions.value.length
    
    if (total === 0) return
    
    quizQuestions.value.forEach((q, idx) => {
        if (userAnswers.value[idx] === q.answer) {
            correctCount++
        } else {
            // Auto-save wrong question
            const userAnswer = userAnswers.value[idx]
            const noteContent = `**错题记录**\n\n**题目**：${q.question}\n\n**你的答案**：${userAnswer} ❌\n**正确答案**：${q.answer} ✅\n\n**解析**：${q.explanation || '暂无解析'}\n\n#错题`
            
            // Check if this wrong question already exists (avoid duplicates)
            const exists = courseStore.notes.some(n => 
                n.nodeId === quizConfig.value.nodeId && 
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
                    sourceType: 'user', // Treat as user note but with special tag
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
            nodeContentForQuiz(quizConfig.value.nodeId), 
            quizConfig.value.style,
            quizConfig.value.difficulty
        )
        
        if (res && Array.isArray(res)) {
            quizQuestions.value = res
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

const saveScrollPosition = debounce((scrollTop: number) => {
    if (courseStore.currentCourseId) {
        localStorage.setItem(`scroll-pos-${courseStore.currentCourseId}`, scrollTop.toString())
    }
}, 500)

const scrollToTop = () => {
    const container = document.getElementById('content-scroll-container')
    if (container) {
        container.scrollTo({ top: 0, behavior: 'smooth' })
    }
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
        
        observer = new IntersectionObserver((entries) => {
            if (isManualScrolling.value) return 

            // Find the intersecting entry that is closest to the top of viewport
            let bestCandidate = null
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
                const nodeId = (bestCandidate.target as HTMLElement).id.replace('node-', '')
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
        
        // Restore scroll position
        if (courseStore.currentCourseId) {
            const savedPos = localStorage.getItem(`scroll-pos-${courseStore.currentCourseId}`)
            if (savedPos) {
                const container = document.getElementById('content-scroll-container')
                if (container) {
                    container.scrollTop = parseInt(savedPos)
                }
            }
        }
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
</script>

<style scoped>
/* ContentArea Styles */
.scale-fade-enter-active,
.scale-fade-leave-active {
  transition: all 0.2s ease;
}

.scale-fade-enter-from,
.scale-fade-leave-to {
  opacity: 0;
  transform: scale(0.9);
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
    bottom: 2rem;
    right: 2rem;
    z-index: 40;
    transition: all 0.3s ease;
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

</style>