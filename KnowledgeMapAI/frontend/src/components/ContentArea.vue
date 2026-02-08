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
                    
                    <!-- New Modern Chapter Header -->
                    <div class="relative z-10 bg-white/40 backdrop-blur-xl rounded-3xl border border-white/60 p-8 shadow-sm mb-10 overflow-hidden">
                        <!-- Decorative bg -->
                        <div class="absolute top-0 right-0 w-64 h-64 bg-gradient-to-br from-primary-50/50 to-transparent rounded-full blur-3xl -translate-y-1/2 translate-x-1/4 pointer-events-none"></div>

                        <div class="flex flex-col gap-6 relative">
                            <!-- Top Row: Badge & Metadata -->
                            <div class="flex items-center justify-between">
                                <div class="flex items-center gap-3">
                                    <span class="px-3 py-1 rounded-full bg-slate-900 text-white text-[10px] font-black tracking-widest uppercase">Chapter</span>
                                    <div class="h-px w-8 bg-slate-300"></div>
                                    <span class="text-xs font-bold text-slate-400 uppercase tracking-wider">Part {{ index + 1 }}</span>
                                </div>
                                
                                <!-- Metadata Pills -->
                                <div class="flex items-center gap-2">
                                    <div v-if="node.is_read" class="flex items-center gap-1.5 text-[10px] font-bold text-emerald-600 bg-emerald-50 border border-emerald-100 px-2.5 py-1 rounded-full">
                                        <el-icon><Check /></el-icon> 已读
                                    </div>
                                    <div class="flex items-center gap-1.5 text-[10px] font-bold text-slate-500 bg-white border border-slate-200 px-2.5 py-1 rounded-full shadow-sm">
                                        <el-icon><Timer /></el-icon> {{ Math.ceil((node.node_content?.length || 0) / 500) }} min
                                    </div>
                                </div>
                            </div>

                            <!-- Middle Row: Title & Action -->
                            <div class="flex flex-col md:flex-row md:items-center justify-between gap-6">
                                <h2 class="text-5xl md:text-6xl font-black text-slate-800 tracking-tight leading-tight">
                                    {{ node.node_name }}
                                </h2>
                                
                                <button 
                                    class="flex-shrink-0 group/btn relative overflow-hidden rounded-xl bg-slate-900 text-white px-8 py-4 flex items-center gap-3 shadow-lg hover:shadow-xl hover:scale-[1.02] transition-all duration-300"
                                    @click="handleStartQuiz(node)"
                                >
                                    <div class="absolute inset-0 bg-gradient-to-r from-primary-500 to-indigo-600 opacity-0 group-hover/btn:opacity-100 transition-opacity duration-300"></div>
                                    <el-icon class="relative z-10 text-2xl"><VideoPlay /></el-icon>
                                    <span class="relative z-10 font-bold text-xl">本章测验</span>
                                    <el-icon class="relative z-10 text-lg opacity-50 group-hover/btn:translate-x-1 transition-transform"><ArrowRight /></el-icon>
                                </button>
                            </div>

                            <!-- Bottom Row: Summary -->
                            <div v-if="node.node_content" class="relative mt-2">
                                <div class="absolute left-0 top-0 bottom-0 w-1 bg-primary-500 rounded-full"></div>
                                <div class="pl-5 py-1">
                                    <p class="text-slate-600 text-sm leading-relaxed font-medium opacity-80 line-clamp-3">
                                        {{ node.node_content.slice(0, 150) }}...
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                    

                </div>

                <!-- Level 3+: Content Card -->
                <div v-else class="group relative pl-8 border-l-2 border-slate-100 hover:border-primary-300 transition-colors duration-300">
                    <div class="absolute -left-[9px] top-0 w-4 h-4 rounded-full bg-slate-50 border-2 border-slate-200 group-hover:border-primary-500 group-hover:bg-primary-50 transition-all duration-300"></div>
                    
                    <div class="flex items-center justify-between mb-4 group/header">
                        <h3 class="text-xl font-bold text-slate-800 flex items-center gap-2">
                            <span class="w-1.5 h-5 bg-primary-500 rounded-full opacity-80"></span>
                            {{ node.node_name }}
                        </h3>
                        <div class="flex gap-2">
                            <button class="px-2 py-1 text-xs font-bold text-primary-600 bg-primary-50 hover:bg-primary-100 rounded-lg transition-colors flex items-center gap-1" @click="handleStartQuiz(node)" title="小节测验">
                                <el-icon><VideoPlay /></el-icon>
                                <span>测验</span>
                            </button>
                            <button class="p-1 text-slate-400 hover:text-primary-500 rounded-md hover:bg-slate-100 transition-colors" @click="showSummary(node)" title="内容摘要">
                                <el-icon><Notebook /></el-icon>
                            </button>
                        </div>
                    </div>
                    
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
        <div id="note-column" v-if="!courseStore.isFocusMode" class="hidden lg:flex flex-col w-[280px] flex-shrink-0 relative bg-slate-50/50 transition-all duration-300 border-l border-white/50">
             <!-- Search Header (Floating Card) -->
            <div class="sticky top-4 z-30 mx-3 mb-2 p-3 glass-panel-floating rounded-2xl flex flex-col gap-3 transition-all hover:shadow-[0_8px_30px_rgb(0,0,0,0.08)]">
                <div class="flex items-center justify-between px-1">
                    <h3 class="text-sm font-black text-slate-800 tracking-tight flex items-center gap-2">
                        <span class="w-1.5 h-4 bg-primary-500 rounded-full"></span>
                        我的笔记
                    </h3>
                    <el-tooltip content="导出笔记" placement="bottom">
                        <button class="p-1.5 text-slate-400 hover:text-primary-600 hover:bg-slate-100 rounded-lg transition-all duration-300" @click="exportContent">
                            <el-icon><Download /></el-icon>
                        </button>
                    </el-tooltip>
                </div>
                
                <!-- Note Filters -->
                <div class="relative flex bg-slate-200/40 p-1 rounded-xl select-none border border-white/20">
                    <div class="absolute top-1 bottom-1 rounded-lg bg-white shadow-[0_2px_8px_rgba(0,0,0,0.08)] border border-white/60 transition-all duration-300 ease-out"
                         :style="activeTabStyle"></div>
                    <button v-for="tab in ['notes', 'mistakes']" :key="tab"
                        class="relative flex-1 py-1.5 text-xs font-bold rounded-lg transition-colors z-10 text-center tracking-wide"
                        :class="activeNoteFilter === tab ? 'text-slate-800' : 'text-slate-500 hover:text-slate-700'"
                        @click="activeNoteFilter = tab"
                    >
                        {{ tab === 'notes' ? `笔记 ${noteCounts.notes}` : `错题 ${noteCounts.mistakes}` }}
                    </button>
                </div>

                <el-input 
                    v-model="noteSearchQuery" 
                    placeholder="搜索..." 
                    :prefix-icon="Search" 
                    size="small" 
                    clearable 
                    class="!w-full glass-input-clean"
                >
                    <template #suffix>
                        <el-icon v-if="isSearching" class="is-loading text-primary-500"><Loading /></el-icon>
                    </template>
                </el-input>
                <div v-if="debouncedSearchQuery" class="text-[10px] text-slate-400 px-1">
                    找到 {{ displayedNotes.length }} 条
                </div>
            </div>

            <div id="notes-container" class="relative flex-1 w-full flex flex-col">
                <!-- Mistakes View (Linear List) -->
                <div v-if="activeNoteFilter === 'mistakes'" class="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-3">
                     <div v-if="displayedNotes.length === 0" class="text-center py-8 text-xs text-slate-400 bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
                        {{ noteEmptyText }}
                    </div>
                    <div v-for="note in displayedNotes" :key="note.id"
                         class="bg-white/90 backdrop-blur-sm rounded-2xl shadow-[0_4px_12px_rgba(0,0,0,0.05)] border border-white p-0 group hover:shadow-[0_8px_20px_rgba(0,0,0,0.08)] transition-all duration-300 cursor-pointer overflow-hidden relative"
                         :class="{'ring-2 ring-primary-100': activeNoteId === note.id}"
                         @click="handleNoteClick(note)">
                         
                         <!-- Header -->
                        <div class="flex justify-between items-center px-4 py-3 border-b border-slate-100/50">
                            <div class="flex flex-col gap-0.5">
                                <div class="text-[10px] font-black text-red-500 flex items-center gap-1.5 uppercase tracking-wide">
                                    <div class="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse"></div>
                                    错题本
                                </div>
                                <div class="text-[10px] font-bold text-slate-400 truncate max-w-[180px]">
                                    {{ getNodeName(note.nodeId) }}
                                </div>
                            </div>
                            
                            <div class="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button class="p-1.5 hover:bg-slate-50 rounded-lg text-slate-400 hover:text-primary-600 transition-colors shadow-sm" @click.stop="handleEditNote(note)" v-if="note.sourceType !== 'wrong' && !note.content.includes('#错题')">
                                    <el-icon :size="14"><Edit /></el-icon>
                                </button>
                                <button class="p-1.5 hover:bg-slate-50 rounded-lg text-slate-400 hover:text-red-500 transition-colors shadow-sm" @click.stop="handleDeleteNote(note.id)">
                                    <el-icon :size="14"><Delete /></el-icon>
                                </button>
                            </div>
                        </div>

                        <!-- Content -->
                        <div class="p-4">
                            <div class="text-sm text-slate-700 font-medium leading-relaxed note-underline" v-html="formatMistakeContent(note.content)"></div>
                            <div class="mt-3 pt-3 border-t border-slate-50 flex items-center justify-between text-[10px] text-slate-300">
                                <div class="flex items-center gap-1">
                                    <el-icon><Timer /></el-icon> {{ dayjs(note.createdAt).fromNow() }}
                                </div>
                                <div class="flex items-center gap-3">
                                    <button class="flex items-center gap-1 hover:text-primary-500 transition-colors" @click.stop="handleNoteClick(note)">
                                        <el-icon><Position /></el-icon> 跳转原文
                                    </button>
                                    <div class="font-mono text-slate-200">#{{ note.id.slice(-4) }}</div>
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
                             class="absolute left-2 right-2 transition-all duration-500 ease-out"
                             :style="{ top: (note.top || 0) + 'px' }">
                            
                             <!-- Connector Line -->
                             <div class="absolute -left-4 top-5 w-4 h-px transition-colors duration-300" 
                                  :class="(activeNoteId === note.id || hoveredNoteId === note.id) ? 'bg-primary-300' : 'bg-slate-200'"></div>
                             <div class="absolute -left-[18px] top-[17px] w-2 h-2 rounded-full shadow-sm ring-2 ring-white transition-all duration-300"
                                  :class="(activeNoteId === note.id || hoveredNoteId === note.id) ? 'bg-primary-500 scale-125' : (note.sourceType === 'ai' ? 'bg-purple-400' : 'bg-slate-300')"></div>

                             <!-- Note Bubble -->
                             <div class="bg-white/90 backdrop-blur-sm rounded-2xl shadow-[0_8px_20px_-6px_rgba(0,0,0,0.08)] border p-0 group hover:shadow-[0_12px_24px_-4px_rgba(0,0,0,0.12)] hover:-translate-y-0.5 transition-all duration-300 cursor-pointer overflow-hidden"
                                  :class="[noteCardBorderClass(note), {'ring-2 ring-primary-200': activeNoteId === note.id || hoveredNoteId === note.id, '!border-purple-200 !shadow-purple-100': note.sourceType === 'ai'}]"
                                 @click="scrollToHighlight(note.highlightId, note.id)"
                                  @mouseenter="setHovered(note.id)"
                                  @mouseleave="setHovered(null)">
                                
                                <!-- Header -->
                                <div class="flex justify-between items-center px-3 py-2 border-b border-slate-50 transition-colors duration-300"
                                     :class="note.sourceType === 'ai' ? 'group-hover:border-purple-100' : 'group-hover:border-amber-100'">
                                    
                                    <div v-if="note.sourceType === 'ai'" class="text-[10px] font-bold text-purple-600 flex items-center gap-1.5 uppercase tracking-wide">
                                        <el-icon><MagicStick /></el-icon> AI 助手
                                    </div>
                                    <div v-else class="text-[10px] font-bold text-slate-500 flex items-center gap-1.5 uppercase tracking-wide">
                                        <div class="w-1.5 h-1.5 rounded-full" :class="noteDotClass(note)"></div>
                                        笔记
                                    </div>
                                    
                                    <div class="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <button class="p-1 hover:bg-slate-50 rounded-md text-slate-400 hover:text-primary-600 transition-colors" @click.stop="handleEditNote(note)">
                                            <el-icon :size="12"><Edit /></el-icon>
                                        </button>
                                        <button class="p-1 hover:bg-slate-50 rounded-md text-slate-400 hover:text-red-500 transition-colors" @click.stop="handleDeleteNote(note.id)">
                                            <el-icon :size="12"><Delete /></el-icon>
                                        </button>
                                    </div>
                                </div>

                                <!-- Content -->
                                <div class="p-3">
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
                                             :class="{'max-h-[500px] overflow-hidden': shouldCollapse(note) && !isAccordionMode, 'max-h-[200px] overflow-hidden': shouldCollapse(note) && isAccordionMode}">
                                            <div class="text-sm text-slate-700 font-medium leading-relaxed whitespace-pre-wrap note-underline" v-html="formatNoteContent(note.content)"></div>
                                            
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
                     class="bg-white rounded-xl shadow-sm border border-slate-200 p-4"
                     :class="{'!border-purple-200 !bg-purple-50/30': note.sourceType === 'ai'}"
                     @click="scrollToHighlight(note.highlightId, note.id); courseStore.isMobileNotesVisible = false">
                    <div class="flex justify-between items-start mb-2">
                        <div v-if="note.sourceType === 'ai'" class="text-xs font-bold text-purple-600 bg-purple-50 px-2 py-0.5 rounded border border-purple-100">AI 助手</div>
                        <div v-else class="text-xs font-bold px-2 py-0.5 rounded border" :class="noteBadgeClass(note)">笔记</div>
                        <div class="flex gap-2">
                             <button class="p-1 text-slate-400 hover:text-primary-600" @click.stop="handleEditNote(note)"><el-icon><Edit /></el-icon></button>
                             <button class="p-1 text-slate-400 hover:text-red-500" @click.stop="handleDeleteNote(note.id)"><el-icon><Delete /></el-icon></button>
                        </div>
                    </div>
                    <div v-if="note.quote" class="text-xs text-slate-500 italic mb-2 border-l-2 border-slate-200 pl-2">"{{ note.quote }}"</div>
                    <div class="text-sm text-slate-700 font-medium whitespace-pre-wrap note-underline" v-html="formatNoteContent(note.content)"></div>
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
             <span class="font-bold text-slate-800">解析：</span> {{ q.explanation || '暂无解析' }}
          </div>
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
        width="600px"
        class="glass-dialog-clean"
        align-center
        append-to-body
    >
        <div v-if="selectedNote" class="flex flex-col gap-4">
            <!-- Quote Context -->
            <div v-if="selectedNote.quote" class="p-4 bg-slate-50 rounded-xl border-l-4 italic text-slate-600 text-sm" :class="noteQuoteBorderClass(selectedNote)">
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
import { renderMarkdown } from '../utils/markdown'
import { Download, MagicStick, VideoPlay, Notebook, Check, Close, Edit, Delete, ChatLineSquare, Search, Timer, Connection, Trophy, ArrowDown, ArrowUp, Loading, ChatDotRound, Position, ArrowRight } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const courseStore = useCourseStore()
const selectionMenu = ref({ visible: false, x: 0, y: 0, text: '', range: null as Range | null })
const noteSearchQuery = ref('')
const activeNoteFilter = ref('notes')
const isAccordionMode = ref(true) // Default to true or false? Let's say false initially or true for better UX
const expandedNoteIds = ref<string[]>([])
const scrollProgress = ref(0)
const lightboxVisible = ref(false)
const lightboxImage = ref('')

const debounce = (fn: Function, delay: number) => {
    let timeout: any
    return (...args: any[]) => {
        clearTimeout(timeout)
        timeout = setTimeout(() => fn(...args), delay)
    }
}

const debouncedUpdatePositions = debounce(() => updateNotePositions(), 100)

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
const quizScore = computed(() => {
    if (!quizSubmitted.value || quizQuestions.value.length === 0) return 0
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
const fontSize = computed(() => courseStore.uiSettings.fontSize)
const fontFamily = computed(() => courseStore.uiSettings.fontFamily)
const lineHeight = computed(() => courseStore.uiSettings.lineHeight)
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
const nodeNameMap = computed(() => new Map(flatNodes.value.map(n => [n.node_id, n.node_name])))

const exportContent = () => {
    const filterLabel = activeNoteFilter.value === 'mistakes' ? '错题' : '笔记'
    const query = debouncedSearchQuery.value.trim()
    courseStore.exportNotesMarkdown(displayedNotes.value.slice(), { filterLabel, query: query || undefined })
}

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
const escapeRegExp = (val: string) => val.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// Debounce logic
let searchTimeout: any = null
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



// Tab Animation Style
const activeTabStyle = computed(() => {
    const tabs = ['notes', 'mistakes']
    const idx = tabs.indexOf(activeNoteFilter.value)
    if (idx === -1) return {}
    return {
        left: `${idx * 50}%`,
        width: '50%'
    }
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
const displayedNotes = computed(() => visibleNotes.value.filter(n => n.sourceType !== 'format'))
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

const setHovered = (noteId: string | null) => {
    hoveredNoteId.value = noteId
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
        } else if (note.nodeId) {
            courseStore.scrollToNode(note.nodeId)
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

watch(editingNoteId, () => {
    nextTick(() => {
        updateNotePositions()
    })
})



const formatNoteContent = (content: string) => {
    if (!content) return ''
    
    let processed = content.replace(/(?<=^|\s)(#[\w\u4e00-\u9fa5]+)/g, '<span class="text-primary-600 font-bold">$1</span>')
    
    if (searchTokens.value.length > 0) {
        const tokens = Array.from(new Set(searchTokens.value.map(t => escapeRegExp(t)).filter(Boolean)))
        if (tokens.length > 0) {
            const regex = new RegExp(`(${tokens.join('|')})`, 'gi')
            processed = processed.replace(regex, '<span class="bg-yellow-200 text-slate-900 rounded px-0.5 box-decoration-clone">$1</span>')
        }
    }
    
    return renderMarkdown(processed)
}

const formatMistakeContent = (content: string) => {
    let html = content
        .replace(/\*\*错题记录\*\*\s*/g, '')
        .replace(/#错题/g, '')
        .trim()

    // 题目
    html = html.replace(/\*\*题目\*\*：([\s\S]*?)(?=\n\n|\n\*\*|$)/, 
        '<div class="mb-4"><div class="text-[10px] font-black text-slate-400 mb-1.5 uppercase tracking-wider flex items-center gap-1"><span class="w-1 h-3 bg-slate-300 rounded-full"></span>题目</div><div class="text-sm font-bold text-slate-800 leading-relaxed">$1</div></div>')

    // 你的答案 (Error)
    html = html.replace(/\*\*你的答案\*\*：(.*?) ❌/g, 
        '<div class="flex items-center justify-between bg-red-50/80 border border-red-100 rounded-xl px-3 py-2.5 mb-2 relative overflow-hidden"><div class="absolute left-0 top-0 bottom-0 w-1 bg-red-400"></div><div class="flex flex-col z-10"><span class="text-[10px] font-bold text-red-400 mb-0.5 uppercase">你的答案</span><span class="text-sm font-bold text-red-700">$1</span></div><div class="w-6 h-6 rounded-full bg-red-100 flex items-center justify-center text-red-500"><svg viewBox="0 0 1024 1024" width="12" height="12"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm165.4 618.2l-66-.3L512 563.4l-99.6 118.4-66.1.3c-4.4 0-8.1-3.5-8.1-8 0-1.9.7-3.7 1.9-5.2l130.1-155L340.5 359a8.32 8.32 0 0 1-1.9-5.2c0-4.4 3.6-8 8.1-8l66.1.3L512 464.6l99.6-118.4 66-.3c4.4 0 8.1 3.5 8.1 8 0 1.9-.7 3.7-1.9 5.2L553.5 514l130 155c1.2 1.5 1.9 3.3 1.9 5.2 0 4.4-3.6 8-8 8z" fill="currentColor"></path></svg></div></div>')

    // 正确答案 (Success)
    html = html.replace(/\*\*正确答案\*\*：(.*?) ✅/g, 
        '<div class="flex items-center justify-between bg-emerald-50/80 border border-emerald-100 rounded-xl px-3 py-2.5 mb-4 relative overflow-hidden"><div class="absolute left-0 top-0 bottom-0 w-1 bg-emerald-400"></div><div class="flex flex-col z-10"><span class="text-[10px] font-bold text-emerald-500 mb-0.5 uppercase">正确答案</span><span class="text-sm font-bold text-emerald-700">$1</span></div><div class="w-6 h-6 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-500"><svg viewBox="0 0 1024 1024" width="12" height="12"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm193.5 301.7l-210.6 292a31.8 31.8 0 0 1-51.7 0L318.5 484.9c-3.8-5.3 0-12.7 6.5-12.7h46.9c10.2 0 19.9 4.9 25.9 13.3l71.2 98.8 157.2-218c6-8.3 15.6-13.3 25.9-13.3H699c6.5 0 10.3 7.4 6.5 12.7z" fill="currentColor"></path></svg></div></div>')

    // 解析
    html = html.replace(/\*\*解析\*\*：([\s\S]*?)$/, 
        '<div class="bg-slate-50 rounded-xl p-3.5 text-xs text-slate-600 leading-relaxed border border-slate-200/60 shadow-inner"><span class="font-bold text-slate-800 flex items-center gap-1.5 mb-2 text-[10px] uppercase tracking-wide"><svg viewBox="0 0 1024 1024" width="12" height="12" class="text-amber-500"><path d="M632 888H392c-4.4 0-8 3.6-8 8v32c0 17.7 14.3 32 32 32h192c17.7 0 32-14.3 32-32v-32c0-4.4-3.6-8-8-8zM512 64c-181.1 0-328 146.9-328 328 0 121.4 66 227.4 164 284.1V792c0 17.7 14.3 32 32 32h264c17.7 0 32-14.3 32-32v-115.9c98-56.7 164-162.7 164-284.1 0-181.1-146.9-328-328-328z" fill="currentColor"></path></svg> 解析</span>$1</div>')

    if (searchTokens.value.length > 0) {
        const tokens = Array.from(new Set(searchTokens.value.map(t => escapeRegExp(t)).filter(Boolean)))
        if (tokens.length > 0) {
            const regex = new RegExp(`(${tokens.join('|')})`, 'gi')
            html = html.replace(regex, '<span class="bg-yellow-200 text-slate-900 rounded px-0.5 box-decoration-clone">$1</span>')
        }
    }

    return html
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
                id: noteId,
                nodeId,
                highlightId,
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

const handleNoteClick = (note: any) => {
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

const handleEditNote = (note: any) => {
    if (courseStore.isMobileNotesVisible) {
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
    difficulty: 'medium',
    style: 'standard',
    questionCount: 3
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
            `<div>${renderMarkdown(summary)}</div><div class="mt-4 text-primary-600 font-bold cursor-pointer hover:underline">点击生成 AI 深度摘要</div>`, 
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

</style>
