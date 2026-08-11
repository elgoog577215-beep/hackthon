<template>
  <main class="portal" :class="`portal--${page}`">
    <header class="portal-header">
      <button class="portal-brand" type="button" @click="openHome">
        <img src="/qizhi-favicon.svg" alt="" />
        <span><strong>启智</strong><small>智能教学与学习平台</small></span>
      </button>

      <nav class="portal-nav" aria-label="平台导航">
        <button type="button" :class="{ active: page === 'home' }" @click="openHome">首页</button>
        <button type="button" :class="{ active: page !== 'home' }" @click="openWorkbench">课程工作台</button>
        <button type="button" @click="notify('知识库入口已保留（模拟）')">知识库</button>
        <button type="button" @click="notify('AI 学习工具入口已保留（模拟）')">AI 学习工具</button>
      </nav>

      <div class="portal-account">
        <button type="button" title="搜索" @click="notify('全局搜索：课程、课件、文件与知识点')"><Search :size="17" /></button>
        <button type="button" title="通知" @click="notify('2 条提醒：第06讲待发布、12条学生反馈待处理')"><Bell :size="17" /><i /></button>
        <span>项老师</span><em>教</em>
      </div>
    </header>

    <template v-if="page === 'home'">
      <section class="home-view">
        <div class="home-intro">
          <div class="home-copy">
            <p>早上好，项老师</p>
            <h1>今天准备哪一门课？</h1>
            <span>从课程生产、资料管理到课堂反馈，都在同一个教学空间里持续积累。</span>
            <div class="home-actions">
              <button type="button" class="primary" @click="openWorkbench"><PanelsTopLeft :size="17" />进入课程工作台<ArrowRight :size="15" /></button>
              <button type="button" class="secondary" @click="openVideo"><Video :size="17" />分析一段视频</button>
            </div>
          </div>
          <aside class="today-panel">
            <header><span>今日教学</span><small>8 月 7 日 · 周五</small></header>
            <div class="today-time"><strong>10:00</strong><i /></div>
            <div><b>高等数学 · 第 6 讲</b><span>紫金港西 2-301 · 90 分钟</span></div>
            <button type="button" @click="openCourse('production')">继续备课<ArrowUpRight :size="14" /></button>
          </aside>
        </div>

        <section class="workbench-entry">
          <header>
            <div><p>核心工作区</p><h2>课程工作台</h2><span>课程是教学资产的长期容器，一门课对应大纲、分讲教案、多个 PPT 及课程文件。</span></div>
            <button type="button" @click="openSpaces">查看全部课程<ArrowRight :size="15" /></button>
          </header>
          <div class="workbench-body">
            <button class="continue-course" type="button" @click="openCourse('production')">
              <span class="course-monogram">高</span>
              <span><small>最近使用 · 2026 秋季</small><strong>高等数学</strong><em>8 / 16 讲教案已完成</em></span>
              <span class="course-progress"><i><b /></i><small>备课进度 50%</small></span>
              <ArrowUpRight :size="18" />
            </button>
            <div class="workbench-tools">
              <button type="button" @click="openSpaces"><FolderKanban :size="18" /><span><strong>课程空间</strong><small>管理全部课程与学期版本</small></span><ChevronRight :size="15" /></button>
              <button type="button" @click="openVideo"><Video :size="18" /><span><strong>视频分析</strong><small>不依赖课程，上传即可生成报告</small></span><ChevronRight :size="15" /></button>
            </div>
          </div>
        </section>

        <section class="feature-section">
          <header><div><p>更多能力</p><h2>教学与学习工具</h2></div><span>按任务进入，不要求所有功能都绑定课程。</span></header>
          <div class="feature-layout">
            <button type="button" class="feature-wide" @click="notify('知识库将在这里打开（模拟）')">
              <span class="feature-icon is-green"><LibraryBig :size="22" /></span>
              <span><strong>知识库</strong><small>沉淀学校资料、专业知识与个人收藏，供课程和 AI 按权限引用。</small></span>
              <ArrowUpRight :size="17" />
            </button>
            <button type="button" @click="notify('AI 学习工具将在这里打开（模拟）')"><span class="feature-icon is-violet"><Sparkles :size="21" /></span><span><strong>AI 学习工具</strong><small>解释、练习与学习规划</small></span></button>
            <button type="button" @click="notify('论文助手是独立功能入口（模拟）')"><span class="feature-icon is-amber"><FilePenLine :size="21" /></span><span><strong>论文助手</strong><small>独立于课程的写作工具</small></span></button>
          </div>
        </section>
      </section>
    </template>

    <template v-else-if="page === 'workbench'">
      <section class="module-view">
        <header class="module-heading">
          <button type="button" @click="openHome"><ArrowLeft :size="15" />首页</button>
          <p>课程工作台</p>
          <h1>选择今天要处理的教学任务</h1>
          <span>课程课件与视频分析是两个平级入口：前者围绕课程长期积累，后者可独立上传视频并形成报告。</span>
        </header>
        <div class="module-grid">
          <button type="button" class="module-card module-card--course" @click="openSpaces">
            <span class="module-number">01</span>
            <span class="module-visual"><FolderKanban :size="31" /><i>COURSE MATERIALS</i></span>
            <span class="module-copy"><small>按课程组织</small><strong>课程课件</strong><em>进入课程空间，管理大纲、分讲教案、多份 PPT、课程文件与发布版本。</em></span>
            <span class="module-action">进入课程空间<ArrowRight :size="16" /></span>
          </button>
          <button type="button" class="module-card module-card--video" @click="openVideo">
            <span class="module-number">02</span>
            <span class="module-visual"><Video :size="31" /><i>VIDEO ANALYSIS</i></span>
            <span class="module-copy"><small>独立工具</small><strong>视频分析</strong><em>不需要先创建或选择课程，上传任意视频后直接查看分析报告。</em></span>
            <span class="module-action">开始视频分析<ArrowRight :size="16" /></span>
          </button>
        </div>
        <aside class="module-rule"><CircleCheck :size="16" /><span><strong>层级规则：</strong>视频分析不会出现在某一门具体课程内部；进入课程课件后，才继续选择课程。</span></aside>
      </section>
    </template>

    <template v-else-if="page === 'video'">
      <section class="video-view">
        <header class="module-heading">
          <button type="button" @click="openWorkbench"><ArrowLeft :size="15" />课程工作台</button>
          <p>视频分析</p><h1>上传视频，生成一份独立分析报告</h1>
          <span>此功能不绑定任何已开设课程；需要时可在报告完成后，再把结果引用进某门课程。</span>
        </header>
        <button type="button" class="video-drop" @click="notify('将调用既有视频分析上传能力（模拟）')"><span><Video :size="32" /></span><strong>选择或拖入视频</strong><small>支持课堂录像、公开课与本地学习视频</small><em>选择视频</em></button>
      </section>
    </template>

    <template v-else-if="page === 'spaces'">
      <section class="spaces-view">
        <header class="spaces-heading">
          <div><button type="button" @click="openWorkbench"><ArrowLeft :size="15" />课程工作台</button><p>课程课件</p><h1>我的课程空间</h1><span>先选择一门课程，再进入该课程的生产、文件、发布与反馈工作台。</span></div>
          <button type="button" class="primary" @click="createOpen = !createOpen"><Plus :size="16" />新建课程</button>
        </header>

        <Transition name="reveal">
          <form v-if="createOpen" class="create-course" @submit.prevent="createCourse">
            <div><span class="create-index">01</span><span><strong>创建课程空间</strong><small>只需先填写基础信息，进入课程后再生成大纲与教学材料。</small></span></div>
            <label><span>课程名称</span><input v-model="newCourseName" autofocus placeholder="例如：概率论与数理统计" /></label>
            <label><span>学期</span><select><option>2026 秋季</option><option>2027 春季</option></select></label>
            <button type="submit" class="primary" :disabled="!newCourseName.trim()">创建并进入</button>
            <button type="button" class="secondary" @click="createOpen = false">取消</button>
          </form>
        </Transition>

        <div class="spaces-toolbar">
          <div class="space-tabs"><button type="button" class="active">进行中 <span>3</span></button><button type="button">已归档 <span>2</span></button></div>
          <label><Search :size="15" /><input v-model="courseQuery" placeholder="搜索课程" /></label>
        </div>

        <div class="course-grid">
          <button v-for="course in filteredCourses" :key="course.name" type="button" class="course-card" @click="openCourse('overview')">
            <span class="course-cover" :class="course.tone"><i>{{ course.short }}</i><small>{{ course.term }}</small></span>
            <span class="course-card-copy"><span><small>{{ course.status }}</small><em>{{ course.role }}</em></span><strong>{{ course.name }}</strong><small>{{ course.detail }}</small></span>
            <span class="course-card-foot"><span><i><b :style="{ width: course.progress }" /></i><small>{{ course.progress }}</small></span><ArrowUpRight :size="16" /></span>
          </button>
          <button type="button" class="course-card course-card--new" @click="createOpen = true"><span><Plus :size="22" /></span><strong>新建一门课程</strong><small>从课程要求开始，逐步生成大纲、教案与 PPT</small></button>
        </div>
      </section>
    </template>

    <template v-else>
      <div class="course-context-bar">
        <nav><button type="button" @click="openWorkbench">课程工作台</button><ChevronRight :size="13" /><button type="button" @click="openSpaces">课程课件</button><ChevronRight :size="13" /><strong>高等数学</strong></nav>
        <button type="button" @click="openSpaces"><LayoutGrid :size="14" />切换课程</button>
      </div>
      <div class="embedded-course"><CourseWorkspaceConceptView /></div>
    </template>

    <Transition name="toast"><div v-if="toastMessage" class="portal-toast"><CircleCheck :size="16" />{{ toastMessage }}</div></Transition>
  </main>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrowLeft, ArrowRight, ArrowUpRight, Bell, ChevronRight, CircleCheck, FilePenLine,
  FolderKanban, LayoutGrid, LibraryBig, PanelsTopLeft, Plus, Search, Sparkles, Video,
} from 'lucide-vue-next'
import CourseWorkspaceConceptView from './CourseWorkspaceConceptView.vue'

type Page = 'home' | 'workbench' | 'spaces' | 'video' | 'course'

const page = ref<Page>('home')
const createOpen = ref(false)
const newCourseName = ref('')
const courseQuery = ref('')
const toastMessage = ref('')
let toastTimer: ReturnType<typeof setTimeout> | undefined

const courses = [
  { short: '高', name: '高等数学', term: '2026 秋季', status: '备课中', role: '主讲教师', detail: '16 讲 · 教案 8 · PPT 5 · 已发布 4', progress: '50%', tone: 'is-indigo' },
  { short: '线', name: '线性代数', term: '2026 春季', status: '授课中', role: '主讲教师', detail: '12 讲 · 教案 12 · PPT 10 · 已发布 9', progress: '82%', tone: 'is-green' },
  { short: '智', name: '人工智能导论', term: '2026 秋季', status: '刚刚创建', role: '课程负责人', detail: '课程要求待确认 · 尚未生成大纲', progress: '8%', tone: 'is-amber' },
]

const filteredCourses = computed(() => {
  const query = courseQuery.value.trim()
  return query ? courses.filter(course => `${course.name}${course.term}`.includes(query)) : courses
})

function openHome() { page.value = 'home'; createOpen.value = false }
function openWorkbench() { page.value = 'workbench'; createOpen.value = false }
function openSpaces() { page.value = 'spaces' }
function openCourse(section: string) {
  page.value = 'course'
  notify(section === 'production' ? '已进入高等数学，继续上次备课位置' : '已进入高等数学课程工作台')
}
function openVideo() { page.value = 'video' }
function createCourse() {
  if (!newCourseName.value.trim()) return
  page.value = 'course'
  notify(`“${newCourseName.value.trim()}”课程空间已创建（模拟）`)
}
function notify(message: string) {
  toastMessage.value = message
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toastMessage.value = '' }, 2400)
}
</script>

<style scoped>
.portal{--ink:#172033;--muted:#68748a;--line:#e5e9f2;--brand:var(--lz-brand,#4f46e5);height:100%;min-height:0;display:grid;grid-template-rows:64px minmax(0,1fr);overflow:hidden;color:var(--ink);background:#f5f6f9;border-radius:16px;font-family:var(--font-sans,"Microsoft YaHei",sans-serif)}
button,input,select{font:inherit}.portal button{cursor:pointer}.portal-header{z-index:10;display:grid;grid-template-columns:minmax(210px,1fr) auto minmax(210px,1fr);align-items:center;gap:24px;padding:0 22px;border-bottom:1px solid var(--line);background:#fcfdff}.portal-brand{width:max-content;display:flex;align-items:center;gap:10px;padding:0;border:0;background:transparent;text-align:left}.portal-brand img{width:34px;height:34px}.portal-brand span,.portal-brand strong,.portal-brand small{display:block}.portal-brand strong{color:#001081;font-size:16px;letter-spacing:.08em}.portal-brand small{margin-top:2px;color:#8b95a6;font-size:9px}.portal-nav{height:100%;display:flex;align-items:center;gap:4px}.portal-nav button{height:100%;position:relative;padding:0 15px;border:0;color:#667085;background:transparent;font-size:12px}.portal-nav button.active{color:#30369a;font-weight:750}.portal-nav button.active::after{content:"";position:absolute;right:15px;bottom:0;left:15px;height:2px;background:var(--brand)}.portal-account{justify-self:end;display:flex;align-items:center;gap:8px;color:#59657a;font-size:11px}.portal-account>button{width:34px;height:34px;position:relative;display:grid;place-items:center;border:0;border-radius:9px;color:#69758a;background:transparent}.portal-account>button:hover{background:#f0f2f7}.portal-account button i{width:5px;height:5px;position:absolute;top:7px;right:7px;border:1px solid #fff;border-radius:50%;background:#e05c63}.portal-account>span{margin-left:5px;font-weight:700}.portal-account>em{width:30px;height:30px;display:grid;place-items:center;border-radius:9px;color:#3730a3;background:#e5e7ff;font-style:normal;font-weight:800}
.home-view,.spaces-view{min-height:0;overflow:auto}.home-view{padding:clamp(28px,4vw,54px) clamp(30px,6vw,86px) 70px;background:radial-gradient(circle at 88% 2%,rgba(79,70,229,.07),transparent 28%),#f8f9fb}.home-intro{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(320px,.65fr);gap:clamp(34px,6vw,86px);align-items:center}.home-copy p,.workbench-entry>header p,.feature-section>header p,.spaces-heading p{margin:0 0 8px;color:var(--brand);font-size:10px;font-weight:800;letter-spacing:.11em}.home-copy h1{margin:0;font-size:clamp(36px,5vw,64px);line-height:1.03;letter-spacing:-.055em}.home-copy>span{display:block;max-width:630px;margin-top:16px;color:#667085;font-size:14px;line-height:1.75}.home-actions{display:flex;gap:9px;margin-top:26px}.primary,.secondary{height:38px;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 14px;border:0;border-radius:9px;font-weight:700}.primary{color:#fff;background:var(--brand);box-shadow:0 8px 18px rgba(79,70,229,.16)}.secondary{color:#536079;background:#e9ecf2}.today-panel{display:grid;grid-template-columns:auto minmax(0,1fr);gap:10px 16px;padding:20px 22px;border:1px solid #e3e6ed;border-radius:14px;background:#fff;box-shadow:0 18px 45px rgba(30,39,59,.07)}.today-panel header{grid-column:1/-1;display:flex;justify-content:space-between;padding-bottom:12px;border-bottom:1px solid #edf0f4}.today-panel header span{font-size:12px;font-weight:750}.today-panel header small{color:#8d96a5;font-size:10px}.today-time{display:flex;align-items:center;gap:10px}.today-time strong{font-size:23px}.today-time i{width:1px;height:32px;background:#dfe3eb}.today-panel>div:nth-of-type(2) b,.today-panel>div:nth-of-type(2) span{display:block}.today-panel>div:nth-of-type(2) b{font-size:12px}.today-panel>div:nth-of-type(2) span{margin-top:5px;color:#8b94a4;font-size:9px}.today-panel>button{grid-column:2;width:max-content;display:flex;align-items:center;gap:5px;padding:0;border:0;color:#4f55b1;background:transparent;font-size:10px;font-weight:700}
.workbench-entry{margin-top:clamp(42px,6vw,72px);padding-top:28px;border-top:1px solid #e2e5eb}.workbench-entry>header,.feature-section>header{display:flex;justify-content:space-between;align-items:end;gap:30px}.workbench-entry h2,.feature-section h2,.spaces-heading h1{margin:0;font-size:clamp(24px,3vw,34px);letter-spacing:-.04em}.workbench-entry>header span{display:block;max-width:680px;margin-top:8px;color:#778194;font-size:11px;line-height:1.6}.workbench-entry>header>button{display:flex;align-items:center;gap:5px;padding:0 0 4px;border:0;color:#535bb2;background:transparent;font-size:10px;font-weight:700}.workbench-body{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(300px,.65fr);gap:14px;margin-top:19px}.continue-course{min-height:150px;display:grid;grid-template-columns:54px minmax(0,1fr) minmax(120px,.5fr) auto;align-items:center;gap:17px;padding:23px;border:1px solid #dfe3eb;border-radius:14px;background:#fff;text-align:left;box-shadow:0 10px 28px rgba(34,43,61,.05)}.continue-course:hover{border-color:#c8cdf7;transform:translateY(-1px)}.course-monogram{width:54px;height:54px;display:grid;place-items:center;border-radius:14px;color:#3730a3;background:#e5e7ff;font-size:20px;font-weight:850}.continue-course>span:nth-child(2) small,.continue-course>span:nth-child(2) strong,.continue-course>span:nth-child(2) em{display:block}.continue-course>span:nth-child(2) small{color:#8b95a6;font-size:9px}.continue-course>span:nth-child(2) strong{margin-top:5px;font-size:20px}.continue-course>span:nth-child(2) em{margin-top:6px;color:#6d788b;font-size:10px;font-style:normal}.course-progress i{height:5px;display:block;overflow:hidden;border-radius:99px;background:#e7e9ef}.course-progress b{display:block;width:50%;height:100%;background:var(--brand)}.course-progress small{display:block;margin-top:7px;color:#8992a2;font-size:9px}.workbench-tools{display:grid;gap:8px}.workbench-tools button{display:grid;grid-template-columns:36px minmax(0,1fr) auto;align-items:center;gap:10px;padding:12px;border:1px solid #e1e4eb;border-radius:12px;color:#707a8d;background:#fff;text-align:left}.workbench-tools button>svg:first-child{width:36px;height:36px;padding:9px;border-radius:9px;color:#535bb4;background:#eef0ff}.workbench-tools strong,.workbench-tools small{display:block}.workbench-tools strong{color:#424d61;font-size:11px}.workbench-tools small{margin-top:4px;color:#949cab;font-size:8px}
.feature-section{margin-top:52px}.feature-section>header>span{color:#8a94a5;font-size:10px}.feature-layout{display:grid;grid-template-columns:1.2fr .8fr .8fr;gap:10px;margin-top:17px}.feature-layout>button{min-height:108px;display:flex;align-items:center;gap:13px;padding:17px;border:1px solid #e1e4eb;border-radius:13px;color:#758095;background:#fff;text-align:left}.feature-layout>button>span:nth-child(2){flex:1}.feature-layout strong,.feature-layout small{display:block}.feature-layout strong{color:#424d61;font-size:12px}.feature-layout small{margin-top:6px;color:#8c96a6;font-size:9px;line-height:1.55}.feature-icon{width:43px;height:43px;display:grid;place-items:center;flex:none;border-radius:11px}.feature-icon.is-green{color:#176c53;background:#e6f4ee}.feature-icon.is-violet{color:#504db1;background:#eeefff}.feature-icon.is-amber{color:#94651e;background:#fff2d9}
.spaces-view{padding:clamp(30px,4vw,52px) clamp(34px,6vw,88px);background:#f8f9fb}.spaces-heading{display:flex;justify-content:space-between;align-items:end;gap:30px}.spaces-heading>div>button{display:flex;align-items:center;gap:5px;margin-bottom:22px;padding:0;border:0;color:#7c8798;background:transparent;font-size:10px}.spaces-heading>div>span{display:block;margin-top:10px;color:#717c8f;font-size:12px}.create-course{display:grid;grid-template-columns:minmax(260px,1.2fr) minmax(180px,.8fr) 160px auto auto;align-items:end;gap:10px;margin-top:22px;padding:18px;border:1px solid #dfe3eb;border-radius:12px;background:#fff}.create-course>div{display:flex;align-items:center;gap:12px}.create-course>div span:last-child,.create-course>div strong,.create-course>div small{display:block}.create-course>div small{margin-top:5px;color:#8c95a5;font-size:8px}.create-index{color:#c1c6d0;font-size:22px;font-weight:800}.create-course label span{display:block;margin-bottom:6px;color:#707b8e;font-size:9px}.create-course input,.create-course select{width:100%;height:36px;padding:0 10px;border:1px solid #dfe3eb;border-radius:8px;outline:0;background:#fafbfc;font-size:10px}.create-course input:focus{border-color:#aeb4ef;box-shadow:0 0 0 3px #f0f1ff}.create-course .primary,.create-course .secondary{font-size:10px}.create-course .primary:disabled{opacity:.45;cursor:not-allowed}.spaces-toolbar{display:flex;justify-content:space-between;align-items:center;margin-top:42px;border-bottom:1px solid #e1e4ea}.space-tabs{display:flex;gap:22px}.space-tabs button{padding:0 0 11px;border:0;border-bottom:2px solid transparent;color:#8b94a4;background:transparent;font-size:11px}.space-tabs button.active{border-color:var(--brand);color:#373d91;font-weight:750}.space-tabs span{margin-left:3px;color:#9ca4b1}.spaces-toolbar>label{width:220px;height:32px;display:flex;align-items:center;gap:7px;margin-bottom:8px;padding:0 9px;border:1px solid #e0e3e9;border-radius:8px;color:#8e97a6;background:#fff}.spaces-toolbar input{min-width:0;flex:1;border:0;outline:0;background:transparent;font-size:10px}.course-grid{display:grid;grid-template-columns:repeat(3,minmax(230px,1fr));gap:14px;margin-top:20px}.course-card{min-height:230px;display:grid;grid-template-rows:80px minmax(0,1fr) auto;padding:0;overflow:hidden;border:1px solid #dfe3eb;border-radius:13px;background:#fff;text-align:left}.course-card:hover{border-color:#c8cdf4;box-shadow:0 14px 34px rgba(36,43,64,.08);transform:translateY(-2px)}.course-cover{display:flex;justify-content:space-between;align-items:flex-start;padding:16px 18px}.course-cover i{width:42px;height:42px;display:grid;place-items:center;border-radius:12px;background:rgba(255,255,255,.75);font-style:normal;font-size:17px;font-weight:850}.course-cover small{font-size:9px}.course-cover.is-indigo{color:#353897;background:#e8e9ff}.course-cover.is-green{color:#17664f;background:#e3f2eb}.course-cover.is-amber{color:#8a5e1d;background:#faeed8}.course-card-copy{padding:16px 18px 12px}.course-card-copy>span{display:flex;justify-content:space-between}.course-card-copy>span small{color:#5d66b7}.course-card-copy em{color:#929baa;font-size:8px;font-style:normal}.course-card-copy>strong,.course-card-copy>small{display:block}.course-card-copy>strong{margin-top:8px;font-size:16px}.course-card-copy>small{margin-top:7px;color:#818b9d;font-size:9px}.course-card-foot{display:flex;justify-content:space-between;align-items:end;padding:0 18px 17px;color:#7f899a}.course-card-foot>span{width:65%}.course-card-foot i{height:4px;display:block;overflow:hidden;border-radius:99px;background:#e8eaf0}.course-card-foot b{display:block;height:100%;background:#686dcc}.course-card-foot small{display:block;margin-top:5px;color:#9aa2af;font-size:8px}.course-card--new{place-items:center;align-content:center;gap:9px;border-style:dashed;color:#8992a2;background:#fafbfc;text-align:center}.course-card--new>span{width:44px;height:44px;display:grid;place-items:center;border-radius:12px;color:#5c64b7;background:#eef0ff}.course-card--new>strong{color:#556075;font-size:12px}.course-card--new>small{max-width:210px;font-size:9px;line-height:1.5}
.portal--course{grid-template-rows:64px 40px minmax(0,1fr)}.course-context-bar{display:flex;justify-content:space-between;align-items:center;padding:0 18px;border-bottom:1px solid var(--line);background:#f7f8fb}.course-context-bar nav{display:flex;align-items:center;gap:5px;color:#929aa8;font-size:9px}.course-context-bar nav button{padding:0;border:0;color:#788397;background:transparent}.course-context-bar nav strong{color:#4a566b}.course-context-bar>button{display:flex;align-items:center;gap:5px;padding:5px 8px;border:1px solid #dde1e9;border-radius:7px;color:#657086;background:#fff;font-size:9px}.embedded-course{min-height:0;overflow:hidden}.embedded-course :deep(.workspace-concept){border-radius:0}.portal-toast{position:fixed;z-index:60;left:50%;bottom:25px;display:flex;align-items:center;gap:7px;padding:10px 14px;border:1px solid #d7e6df;border-radius:9px;color:#22614c;background:#f1faf6;box-shadow:0 12px 30px rgba(36,54,47,.14);font-size:10px;transform:translateX(-50%)}.toast-enter-active,.toast-leave-active,.reveal-enter-active,.reveal-leave-active{transition:opacity .2s ease,transform .28s cubic-bezier(.16,1,.3,1)}.toast-enter-from,.toast-leave-to{opacity:0;transform:translate(-50%,7px)}.reveal-enter-from,.reveal-leave-to{opacity:0;transform:translateY(-7px)}
.module-view,.video-view{min-height:0;overflow:auto;padding:clamp(32px,5vw,70px) clamp(34px,8vw,120px);background:#f8f9fb}.module-heading>button{display:flex;align-items:center;gap:5px;margin-bottom:34px;padding:0;border:0;color:#7c8798;background:transparent;font-size:10px}.module-heading p{margin:0 0 8px;color:var(--brand);font-size:10px;font-weight:800;letter-spacing:.11em}.module-heading h1{max-width:780px;margin:0;font-size:clamp(30px,4vw,48px);letter-spacing:-.05em}.module-heading>span{display:block;max-width:760px;margin-top:14px;color:#6f7a8d;font-size:13px;line-height:1.7}.module-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:38px}.module-card{min-height:330px;position:relative;display:grid;grid-template-rows:1fr auto auto;overflow:hidden;padding:0;border:1px solid #dde1e9;border-radius:16px;background:#fff;text-align:left;transition:transform .22s cubic-bezier(.16,1,.3,1),box-shadow .22s ease}.module-card:hover{transform:translateY(-3px);box-shadow:0 20px 48px rgba(36,43,64,.1)}.module-number{position:absolute;z-index:2;top:20px;right:22px;color:rgba(32,42,68,.35);font-size:12px;font-weight:800;letter-spacing:.1em}.module-visual{min-height:130px;display:flex;flex-direction:column;justify-content:space-between;padding:23px}.module-visual i{font-size:9px;font-style:normal;letter-spacing:.15em}.module-card--course .module-visual{color:#444aa3;background:#e9eaff}.module-card--video .module-visual{color:#dce3ef;background:#293143}.module-card--video .module-number{color:rgba(255,255,255,.38)}.module-copy{display:block;padding:24px 24px 18px}.module-copy small,.module-copy strong,.module-copy em{display:block}.module-copy small{color:#7d8798;font-size:9px}.module-copy strong{margin-top:7px;color:#273044;font-size:24px}.module-copy em{max-width:480px;margin-top:10px;color:#6e798c;font-size:11px;font-style:normal;line-height:1.65}.module-action{display:flex;justify-content:space-between;align-items:center;margin:0 24px;padding:14px 0 20px;border-top:1px solid #eceef2;color:#4d55ab;font-size:10px;font-weight:750}.module-rule{display:flex;align-items:flex-start;gap:9px;margin-top:18px;padding:13px 15px;border:1px solid #dfe3ed;border-radius:10px;color:#6d788a;background:#fff;font-size:10px;line-height:1.55}.module-rule svg{flex:none;color:#26805f}.module-rule strong{color:#475267}.video-view{display:grid;grid-template-columns:minmax(0,1fr) minmax(340px,.65fr);align-items:center;gap:70px}.video-drop{min-height:330px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px;border:1px dashed #cbd1de;border-radius:16px;color:#798496;background:#fff}.video-drop>span{width:64px;height:64px;display:grid;place-items:center;border-radius:16px;color:#4f56ad;background:#eef0ff}.video-drop strong{margin-top:18px;color:#414c61;font-size:17px}.video-drop small{margin-top:8px;font-size:10px}.video-drop em{margin-top:20px;padding:9px 15px;border-radius:8px;color:#fff;background:var(--brand);font-size:10px;font-style:normal;font-weight:750}.embedded-course :deep(.product-switch){display:none}.embedded-course :deep(.concept-header){grid-template-columns:minmax(250px,1fr) auto}

/* Layout rhythm pass: preserve the original information architecture while removing squeeze. */
.portal{width:100vw;height:100dvh;position:fixed;z-index:100;inset:0;border-radius:0}
.home-view{--portal-content:1280px;--space-section:48px;padding-inline:clamp(24px,5vw,72px)}
.home-intro,.workbench-entry,.feature-section{width:min(100%,var(--portal-content));margin-inline:auto}
.home-intro{grid-template-columns:minmax(0,1fr) minmax(340px,380px);gap:clamp(28px,4vw,56px)}
.today-panel{align-self:center}
.workbench-entry{margin-top:var(--space-section);padding-top:32px}
.feature-section{margin-top:var(--space-section)}
.workbench-body{grid-template-columns:minmax(0,1fr) minmax(300px,360px);gap:16px}
.continue-course{grid-template-columns:56px minmax(260px,1fr) 148px 24px;gap:16px;padding:20px 22px}
.workbench-tools{gap:10px}.workbench-tools button{min-height:68px;padding:12px 14px}.workbench-tools small{font-size:10px;line-height:1.45}
.feature-layout{grid-template-columns:minmax(320px,1.25fr) repeat(2,minmax(240px,.75fr));gap:12px}.feature-layout>button{min-height:104px;padding:16px 18px}.feature-layout small{font-size:10px;line-height:1.5}
.continue-course>span:nth-child(2) small,.continue-course>span:nth-child(2) em,.course-progress small{font-size:10px}
@media(max-width:1180px) and (min-width:1001px){.continue-course{grid-template-columns:54px minmax(0,1fr) 24px}.continue-course .course-progress{grid-column:2;width:min(260px,100%)}.feature-layout{grid-template-columns:1.1fr .9fr}.feature-wide{grid-column:1/-1}.home-intro{grid-template-columns:minmax(0,1fr) 340px}.home-copy h1{font-size:clamp(42px,5vw,54px)}}
@media(max-height:850px) and (min-width:1001px){.home-view{--space-section:36px;padding-top:32px;padding-bottom:48px}.home-copy h1{font-size:clamp(42px,4.3vw,52px)}.home-copy>span{margin-top:12px;line-height:1.65}.home-actions{margin-top:18px}.workbench-entry{padding-top:24px}.workbench-body{margin-top:16px}.continue-course{min-height:132px}.feature-layout{margin-top:14px}.feature-layout>button{min-height:96px}}
@media(max-width:1000px){.portal-header{grid-template-columns:1fr auto}.portal-nav{display:none}.home-intro,.workbench-body,.video-view{grid-template-columns:1fr}.feature-layout{grid-template-columns:1fr 1fr}.feature-wide{grid-column:1/-1}.course-grid{grid-template-columns:repeat(2,minmax(220px,1fr))}.create-course{grid-template-columns:1fr 1fr}.create-course>div{grid-column:1/-1}}
@media(max-width:680px){.portal{border-radius:0}.portal-header{padding:0 12px}.portal-brand small,.portal-account>span,.portal-account>button{display:none}.home-view,.spaces-view,.module-view,.video-view{padding:24px 16px 50px}.home-copy h1{font-size:36px}.home-intro{gap:28px}.workbench-entry>header,.feature-section>header,.spaces-heading{align-items:flex-start;flex-direction:column}.workbench-entry>header>button{margin-top:-18px}.continue-course{grid-template-columns:48px 1fr auto}.continue-course .course-progress{grid-column:2}.feature-layout,.course-grid,.module-grid{grid-template-columns:1fr}.create-course{grid-template-columns:1fr}.spaces-toolbar>label{width:160px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition-duration:.01ms!important}}
</style>
