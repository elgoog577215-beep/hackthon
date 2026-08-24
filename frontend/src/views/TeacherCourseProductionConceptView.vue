<template>
  <section class="teacher-production-concept">
    <header class="product-bar">
      <button type="button" class="brand-link" aria-label="返回课程库" @click="router.push({ name: 'teacher-course-library' })">
        <img src="/qizhi-favicon.svg" alt="" />
        <strong>启智</strong>
      </button>

      <div class="breadcrumbs" aria-label="当前位置">
        <button type="button" @click="router.push({ name: 'teacher-course-library' })">课程工作台</button>
        <ChevronRight :size="14" />
        <button type="button" @click="activeNav = 'overview'">设计思维与创新设计</button>
        <ChevronRight :size="14" />
        <span>{{ activeNavLabel }}</span>
      </div>

      <div class="product-actions">
        <button type="button" class="quiet-button" @click="previewStudent">
          <Eye :size="16" />
          预览学生版
        </button>
        <el-dropdown trigger="click" @command="handleMoreCommand">
          <button type="button" class="icon-button" aria-label="更多操作" title="更多操作">
            <Ellipsis :size="18" />
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="duplicate">复制本学期结构</el-dropdown-item>
              <el-dropdown-item command="export">导出课程清单</el-dropdown-item>
              <el-dropdown-item command="settings">课程设置</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <div class="workspace-grid">
      <aside class="course-sidebar" aria-label="课程功能">
        <div class="course-identity">
          <span class="course-identity__mark">设</span>
          <div>
            <strong>设计思维与创新设计</strong>
            <span>2026 春夏</span>
          </div>
        </div>

        <nav class="course-nav">
          <button
            v-for="item in courseNavItems"
            :key="item.key"
            type="button"
            :class="{ active: activeNav === item.key }"
            :aria-current="activeNav === item.key ? 'page' : undefined"
            @click="activeNav = item.key"
          >
            <component :is="item.icon" :size="17" />
            <span>{{ item.label }}</span>
            <small v-if="item.count">{{ item.count }}</small>
          </button>
        </nav>

        <div class="sidebar-footer">
          <button type="button" @click="router.push('/workspace-concept/modes')">
            <ArrowLeft :size="15" />
            返回交互方案
          </button>
        </div>
      </aside>

      <main class="course-surface">
        <header class="course-status-bar" aria-label="课程状态">
          <strong>设计思维与创新设计</strong>
          <span>32讲</span>
          <span>教案完成 18</span>
          <span>PPT确认 16</span>
          <span>待处理 4</span>
          <span class="next-class"><CalendarClock :size="14" />下次：3月12日 · 第09讲</span>
          <button type="button" @click="activeNav = 'production'; selectLesson(9)">准备第09讲<ArrowRight :size="14" /></button>
        </header>

        <div v-if="activeNav === 'production'" class="production-layout">
          <aside class="lesson-rail" aria-label="课程讲次">
            <div class="lesson-rail__toolbar">
              <strong>课程讲次</strong>
              <span>{{ filteredLessons.length }}/{{ lessons.length }}</span>
              <el-tooltip content="搜索讲次" placement="bottom">
                <button type="button" class="mini-icon-button" aria-label="搜索讲次" @click="searchOpen = !searchOpen">
                  <Search :size="15" />
                </button>
              </el-tooltip>
            </div>

            <label v-if="searchOpen" class="lesson-search">
              <Search :size="14" />
              <input v-model="lessonQuery" type="search" placeholder="标题或讲次" autofocus />
            </label>

            <div class="lesson-filters" role="group" aria-label="讲次筛选">
              <button type="button" :class="{ active: lessonFilter === 'all' }" @click="lessonFilter = 'all'">全部</button>
              <button type="button" :class="{ active: lessonFilter === 'attention' }" @click="lessonFilter = 'attention'">待处理</button>
            </div>

            <el-scrollbar class="lesson-scroll">
              <ol class="lesson-list">
                <li v-for="lesson in filteredLessons" :key="lesson.number">
                  <button
                    type="button"
                    :class="{ active: selectedLessonNumber === lesson.number }"
                    @click="selectLesson(lesson.number)"
                  >
                    <span class="lesson-number">{{ String(lesson.number).padStart(2, '0') }}</span>
                    <span class="lesson-copy">
                      <strong>{{ lesson.title }}</strong>
                      <small>{{ lesson.date }} · {{ lesson.type }}</small>
                    </span>
                    <span class="lesson-state" :data-state="lesson.state" :title="lessonStateLabel(lesson.state)">
                      <Check v-if="lesson.state === 'ready'" :size="13" />
                      <TriangleAlert v-else-if="lesson.state === 'attention'" :size="13" />
                      <CircleDashed v-else :size="13" />
                    </span>
                  </button>
                </li>
              </ol>
            </el-scrollbar>
          </aside>

          <section class="artifact-workspace" aria-label="当前讲次内容">
            <header class="artifact-header">
              <div>
                <div class="artifact-title-line">
                  <span>第{{ String(selectedLesson.number).padStart(2, '0') }}讲</span>
                  <h1>{{ selectedLesson.title }}</h1>
                  <em>{{ selectedLesson.type }}</em>
                </div>
                <p>{{ selectedLesson.date }} {{ selectedLesson.time }} · {{ selectedLesson.room }}</p>
              </div>
              <div class="artifact-actions">
                <button type="button" class="quiet-button" @click="openImport">
                  <Upload :size="15" />导入
                </button>
                <button type="button" class="quiet-button" @click="openBlank">
                  <FilePlus2 :size="15" />新建
                </button>
                <button type="button" class="primary-button" @click="openGeneration">
                  <Sparkles :size="15" />AI生成
                </button>
                <input ref="fileInput" class="sr-only" type="file" accept=".doc,.docx,.pdf,.ppt,.pptx" @change="handleFileSelected" />
              </div>
            </header>

            <nav class="artifact-tabs" role="tablist" aria-label="讲次材料">
              <button
                v-for="tab in artifactTabs"
                :key="tab.key"
                type="button"
                role="tab"
                :aria-selected="activeArtifact === tab.key"
                :class="{ active: activeArtifact === tab.key }"
                @click="selectArtifact(tab.key)"
              >
                <component :is="tab.icon" :size="16" />
                <span>{{ tab.label }}</span>
                <small :data-state="artifactState(tab.key)">{{ artifactStateLabel(tab.key) }}</small>
              </button>
            </nav>

            <div class="artifact-body">
              <template v-if="activeArtifact === 'outline'">
                <div class="document-toolbar">
                  <span><Link2 :size="14" />来源：教学大纲 v3 · 第{{ selectedLesson.number }}讲</span>
                  <button type="button" @click="editMode = !editMode"><Pencil :size="14" />{{ editMode ? '完成编辑' : '编辑片段' }}</button>
                </div>
                <article class="outline-document">
                  <header>
                    <span>教学内容</span>
                    <strong>{{ selectedLesson.title }}</strong>
                  </header>
                  <section>
                    <h2>本讲内容</h2>
                    <p :contenteditable="editMode" :class="{ editable: editMode }">
                      {{ selectedLesson.outline }}
                    </p>
                  </section>
                  <dl>
                    <div><dt>建议学时</dt><dd>2 学时</dd></div>
                    <div><dt>教学形式</dt><dd>{{ selectedLesson.type }}</dd></div>
                    <div><dt>关联日历</dt><dd>{{ selectedLesson.date }}</dd></div>
                  </dl>
                </article>
              </template>

              <template v-else-if="activeArtifact === 'plan'">
                <div class="document-toolbar">
                  <span><FileText :size="14" />第{{ selectedLesson.number }}讲教案 · 工作稿 v3</span>
                  <div>
                    <button type="button" @click="editMode = !editMode"><Pencil :size="14" />{{ editMode ? '结束编辑' : '编辑' }}</button>
                    <button type="button" @click="saveDraft"><Save :size="14" />保存草稿</button>
                  </div>
                </div>

                <article class="plan-document">
                  <section class="plan-summary-row">
                    <dl>
                      <div><dt>教学对象</dt><dd>本科生 · 通识核心课</dd></div>
                      <div><dt>课时</dt><dd>2 学时</dd></div>
                      <div><dt>授课方式</dt><dd>线下课堂</dd></div>
                    </dl>
                  </section>

                  <section class="plan-section">
                    <header><span>01</span><h2>教学目标</h2></header>
                    <div class="plan-lines" :contenteditable="editMode" :class="{ editable: editMode }">
                      <p><strong>知识目标</strong>理解本讲核心概念以及它在完整课程中的位置。</p>
                      <p><strong>能力目标</strong>能够把本讲方法应用到真实问题并形成可讨论的方案。</p>
                    </div>
                  </section>

                  <section class="plan-section">
                    <header><span>02</span><h2>重点与难点</h2></header>
                    <div class="plan-lines" :contenteditable="editMode" :class="{ editable: editMode }">
                      <p><strong>重点</strong>{{ selectedLesson.focus }}</p>
                      <p><strong>难点</strong>将抽象方法转化为可验证、可迭代的课堂实践。</p>
                    </div>
                  </section>

                  <section class="plan-section plan-sequence">
                    <header><span>03</span><h2>教学过程</h2></header>
                    <ol>
                      <li><time>10分钟</time><strong>案例引入</strong><span>从真实案例提出本讲核心问题</span></li>
                      <li><time>35分钟</time><strong>知识讲解</strong><span>围绕概念、方法和典型误区展开</span></li>
                      <li><time>30分钟</time><strong>课堂讨论</strong><span>小组分析并汇报初步判断</span></li>
                      <li><time>15分钟</time><strong>总结与任务</strong><span>回收关键结论并布置下一步任务</span></li>
                    </ol>
                  </section>
                </article>
              </template>

              <template v-else>
                <div class="document-toolbar">
                  <span><Presentation :size="14" />本讲课件</span>
                  <button type="button" @click="ElMessage.info('模拟页保留现有 PPT 工作台入口')"><ExternalLink :size="14" />打开PPT工作台</button>
                </div>
                <div class="ppt-list">
                  <button type="button" class="ppt-row" @click="ElMessage.success('已打开第06讲主课件模拟预览')">
                    <span class="ppt-thumb"><Presentation :size="22" /></span>
                    <span><strong>第{{ String(selectedLesson.number).padStart(2, '0') }}讲主课件</strong><small>18页 · 教学版 · 2小时前更新</small></span>
                    <em>工作稿 v3</em>
                    <ChevronRight :size="17" />
                  </button>
                  <button type="button" class="ppt-row is-empty" @click="openGeneration">
                    <span class="ppt-thumb"><Plus :size="22" /></span>
                    <span><strong>补充课件</strong><small>导入已有PPT，或基于本讲教案生成</small></span>
                    <em>尚未创建</em>
                    <ChevronRight :size="17" />
                  </button>
                </div>
              </template>
            </div>
          </section>

          <aside class="context-panel" aria-label="状态与版本">
            <template v-if="panelMode === 'status'">
              <header class="context-panel__header">
                <strong>状态与版本</strong>
                <el-tooltip content="刷新状态" placement="bottom">
                  <button type="button" class="mini-icon-button" aria-label="刷新状态" @click="refreshStatus"><RefreshCw :size="14" /></button>
                </el-tooltip>
              </header>

              <section class="status-section">
                <div><span>当前材料</span><strong>{{ activeArtifactLabel }}</strong></div>
                <div><span>工作版本</span><strong>v3 草稿</strong></div>
                <div><span>教师确认</span><strong>v2</strong></div>
                <div><span>学生发布</span><strong>v1</strong></div>
              </section>

              <section class="context-section">
                <header><strong>生成依据</strong><button type="button" @click="openGeneration">调整</button></header>
                <ul class="source-list">
                  <li><FileCheck2 :size="15" /><span>教学大纲 v3</span><small>主要依据</small></li>
                  <li><BookOpenText :size="15" /><span>课程教材.pdf</span><small>参考</small></li>
                  <li><Files :size="15" /><span>去年教案.docx</span><small>参考</small></li>
                </ul>
              </section>

              <section class="context-section">
                <header><strong>版本记录</strong><button type="button" @click="ElMessage.info('已展开完整版本记录')">全部</button></header>
                <ol class="version-list">
                  <li class="current"><span></span><div><strong>工作稿 v3</strong><small>今天 10:42 · 你</small></div></li>
                  <li><span></span><div><strong>确认版 v2</strong><small>3月8日 · 你</small></div></li>
                  <li><span></span><div><strong>学生版 v1</strong><small>3月5日 · 已发布</small></div></li>
                </ol>
              </section>

              <footer class="context-actions">
                <button type="button" @click="confirmLesson">确认本讲</button>
                <button type="button" class="primary" @click="ElMessage.success('模拟：已进入发布影响检查')">发布学生版</button>
              </footer>
            </template>

            <template v-else-if="panelMode === 'generate'">
              <header class="context-panel__header">
                <div><small>AI生成</small><strong>{{ activeArtifactLabel }}</strong></div>
                <button type="button" class="mini-icon-button" aria-label="关闭生成设置" @click="panelMode = 'status'"><X :size="15" /></button>
              </header>

              <section class="generation-form">
                <label>
                  <span>主要依据</span>
                  <select v-model="generationForm.primarySource">
                    <option>教学大纲 v3</option>
                    <option>当前教案 v3</option>
                  </select>
                </label>

                <fieldset>
                  <legend>参考资料</legend>
                  <label><input v-model="generationForm.materials" type="checkbox" value="教材" />课程教材.pdf</label>
                  <label><input v-model="generationForm.materials" type="checkbox" value="旧教案" />去年教案.docx</label>
                  <label><input v-model="generationForm.materials" type="checkbox" value="案例" />课堂案例.pdf</label>
                </fieldset>

                <label>
                  <span>本次要求</span>
                  <textarea v-model="generationForm.instruction" rows="4" placeholder="例如：加强课堂案例，控制在2学时内" />
                </label>
              </section>

              <div v-if="generationState !== 'idle'" class="generation-progress" role="status">
                <span><LoaderCircle v-if="generationState === 'running'" class="spin" :size="15" /><Check v-else :size="15" />{{ generationProgressLabel }}</span>
                <el-progress :percentage="generationProgress" :stroke-width="5" :show-text="false" />
              </div>

              <footer class="context-actions">
                <button type="button" @click="panelMode = 'status'">取消</button>
                <button type="button" class="primary" :disabled="generationState === 'running'" @click="startGeneration">
                  {{ generationState === 'running' ? '生成中' : generationState === 'done' ? '重新生成草稿' : '生成新草稿' }}
                </button>
              </footer>
            </template>

            <template v-else>
              <header class="context-panel__header">
                <div><small>新建空白</small><strong>{{ activeArtifactLabel }}</strong></div>
                <button type="button" class="mini-icon-button" aria-label="关闭新建面板" @click="panelMode = 'status'"><X :size="15" /></button>
              </header>
              <section class="blank-form">
                <label><span>文件名称</span><input v-model="blankName" /></label>
                <div><span>保存位置</span><strong>课程文件 / {{ selectedLesson.number }}、{{ selectedLesson.title }}</strong></div>
                <div><span>创建后</span><strong>自动关联第{{ selectedLesson.number }}讲</strong></div>
              </section>
              <footer class="context-actions">
                <button type="button" @click="panelMode = 'status'">取消</button>
                <button type="button" class="primary" @click="createBlank">创建并打开</button>
              </footer>
            </template>
          </aside>
        </div>

        <section v-else class="secondary-view">
          <header>
            <div><span>{{ secondaryView.eyebrow }}</span><h1>{{ secondaryView.title }}</h1></div>
            <button type="button" class="primary-button" @click="ElMessage.success(secondaryView.actionMessage)"><Plus :size="15" />{{ secondaryView.action }}</button>
          </header>
          <div class="secondary-table">
            <button v-for="row in secondaryView.rows" :key="row.title" type="button" @click="ElMessage.info(`已打开：${row.title}`)">
              <component :is="row.icon" :size="18" />
              <span><strong>{{ row.title }}</strong><small>{{ row.meta }}</small></span>
              <em :data-tone="row.tone">{{ row.state }}</em>
              <ChevronRight :size="17" />
            </button>
          </div>
        </section>
      </main>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, ArrowRight, BookOpenText, CalendarClock, CalendarDays, Check, ChevronRight,
  CircleDashed, ClipboardList, Ellipsis, ExternalLink, Eye, FileCheck2, FilePlus2,
  Files, FileText, FolderOpen, LayoutDashboard, Link2, LoaderCircle, Pencil, Plus,
  Presentation, RefreshCw, Save, Search, Sparkles, TriangleAlert, Upload, Users,
  X,
} from 'lucide-vue-next'

type NavKey = 'overview' | 'planning' | 'production' | 'files' | 'students'
type ArtifactKey = 'outline' | 'plan' | 'ppt'
type LessonState = 'ready' | 'attention' | 'empty'
type PanelMode = 'status' | 'generate' | 'blank'

interface LessonItem {
  number: number
  title: string
  date: string
  time: string
  room: string
  type: string
  state: LessonState
  outline: string
  focus: string
}

const router = useRouter()
const fileInput = ref<HTMLInputElement | null>(null)
const activeNav = ref<NavKey>('production')
const activeArtifact = ref<ArtifactKey>('plan')
const selectedLessonNumber = ref(6)
const lessonFilter = ref<'all' | 'attention'>('all')
const lessonQuery = ref('')
const searchOpen = ref(false)
const editMode = ref(false)
const panelMode = ref<PanelMode>('status')
const generationState = ref<'idle' | 'running' | 'done'>('idle')
const generationProgress = ref(0)
const blankName = ref('第06讲教案')

const generationForm = ref({
  primarySource: '教学大纲 v3',
  materials: ['教材', '旧教案'],
  instruction: '保持课堂节奏清晰，补充一个真实案例。',
})

const courseNavItems = [
  { key: 'overview' as const, label: '课程概览', icon: LayoutDashboard },
  { key: 'planning' as const, label: '课程规划', icon: CalendarDays, count: '2' },
  { key: 'production' as const, label: '课程生产', icon: ClipboardList, count: '4' },
  { key: 'files' as const, label: '课程文件', icon: FolderOpen },
  { key: 'students' as const, label: '学生与反馈', icon: Users, count: '12' },
]

const artifactTabs = [
  { key: 'outline' as const, label: '大纲片段', icon: Link2 },
  { key: 'plan' as const, label: '教案', icon: FileText },
  { key: 'ppt' as const, label: 'PPT', icon: Presentation },
]

const lessons = ref<LessonItem[]>([
  { number: 1, title: '课程概述', date: '2月26日', time: '08:00—09:50', room: '西1-301', type: '理论', state: 'ready', outline: '介绍课程内容体系、学习方式、考核要求及设计思维基本概念。', focus: '建立对课程整体结构与设计思维的初步认识。' },
  { number: 2, title: '设计思维第一印象', date: '2月28日', time: '13:30—15:20', room: '东2-102', type: '讨论', state: 'ready', outline: '结合个人兴趣与案例分享对设计思维的第一印象，并完成课程破冰。', focus: '从学生经验出发形成对设计思维的共同理解。' },
  { number: 3, title: '设计思维导论与实践', date: '3月5日', time: '08:00—09:50', room: '西1-301', type: '理论', state: 'ready', outline: '认识设计思维的特点、应用价值、代表性观点以及基本实践步骤。', focus: '理解设计思维从发现问题到验证方案的基本过程。' },
  { number: 4, title: '身边的设计思维', date: '3月7日', time: '13:30—15:20', room: '东2-102', type: '讨论', state: 'attention', outline: '分享生活中的设计思维案例，分析其创新点和用户价值。', focus: '从日常产品中识别需求、方案和价值之间的关系。' },
  { number: 5, title: '需求理解与问题定义', date: '3月10日', time: '08:00—09:50', room: '西1-301', type: '理论', state: 'ready', outline: '学习观察、问卷、访谈、同理心地图和观点陈述等需求研究方法。', focus: '把模糊需求转化为清晰、可验证的问题定义。' },
  { number: 6, title: '大作业理解与解读', date: '3月12日', time: '08:00—09:50', room: '西1-301', type: '实践', state: 'attention', outline: '结合案例理解课程大作业要求，明确选题价值、研究边界和后续推进方式。', focus: '帮助学生形成有意义、有价值且具备实践空间的选题。' },
  { number: 7, title: '思维发散与原型设计', date: '3月17日', time: '08:00—09:50', room: '西1-301', type: '理论', state: 'empty', outline: '学习思维发散、方案归纳、快速原型以及低成本验证方法。', focus: '用结构化方法产生、筛选并快速表达方案。' },
  { number: 8, title: '选题分享', date: '3月19日', time: '13:30—15:20', room: '东2-102', type: '实践', state: 'attention', outline: '各组分享选题，围绕问题意义、用户价值和实施边界进行问答。', focus: '通过展示和反馈确定值得持续推进的问题。' },
  { number: 9, title: '模型迭代与产品发布', date: '3月24日', time: '08:00—09:50', room: '西1-301', type: '理论', state: 'attention', outline: '介绍原型测试、模型迭代、设计工具与产品发布的基本方式。', focus: '根据测试证据持续修正产品模型和发布表达。' },
  { number: 10, title: '开题分享', date: '3月26日', time: '13:30—15:20', room: '东2-102', type: '实践', state: 'empty', outline: '各组进行开题分享，并围绕创新性、社会价值和实施路径接受问答。', focus: '形成结构完整、目标明确的项目开题方案。' },
  { number: 11, title: '设计驱动式创新', date: '3月31日', time: '08:00—09:50', room: '西1-301', type: '理论', state: 'empty', outline: '理解设计驱动创新的价值、方法以及典型应用场景。', focus: '理解意义创新如何改变产品定位与用户体验。' },
  { number: 12, title: '进展分享', date: '4月2日', time: '13:30—15:20', room: '东2-102', type: '实践', state: 'empty', outline: '提交阶段成果并进行抽查分享，检验问题理解和初步解决方案。', focus: '发现当前方案中的证据缺口和执行风险。' },
])

const activeNavLabel = computed(() => courseNavItems.find(item => item.key === activeNav.value)?.label || '课程生产')
const selectedLesson = computed(() => lessons.value.find(item => item.number === selectedLessonNumber.value) || lessons.value[0]!)
const activeArtifactLabel = computed(() => artifactTabs.find(item => item.key === activeArtifact.value)?.label || '教案')
const filteredLessons = computed(() => lessons.value.filter(lesson => {
  const matchesFilter = lessonFilter.value === 'all' || lesson.state !== 'ready'
  const query = lessonQuery.value.trim().toLowerCase()
  const matchesQuery = !query || lesson.title.toLowerCase().includes(query) || String(lesson.number).includes(query)
  return matchesFilter && matchesQuery
}))
const generationProgressLabel = computed(() => generationState.value === 'done' ? '新草稿已生成' : `正在生成${activeArtifactLabel.value}`)

const secondaryViews = {
  overview: {
    eyebrow: '课程概览', title: '当前需要处理的事项', action: '更新课程信息', actionMessage: '课程信息已进入编辑状态',
    rows: [
      { title: '准备第09讲', meta: '3月24日 · 教案待确认', state: '待处理', tone: 'warning', icon: CalendarClock },
      { title: '确认教学日历', meta: '32讲已安排30讲', state: '缺2讲', tone: 'warning', icon: CalendarDays },
      { title: '查看学生反馈', meta: '第05讲收到12条反馈', state: '12条', tone: 'brand', icon: Users },
    ],
  },
  planning: {
    eyebrow: '课程规划', title: '大纲与教学日历', action: '导入规划文件', actionMessage: '已打开规划文件导入入口',
    rows: [
      { title: '教学大纲', meta: '32讲 · 当前确认版 v3', state: '已确认', tone: 'success', icon: BookOpenText },
      { title: '教学日历', meta: '30/32讲已安排日期', state: '待补齐', tone: 'warning', icon: CalendarDays },
    ],
  },
  files: {
    eyebrow: '课程文件', title: '课程资料', action: '上传文件', actionMessage: '已打开文件上传入口',
    rows: [
      { title: '0、教学大纲', meta: '1个受管文档', state: '已同步', tone: 'success', icon: FolderOpen },
      { title: '1、教案', meta: '18份教案 · 4份待处理', state: '18份', tone: 'brand', icon: FolderOpen },
      { title: '2、PPT', meta: '16份课件', state: '16份', tone: 'brand', icon: FolderOpen },
      { title: '6、教学日历', meta: '1个受管文档', state: '已同步', tone: 'success', icon: FolderOpen },
    ],
  },
  students: {
    eyebrow: '学生与反馈', title: '需要教师判断的反馈', action: '查看全部反馈', actionMessage: '已进入全部学生反馈',
    rows: [
      { title: '第05讲 · 问题定义', meta: '12名学生在同一知识点提出疑问', state: '12人', tone: 'warning', icon: Users },
      { title: '第03讲 · 设计思维导论', meta: '课程材料已发布，42人完成阅读', state: '42人', tone: 'success', icon: Users },
    ],
  },
}

const secondaryView = computed(() => secondaryViews[activeNav.value as keyof typeof secondaryViews] || secondaryViews.overview)

function lessonStateLabel(state: LessonState) {
  return state === 'ready' ? '材料已确认' : state === 'attention' ? '需要处理' : '尚未准备'
}

function artifactState(key: ArtifactKey) {
  if (key === 'outline') return 'ready'
  if (key === 'plan') return selectedLesson.value.state === 'empty' ? 'empty' : 'draft'
  return selectedLesson.value.number % 3 === 1 ? 'empty' : 'ready'
}

function artifactStateLabel(key: ArtifactKey) {
  const state = artifactState(key)
  return state === 'ready' ? '已确认' : state === 'draft' ? '草稿 v3' : '未创建'
}

function selectLesson(number: number) {
  selectedLessonNumber.value = number
  blankName.value = `第${String(number).padStart(2, '0')}讲${activeArtifact.value === 'ppt' ? 'PPT' : '教案'}`
  panelMode.value = 'status'
  editMode.value = false
}

function selectArtifact(key: ArtifactKey) {
  activeArtifact.value = key
  blankName.value = `第${String(selectedLesson.value.number).padStart(2, '0')}讲${key === 'ppt' ? 'PPT' : key === 'outline' ? '大纲片段' : '教案'}`
  panelMode.value = 'status'
  editMode.value = false
}

function openImport() {
  fileInput.value?.click()
}

function handleFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const lesson = lessons.value.find(item => item.number === selectedLessonNumber.value)
  if (lesson) lesson.state = 'attention'
  ElMessage.success(`已识别“${file.name}”，作为${activeArtifactLabel.value}导入当前讲次`)
  input.value = ''
}

function openGeneration() {
  panelMode.value = 'generate'
  generationState.value = 'idle'
  generationProgress.value = 0
}

function openBlank() {
  panelMode.value = 'blank'
}

function createBlank() {
  const lesson = lessons.value.find(item => item.number === selectedLessonNumber.value)
  if (lesson) lesson.state = 'attention'
  panelMode.value = 'status'
  editMode.value = true
  ElMessage.success(`已创建“${blankName.value}”并关联第${selectedLesson.value.number}讲`)
}

function startGeneration() {
  generationState.value = 'running'
  generationProgress.value = 18
  window.setTimeout(() => { generationProgress.value = 58 }, 420)
  window.setTimeout(() => { generationProgress.value = 86 }, 820)
  window.setTimeout(() => {
    generationProgress.value = 100
    generationState.value = 'done'
    const lesson = lessons.value.find(item => item.number === selectedLessonNumber.value)
    if (lesson) lesson.state = 'attention'
    ElMessage.success(`${activeArtifactLabel.value}新草稿已生成，正式版本未改变`)
  }, 1250)
}

function saveDraft() {
  editMode.value = false
  ElMessage.success('草稿已保存')
}

async function confirmLesson() {
  try {
    await ElMessageBox.confirm(
      `确认第${selectedLesson.value.number}讲${activeArtifactLabel.value}为教师确认版？学生当前发布版不会自动改变。`,
      '确认本讲',
      { confirmButtonText: '确认版本', cancelButtonText: '取消', type: 'warning' },
    )
    const lesson = lessons.value.find(item => item.number === selectedLessonNumber.value)
    if (lesson) lesson.state = 'ready'
    ElMessage.success('已产生新的教师确认版')
  } catch {
    // The teacher cancelled the simulated confirmation.
  }
}

function refreshStatus() {
  ElMessage.success('状态已刷新')
}

function previewStudent() {
  ElMessage.info('学生当前看到第01—05讲的已发布版本')
}

function handleMoreCommand(command: string) {
  const labels: Record<string, string> = {
    duplicate: '已进入复制课程结构流程',
    export: '已准备课程清单导出',
    settings: '已打开课程设置',
  }
  ElMessage.info(labels[command] || '操作已触发')
}
</script>

<style scoped>
.teacher-production-concept {
  width: 100%;
  height: 100vh;
  display: grid;
  grid-template-rows: 52px minmax(0, 1fr);
  overflow: hidden;
  color: var(--lz-text);
  background: #f5f7fb;
  font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
}

button,
input,
select,
textarea { font: inherit; }
button { cursor: pointer; }

.product-bar {
  position: relative;
  z-index: 10;
  min-width: 0;
  display: grid;
  grid-template-columns: 188px minmax(0, 1fr) auto;
  align-items: center;
  border-bottom: 1px solid var(--lz-border);
  background: rgba(255, 255, 255, .97);
}

.brand-link {
  height: 100%;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 18px;
  border: 0;
  border-right: 1px solid var(--lz-border);
  color: #001081;
  background: transparent;
}
.brand-link img { width: 29px; height: 29px; }
.brand-link strong { font-size: 17px; font-weight: 850; letter-spacing: .08em; }

.breadcrumbs {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 16px;
  color: var(--lz-text-muted);
  font-size: 12px;
  overflow: hidden;
}
.breadcrumbs button,
.breadcrumbs span {
  min-width: 0;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.breadcrumbs button { padding: 5px 7px; border: 0; border-radius: 6px; color: var(--lz-text-secondary); background: transparent; }
.breadcrumbs button:hover { color: var(--lz-brand-strong); background: var(--lz-brand-soft); }
.breadcrumbs span { color: var(--lz-text-strong); font-weight: 700; }

.product-actions { display: flex; align-items: center; gap: 5px; padding-right: 12px; }
.quiet-button,
.primary-button,
.icon-button,
.mini-icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  color: var(--lz-text-secondary);
  background: transparent;
}
.quiet-button { min-height: 32px; gap: 6px; padding: 0 10px; border-color: var(--lz-border); border-radius: 8px; background: #fff; font-size: 12px; font-weight: 700; }
.quiet-button:hover { color: var(--lz-brand-strong); border-color: #d8ddff; background: #f8f9ff; }
.primary-button { min-height: 34px; gap: 6px; padding: 0 12px; border-radius: 8px; color: #fff; background: var(--lz-brand-strong); font-size: 12px; font-weight: 750; }
.primary-button:hover { background: #4338ca; }
.icon-button { width: 34px; height: 34px; border-radius: 8px; }
.icon-button:hover,
.mini-icon-button:hover { color: var(--lz-brand-strong); background: var(--lz-brand-soft); }
.mini-icon-button { width: 28px; height: 28px; border-radius: 7px; }

.workspace-grid { min-width: 0; min-height: 0; display: grid; grid-template-columns: 188px minmax(0, 1fr); }
.course-sidebar { min-height: 0; display: grid; grid-template-rows: auto minmax(0, 1fr) auto; border-right: 1px solid var(--lz-border); background: #fbfcfe; }
.course-identity { min-width: 0; display: flex; align-items: center; gap: 10px; padding: 15px 14px 13px; border-bottom: 1px solid var(--lz-border); }
.course-identity__mark { width: 34px; height: 34px; display: grid; flex: 0 0 auto; place-items: center; border-radius: 9px; color: var(--lz-brand-strong); background: var(--lz-brand-soft); font-size: 14px; font-weight: 850; }
.course-identity div { min-width: 0; display: grid; gap: 2px; }
.course-identity strong { overflow: hidden; color: var(--lz-text-strong); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.course-identity span { color: var(--lz-text-muted); font-size: 10px; }

.course-nav { display: grid; align-content: start; gap: 3px; padding: 10px 8px; }
.course-nav button { min-height: 38px; display: grid; grid-template-columns: 24px minmax(0, 1fr) auto; align-items: center; gap: 6px; padding: 0 10px; border: 0; border-radius: 8px; color: var(--lz-text-secondary); background: transparent; text-align: left; font-size: 12px; font-weight: 700; }
.course-nav button:hover { color: var(--lz-text-strong); background: #f1f4f9; }
.course-nav button.active { color: var(--lz-brand-strong); background: var(--lz-brand-soft); }
.course-nav small { min-width: 20px; padding: 2px 5px; border-radius: 999px; color: var(--lz-text-muted); background: #eef1f6; text-align: center; font-size: 9px; }
.course-nav button.active small { color: var(--lz-brand-strong); background: #fff; }
.sidebar-footer { padding: 8px; border-top: 1px solid var(--lz-border); }
.sidebar-footer button { width: 100%; min-height: 34px; display: flex; align-items: center; gap: 7px; padding: 0 10px; border: 0; border-radius: 7px; color: var(--lz-text-muted); background: transparent; font-size: 11px; }
.sidebar-footer button:hover { color: var(--lz-text-secondary); background: #f1f4f9; }

.course-surface { min-width: 0; min-height: 0; display: grid; grid-template-rows: 42px minmax(0, 1fr); overflow: hidden; background: #fff; }
.course-status-bar { min-width: 0; display: flex; align-items: center; gap: 0; padding: 0 14px; border-bottom: 1px solid var(--lz-border); background: #fff; overflow: hidden; }
.course-status-bar > strong { margin-right: 4px; color: var(--lz-text-strong); font-size: 12px; white-space: nowrap; }
.course-status-bar > span { display: inline-flex; align-items: center; gap: 5px; padding: 0 10px; border-left: 1px solid #edf0f5; color: var(--lz-text-secondary); font-size: 11px; white-space: nowrap; }
.course-status-bar .next-class { margin-left: auto; color: var(--lz-brand-strong); }
.course-status-bar button { display: inline-flex; align-items: center; gap: 4px; margin-left: 8px; padding: 5px 8px; border: 0; border-radius: 6px; color: var(--lz-brand-strong); background: var(--lz-brand-soft); font-size: 11px; font-weight: 750; white-space: nowrap; }

.production-layout { min-width: 0; min-height: 0; display: grid; grid-template-columns: 224px minmax(420px, 1fr) 252px; overflow: hidden; }
.lesson-rail { min-width: 0; min-height: 0; display: grid; grid-template-rows: 42px auto auto minmax(0, 1fr); border-right: 1px solid var(--lz-border); background: #fafbfc; }
.lesson-rail__toolbar { display: grid; grid-template-columns: minmax(0, 1fr) auto 28px; align-items: center; gap: 6px; padding: 0 10px 0 13px; border-bottom: 1px solid #edf0f5; }
.lesson-rail__toolbar strong { color: var(--lz-text-strong); font-size: 12px; }
.lesson-rail__toolbar > span { color: var(--lz-text-muted); font-size: 10px; }
.lesson-search { height: 36px; display: flex; align-items: center; gap: 6px; margin: 8px 8px 0; padding: 0 8px; border: 1px solid var(--lz-border); border-radius: 7px; color: var(--lz-text-muted); background: #fff; }
.lesson-search:focus-within { border-color: #a5b4fc; box-shadow: 0 0 0 3px rgba(99, 102, 241, .08); }
.lesson-search input { min-width: 0; flex: 1; border: 0; outline: 0; color: var(--lz-text); background: transparent; font-size: 11px; }
.lesson-filters { display: flex; gap: 3px; padding: 8px; }
.lesson-filters button { min-height: 26px; padding: 0 9px; border: 0; border-radius: 6px; color: var(--lz-text-muted); background: transparent; font-size: 10px; }
.lesson-filters button.active { color: var(--lz-brand-strong); background: var(--lz-brand-soft); font-weight: 750; }
.lesson-scroll { min-height: 0; }
.lesson-list { display: grid; gap: 2px; margin: 0; padding: 0 6px 10px; list-style: none; }
.lesson-list button { width: 100%; min-height: 50px; display: grid; grid-template-columns: 31px minmax(0, 1fr) 24px; align-items: center; gap: 7px; padding: 5px 7px; border: 1px solid transparent; border-radius: 8px; color: var(--lz-text-secondary); background: transparent; text-align: left; }
.lesson-list button:hover { border-color: #e5e9f1; background: #fff; }
.lesson-list button.active { border-color: #d8ddff; color: var(--lz-text-strong); background: #fff; box-shadow: 0 2px 8px rgba(79, 70, 229, .06); }
.lesson-number { color: var(--lz-text-muted); font-size: 10px; font-weight: 800; }
.lesson-list button.active .lesson-number { color: var(--lz-brand-strong); }
.lesson-copy { min-width: 0; display: grid; gap: 3px; }
.lesson-copy strong { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.lesson-copy small { color: var(--lz-text-muted); font-size: 9px; }
.lesson-state { width: 20px; height: 20px; display: grid; place-items: center; border-radius: 999px; }
.lesson-state[data-state="ready"] { color: var(--lz-success); background: var(--lz-success-soft); }
.lesson-state[data-state="attention"] { color: var(--lz-warning); background: var(--lz-warning-soft); }
.lesson-state[data-state="empty"] { color: var(--lz-text-muted); background: #eef1f6; }

.artifact-workspace { min-width: 0; min-height: 0; display: grid; grid-template-rows: 64px 43px minmax(0, 1fr); overflow: hidden; }
.artifact-header { min-width: 0; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 0 15px 0 18px; border-bottom: 1px solid var(--lz-border); }
.artifact-header > div:first-child { min-width: 0; }
.artifact-title-line { min-width: 0; display: flex; align-items: center; gap: 7px; }
.artifact-title-line > span { color: var(--lz-brand-strong); font-size: 10px; font-weight: 800; }
.artifact-title-line h1 { min-width: 0; margin: 0; overflow: hidden; color: var(--lz-text-strong); font-size: 16px; text-overflow: ellipsis; white-space: nowrap; }
.artifact-title-line em { flex: 0 0 auto; padding: 2px 6px; border-radius: 5px; color: var(--lz-text-secondary); background: #f0f2f6; font-size: 9px; font-style: normal; }
.artifact-header p { margin: 4px 0 0; color: var(--lz-text-muted); font-size: 10px; }
.artifact-actions { flex: 0 0 auto; display: flex; gap: 5px; }
.artifact-actions .primary-button { min-height: 32px; }

.artifact-tabs { display: flex; align-items: end; gap: 18px; padding: 0 18px; border-bottom: 1px solid var(--lz-border); }
.artifact-tabs button { position: relative; height: 42px; display: flex; align-items: center; gap: 6px; padding: 0; border: 0; color: var(--lz-text-muted); background: transparent; font-size: 11px; }
.artifact-tabs button::after { content: ""; position: absolute; right: 0; bottom: -1px; left: 0; height: 2px; background: transparent; }
.artifact-tabs button.active { color: var(--lz-brand-strong); font-weight: 750; }
.artifact-tabs button.active::after { background: var(--lz-brand-strong); }
.artifact-tabs small { padding: 2px 5px; border-radius: 5px; background: #f1f3f7; color: var(--lz-text-muted); font-size: 8px; }
.artifact-tabs small[data-state="ready"] { color: var(--lz-success); background: var(--lz-success-soft); }
.artifact-tabs small[data-state="draft"] { color: var(--lz-warning); background: var(--lz-warning-soft); }

.artifact-body { min-height: 0; overflow: auto; background: #fff; }
.document-toolbar { position: sticky; top: 0; z-index: 2; min-height: 38px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 16px; border-bottom: 1px solid #edf0f5; background: rgba(250, 251, 253, .96); }
.document-toolbar span,
.document-toolbar div { display: flex; align-items: center; gap: 6px; color: var(--lz-text-muted); font-size: 10px; }
.document-toolbar button { min-height: 26px; display: inline-flex; align-items: center; gap: 5px; padding: 0 7px; border: 0; border-radius: 6px; color: var(--lz-text-secondary); background: transparent; font-size: 10px; }
.document-toolbar button:hover { color: var(--lz-brand-strong); background: var(--lz-brand-soft); }

.outline-document,
.plan-document { width: min(760px, calc(100% - 36px)); margin: 18px auto 30px; }
.outline-document > header { display: grid; gap: 5px; padding-bottom: 14px; border-bottom: 1px solid var(--lz-border); }
.outline-document > header span { color: var(--lz-text-muted); font-size: 10px; }
.outline-document > header strong { color: var(--lz-text-strong); font-size: 18px; }
.outline-document section { padding: 18px 0; }
.outline-document h2,
.plan-section h2 { margin: 0; color: var(--lz-text-strong); font-size: 13px; }
.outline-document p { margin: 9px 0 0; color: var(--lz-text); font-size: 13px; line-height: 1.85; }
.outline-document dl,
.plan-summary-row dl { display: grid; grid-template-columns: repeat(3, 1fr); margin: 0; border-top: 1px solid var(--lz-border); border-bottom: 1px solid var(--lz-border); }
.outline-document dl div,
.plan-summary-row dl div { padding: 11px 12px; border-right: 1px solid var(--lz-border); }
.outline-document dl div:last-child,
.plan-summary-row dl div:last-child { border-right: 0; }
.outline-document dt,
.plan-summary-row dt { margin-bottom: 4px; color: var(--lz-text-muted); font-size: 9px; }
.outline-document dd,
.plan-summary-row dd { margin: 0; color: var(--lz-text-strong); font-size: 11px; font-weight: 700; }

.plan-document { display: grid; gap: 0; }
.plan-summary-row { margin-bottom: 8px; }
.plan-section { display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: 20px; padding: 17px 0; border-bottom: 1px solid #edf0f5; }
.plan-section > header { display: flex; align-items: baseline; gap: 7px; }
.plan-section > header span { color: var(--lz-brand); font-size: 10px; font-weight: 850; }
.plan-lines { display: grid; gap: 9px; outline: none; }
.plan-lines p { display: grid; grid-template-columns: 70px minmax(0, 1fr); gap: 10px; margin: 0; color: var(--lz-text); font-size: 12px; line-height: 1.65; }
.plan-lines p strong { color: var(--lz-text-secondary); font-size: 10px; }
.editable { border-radius: 6px; outline: 2px solid rgba(99, 102, 241, .16); outline-offset: 5px; }
.plan-sequence ol { display: grid; gap: 0; margin: 0; padding: 0; list-style: none; }
.plan-sequence li { display: grid; grid-template-columns: 54px 80px minmax(0, 1fr); align-items: baseline; gap: 9px; padding: 8px 0; border-bottom: 1px dashed #e7eaf0; color: var(--lz-text-secondary); font-size: 11px; }
.plan-sequence li:last-child { border-bottom: 0; }
.plan-sequence time { color: var(--lz-brand-strong); font-size: 9px; font-weight: 750; }
.plan-sequence strong { color: var(--lz-text-strong); }

.ppt-list { display: grid; margin: 0; }
.ppt-row { min-height: 70px; display: grid; grid-template-columns: 48px minmax(0, 1fr) auto 22px; align-items: center; gap: 12px; padding: 10px 18px; border: 0; border-bottom: 1px solid #edf0f5; color: var(--lz-text-secondary); background: #fff; text-align: left; }
.ppt-row:hover { background: #fafbff; }
.ppt-thumb { width: 44px; height: 34px; display: grid; place-items: center; border-radius: 6px; color: var(--lz-brand-strong); background: var(--lz-brand-soft); }
.ppt-row.is-empty .ppt-thumb { color: var(--lz-text-muted); background: #f1f3f6; }
.ppt-row > span:nth-child(2) { min-width: 0; display: grid; gap: 4px; }
.ppt-row strong { color: var(--lz-text-strong); font-size: 12px; }
.ppt-row small { color: var(--lz-text-muted); font-size: 10px; }
.ppt-row em { padding: 3px 7px; border-radius: 5px; color: var(--lz-warning); background: var(--lz-warning-soft); font-size: 9px; font-style: normal; }
.ppt-row.is-empty em { color: var(--lz-text-muted); background: #f1f3f6; }

.context-panel { min-width: 0; min-height: 0; display: grid; grid-template-rows: auto auto auto minmax(0, 1fr) auto; overflow: hidden; border-left: 1px solid var(--lz-border); background: #fbfcfe; }
.context-panel__header { min-height: 48px; display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 0 12px 0 14px; border-bottom: 1px solid var(--lz-border); }
.context-panel__header > div { display: grid; gap: 1px; }
.context-panel__header strong { color: var(--lz-text-strong); font-size: 12px; }
.context-panel__header small { color: var(--lz-text-muted); font-size: 9px; }
.status-section { display: grid; grid-template-columns: 1fr 1fr; border-bottom: 1px solid var(--lz-border); }
.status-section div { display: grid; gap: 4px; padding: 10px 12px; border-right: 1px solid #edf0f5; border-bottom: 1px solid #edf0f5; }
.status-section div:nth-child(even) { border-right: 0; }
.status-section div:nth-last-child(-n+2) { border-bottom: 0; }
.status-section span,
.blank-form span { color: var(--lz-text-muted); font-size: 9px; }
.status-section strong,
.blank-form strong { color: var(--lz-text-strong); font-size: 10px; }
.context-section { padding: 12px 13px; border-bottom: 1px solid var(--lz-border); }
.context-section > header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 9px; }
.context-section > header strong { color: var(--lz-text-strong); font-size: 10px; }
.context-section > header button { padding: 0; border: 0; color: var(--lz-brand-strong); background: transparent; font-size: 9px; }
.source-list,
.version-list { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.source-list li { display: grid; grid-template-columns: 20px minmax(0, 1fr) auto; align-items: center; gap: 5px; color: var(--lz-text-secondary); font-size: 10px; }
.source-list small { color: var(--lz-text-muted); font-size: 8px; }
.version-list li { display: grid; grid-template-columns: 10px minmax(0, 1fr); gap: 7px; }
.version-list li > span { width: 7px; height: 7px; margin-top: 4px; border: 2px solid #cbd2dd; border-radius: 999px; }
.version-list li.current > span { border-color: var(--lz-brand); background: var(--lz-brand); }
.version-list div { display: grid; gap: 2px; }
.version-list strong { color: var(--lz-text-secondary); font-size: 10px; }
.version-list small { color: var(--lz-text-muted); font-size: 8px; }
.context-actions { align-self: end; display: grid; grid-template-columns: 1fr 1.3fr; gap: 7px; padding: 10px; border-top: 1px solid var(--lz-border); background: #fff; }
.context-actions button { min-height: 34px; border: 1px solid var(--lz-border); border-radius: 7px; color: var(--lz-text-secondary); background: #fff; font-size: 10px; font-weight: 750; }
.context-actions button.primary { border-color: var(--lz-brand-strong); color: #fff; background: var(--lz-brand-strong); }
.context-actions button:disabled { cursor: not-allowed; opacity: .6; }

.generation-form { min-height: 0; display: grid; align-content: start; gap: 13px; padding: 14px; overflow: auto; }
.generation-form > label,
.blank-form label { display: grid; gap: 6px; }
.generation-form label > span,
.generation-form legend,
.blank-form label > span { color: var(--lz-text-secondary); font-size: 10px; font-weight: 700; }
.generation-form select,
.generation-form textarea,
.blank-form input { width: 100%; border: 1px solid var(--lz-border); border-radius: 7px; outline: 0; color: var(--lz-text); background: #fff; font-size: 10px; }
.generation-form select,
.blank-form input { height: 34px; padding: 0 8px; }
.generation-form textarea { resize: vertical; padding: 8px; line-height: 1.5; }
.generation-form select:focus,
.generation-form textarea:focus,
.blank-form input:focus { border-color: #a5b4fc; box-shadow: 0 0 0 3px rgba(99, 102, 241, .08); }
.generation-form fieldset { display: grid; gap: 7px; margin: 0; padding: 10px; border: 1px solid var(--lz-border); border-radius: 8px; }
.generation-form fieldset label { display: flex; align-items: center; gap: 7px; color: var(--lz-text-secondary); font-size: 10px; }
.generation-form input[type="checkbox"] { accent-color: var(--lz-brand); }
.generation-progress { display: grid; gap: 6px; padding: 10px 14px; border-top: 1px solid var(--lz-border); }
.generation-progress > span { display: flex; align-items: center; gap: 6px; color: var(--lz-brand-strong); font-size: 10px; font-weight: 700; }
.blank-form { display: grid; align-content: start; gap: 14px; padding: 14px; }
.blank-form > div { display: grid; gap: 4px; padding-bottom: 11px; border-bottom: 1px solid #edf0f5; }

.secondary-view { min-height: 0; overflow: auto; background: #fff; }
.secondary-view > header { min-height: 68px; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 0 18px; border-bottom: 1px solid var(--lz-border); }
.secondary-view > header div { display: grid; gap: 2px; }
.secondary-view > header span { color: var(--lz-text-muted); font-size: 9px; }
.secondary-view > header h1 { margin: 0; color: var(--lz-text-strong); font-size: 16px; }
.secondary-table { display: grid; }
.secondary-table > button { min-height: 64px; display: grid; grid-template-columns: 30px minmax(0, 1fr) auto 24px; align-items: center; gap: 12px; padding: 8px 18px; border: 0; border-bottom: 1px solid #edf0f5; color: var(--lz-text-secondary); background: #fff; text-align: left; }
.secondary-table > button:hover { background: #fafbff; }
.secondary-table > button > span { display: grid; gap: 4px; }
.secondary-table strong { color: var(--lz-text-strong); font-size: 12px; }
.secondary-table small { color: var(--lz-text-muted); font-size: 10px; }
.secondary-table em { padding: 3px 7px; border-radius: 5px; font-size: 9px; font-style: normal; }
.secondary-table em[data-tone="success"] { color: var(--lz-success); background: var(--lz-success-soft); }
.secondary-table em[data-tone="warning"] { color: var(--lz-warning); background: var(--lz-warning-soft); }
.secondary-table em[data-tone="brand"] { color: var(--lz-brand-strong); background: var(--lz-brand-soft); }

.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.spin { animation: spin .9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 1180px) {
  .production-layout { grid-template-columns: 210px minmax(420px, 1fr); }
  .context-panel { position: absolute; z-index: 8; top: 94px; right: 0; bottom: 0; width: 268px; border-left: 1px solid var(--lz-border); box-shadow: -14px 0 30px rgba(30, 41, 59, .08); }
  .artifact-workspace { padding-right: 268px; }
  .course-surface { position: relative; }
}

@media (max-width: 880px) {
  .product-bar { grid-template-columns: 150px minmax(0, 1fr) auto; }
  .brand-link { padding: 0 12px; }
  .workspace-grid { grid-template-columns: 156px minmax(0, 1fr); }
  .course-sidebar { width: 156px; }
  .course-identity { padding-inline: 10px; }
  .course-status-bar > span:not(.next-class) { display: none; }
  .production-layout { grid-template-columns: 194px minmax(360px, 1fr); }
  .artifact-header { align-items: flex-start; padding-top: 9px; }
  .artifact-actions .quiet-button { display: none; }
  .artifact-workspace { padding-right: 0; }
  .context-panel { display: none; }
}

@media (max-width: 680px) {
  .teacher-production-concept { grid-template-rows: 48px minmax(0, 1fr); }
  .product-bar { grid-template-columns: auto minmax(0, 1fr) auto; }
  .brand-link { width: 52px; border-right: 0; }
  .brand-link strong { display: none; }
  .breadcrumbs button:first-child,
  .breadcrumbs svg:first-of-type,
  .product-actions .quiet-button { display: none; }
  .workspace-grid { grid-template-columns: 1fr; grid-template-rows: 46px minmax(0, 1fr); }
  .course-sidebar { width: 100%; grid-template-rows: 1fr; border-right: 0; border-bottom: 1px solid var(--lz-border); }
  .course-identity,
  .sidebar-footer { display: none; }
  .course-nav { display: grid; grid-template-columns: repeat(5, 1fr); gap: 2px; padding: 5px; }
  .course-nav button { min-height: 34px; grid-template-columns: 1fr; justify-items: center; gap: 0; padding: 0 3px; font-size: 9px; }
  .course-nav button svg,
  .course-nav small { display: none; }
  .course-status-bar { padding-inline: 8px; }
  .course-status-bar > strong { max-width: 125px; overflow: hidden; text-overflow: ellipsis; }
  .course-status-bar .next-class { margin-left: auto; }
  .course-status-bar button { display: none; }
  .production-layout { grid-template-columns: 1fr; grid-template-rows: 174px minmax(0, 1fr); }
  .lesson-rail { grid-template-rows: 36px auto minmax(0, 1fr); border-right: 0; border-bottom: 1px solid var(--lz-border); }
  .lesson-filters { display: none; }
  .lesson-list { grid-auto-flow: column; grid-auto-columns: 172px; overflow-x: auto; padding: 5px 7px 8px; }
  .lesson-list button { min-height: 48px; }
  .artifact-workspace { grid-template-rows: auto 42px minmax(0, 1fr); }
  .artifact-header { min-height: 70px; align-items: center; padding: 7px 10px; }
  .artifact-actions .primary-button { padding-inline: 9px; }
  .artifact-tabs { gap: 13px; padding-inline: 12px; }
  .artifact-tabs small { display: none; }
  .outline-document,
  .plan-document { width: calc(100% - 24px); margin-top: 12px; }
  .plan-section { grid-template-columns: 1fr; gap: 10px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; animation-duration: .001ms !important; animation-iteration-count: 1 !important; }
}
</style>
