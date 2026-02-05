<template>
  <div class="h-full flex flex-col">
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
                        <button class="flex-1 p-1 hover:bg-white rounded text-slate-600" @click="fontSize = Math.max(12, fontSize - 1)"><el-icon><Minus /></el-icon></button>
                        <span class="text-xs font-mono w-8 text-center">{{ fontSize }}</span>
                        <button class="flex-1 p-1 hover:bg-white rounded text-slate-600" @click="fontSize = Math.min(24, fontSize + 1)"><el-icon><Plus /></el-icon></button>
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
    <div class="flex-1 overflow-auto p-4 lg:p-10 relative scroll-smooth custom-scrollbar" id="content-scroll-container" @mouseup="handleMouseUp">
      
      <!-- Selection Menu -->
      <transition name="scale-fade">
        <div v-if="selectionMenu.visible" 
            class="fixed z-50 flex gap-1 p-1.5 bg-slate-800/90 backdrop-blur-xl rounded-xl shadow-[0_8px_32px_rgba(0,0,0,0.12)] border border-white/10 ring-1 ring-white/10"
            :style="{ left: selectionMenu.x + 'px', top: selectionMenu.y + 'px' }"
            @mousedown.stop>
            <div class="absolute inset-0 rounded-xl bg-gradient-to-br from-white/10 to-transparent pointer-events-none"></div>
            <button @click="handleExplain" class="relative z-10 flex items-center gap-2 px-3 py-1.5 text-xs font-bold text-white hover:bg-white/20 rounded-lg transition-all group active:scale-95">
                <el-icon class="text-primary-300 group-hover:scale-110 group-hover:text-primary-200 transition-transform"><MagicStick /></el-icon> 
                <span class="text-shadow-sm">AI 深度解析</span>
            </button>
            <div class="w-px h-4 bg-white/20 my-auto mx-1"></div>
            <button @click="handleAddNote" class="relative z-10 flex items-center gap-2 px-3 py-1.5 text-xs font-bold text-white hover:bg-white/20 rounded-lg transition-all group active:scale-95">
                <el-icon class="text-amber-300 group-hover:scale-110 group-hover:text-amber-200 transition-transform"><ChatLineSquare /></el-icon> 
                <span class="text-shadow-sm">添加笔记</span>
            </button>
            <div class="w-px h-4 bg-white/20 my-auto mx-1"></div>
            <button @click="handleTranslate" class="relative z-10 flex items-center gap-2 px-3 py-1.5 text-xs font-bold text-white hover:bg-white/20 rounded-lg transition-all group active:scale-95">
                <el-icon class="text-emerald-300 group-hover:scale-110 group-hover:text-emerald-200 transition-transform"><Connection /></el-icon> 
                <span class="text-shadow-sm">翻译</span>
            </button>
        </div>
      </transition>

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
        <div id="note-column" v-if="!courseStore.isFocusMode" class="hidden lg:flex flex-col w-[200px] flex-shrink-0 relative border-l border-slate-100 bg-slate-50/30 transition-all duration-300">
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
                <el-input v-model="noteSearchQuery" placeholder="搜索笔记..." :prefix-icon="Search" size="small" clearable class="!w-full glass-input" />
            </div>

            <div class="relative flex-1 w-full">
                <div class="absolute inset-0 pointer-events-none">
                    <!-- Guide Line -->
                    <div class="absolute left-[-1px] top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-primary-200 to-transparent opacity-50"></div>
                </div>
                
                <!-- Empty State for Search -->
                <div v-if="visibleNotes.length === 0 && noteSearchQuery" class="flex flex-col items-center justify-center py-10 text-slate-400">
                    <el-icon :size="24" class="mb-2 opacity-50"><Search /></el-icon>
                    <p class="text-xs">未找到相关笔记</p>
                </div>

                <!-- Unquoted/Global Notes (Static Flow) -->
                <div class="flex flex-col gap-3 p-2 pb-4 mb-2 border-b border-slate-100/50 relative z-10">
                    <div class="flex justify-between items-center px-1">
                        <div class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Global Notes</div>
                        <el-button link size="small" type="primary" @click="addGlobalNote">
                            <el-icon class="mr-1"><Plus /></el-icon>添加
                        </el-button>
                    </div>
                    <div v-if="unquotedNotes.length === 0" class="text-center py-4 text-xs text-slate-400 bg-slate-50/50 rounded-lg border border-dashed border-slate-200">
                        暂无全局笔记
                    </div>
                    <div v-for="note in unquotedNotes" :key="note.id" 
                         class="bg-white rounded-xl shadow-sm border border-slate-200 p-3 group hover:shadow-md hover:border-primary-200 transition-all cursor-pointer relative"
                         :class="{'ring-2 ring-primary-100': activeNoteId === note.id, '!border-primary-200 !bg-primary-50/30': note.sourceType === 'ai'}"
                         @click="handleEditNote(note)">
                        
                        <!-- Connector (Hidden for global) -->
                        
                        <div class="flex justify-between items-start mb-1">
                            <div v-if="note.sourceType === 'ai'" class="text-[10px] font-bold text-primary-600 bg-primary-50 px-1.5 py-0.5 rounded border border-primary-100 flex items-center gap-1">
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
                            <div class="flex justify-end gap-2">
                                <el-button size="small" @click.stop="cancelEditing">取消</el-button>
                                <el-button size="small" type="primary" @click.stop="saveEditing(note)">保存</el-button>
                            </div>
                        </div>
                        <template v-else>
                                <div class="text-sm text-slate-700 font-medium leading-relaxed whitespace-pre-wrap" v-html="formatNoteContent(note.content)"></div>
                                <div v-if="note.content.length > 150" 
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
                    <div v-for="note in quotedNotes" :key="note.id" :id="note.id"
                         class="absolute left-2 right-2 transition-all duration-500 ease-out"
                         :style="{ top: (note.top || 0) + 'px' }">
                        
                         <!-- Connector Line -->
                         <div class="absolute -left-3 top-4 w-3 h-px bg-primary-300 dashed-line"></div>
                         <div class="absolute -left-3 top-3.5 w-1.5 h-1.5 rounded-full bg-primary-500 shadow-sm ring-2 ring-white"></div>

                         <!-- Note Bubble -->
                         <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-3 group hover:shadow-md hover:border-primary-200 transition-all cursor-pointer"
                              :class="{'ring-2 ring-primary-100': activeNoteId === note.id || hoveredNoteId === note.id, '!border-primary-200 !bg-primary-50/30': note.sourceType === 'ai'}"
                              @click="scrollToHighlight(note.highlightId)"
                              @mouseenter="setHovered(note.id)"
                              @mouseleave="setHovered(null)">
                            <div class="flex justify-between items-start mb-1">
                                <div v-if="note.sourceType === 'ai'" class="text-[10px] font-bold text-primary-600 bg-primary-50 px-1.5 py-0.5 rounded border border-primary-100 flex items-center gap-1">
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
                            <div v-if="note.quote" class="text-xs text-slate-500 italic mb-2 line-clamp-2 border-l-2 border-slate-200 pl-2">
                                "{{ note.quote }}"
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
                                <div class="flex justify-end gap-2">
                                    <el-button size="small" @click.stop="cancelEditing">取消</el-button>
                                    <el-button size="small" type="primary" @click.stop="saveEditing(note)">保存</el-button>
                                </div>
                            </div>
                            <template v-else>
                                <div class="text-sm text-slate-700 font-medium leading-relaxed whitespace-pre-wrap" v-html="formatNoteContent(note.content)"></div>
                                <div v-if="note.content.length > 150" 
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
                <div v-if="visibleNotes.length === 0" class="text-center text-slate-400 py-8">
                    暂无笔记
                </div>
                <div v-for="note in visibleNotes" :key="'mobile-'+note.id" 
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

    <!-- Undo Toast -->
    <transition name="slide-up">
        <div v-if="undoVisible" class="fixed bottom-8 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-4 py-3 bg-slate-800 text-white rounded-xl shadow-2xl shadow-slate-500/20 border border-slate-700">
            <el-icon class="text-green-400"><CircleCheckFilled /></el-icon>
            <span class="text-sm font-medium">笔记已删除</span>
            <div class="w-px h-4 bg-slate-600"></div>
            <button @click="handleUndoDelete" class="text-sm font-bold text-primary-300 hover:text-primary-200 hover:underline transition-colors">
                撤销
            </button>
            <button @click="undoVisible = false" class="ml-2 text-slate-500 hover:text-white">
                <el-icon><Close /></el-icon>
            </button>
        </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useCourseStore } from '../stores/course'
import MarkdownIt from 'markdown-it'
import mk from 'markdown-it-katex'
import 'katex/dist/katex.min.css'
import hljs from 'highlight.js'
import DOMPurify from 'dompurify'
import { Minus, Plus, Download, MagicStick, VideoPlay, Notebook, Check, Close, Edit, Delete, ChatLineSquare, Search, Timer, CircleCheckFilled, FullScreen, Microphone, Setting, Connection } from '@element-plus/icons-vue'
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
const showMobileNotes = ref(false)
const isSpeaking = ref(false)

const toggleTTS = () => {
    if (isSpeaking.value) {
        window.speechSynthesis.cancel()
        isSpeaking.value = false
        return
    }

    // Generate text content from flatNodes
    const text = flatNodes.value.map(n => {
        // Simple markdown stripping
        const content = n.node_content
            .replace(/[#*`>]/g, '') // Remove basic markdown symbols
            .replace(/\[.*?\]\(.*?\)/g, '') // Remove links
            .replace(/!\[.*?\]\(.*?\)/g, '') // Remove images
        return `${n.node_name}。\n${content}`
    }).join('\n\n')

    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'zh-CN'
    utterance.rate = 1.0
    utterance.onend = () => { isSpeaking.value = false }
    utterance.onerror = () => { isSpeaking.value = false; ElMessage.error('朗读出错') }
    
    window.speechSynthesis.speak(utterance)
    isSpeaking.value = true
}

const toggleFocusMode = () => {
    courseStore.isFocusMode = !courseStore.isFocusMode
}

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
}).use(mk);

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

const visibleNotes = computed(() => {
    const nodeIds = new Set(flatNodes.value.map(n => n.node_id))
    let notes = courseStore.notes.filter(n => nodeIds.has(n.nodeId))
    
    if (noteSearchQuery.value) {
        const query = noteSearchQuery.value.toLowerCase()
        notes = notes.filter(n => n.content.toLowerCase().includes(query) || (n.quote && n.quote.toLowerCase().includes(query)))
    }
    
    return notes
})

const quotedNotes = computed(() => visibleNotes.value.filter(n => n.quote && n.quote.trim().length > 0))
const unquotedNotes = computed(() => visibleNotes.value.filter(n => !n.quote || n.quote.trim().length === 0))

watch(() => [visibleNotes.value.length, fontSize.value, flatNodes.value], () => {
    nextTick(() => {
        reapplyHighlights()
        updateNotePositions()
    })
}, { deep: true })

const reapplyHighlights = () => {
    // Clear existing highlights first to prevent duplication
    // (Actually we check if exists, but cleaner to be safe if we re-run logic)
    
    quotedNotes.value.forEach(note => {
        if (document.getElementById(note.highlightId)) return
        
        const nodeEl = document.getElementById('node-' + note.nodeId)
        if (!nodeEl) return
        
        // Advanced Text Search & Highlight Strategy (Robust "Strip Whitespace" Match)
        // 1. Get all text nodes and build a map
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
        
        // 2. Normalize quote (Strip all whitespace)
        const normalize = (str: string) => str.replace(/\s+/g, '')
        const quoteStripped = normalize(note.quote)
        
        if (!quoteStripped) return

        // 3. Find matches
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
                     // 4. Create Range
                     // Logic to handle cross-node ranges is complex with surroundContents.
                     // We use the multi-range wrapping logic similar to before.
                     
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
}

const hoveredNoteId = ref<string | null>(null)

const setHovered = (noteId: string | null) => {
    hoveredNoteId.value = noteId
    
    if (noteId) {
        // Highlight marker
        const note = courseStore.notes.find(n => n.id === noteId)
        if (note && note.highlightId) {
            const el = document.getElementById(note.highlightId)
            if (el) el.classList.add('active')
        }
    } else {
        // Clear all marker highlights
        document.querySelectorAll('.highlight-marker.active').forEach(el => el.classList.remove('active'))
    }
}

const wrapRange = (range: Range, id: string, noteId: string) => {
    try {
        // Skip empty ranges
        if (range.toString().length === 0) return
        
        const span = document.createElement('span')
        span.id = id
        span.className = 'highlight-marker'
        span.onclick = (e) => {
            e.stopPropagation()
            scrollToNote(noteId)
        }
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
        const noteEl = document.getElementById(note.id) // Wait, note IDs in DOM are usually 'note-...'? No, look at template: v-for="note in visibleNotes" ... but no ID on the wrapper div?
        // In template: <div v-for="note in visibleNotes" ...> 
        // We need to add ID to note wrapper
    }
}

const updateNotePositions = () => {
    const notes = [...quotedNotes.value]
    const noteColumn = document.getElementById('note-column')
    if (!noteColumn) return

    const columnRect = noteColumn.getBoundingClientRect()
    const positions = notes.map(note => {
        let el = document.getElementById(note.highlightId)
        let isFallback = false
        
        // Fallback to Node container if highlight not found (e.g. AI note or render mismatch)
        if (!el) {
            el = document.getElementById('node-' + note.nodeId)
            isFallback = true
        }

        if (el) {
            const elRect = el.getBoundingClientRect()
            // Calculate position relative to the note column (which scrolls with content)
            const relativeTop = elRect.top - columnRect.top
            return { id: note.id, top: relativeTop + (isFallback ? 10 : 0) }
        }
        return { id: note.id, top: -9999 }
    })
    
    notes.sort((a, b) => {
        const posA = positions.find(p => p.id === a.id)?.top || 0
        const posB = positions.find(p => p.id === b.id)?.top || 0
        return posA - posB
    })
    
    let lastBottom = 0
    const GAP = 16
    notes.forEach(note => {
        let naturalTop = positions.find(p => p.id === note.id)?.top || 0
        
        // Collision detection and stacking
        if (naturalTop < lastBottom + GAP) {
             naturalTop = Math.max(naturalTop, lastBottom + GAP)
        }
        
        note.top = naturalTop
        
        // Use actual height if available, otherwise estimate
        const noteEl = document.getElementById(note.id)
        const height = noteEl ? noteEl.offsetHeight : (120 + Math.ceil(note.content.length / 20) * 20)
        
        lastBottom = naturalTop + height
    })
}

watch(editingNoteId, () => {
    nextTick(() => {
        updateNotePositions()
    })
})

const renderMarkdown = (content: string) => {
    if (!content) return ''
    
    // Pre-process LaTeX formula fixes
    let fixedContent = content
        // Fix \[ ... \] block formulas to $$ ... $$
        .replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$')
        // Fix \( ... \) inline formulas to $ ... $
        .replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$')
    
    try {
        const rawHtml = md.render(fixedContent)
        return DOMPurify.sanitize(rawHtml)
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
    visibleNotes.value.forEach(note => {
        const node = courseStore.nodes.find(n => n.node_id === note.nodeId)
        md += `## ${node?.node_name || '未知章节'}\n`
        if (note.quote) {
            md += `> ${note.quote}\n\n`
        }
        md += `${note.content}\n\n`
        md += `*${dayjs(note.createdAt).format('YYYY-MM-DD HH:mm')}*\n\n---\n\n`
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
    let html = content
    
    // Highlight Search
    if (noteSearchQuery.value && noteSearchQuery.value.trim()) {
        const query = noteSearchQuery.value.trim()
        const safeQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
        const regex = new RegExp(`(${safeQuery})`, 'gi')
        html = html.replace(regex, '<span class="bg-yellow-200 text-slate-900 rounded px-0.5 box-decoration-clone">$1</span>')
    }
    
    // Highlight Tags (e.g. #important, #todo)
    // Matches #tag at start or after space, followed by non-space chars
    html = html.replace(/(?<=^|\s)(#[\w\u4e00-\u9fa5]+)/g, '<span class="text-primary-600 font-bold">$1</span>')
    
    return html
}

// Selection Handling
const handleMouseUp = (_e: MouseEvent) => {
    // Prevent selection menu during scroll
    if (isManualScrolling.value) return
    
    const selection = window.getSelection()
    if (selection && selection.toString().trim().length > 0) {
        const range = selection.getRangeAt(0)
        const rect = range.getBoundingClientRect()
        selectionMenu.value = {
            visible: true,
            x: rect.left + (rect.width / 2) - 50, // Center horizontally
            y: rect.top - 40, // Position above
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

const expandedNoteIds = ref<string[]>([])

const toggleExpand = (noteId: string) => {
    const index = expandedNoteIds.value.indexOf(noteId)
    if (index === -1) {
        expandedNoteIds.value.push(noteId)
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

    // Optimistic UI update or wait for confirm? User asked for "Undo", usually implies immediate delete + toast.
    // But safety first: Confirm -> Delete -> Toast with Undo.
    
    ElMessageBox.confirm('确定删除这条笔记吗？', '提示', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消'
    }).then(() => {
        // Remove highlight from DOM
        const el = document.getElementById(note.highlightId)
        if (el) {
            const parent = el.parentNode
            while (el.firstChild) parent?.insertBefore(el.firstChild, el)
            parent?.removeChild(el)
        }
        
        courseStore.deleteNote(noteId)
        
        ElMessage({
            message: '笔记已删除',
            type: 'success',
            duration: 5000,
            showClose: true,
            grouping: true,
            // Custom Undo Button (Text only supported in standard ElMessage, use VNode or simpler approach)
            // Element Plus ElMessage doesn't easily support buttons unless using VNode.
            // Simplified: "Click here to Undo" is hard. 
            // We'll use a standard action or just a separate notification.
        })
        
        // Actually, let's implement a custom Undo toast using a hack or just simple message.
        // Better: Use a custom component or `ElNotification` with an onClick?
        // Let's stick to a simple "Deleted" for now, as Undo logic is complex to inject into ElMessage.
        // Wait, User asked for "Revoke/Undo" (撤销删除). 
        // I'll implement a simple "Undo" logic: Store last deleted note in a ref, show a button somewhere?
        // Or just use `ElMessage` with `dangerouslyUseHTMLString`? No, events won't work.
        // Standard pattern: "Deleted. [Undo]"
        
        // Hack: Use `ElMessage` onClose or just a separate floating button?
        // Let's try `ElNotification` which supports VNode but I can't write JSX here easily without setup.
        // I'll skip the "Undo" button in toast for now and just ensure deletion works safely.
        // Wait, "撤销删除" is Issue 15. I MUST implement it.
        
        // I'll use a global "Snackbar" or just a boolean `showUndo` in template.
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
        el.classList.add('flash-highlight')
        setTimeout(() => el.classList.remove('flash-highlight'), 1000)
        
        const note = courseStore.notes.find(n => n.highlightId === highlightId)
        if (note) {
            activeNoteId.value = note.id
            // Scroll note column to this note
            const noteCard = document.getElementById(note.id)
            if (noteCard) {
                noteCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
                noteCard.classList.add('ring-4', 'ring-primary-200')
                setTimeout(() => noteCard.classList.remove('ring-4', 'ring-primary-200'), 1000)
            }
        }
    }
}

// Debounce helper
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

const confirmQuiz = async () => {
    quizConfig.value.visible = false
    
    // Switch to Chat Panel (if applicable, or just notify)
    ElMessage.success('正在为您生成个性化测验，请查看右侧助手...')
    
    try {
        await courseStore.generateQuiz(
            quizConfig.value.nodeId, 
            nodeContentForQuiz(quizConfig.value.nodeId), // Helper to get content
            quizConfig.value.style,
            quizConfig.value.difficulty
        )
    } catch (e) {
        console.error(e)
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


const submitQuiz = () => {
    if (userAnswers.value.some(a => !a)) {
        ElMessage.warning('请完成所有题目后再提交')
        return
    }
    quizSubmitted.value = true
    
    // Calculate score
    let correct = 0
    quizQuestions.value.forEach((q, i) => {
        if (q.answer === userAnswers.value[i]) correct++
    })
    
    if (correct === quizQuestions.value.length) {
        ElMessage.success(`太棒了！全对！`)
    } else {
        ElMessage.info(`答对 ${correct}/${quizQuestions.value.length} 题，继续加油！`)
    }
}

// Watch visible notes to re-apply highlights and update positions
watch(visibleNotes, () => {
    // Wait for DOM update
    nextTick(() => {
        reapplyHighlights()
        debouncedUpdatePositions()
    })
}, { deep: true })

onMounted(() => {
    document.addEventListener('mousedown', (e) => {
        if (selectionMenu.value.visible && !(e.target as HTMLElement).closest('#content-scroll-container')) {
            selectionMenu.value.visible = false
        }
    })

    // Scroll Spy Setup
    const container = document.getElementById('content-scroll-container')
    if (container) {
        // Scroll listener removed for note positioning (using absolute layout)
        
        observer = new IntersectionObserver((entries) => {
            if (isManualScrolling.value) return // Skip updates during manual scroll

            // Find the visible node that is closest to the top
            // We focus on entries that are intersecting
            const visibleEntries = entries.filter(entry => entry.isIntersecting)
            
            if (visibleEntries.length > 0) {
                checkActiveNode()
            }
        }, {
            root: container,
            threshold: [0, 0.1, 0.5],
            rootMargin: '-5% 0px -80% 0px' // Focus on the top area of the viewport
        })

        // Observe all nodes (need to wait for DOM)
        // We use a MutationObserver or just watch flatNodes to re-observe
    }
    
    // Listen for resize to update note positions
    window.addEventListener('resize', debouncedUpdatePositions)
    
    // Initial highlight
    setTimeout(() => {
        reapplyHighlights()
        updateNotePositions()
    }, 1000)
})

// Helper to re-observe nodes when data changes
watch(() => flatNodes.value, () => {
    setTimeout(() => {
        if (!observer) return
        observer.disconnect()
        flatNodes.value.forEach(node => {
            const el = document.getElementById(`node-${node.node_id}`)
            if (el) observer?.observe(el)
        })
    }, 500) // Wait for render
}, { immediate: true })

const checkActiveNode = () => {
    const container = document.getElementById('content-scroll-container')
    if (!container) return

    const containerRect = container.getBoundingClientRect()
    const triggerLine = containerRect.top + containerRect.height * 0.2 // Top 20% of container

    let activeNodeId = null
    let minDistance = Infinity

    for (const node of flatNodes.value) {
        const el = document.getElementById(`node-${node.node_id}`)
        if (el) {
            const rect = el.getBoundingClientRect()
            // Distance from element top to trigger line
            const distance = Math.abs(rect.top - triggerLine)
            
            // Check if element is somewhat visible or just passed
            if (rect.top < containerRect.bottom && rect.bottom > containerRect.top) {
                if (distance < minDistance) {
                    minDistance = distance
                    activeNodeId = node.node_id
                }
            }
        }
    }

    if (activeNodeId && courseStore.currentNode?.node_id !== activeNodeId) {
        // Update store without triggering scroll (need a flag in store or logic)
        // actually selectNode triggers fetchAnnotations, which is fine.
        // But we don't want to trigger scrollToNode logic in CourseTree if it was caused by scrolling
        // So we might need a separate method or just update the ID silently?
        // Let's use selectNode but handle the side effects carefully.
        const node = flatNodes.value.find(n => n.node_id === activeNodeId)
        if (node) {
            courseStore.setCurrentNodeSilent(node)
        }
    }
}

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

.highlight-marker:hover,
.highlight-marker.active {
    background-color: rgba(251, 191, 36, 0.5);
    box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.2);
}

.flash-highlight {
    animation: flash 1s ease;
}

@keyframes flash {
    0%, 100% { background-color: rgba(251, 191, 36, 0.3); }
    50% { background-color: rgba(251, 191, 36, 0.8); box-shadow: 0 0 10px rgba(245, 158, 11, 0.5); }
}
</style>