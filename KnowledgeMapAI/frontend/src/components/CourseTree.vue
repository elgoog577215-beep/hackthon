<template>
  <div class="h-full flex flex-col relative">
    
    <!-- MODE 1: COURSE LIST -->
    <transition name="fade-slide" mode="out-in">
      <div v-if="!courseStore.currentCourseId" class="flex flex-col h-full" key="list">
        <div class="mx-3 mt-3 mb-1 px-4 py-3 flex justify-between items-center flex-shrink-0 glass-panel-tech-floating rounded-2xl z-10 relative">
            <div class="flex items-center gap-2">
                <button 
                    class="p-1 -ml-1 text-slate-400 hover:text-primary-600 rounded-lg hover:bg-slate-100 transition-colors"
                    @click="$emit('toggle-sidebar')"
                    title="收起侧边栏"
                >
                    <el-icon :size="16"><Fold /></el-icon>
                </button>
                <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500/10 to-primary-500/10 flex items-center justify-center text-primary-600 ring-1 ring-inset ring-white/60 shadow-sm">
                    <el-icon :size="16"><Collection /></el-icon>
                </div>
                <span class="font-bold text-slate-700 tracking-tight font-display">我的课程</span>
            </div>
            
            <button 
                class="glass-icon-btn bg-white/40 hover:bg-white/80 !border-white/50 text-slate-600 hover:!text-primary-600 group"
                @click="createNewCourse"
                title="新建课程"
            >
                <el-icon :size="16" class="transition-transform duration-300 group-hover:rotate-90"><Plus /></el-icon>
            </button>
        </div>

        <!-- List Content -->
        <div class="flex-1 overflow-auto p-3 custom-scrollbar space-y-2.5 scroll-smooth">
            <div 
                v-for="(course, index) in courseStore.courseList" 
                :key="course.course_id" 
                class="animate-fade-in-up"
                :style="{ animationDelay: (index * 50) + 'ms' }"
            >
                <div 
                    class="group relative p-3.5 rounded-2xl glass-card-tech-hover cursor-pointer overflow-hidden h-full"
                    @click="handleCourseClick(course.course_id)"
                >
                 <!-- Hover Gradient -->
                 <div class="absolute inset-0 bg-gradient-to-r from-primary-500/5 via-primary-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>

                 <div class="relative flex justify-between items-start">
                     <div class="flex items-start gap-3 overflow-hidden">
                        <!-- Course Icon -->
                        <div class="mt-0.5 w-8 h-8 rounded-lg bg-gradient-to-br from-slate-100 to-white border border-white/60 shadow-sm flex items-center justify-center text-slate-400 group-hover:text-primary-500 group-hover:scale-110 transition-all duration-300">
                            <el-icon :size="16"><Notebook /></el-icon>
                        </div>
                        
                        <div class="flex-1 min-w-0">
                            <div class="font-bold text-slate-700 group-hover:text-slate-900 truncate transition-colors">{{ course.course_name }}</div>
                            <div class="text-xs text-slate-400 group-hover:text-slate-500 mt-1 flex items-center gap-2 transition-colors">
                                <span class="bg-slate-100/50 px-1.5 py-0.5 rounded border border-slate-100 group-hover:border-primary-100 group-hover:bg-primary-50/50 transition-colors">
                                    {{ course.node_count }} 章节
                                </span>
                                <!-- Status Badge -->
                                <span v-if="courseStore.getTask(course.course_id)?.status === 'running'" class="flex items-center gap-1 text-primary-500 font-bold animate-pulse">
                                    <span class="w-1.5 h-1.5 rounded-full bg-primary-500"></span>
                                    生成中 {{ courseStore.getTask(course.course_id)?.progress }}%
                                </span>
                                <span v-else-if="courseStore.getTask(course.course_id)?.status === 'paused'" class="flex items-center gap-1 text-amber-500 font-bold">
                                    <span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
                                    已暂停 {{ courseStore.getTask(course.course_id)?.progress }}%
                                </span>
                                <span v-else-if="courseStore.getTask(course.course_id)?.status === 'completed'" class="flex items-center gap-1 text-emerald-500 font-bold">
                                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                                    已完成
                                </span>
                            </div>
                        </div>
                     </div>

                     <!-- Actions -->
                     <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all duration-200 translate-x-2 group-hover:translate-x-0" @click.stop>
                        <!-- Control Button -->
                        <button 
                            v-if="courseStore.getTask(course.course_id)?.status === 'running'"
                            class="p-1.5 hover:bg-amber-50 text-slate-400 hover:text-amber-500 rounded-lg transition-colors"
                            title="暂停生成"
                            @click.stop="courseStore.pauseTask(course.course_id)"
                        >
                            <el-icon :size="15"><VideoPause /></el-icon>
                        </button>
                        <button 
                            v-else-if="courseStore.getTask(course.course_id)?.status === 'paused' || courseStore.getTask(course.course_id)?.status === 'idle'"
                            class="p-1.5 hover:bg-primary-50 text-slate-400 hover:text-primary-500 rounded-lg transition-colors"
                            title="继续生成"
                            @click.stop="courseStore.startTask(course.course_id)"
                        >
                            <el-icon :size="15"><VideoPlay /></el-icon>
                        </button>

                        <el-popconfirm
                            title="确定删除该课程吗？"
                            confirm-button-text="删除"
                            cancel-button-text="取消"
                            confirm-button-type="danger"
                            @confirm="handleDeleteCourse(course.course_id)"
                            width="200"
                        >
                            <template #reference>
                                <button class="p-1.5 hover:bg-red-50 text-slate-400 hover:text-red-500 rounded-lg transition-colors">
                                    <el-icon :size="15"><Delete /></el-icon>
                                </button>
                            </template>
                        </el-popconfirm>
                     </div>
                </div>
            </div>
            </div>

             <!-- Empty State -->
            <div v-if="courseStore.courseList.length === 0 && !courseStore.loading" class="flex flex-col items-center justify-center h-64 animate-fade-in-up p-6">
                <div class="glass-card-tech rounded-[2.5rem] p-8 flex flex-col items-center text-center shadow-2xl shadow-primary-500/10 border-white/70">
                    <div class="w-20 h-20 rounded-[2rem] bg-gradient-to-br from-primary-50 to-white border border-white shadow-[0_8px_30px_rgba(139,92,246,0.1)] flex items-center justify-center mb-6 relative group transition-transform hover:scale-105">
                        <div class="absolute inset-0 bg-primary-500/5 rounded-[2rem] animate-pulse-slow"></div>
                        <el-icon :size="32" class="text-primary-400 group-hover:text-primary-600 transition-colors"><Notebook /></el-icon>
                    </div>
                    <h3 class="text-lg font-bold text-slate-700 mb-2 font-display">开启知识之旅</h3>
                    <p class="text-sm text-slate-400 mb-6 max-w-[200px] leading-relaxed">创建一个新课程，让 AI 帮你构建完整的知识体系</p>
                    <el-button type="primary" class="!rounded-xl !px-6 !font-bold !bg-gradient-to-r !from-primary-500 !to-primary-600 !border-none !shadow-lg !shadow-primary-500/20 hover:!shadow-primary-500/40 hover:!scale-105 transition-all" @click="createNewCourse">
                        新建课程
                    </el-button>
                </div>
            </div>
            
            <!-- Loading State -->
            <div v-if="courseStore.loading && courseStore.courseList.length === 0" class="flex flex-col items-center justify-center h-60">
                <div class="relative flex flex-col items-center gap-4">
                    <!-- Holographic Spinner -->
                    <div class="relative w-16 h-16 flex items-center justify-center">
                        <div class="absolute inset-0 rounded-full border-2 border-primary-500/20"></div>
                        <div class="absolute inset-0 rounded-full border-t-2 border-primary-500 animate-spin"></div>
                        <div class="absolute inset-2 rounded-full border-2 border-primary-500/20"></div>
                        <div class="absolute inset-2 rounded-full border-b-2 border-primary-500 animate-spin-reverse"></div>
                        <div class="absolute inset-0 bg-primary-500/5 blur-xl rounded-full animate-pulse-slow"></div>
                        
                        <el-icon class="text-2xl text-transparent bg-clip-text bg-gradient-to-br from-primary-500 to-primary-600 animate-pulse"><Loading /></el-icon>
                    </div>
                    
                    <div class="flex flex-col items-center gap-1">
                        <span class="text-sm font-bold text-transparent bg-clip-text bg-gradient-to-r from-primary-600 to-primary-600 tracking-wider">LOADING DATA</span>
                        <span class="text-[10px] text-slate-400 font-mono">正在初始化课程数据...</span>
                    </div>
                </div>
            </div>
        </div>
      </div>
    

      <!-- MODE 2: TREE VIEW -->
      <div v-else class="flex flex-col h-full" key="tree">
        <!-- Compact Header -->
        <div class="mx-4 mt-4 mb-2 h-16 px-4 flex gap-3 items-center justify-between flex-shrink-0 glass-panel-tech-floating rounded-2xl z-10 relative box-border">
          
          <div class="flex items-center gap-1">
            <!-- Collapse Button -->
            <button 
                class="flex-shrink-0 w-8 h-8 glass-card-tech-hover !p-0 !rounded-xl !border-white/50 text-slate-500 hover:text-primary-600 flex items-center justify-center group"
                @click="$emit('toggle-sidebar')"
                title="收起侧边栏"
            >
                <el-icon :size="16"><Fold /></el-icon>
            </button>

            <!-- Back Button -->
            <button 
                class="flex-shrink-0 w-8 h-8 glass-card-tech-hover !p-0 !rounded-xl !border-white/50 text-slate-500 hover:text-primary-600 flex items-center justify-center group"
                @click="backToCourses"
                title="返回课程列表"
            >
                <el-icon :size="16" class="group-hover:-translate-x-0.5 transition-transform"><ArrowLeft /></el-icon>
            </button>

            <!-- Notes Button -->
            <button 
                class="flex-shrink-0 w-8 h-8 glass-card-tech-hover !p-0 !rounded-xl !border-white/50 text-slate-500 hover:text-amber-500 flex items-center justify-center group"
                @click="notesDialogVisible = true"
                title="课程笔记"
            >
                <el-icon :size="16"><Document /></el-icon>
            </button>
          </div>

          <!-- Search Input -->
          <div class="relative group flex-1 transition-all duration-300 ease-out min-w-0">
            <div class="relative flex items-center bg-white/40 hover:bg-white/60 focus-within:!bg-white/80 backdrop-blur-md border border-white/60 focus-within:border-primary-300/50 rounded-xl transition-all duration-300 shadow-sm group-focus-within:shadow-lg group-focus-within:shadow-primary-500/10 overflow-hidden h-9">
                <!-- Inner Shadow for depth -->
                <div class="absolute inset-0 shadow-[inset_0_2px_4px_rgba(0,0,0,0.02)] pointer-events-none rounded-xl"></div>
                
                <div class="pl-3 flex items-center justify-center text-slate-400 group-focus-within:text-primary-500 transition-colors duration-300 relative z-10">
                     <el-icon :size="14" class="group-focus-within:scale-110 group-focus-within:rotate-12 transition-transform duration-300"><Search /></el-icon>
                </div>
                <input 
                    v-model="filterText"
                    type="text"
                    placeholder="搜索章节..."
                    class="w-full pl-2 pr-8 py-2 bg-transparent border-none outline-none focus:outline-none focus:ring-0 text-xs font-medium text-slate-700 placeholder-slate-400/80 group-focus-within:placeholder-primary-300/50 relative z-10 h-full"
                />
                <!-- Clear Button -->
                <transition name="scale-fade">
                    <button 
                        v-if="filterText" 
                        class="absolute right-2 text-slate-400 hover:text-primary-500 transition-colors z-20"
                        @click="filterText = ''"
                    >
                        <el-icon :size="14"><CircleClose /></el-icon>
                    </button>
                </transition>
            </div>
          </div>
        </div>
        
        <!-- Tree Content -->
        <div class="flex-1 overflow-auto p-3 custom-scrollbar">
          <!-- Wrapper must allow shrinking to content width to avoid infinite loop with parent width -->
          <div class="w-max" ref="treeContentRef">
           <el-tree
            ref="treeRef"
            :data="courseStore.courseTree"
            :props="defaultProps"
            default-expand-all
            node-key="node_id"
            :filter-node-method="filterNode"
            highlight-current
            :expand-on-click-node="false"
            :indent="16"
            @node-click="handleNodeClick"
            class="!bg-transparent course-tree-glass"
          >
            <template #default="{ node, data }">
              <div 
                class="flex items-center py-2 px-3 w-full rounded-xl transition-all duration-500 group relative overflow-hidden border border-transparent 
                       hover:bg-white/40 hover:border-white/50 hover:shadow-[0_4px_20px_-4px_rgba(139,92,246,0.1)]
                       data-[current=true]:bg-gradient-to-r data-[current=true]:from-white/90 data-[current=true]:to-primary-50/80 data-[current=true]:text-primary-900 data-[current=true]:shadow-[0_8px_30px_-6px_rgba(139,92,246,0.2)] data-[current=true]:border-white/60"
                :data-current="node.isCurrent"
              >
                <!-- Active Indicator (Glow) -->
                <div class="absolute inset-0 bg-gradient-to-r from-primary-500/10 via-transparent to-transparent opacity-0 group-data-[current=true]:opacity-100 transition-opacity duration-500 pointer-events-none"></div>
                
                <!-- Glass Reflection (Diagonal Shine) -->
                <div class="absolute -inset-full top-0 block h-full w-1/2 -skew-x-12 bg-gradient-to-r from-transparent to-white opacity-20 group-hover:animate-shine pointer-events-none"></div>

                <!-- Left Accent Pill -->
                <div class="absolute left-1 top-1/2 -translate-y-1/2 w-1 h-0 bg-gradient-to-b from-primary-400 to-primary-600 rounded-full transition-all duration-300 opacity-0 group-data-[current=true]:opacity-100 group-data-[current=true]:h-5 shadow-[0_0_8px_rgba(139,92,246,0.6)]"></div>

                <!-- Icon Indicator -->
                <div class="mr-3 flex-shrink-0 w-5 h-5 flex items-center justify-center transition-all duration-300 transform group-hover:scale-110 group-data-[current=true]:scale-110"
                    :class="data.node_level === 1 
                        ? 'text-primary-600 drop-shadow-sm' 
                        : 'text-slate-400 group-hover:text-slate-600 group-data-[current=true]:text-primary-600'">
                    <component :is="getIcon(data.node_level)" class="w-4 h-4" stroke-width="2.5" />
                </div>
                
                <!-- Text -->
                    <span class="whitespace-nowrap text-sm transition-colors tracking-tight mr-2 truncate max-w-40 lg:max-w-52" 
                        :class="data.node_level === 1 ? 'font-bold text-slate-800' : 'text-slate-600 font-medium group-hover:text-slate-900 group-data-[current=true]:text-primary-950'">
                        
                        <!-- Status Dot / Read Indicator -->
                        <span class="inline-block w-1.5 h-1.5 rounded-full mr-1.5 mb-0.5 align-middle transition-colors duration-300"
                              :class="{
                                  'bg-emerald-400 shadow-[0_0_5px_rgba(52,211,153,0.4)]': 
                                      (data.node_level <= 2 && data.children && data.children.length > 0) || 
                                      (data.node_level > 2 && data.node_content && data.node_content.includes('<!-- BODY_START -->')),
                                  'bg-slate-200 group-hover:bg-slate-300': 
                                      !((data.node_level <= 2 && data.children && data.children.length > 0) || 
                                        (data.node_level > 2 && data.node_content && data.node_content.includes('<!-- BODY_START -->')))
                              }">
                        </span>
                        
                        <span v-html="highlightSearch(node.label)"></span>
                    </span>
                
                <!-- Hover Actions (Next to text) -->
                <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 group-data-[current=true]:opacity-100 transition-opacity bg-white/50 backdrop-blur-sm rounded-lg px-1 shadow-sm border border-white/40 flex-shrink-0" @click.stop>
                    <button v-if="data.node_level >= 2" class="p-1 text-slate-400 hover:text-primary-600 hover:bg-white rounded transition-colors" title="生成本章内容" @click="handleGenerate(data)">
                        <el-icon :size="12"><MagicStick /></el-icon>
                    </button>
                    <button class="p-1 text-slate-400 hover:text-primary-600 hover:bg-white rounded transition-colors" title="添加子节点" @click="handleAdd(data)">
                        <el-icon :size="12"><Plus /></el-icon>
                    </button>
                    <button class="p-1 text-slate-400 hover:text-primary-600 hover:bg-white rounded transition-colors" title="重命名" @click="handleRename(data)">
                        <el-icon :size="12"><Edit /></el-icon>
                    </button>
                    
                    <el-popconfirm
                        title="确定删除此节点及其子节点吗？"
                        confirm-button-text="删除"
                        cancel-button-text="取消"
                        confirm-button-type="danger"
                        @confirm="handleDelete(data)"
                        width="200"
                    >
                        <template #reference>
                            <button class="p-1 text-slate-400 hover:text-red-500 hover:bg-white rounded transition-colors" title="删除">
                                <el-icon :size="12"><Delete /></el-icon>
                            </button>
                        </template>
                    </el-popconfirm>
                </div>
              </div>
            </template>
          </el-tree>
          </div>
        </div>
      </div>
    </transition>
    
    <!-- Notes Dialog -->
    <el-dialog
        v-model="notesDialogVisible"
        title="课程笔记"
        width="600px"
        append-to-body
        class="glass-dialog"
    >
        <div class="max-h-[60vh] overflow-y-auto custom-scrollbar p-1">
            <div v-if="courseStore.notes.length === 0" class="text-center text-gray-400 py-10">
                暂无笔记
            </div>
            <div v-else class="space-y-4">
                <div v-for="note in courseStore.notes" :key="note.id" class="bg-white/50 border border-white/60 rounded-xl p-4 shadow-sm hover:shadow-md transition-all">
                    <div class="flex justify-between items-start mb-2">
                        <div class="flex flex-col gap-1 w-full mr-2">
                            <div class="flex items-center gap-2">
                                <span v-if="note.sourceType === 'ai'" class="text-[10px] font-bold text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded border border-purple-100 whitespace-nowrap">AI 助手</span>
                                <span v-else class="text-[10px] font-bold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-100 whitespace-nowrap">笔记</span>
                                <div class="font-bold text-slate-700 text-sm truncate">{{ note.content.split('\n')[0] }}</div>
                            </div>
                            <div class="flex items-center gap-2 text-[10px] text-slate-400">
                                <span class="bg-slate-100 px-1.5 py-0.5 rounded flex items-center gap-1">
                                    <el-icon><Location /></el-icon>
                                    {{ getNodeName(note.nodeId) }}
                                </span>
                                <span class="flex items-center gap-1">
                                    <el-icon><Clock /></el-icon>
                                    {{ formatDate(note.createdAt) }}
                                </span>
                            </div>
                        </div>
                        <el-button link type="danger" size="small" @click="courseStore.deleteNote(note.id)">
                            <el-icon><Delete /></el-icon>
                        </el-button>
                    </div>
                    <div v-if="note.quote" class="text-xs text-slate-500 italic border-l-2 border-primary-300 pl-2 mb-2 bg-slate-50/50 py-1 rounded-r">
                        "{{ note.quote }}"
                    </div>
                    <div class="text-xs text-slate-600 leading-relaxed whitespace-pre-wrap max-h-32 overflow-hidden relative group cursor-pointer" @click="note.expanded = !note.expanded">
                        <div :class="{ 'line-clamp-3': !note.expanded }">{{ note.content }}</div>
                        <div v-if="!note.expanded && note.content.length > 100" class="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-white/80 to-transparent flex items-end justify-center">
                            <span class="text-[10px] text-primary-500 bg-white/80 px-2 rounded-full shadow-sm mb-1">展开更多</span>
                        </div>
                    </div>
                    <div class="flex justify-end mt-2">
                        <el-button link type="primary" size="small" @click="courseStore.scrollToNode(note.nodeId); notesDialogVisible = false">
                            跳转到原文
                        </el-button>
                    </div>
                </div>
            </div>
        </div>
    </el-dialog>
      <!-- Create Course Dialog -->
      <el-dialog 
        v-model="createDialogVisible" 
        width="680px" 
        class="glass-dialog !rounded-[2rem] !p-0 overflow-hidden shadow-2xl" 
        :show-close="false"
        append-to-body
        align-center
      >
        <template #header>
            <div class="px-8 py-6 border-b border-slate-100/80 flex justify-between items-center bg-white/80 backdrop-blur-xl relative z-10">
                <div class="flex items-center gap-4">
                    <div class="relative w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20 group-hover:scale-105 transition-transform duration-500">
                        <div class="absolute inset-0 bg-white/20 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity"></div>
                        <el-icon :size="24" class="drop-shadow-md"><MagicStick /></el-icon>
                    </div>
                    <div>
                        <h4 class="text-xl font-bold text-slate-800 leading-tight font-display tracking-tight">AI 智能课程生成</h4>
                        <p class="text-xs text-slate-500 font-medium mt-1 tracking-wide">基于深度学习模型构建个性化知识图谱</p>
                    </div>
                </div>
                <button @click="createDialogVisible = false" class="w-8 h-8 flex items-center justify-center rounded-full hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-all duration-300">
                    <el-icon :size="18"><Close /></el-icon>
                </button>
            </div>
        </template>
        
        <div class="p-8 space-y-8 bg-gradient-to-b from-slate-50/50 to-white">
            <el-form :model="createForm" label-position="top" class="space-y-8">
                
                <!-- Topic Input -->
                <div class="space-y-3">
                    <label class="text-sm font-bold text-slate-700 flex items-center gap-2 select-none">
                        <div class="w-6 h-6 rounded-lg bg-blue-50 text-blue-500 flex items-center justify-center shadow-sm border border-blue-100">
                            <el-icon :size="14"><Notebook /></el-icon>
                        </div>
                        课程主题
                    </label>
                    <div class="relative group">
                        <el-input 
                            v-model="createForm.keyword" 
                            placeholder="例如：量子力学基础、Python编程、西方哲学史..." 
                            size="large" 
                            class="!text-base custom-input-shadow transition-all duration-300"
                            clearable
                        />
                        <div class="absolute inset-0 rounded-xl ring-2 ring-primary-500/20 opacity-0 group-focus-within:opacity-100 transition-opacity pointer-events-none"></div>
                    </div>
                </div>

                <!-- Grid Layout for Options -->
                <div class="grid grid-cols-2 gap-8">
                    <!-- Difficulty Selection -->
                    <div class="space-y-3">
                        <label class="text-sm font-bold text-slate-700 flex items-center gap-2 select-none">
                            <div class="w-6 h-6 rounded-lg bg-amber-50 text-amber-500 flex items-center justify-center shadow-sm border border-amber-100">
                                <el-icon :size="14"><Trophy /></el-icon>
                            </div>
                            难度等级
                        </label>
                        <div class="grid grid-cols-1 gap-3">
                            <div 
                                v-for="level in [
                                    { val: 'beginner', label: '入门', sub: '零基础友好', color: 'bg-emerald-400', shadow: 'shadow-emerald-100' },
                                    { val: 'medium', label: '进阶', sub: '有一定基础', color: 'bg-blue-400', shadow: 'shadow-blue-100' },
                                    { val: 'advanced', label: '专家', sub: '深入原理', color: 'bg-violet-400', shadow: 'shadow-violet-100' }
                                ]" 
                                :key="level.val"
                                class="relative flex items-center p-3 rounded-xl border-2 transition-all cursor-pointer group hover:-translate-y-0.5"
                                :class="createForm.difficulty === level.val 
                                    ? 'bg-white border-primary-500 shadow-md ring-1 ring-primary-500/20' 
                                    : 'bg-white border-slate-100 hover:border-slate-300 hover:shadow-sm'"
                                @click="createForm.difficulty = level.val"
                            >
                                <div class="w-1.5 h-8 rounded-full mr-3 transition-colors duration-300" 
                                     :class="createForm.difficulty === level.val ? level.color : 'bg-slate-200 group-hover:bg-slate-300'"></div>
                                <div class="flex-1">
                                    <div class="font-bold text-sm text-slate-700 group-hover:text-slate-900 transition-colors">{{ level.label }}</div>
                                    <div class="text-[10px] text-slate-400 font-medium group-hover:text-slate-500 transition-colors">{{ level.sub }}</div>
                                </div>
                                <div class="w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all duration-300"
                                     :class="createForm.difficulty === level.val ? 'border-primary-500 bg-primary-500 text-white scale-110' : 'border-slate-200 bg-slate-50 text-transparent'">
                                    <el-icon :size="12" class="font-bold"><Check /></el-icon>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Style Selection -->
                    <div class="space-y-3">
                        <label class="text-sm font-bold text-slate-700 flex items-center gap-2 select-none">
                            <div class="w-6 h-6 rounded-lg bg-pink-50 text-pink-500 flex items-center justify-center shadow-sm border border-pink-100">
                                <el-icon :size="14"><MagicStick /></el-icon>
                            </div>
                            教学风格
                        </label>
                        <div class="grid grid-cols-2 gap-3">
                            <div 
                                v-for="style in [
                                    { val: 'academic', label: '学术严谨', icon: '🎓' },
                                    { val: 'easy', label: '通俗易懂', icon: '👶' },
                                    { val: 'practical', label: '实战案例', icon: '🛠️' },
                                    { val: 'humorous', label: '幽默风趣', icon: '😄' }
                                ]" 
                                :key="style.val"
                                class="flex flex-col items-center justify-center p-3 rounded-xl border-2 transition-all cursor-pointer hover:-translate-y-0.5 aspect-[4/3]"
                                :class="createForm.style === style.val 
                                    ? 'bg-white border-primary-500 shadow-md ring-1 ring-primary-500/20' 
                                    : 'bg-white border-slate-100 hover:border-slate-300 hover:shadow-sm'"
                                @click="createForm.style = style.val"
                            >
                                <span class="text-2xl mb-1 filter drop-shadow-sm transform transition-transform duration-300" 
                                      :class="createForm.style === style.val ? 'scale-110' : 'group-hover:scale-110'">
                                    {{ style.icon }}
                                </span>
                                <span class="font-bold text-xs text-slate-700 text-center">{{ style.label }}</span>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Requirements Input -->
                <div class="space-y-3">
                    <label class="text-sm font-bold text-slate-700 flex items-center gap-2 select-none">
                        <div class="w-6 h-6 rounded-lg bg-emerald-50 text-emerald-500 flex items-center justify-center shadow-sm border border-emerald-100">
                            <el-icon :size="14"><ChatLineSquare /></el-icon>
                        </div>
                        额外要求
                    </label>
                    <el-input 
                        v-model="createForm.requirements" 
                        type="textarea" 
                        :rows="3" 
                        placeholder="例如：侧重历史发展，或者多一些代码示例..." 
                        resize="none"
                        class="!bg-white shadow-sm hover:shadow transition-shadow duration-300"
                    />
                </div>
            </el-form>
        </div>
        
        <div class="px-8 py-6 border-t border-slate-100 bg-slate-50/80 backdrop-blur flex justify-between items-center">
            <div class="text-xs text-slate-400 font-medium px-2">
                 预计耗时: <span class="text-slate-600 font-bold">30-60秒</span>
            </div>
            <div class="flex gap-3">
                <el-button @click="createDialogVisible = false" class="!rounded-xl !px-6 !h-11 !text-slate-600 hover:!text-slate-800 !bg-white hover:!bg-slate-50 !border-slate-200 hover:!border-slate-300 shadow-sm hover:shadow transition-all">取消</el-button>
                <el-button type="primary" @click="handleCreateConfirm" :loading="courseStore.loading" class="!rounded-xl !px-8 !h-11 !bg-gradient-to-r !from-indigo-500 !to-violet-600 !border-none shadow-lg shadow-indigo-500/30 hover:shadow-indigo-500/50 hover:-translate-y-0.5 active:translate-y-0 transition-all font-bold tracking-wide">
                    <el-icon class="mr-2 animate-pulse"><MagicStick /></el-icon> 开始生成
                </el-button>
            </div>
        </div>
      </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted, computed, reactive } from 'vue'
import { useCourseStore } from '../stores/course'
import { useRouter } from 'vue-router'
import { ElTree, ElMessage, ElPopconfirm, ElMessageBox } from 'element-plus'
import { Plus, Search, CircleClose, Collection, Delete, Notebook, ArrowLeft, Loading, Edit, VideoPlay, VideoPause, MagicStick, Document, Fold, Location, Clock, Check, Close, Trophy, ChatLineSquare } from '@element-plus/icons-vue'
import { BookOpen, Hash, FileText, Circle } from 'lucide-vue-next'

const courseStore = useCourseStore()
const router = useRouter()
const emit = defineEmits(['update:preferredWidth', 'node-selected', 'toggle-sidebar'])

const filterText = ref('')
const notesDialogVisible = ref(false)
const treeRef = ref<InstanceType<typeof ElTree>>()
const treeContentRef = ref<HTMLElement | null>(null)
let resizeObserver: ResizeObserver | null = null

// Helper functions for Notes
const flatNodeMap = computed(() => {
    const map = new Map<string, string>()
    const traverse = (nodes: any[]) => {
        for (const node of nodes) {
            map.set(node.node_id, node.node_name)
            if (node.children) traverse(node.children)
        }
    }
    traverse(courseStore.courseTree)
    return map
})

const getNodeName = (nodeId: string) => {
    return flatNodeMap.value.get(nodeId) || '未知章节'
}

const formatDate = (timestamp: number) => {
    if (!timestamp) return ''
    return new Date(timestamp).toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    })
}

const setupResizeObserver = (el: HTMLElement) => {
    if (resizeObserver) resizeObserver.disconnect()
    
    resizeObserver = new ResizeObserver((entries) => {
        window.requestAnimationFrame(() => {
            for (const entry of entries) {
                // Measure intrinsic content width
                // Add padding (24px for p-3) + safety buffer (20px)
                const width = entry.contentRect.width + 44
                emit('update:preferredWidth', width)
            }
        })
    })
    
    resizeObserver.observe(el)
}

watch(treeContentRef, (el) => {
    if (el) {
        setupResizeObserver(el)
    } else {
        if (resizeObserver) {
            resizeObserver.disconnect()
            resizeObserver = null
        }
    }
})

onUnmounted(() => {
    if (resizeObserver) resizeObserver.disconnect()
})

const defaultProps = {
  children: 'children',
  label: 'node_name',
}

const getIcon = (level: number) => {
    switch(level) {
        case 1: return BookOpen;
        case 2: return Hash;
        case 3: return FileText;
        default: return Circle;
    }
}

// Watch for external current node changes (e.g. from scroll spy)
watch(() => courseStore.currentNode, (newNode) => {
    if (newNode && treeRef.value) {
        treeRef.value.setCurrentKey(newNode.node_id)
        
        // Optional: Auto-scroll sidebar to keep active node in view
         // Use nextTick to ensure DOM is updated
         setTimeout(() => {
             if (treeRef.value && treeRef.value.$el) {
                 const currentEl = treeRef.value.$el.querySelector('.el-tree-node.is-current')
                 if (currentEl) {
                     currentEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
                 }
             }
         }, 100)
    }
})

watch(filterText, (val) => {
  treeRef.value!.filter(val)
})

const filterNode = (value: string, data: any) => {
  if (!value) return true
  return data.node_name.toLowerCase().includes(value.toLowerCase())
}

const highlightSearch = (label: string) => {
    if (!filterText.value) return label
    const reg = new RegExp(filterText.value, 'gi')
    return label.replace(reg, (match) => `<span class="text-primary-600 font-bold bg-yellow-100 rounded px-0.5">${match}</span>`)
}

const handleNodeClick = (data: any) => {
  // Update current node in store
  courseStore.selectNode(data)
  
  // Trigger scroll in ContentArea
  courseStore.scrollToNode(data.node_id)

  // Mobile UX: Close sidebar on selection
  if (window.innerWidth < 768) {
      emit('node-selected', data)
  }
}

const handleAdd = (data: any) => {
    ElMessageBox.prompt('请输入新节点名称', '添加子节点', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空'
    }).then((res: any) => {
        const { value } = res
        courseStore.addCustomNode(data.node_id, value)
    }).catch(() => {})
}

const handleGenerate = async (data: any) => {
    if (courseStore.isGenerating) {
        ElMessage.warning('正在生成中，请稍后')
        return
    }
    await courseStore.generateNodeContent(data.node_id)
}

const handleRename = (data: any) => {
    ElMessageBox.prompt('请输入新名称', '重命名', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValue: data.node_name,
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空'
    }).then((res: any) => {
        const { value } = res
        courseStore.renameNode(data.node_id, value)
    }).catch(() => {})
}

const handleDelete = (data: any) => {
    courseStore.deleteNode(data.node_id)
}

const createDialogVisible = ref(false)
const createForm = reactive({
    keyword: '',
    difficulty: 'medium',
    style: 'academic',
    requirements: ''
})

const createNewCourse = () => {
    // Reset form
    createForm.keyword = ''
    createForm.difficulty = 'medium'
    createForm.style = 'academic'
    createForm.requirements = ''
    createDialogVisible.value = true
}

const handleCreateConfirm = async () => {
    if (!createForm.keyword.trim()) {
        ElMessage.warning('请输入课程主题')
        return
    }
    createDialogVisible.value = false
    
    // Trigger generation with options
    await courseStore.generateCourse(createForm.keyword, {
        difficulty: createForm.difficulty,
        style: createForm.style,
        requirements: createForm.requirements
    })
    
    // Navigate to the new course route to persist state
    if (courseStore.currentCourseId) {
        router.push(`/course/${courseStore.currentCourseId}`)
    }
}

const handleCourseClick = async (courseId: string) => {
    // Navigate to course route
    router.push(`/course/${courseId}`)
}

const handleDeleteCourse = async (courseId: string) => {
    await courseStore.deleteCourse(courseId)
}

const backToCourses = () => {
    // Navigate back to home (course list)
    router.push('/')
}
</script>

<style scoped>
:deep(.el-tree) {
    background: transparent;
}
:deep(.el-tree-node__content) {
    height: auto;
    background-color: transparent !important;
    padding: 6px 0; /* Increased padding */
    margin-bottom: 6px;
    border-radius: 12px;
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}
:deep(.el-tree-node:focus > .el-tree-node__content) {
    background-color: transparent !important;
}

/* Custom Scrollbar */
.custom-scrollbar::-webkit-scrollbar {
    width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
    background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
    background: rgba(148, 163, 184, 0.2);
    border-radius: 10px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: rgba(148, 163, 184, 0.4);
}

/* Tree Lines - Refined */
:deep(.el-tree-node__children) {
    border-left: 2px dashed rgba(203, 213, 225, 0.6); /* More visible dashed line */
    margin-left: 22px; 
    padding-left: 4px;
    transition: border-color 0.3s;
}

:deep(.el-tree-node__children:hover) {
    border-left-color: rgba(139, 92, 246, 0.4); /* Highlight line on hover */
}

/* Node Appearance Animation */
:deep(.el-tree-node) {
    animation: slideIn 0.4s ease-out;
}

@keyframes slideIn {
    from { opacity: 0; transform: translateX(-10px); }
    to { opacity: 1; transform: translateX(0); }
}

/* Transition Animations */
.fade-slide-enter-active,
.fade-slide-leave-active {
    transition: all 0.3s ease;
}

.fade-slide-enter-from {
    opacity: 0;
    transform: translateX(-10px);
}

.fade-slide-leave-to {
    opacity: 0;
    transform: translateX(10px);
}

.glass-panel-tech-floating {
    background: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(20px) saturate(180%);
    border: 1px solid rgba(255, 255, 255, 0.6);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.04);
}

.glass-card-tech-hover {
    background: rgba(255, 255, 255, 0.5);
    border: 1px solid rgba(255, 255, 255, 0.5);
    backdrop-filter: blur(10px);
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.glass-card-tech-hover:hover {
    background: rgba(255, 255, 255, 0.8);
    border-color: rgba(255, 255, 255, 0.8);
    transform: translateY(-2px);
    box-shadow: 0 12px 30px -4px rgba(0, 0, 0, 0.08);
}
</style>
