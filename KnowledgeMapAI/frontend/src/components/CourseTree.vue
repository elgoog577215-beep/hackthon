<template>
  <div class="h-full flex flex-col relative bg-gradient-to-br from-slate-50/50 to-white/30">
    
    <!-- MODE 1: COURSE LIST -->
    <transition name="fade-slide" mode="out-in">
      <div v-if="!courseStore.currentCourseId" class="flex flex-col h-full" key="list">
        <div class="mx-3 mt-3 mb-1 px-4 py-3 flex justify-between items-center flex-shrink-0 glass-panel-tech-floating rounded-xl z-10 relative">
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

        <!-- List Content - Optimized Scrollbar -->
        <div class="flex-1 overflow-y-auto overflow-x-hidden p-3 sidebar-scroll space-y-2.5 scroll-smooth pr-2">
            <div 
                v-for="(course, index) in courseStore.courseList" 
                :key="course.course_id" 
                class="animate-fade-in-up"
                :style="{ animationDelay: (index * 50) + 'ms' }"
            >
                <div 
                    class="group relative p-3.5 rounded-lg glass-card-tech-hover cursor-pointer overflow-hidden h-full"
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

             <!-- Enhanced Empty State -->
            <div v-if="courseStore.courseList.length === 0 && !courseStore.loading" class="flex flex-col items-center justify-center h-64 animate-fade-in-up p-6">
                <div class="glass-panel p-8 flex flex-col items-center text-center max-w-[280px]">
                    <div class="w-16 h-16 rounded-xl bg-gradient-to-br from-primary-100 to-primary-50 border border-primary-200 flex items-center justify-center mb-5 relative">
                        <el-icon :size="28" class="text-primary-600"><Notebook /></el-icon>
                        <div class="absolute -top-1 -right-1 w-4 h-4 bg-primary-500 rounded-full flex items-center justify-center">
                            <el-icon :size="10" class="text-white"><Plus /></el-icon>
                        </div>
                    </div>
                    <h3 class="text-base font-semibold text-slate-800 mb-2">开始您的学习之旅</h3>
                    <p class="text-sm text-slate-500 mb-5 leading-relaxed">创建第一个课程，让 AI 为您构建完整的知识图谱</p>
                    <button 
                        class="glass-button-primary w-full flex items-center justify-center gap-2" 
                        @click="createNewCourse"
                    >
                        <el-icon :size="16"><Plus /></el-icon>
                        <span>新建课程</span>
                    </button>
                    <div class="mt-4 flex items-center gap-2 text-xs text-slate-400">
                        <el-icon :size="12"><InfoFilled /></el-icon>
                        <span>支持 PDF、Markdown 导入</span>
                    </div>
                </div>
            </div>
            
            <!-- Enhanced Loading State -->
            <div v-if="courseStore.loading && courseStore.courseList.length === 0" class="flex flex-col items-center justify-center h-60">
                <div class="flex flex-col items-center gap-4">
                    <!-- Clean Spinner -->
                    <div class="relative w-12 h-12">
                        <div class="absolute inset-0 rounded-full border-2 border-slate-200"></div>
                        <div class="absolute inset-0 rounded-full border-2 border-primary-500 border-t-transparent animate-spin"></div>
                    </div>
                    <div class="flex flex-col items-center gap-1">
                        <span class="text-sm font-medium text-slate-600">加载中...</span>
                        <span class="text-xs text-slate-400">正在获取课程数据</span>
                    </div>
                </div>
            </div>
        </div>
      </div>
    

      <!-- MODE 2: TREE VIEW -->
      <div v-else class="flex flex-col h-full" key="tree">
        <!-- Compact Header - Optimized -->
        <div class="mx-3 mt-3 mb-2 h-14 px-3 flex gap-2 items-center justify-between flex-shrink-0 glass-panel-tech-floating rounded-xl z-10 relative box-border">
          
          <div class="flex items-center gap-1">
            <!-- Collapse Button -->
            <button 
                class="flex-shrink-0 w-7 h-7 glass-card-tech-hover !p-0 !rounded-lg !border-white/50 text-slate-500 hover:text-primary-600 flex items-center justify-center group"
                @click="$emit('toggle-sidebar')"
                title="收起侧边栏"
            >
                <el-icon :size="14"><Fold /></el-icon>
            </button>

            <!-- Back Button -->
            <button 
                class="flex-shrink-0 w-7 h-7 glass-card-tech-hover !p-0 !rounded-lg !border-white/50 text-slate-500 hover:text-primary-600 flex items-center justify-center group"
                @click="backToCourses"
                title="返回课程列表"
            >
                <el-icon :size="14" class="group-hover:-translate-x-0.5 transition-transform"><ArrowLeft /></el-icon>
            </button>

            <!-- Notes Button -->
            <button 
                class="flex-shrink-0 w-7 h-7 glass-card-tech-hover !p-0 !rounded-lg !border-white/50 text-slate-500 hover:text-amber-500 flex items-center justify-center group"
                @click="notesDialogVisible = true"
                title="课程笔记"
            >
                <el-icon :size="14"><Document /></el-icon>
            </button>
          </div>

          <!-- Search Input - Beautiful Design -->
          <div class="relative flex-1 min-w-0">
            <div class="flex items-center bg-white rounded-lg h-8 shadow-sm border border-slate-200/60 transition-all duration-300 focus-within:shadow-[0_0_15px_rgba(139,92,246,0.2)] focus-within:border-primary-300/50 hover:shadow-md hover:border-slate-300/60">
                <div class="pl-2.5 pr-1.5 text-slate-400 transition-colors duration-300">
                     <el-icon :size="14"><Search /></el-icon>
                </div>
                <input 
                    v-model="filterText"
                    type="text"
                    placeholder="搜索章节..."
                    class="flex-1 bg-transparent border-none outline-none focus:outline-none focus:ring-0 text-xs text-slate-600 placeholder:text-slate-400/70 h-full pr-7"
                />
                <button 
                    v-if="filterText" 
                    class="absolute right-1.5 text-slate-400 hover:text-slate-600 transition-colors"
                    @click="filterText = ''"
                >
                    <el-icon :size="12"><CircleClose /></el-icon>
                </button>
            </div>
          </div>
        </div>
        
        <!-- Tree Content - Optimized Scrollbar -->
        <div class="flex-1 overflow-y-auto overflow-x-hidden p-3 sidebar-scroll pr-2">
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
import { Plus, Search, CircleClose, Collection, Delete, Notebook, ArrowLeft, Edit, VideoPlay, VideoPause, MagicStick, Document, Fold, Location, Clock, Check, Close, Trophy, ChatLineSquare, InfoFilled } from '@element-plus/icons-vue'
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

// Smart width calculation based on content
const calculateOptimalWidth = () => {
    // Helper: calculate text width
    const calculateTextWidth = (text: string): number => {
        let width = 0
        for (const char of text) {
            // Check if Chinese character
            if (/[\u4e00-\u9fa5]/.test(char)) {
                width += 14
            } else {
                width += 8
            }
        }
        return width
    }

    // Mode 1: Course List View
    if (!courseStore.currentCourseId) {
        const courseNames = courseStore.courseList.map(c => c.course_name)
        if (courseNames.length === 0) return 260

        let maxWidth = 0
        courseNames.forEach(name => {
            // Course name + "章节" badge + actions + padding
            const textWidth = calculateTextWidth(name)
            // Icon (32px) + gap (12px) + badge (~60px) + actions (~80px) + padding (48px)
            const width = textWidth + 32 + 12 + 60 + 80 + 48
            maxWidth = Math.max(maxWidth, width)
        })

        return Math.max(260, Math.min(maxWidth, 340))
    }

    // Mode 2: Tree View
    const getAllNodeNames = (nodes: any[]): string[] => {
        let names: string[] = []
        for (const node of nodes) {
            names.push(node.node_name)
            if (node.children && node.children.length > 0) {
                names = names.concat(getAllNodeNames(node.children))
            }
        }
        return names
    }

    const nodeNames = getAllNodeNames(courseStore.courseTree)
    if (nodeNames.length === 0) return 260

    let maxWidth = 0
    nodeNames.forEach(name => {
        const textWidth = calculateTextWidth(name)
        // Add space for icon (24px) + indent (16px per level) + padding (40px) + actions (60px)
        const level = (name.match(/\./g) || []).length + 1
        const width = textWidth + 24 + (level * 16) + 40 + 60
        maxWidth = Math.max(maxWidth, width)
    })

    // Add safety buffer for scrollbar and margins
    maxWidth += 20

    // Constrain within reasonable bounds
    // Min: 240px (enough for short names), Max: 380px (prevent too wide)
    return Math.max(240, Math.min(maxWidth, 380))
}

const setupResizeObserver = (el: HTMLElement) => {
    if (resizeObserver) resizeObserver.disconnect()
    
    resizeObserver = new ResizeObserver((entries) => {
        window.requestAnimationFrame(() => {
            for (const entry of entries) {
                // Use smart width calculation
                const optimalWidth = calculateOptimalWidth()
                emit('update:preferredWidth', optimalWidth)
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

// Watch for course list changes to auto-adjust width
watch(() => courseStore.courseList.length, () => {
    if (!courseStore.currentCourseId) {
        // In course list mode, recalculate width
        const optimalWidth = calculateOptimalWidth()
        emit('update:preferredWidth', optimalWidth)
    }
}, { immediate: true })

// Watch for tree data changes to auto-adjust width
watch(() => courseStore.courseTree.length, () => {
    if (courseStore.currentCourseId) {
        // In tree view mode, recalculate width
        setTimeout(() => {
            const optimalWidth = calculateOptimalWidth()
            emit('update:preferredWidth', optimalWidth)
        }, 100) // Delay to ensure DOM is updated
    }
}, { immediate: true })

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
