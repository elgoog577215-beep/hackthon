<template>
  <main class="mode-lab">
    <header class="lab-header">
      <button type="button" class="lab-brand" @click="router.push('/workspace-concept')">
        <img src="/qizhi-favicon.svg" alt="" />
        <span><strong>课程结构体验室</strong><small>同一课程 · 三种交互模式</small></span>
      </button>

      <nav class="mode-switch" aria-label="选择体验方案">
        <button v-for="item in modes" :key="item.id" type="button" :class="{ active: mode === item.id }" @click="setMode(item.id)">
          <span>{{ item.id }}</span><strong>{{ item.short }}</strong><small>{{ item.label }}</small>
        </button>
      </nav>

        <div class="header-actions">
          <button type="button" class="back-button" @click="router.push('/workspace-concept')"><ArrowLeft :size="15" />返回总览</button>
        <div class="role-switch"><button type="button" :class="{ active: role === 'teacher' }" @click="setRole('teacher')"><GraduationCap :size="14" />教师</button><button type="button" :class="{ active: role === 'student' }" @click="setRole('student')"><UserRound :size="14" />学生</button></div>
      </div>
    </header>

    <section class="mode-intro">
      <div><span>方案 {{ currentMode.id }}</span><strong>{{ currentMode.title }}</strong><small>{{ currentMode.description }}</small></div>
      <p><Info :size="14" />{{ currentMode.rule }}</p>
    </section>

    <section class="course-shell">
      <aside class="course-rail">
        <div class="course-identity"><span>高</span><div><strong>高等数学</strong><small>2026 秋季 · 项老师</small></div><ChevronDown :size="14" /></div>
        <nav v-if="role === 'teacher'" class="course-nav">
          <button v-for="item in teacherNav" :key="item.id" type="button" :class="{ active: section === item.id }" @click="section = item.id">
            <component :is="item.icon" :size="16" />{{ item.label }}<small v-if="item.count">{{ item.count }}</small>
          </button>
        </nav>
        <nav v-else class="course-nav">
          <button v-for="item in studentNav" :key="item.id" type="button" :class="{ active: studentSection === item.id }" @click="studentSection = item.id">
            <component :is="item.icon" :size="16" />{{ item.label }}
          </button>
        </nav>
        <div class="rail-foot"><Link2 :size="14" /><span>{{ role === 'teacher' ? '教师草稿与学生发布版分开保存。' : '教师内容只读，个人笔记仅自己可见。' }}</span></div>
      </aside>

      <section class="work-area">
        <template v-if="role === 'teacher'">
          <header class="work-heading">
            <div><small>{{ currentMode.title }} / {{ activeNavLabel }}</small><h1>{{ activeNavLabel }}</h1><p>{{ sectionDescription }}</p></div>
            <div class="work-actions" v-if="isContentSection">
              <template v-if="activeView === 'files'"><button type="button" class="secondary" @click="importIntoCurrentFolder"><FolderInput :size="15" />{{ importedCount ? `已导入 ${importedCount} 项` : '导入文件夹' }}</button><button type="button" class="primary" @click="mode === 'C' ? createInCurrentFolder() : createFolder()"><Plus :size="15" />新建</button></template>
              <template v-else><button type="button" class="secondary" @click="notify('已检查全部讲次缺项（模拟）')"><ScanSearch :size="15" />检查缺项</button><button type="button" class="primary" @click="openAsset(assets.plan6)"><Sparkles :size="15" />继续备课</button></template>
            </div>
          </header>

          <div v-if="mode === 'B' && section === 'content'" class="view-switch">
            <button type="button" :class="{ active: contentView === 'production' }" @click="switchContentView('production')"><Workflow :size="15" />生产视图<small>看进度与缺项</small></button>
            <button type="button" :class="{ active: contentView === 'files' }" @click="switchContentView('files')"><FolderTree :size="15" />文件视图<small>找文件与归档</small></button>
            <span>视图变化，内容不复制</span>
          </div>

          <div v-if="isContentSection" class="object-context" :data-mode="mode">
            <div class="object-context__identity"><span>{{ mode }}</span><div><small>{{ modeContext.eyebrow }}</small><strong>{{ modeContext.title }}</strong></div></div>
            <div class="object-context__facts"><span><small>当前对象</small><b>第 06 讲 · 教案</b></span><span><small>教师工作版</small><b>v{{ draftVersion }} 草稿</b></span><span><small>学生发布版</small><b>v{{ publishedVersion }}</b></span></div>
            <CourseOfferingStatusBadge status="published" :has-unpublished-changes="draftVersion > publishedVersion" />
          </div>

          <section v-if="section === 'overview'" class="overview-page">
            <div class="next-lesson"><span>下一次授课 · 明天 10:00</span><h2>第 06 讲　导数的应用</h2><p>教案已确认，主课件基于旧教案，需要生成新版本。</p><button type="button" class="primary" @click="goToContent"><ArrowRight :size="15" />继续准备本讲</button></div>
            <div class="overview-stats"><div><span>教案完成</span><strong>8 / 16</strong><i><b style="width:50%" /></i></div><div><span>PPT完成</span><strong>5 / 16</strong><i><b style="width:31%" /></i></div><div><span>已发布</span><strong>4 / 16</strong><i><b style="width:25%" /></i></div></div>
            <div class="overview-list"><header><strong>需要处理</strong><small>3 项</small></header><button type="button" @click="openAsset(assets.ppt4)"><AlertTriangle :size="15" /><span><strong>第04讲主课件需要更新</strong><small>上游教案已从 v2 更新为 v3</small></span><ChevronRight :size="15" /></button><button type="button" @click="goToContent"><CircleDashed :size="15" /><span><strong>第08讲尚未生成教案</strong><small>大纲内容已确认，可以开始生成</small></span><ChevronRight :size="15" /></button></div>
          </section>

          <section v-else-if="section === 'publish'" class="simple-page publish-page">
            <header><Send :size="22" /><div><strong>发布与学生</strong><small>教师草稿不会自动覆盖学生正在学习的版本。</small></div></header>
            <div class="release-summary"><div><small>本次候选发布</small><strong>2026 秋 · 第 2 次发布</strong><span>确认大纲、教案与课件的明确版本，不覆盖教师工作稿。</span></div><button type="button" class="primary" @click="publishCurrent"><Send :size="14" />{{ publishedVersion === draftVersion ? '已发布最新版本' : '发布第06讲更新' }}</button></div>
            <div class="release-table"><div class="release-head"><span>讲次</span><span>教师草稿</span><span>学生版本</span><span>学习情况</span><span /></div><div v-for="lesson in lessons.slice(0,6)" :key="lesson.id" class="release-row"><strong>第{{ pad(lesson.order) }}讲　{{ lesson.title }}</strong><span>{{ lesson.order === 6 ? `教案 v${draftVersion}` : lesson.plan }}</span><span :class="`state-${lesson.order === 6 && publishedVersion === draftVersion ? 'published' : lesson.releaseState}`">{{ lesson.order === 6 ? `学生版 v${publishedVersion}` : lesson.release }}</span><span>{{ lesson.students }} 人已学习</span><button type="button" @click="lesson.order === 6 ? publishCurrent() : notify(`${lesson.title}发布快照已打开`)">{{ lesson.order === 6 && publishedVersion < draftVersion ? '发布更新' : '查看' }}</button></div></div>
          </section>

          <section v-else-if="section === 'feedback'" class="simple-page feedback-page">
            <header><MessageSquareText :size="22" /><div><strong>学生反馈</strong><small>只显示主动提交内容与匿名聚合，不读取私人笔记。</small></div></header>
            <div class="feedback-summary"><div><span>本周主动问题</span><strong>23</strong><small>较上周 +5</small></div><div><span>待巩固知识点</span><strong>6</strong><small>导数定义最多</small></div><div><span>练习完成率</span><strong>78%</strong><small>共 86 名学生</small></div></div>
            <div class="question-list"><strong>高频问题</strong><button type="button" :class="{ selected: feedbackProposal !== 'idle' }" @click="createFeedbackProposal"><span>1</span><p><b>为什么导数为 0 不一定是极值点？</b><small>12 名学生提交 · 关联第06讲</small></p><em>{{ feedbackProposal === 'idle' ? '创建改进建议' : feedbackProposal === 'suggested' ? '建议待确认' : '已创建草稿' }}</em></button><button type="button"><span>2</span><p><b>间断点类型应该怎样快速判断？</b><small>8 名学生提交 · 关联第04讲</small></p><em>查看证据</em></button></div>
            <div v-if="feedbackProposal !== 'idle'" class="feedback-proposal"><Sparkles :size="18" /><div><small>基于主动反馈 · 不读取私人笔记</small><strong>为第06讲补充“驻点不等于极值点”的反例</strong><p>将影响教案“概念辨析”和 PPT 第18页后两页；学生当前 v{{ publishedVersion }} 不变。</p></div><button v-if="feedbackProposal === 'suggested'" type="button" class="primary" @click="acceptFeedbackProposal">接受并创建 v{{ draftVersion + 1 }} 草稿</button><CourseOfferingStatusBadge v-else status="draft" /></div>
          </section>

          <template v-else-if="isContentSection">
            <section v-if="activeView === 'production'" class="production-view">
              <div v-if="mode === 'A'" class="mode-operation mode-operation--flow">
                <div><small>今天的生产任务</small><strong>第06讲：确认教案后更新主课件</strong><span>系统按“大纲 → 教案 → PPT → 发布”检查依赖，文件会自动归入对应目录。</span></div>
                <ol><li class="done"><Check :size="13" />大纲 v3</li><li class="active">教案 v{{ draftVersion }}</li><li>主课件 v3</li><li>学生发布</li></ol>
                <button type="button" class="primary" @click="advanceFlow"><Sparkles :size="14" />{{ flowActionLabel }}</button>
              </div>
              <div v-else-if="mode === 'B'" class="mode-operation mode-operation--object">
                <div><small>统一内容对象 · content/lesson-06/plan</small><strong>第06讲教案</strong><span>切换视图、打开编辑器或查看版本时，始终保持这一个对象。</span></div>
                <div class="object-pointers"><span>工作稿 v{{ draftVersion }}</span><span>确认版 v{{ Math.max(2, draftVersion - 1) }}</span><span>学生版 v{{ publishedVersion }}</span></div>
              </div>
              <section v-if="mode === 'B'" class="lesson-focus-workbench">
                <aside class="lesson-focus-list"><header><small>16 个教学单元</small><strong>按讲次切换工作现场</strong></header><button v-for="lesson in lessons.slice(3,8)" :key="lesson.id" type="button" :class="{ active: selectedLessonOrder === lesson.order }" @click="selectLesson(lesson.order)"><span>{{ pad(lesson.order) }}</span><div><strong>{{ lesson.title }}</strong><small>{{ lesson.knowledge }}</small></div><i :class="`state-${lesson.releaseState}`" /></button></aside>
                <div class="lesson-focus-main"><header><div><small>第 {{ pad(selectedLessonOrder) }} 讲 · 内容驾驶舱</small><h2>{{ selectedLesson.title }}</h2><p>所有教学产物、学生版本和反馈围绕这一讲集中呈现。</p></div><button type="button" class="primary" @click="openLessonAsset(selectedLessonOrder, 'plan')"><Sparkles :size="14" />继续本讲</button></header><div class="artifact-board"><button type="button" @click="openAsset(assets.outline)"><BookOpenCheck :size="19" /><span><small>上游依据</small><strong>教学大纲 v3</strong><em>已确认 · 3 个知识节点</em></span><ChevronRight :size="14" /></button><button type="button" @click="openLessonAsset(selectedLessonOrder, 'plan')"><FileText :size="19" /><span><small>本讲教案</small><strong>{{ selectedLessonOrder === 6 ? `工作稿 v${draftVersion}` : selectedLesson.plan }}</strong><em>{{ selectedLessonOrder === 6 ? flowPlanState : selectedLesson.planState }}</em></span><ChevronRight :size="14" /></button><button type="button" @click="openLessonAsset(selectedLessonOrder, 'ppt')"><Presentation :size="19" /><span><small>课堂课件</small><strong>{{ selectedLesson.ppt }}</strong><em>{{ selectedLesson.pptState }}</em></span><ChevronRight :size="14" /></button><button type="button" @click="section = 'feedback'"><MessageSquareText :size="19" /><span><small>学习反馈</small><strong>{{ selectedLessonOrder === 6 ? '12 条高频问题' : '查看本讲反馈' }}</strong><em>仅主动反馈与匿名聚合</em></span><ChevronRight :size="14" /></button></div><div class="dependency-line"><span>大纲 v3</span><ArrowRight :size="13" /><span>教案 v{{ selectedLessonOrder === 6 ? draftVersion : 2 }}</span><ArrowRight :size="13" /><span>PPT v{{ selectedLessonOrder === 6 ? 2 : 3 }}</span><ArrowRight :size="13" /><span class="student">学生版 v{{ selectedLessonOrder === 6 ? publishedVersion : 2 }}</span></div></div>
                <aside class="lesson-focus-status"><small>本讲状态</small><CourseOfferingStatusBadge status="published" :has-unpublished-changes="selectedLessonOrder === 6 && draftVersion > publishedVersion" /><dl><div><dt>备课完整度</dt><dd>82%</dd></div><div><dt>待处理</dt><dd>2 项</dd></div><div><dt>学生已学习</dt><dd>{{ selectedLesson.students }} 人</dd></div></dl><button type="button" @click="section = 'publish'"><Send :size="14" />查看发布影响</button><button type="button" @click="switchContentView('files')"><FolderTree :size="14" />在文件中定位</button></aside>
              </section>
              <div v-if="mode !== 'B'" class="stage-line"><div class="done"><span><Check :size="13" /></span><b>课程要求</b><small>已确认</small></div><i /><div class="done"><span><Check :size="13" /></span><b>教学大纲</b><small>v3 已确认</small></div><i /><div class="active"><span>3</span><b>分讲生产</b><small>8 / 16</small></div><i /><div><span>4</span><b>发布准备</b><small>4 / 16</small></div></div>
              <div v-if="mode !== 'B'" class="outline-card"><BookOpenCheck :size="19" /><span><strong>课程教学大纲</strong><small>16讲 · 32学时 · 42个知识节点 · v3</small></span><em>已确认</em><button type="button" @click="openAsset(assets.outline)">打开</button></div>
              <div v-if="mode !== 'B'" class="lesson-toolbar"><div><strong>分讲生产</strong><small>按讲次查看教案、PPT与学生版本</small></div><label><Search :size="14" /><input v-model="lessonQuery" placeholder="搜索讲次" /></label></div>
              <div v-if="mode !== 'B'" class="lesson-table"><div class="lesson-head"><span>讲次</span><span>分讲教案</span><span>PPT</span><span>学生版本</span></div><div v-for="lesson in filteredLessons" :key="lesson.id" class="lesson-row" :class="{ selected: selectedLessonOrder === lesson.order }" @click="selectLesson(lesson.order)"><span><b>{{ pad(lesson.order) }}</b><strong>{{ lesson.title }}</strong><small>{{ lesson.knowledge }}</small></span><button type="button" @click.stop="openLessonAsset(lesson.order, 'plan')"><FileText :size="15" /><span><b>{{ lesson.order === 6 ? `教案 v${draftVersion}` : lesson.plan }}</b><small>{{ lesson.order === 6 ? flowPlanState : lesson.planState }}</small></span></button><button type="button" @click.stop="openLessonAsset(lesson.order, 'ppt')"><Presentation :size="15" /><span><b>{{ lesson.ppt }}</b><small>{{ lesson.pptState }}</small></span></button><span><b :class="`state-${lesson.order === 6 && publishedVersion === draftVersion ? 'published' : lesson.releaseState}`">{{ lesson.order === 6 ? `学生版 v${publishedVersion}` : lesson.release }}</b><small>{{ lesson.students }}人已学习</small></span></div></div>
            </section>

            <section v-else class="file-view" :class="{ 'file-first': mode === 'C' }">
              <aside class="file-tree">
                <header><FolderOpen :size="16" /><strong>高等数学</strong><button type="button" @click="notify('课程根目录：重命名、模板补齐、导出整课 ZIP')"><MoreHorizontal :size="15" /></button></header>
                <button v-for="folder in folders" :key="folder.id" type="button" :class="{ active: selectedFolder === folder.id }" @click="selectedFolder = folder.id"><ChevronRight :size="13" :class="{ open: selectedFolder === folder.id }" /><component :is="folder.icon" :size="16" /><span>{{ folder.name }}</span><small>{{ folder.assets.length }}</small></button>
                <div class="tree-foot"><button type="button" @click="createFolder"><FolderPlus :size="14" />新建文件夹</button><button type="button" @click="importIntoCurrentFolder"><FolderInput :size="14" />导入</button></div>
              </aside>
              <div class="file-list" :class="{ 'grid-layout': fileLayout === 'grid' }">
                <header><nav><span>高等数学</span><ChevronRight :size="12" /><strong>{{ currentFolder.name }}</strong></nav><div><button type="button" :class="{ active: fileLayout === 'list' }" @click="fileLayout = 'list'"><List :size="15" /></button><button type="button" :class="{ active: fileLayout === 'grid' }" @click="fileLayout = 'grid'"><Grid2X2 :size="15" /></button></div></header>
                <div v-if="mode === 'C'" class="file-first-banner"><Sparkles :size="16" /><span><strong>{{ currentFolder.name }} 就是当前工作现场</strong>{{ missingChecked ? '检查完成：发现第07、08讲主课件缺失，可在当前目录补齐。' : '新建、导入、生成、版本和发布都作用于这个目录，不跳转到另一套生产页面。' }}</span><button type="button" @click="createInCurrentFolder">{{ folderCreated ? '已新建草稿' : '在此处生成' }}</button></div>
                <div v-if="mode === 'C'" class="path-actions"><button type="button" @click="createInCurrentFolder"><Plus :size="14" />新建受管文档</button><button type="button" @click="importIntoCurrentFolder"><FolderInput :size="14" />导入到此处</button><button type="button" :class="{ active: missingChecked }" @click="checkMissing"><ScanSearch :size="14" />{{ missingChecked ? '发现 2 项缺失' : 'AI检查缺项' }}</button><span>路径保持 · 空文件夹保留</span></div>
                <div class="file-head"><span>名称</span><span>类型</span><span>关联</span><span>更新</span></div>
                <div v-for="asset in currentFolder.assets" :key="asset.id" class="file-row" :class="{ selected: selectedFileId === asset.id }" role="button" tabindex="0" @dblclick="openAsset(asset)" @click="selectedFileId = asset.id" @keydown.enter="openAsset(asset)"><span class="file-name"><i><component :is="asset.icon" :size="18" /></i><span><strong>{{ asset.name }}</strong><small>{{ asset.detail }}</small></span></span><em>{{ asset.kindLabel }}</em><span>{{ asset.relation }}</span><small>{{ asset.updated }}</small><button type="button" title="打开" @click.stop="openAsset(asset)"><ChevronRight :size="14" /></button></div>
              </div>
              <aside class="file-context"><template v-if="selectedFile"><span class="file-context-icon"><component :is="selectedFile.icon" :size="21" /></span><strong>{{ selectedFile.name }}</strong><small>{{ selectedFile.detail }}</small><CourseOfferingStatusBadge :status="selectedFilePublished ? 'published' : 'draft'" :has-unpublished-changes="selectedFile.id === 'plan-6' && draftVersion > publishedVersion" /><dl><div><dt>内容类型</dt><dd>{{ selectedFile.kindLabel }}</dd></div><div><dt>教学关联</dt><dd>{{ selectedFile.relation }}</dd></div><div><dt>当前工作版</dt><dd>{{ selectedFile.id === 'plan-6' ? `v${draftVersion}` : selectedFile.version || '原始文件' }}</dd></div><div><dt>学生版本</dt><dd>{{ selectedFilePublished ? `已发布${selectedFile.id === 'plan-6' ? ` v${publishedVersion}` : ''}` : '仅教师可见' }}</dd></div></dl><button type="button" class="primary" @click="openAsset(selectedFile)">打开{{ selectedFile.openLabel }}</button><button v-if="mode === 'C'" type="button" class="secondary" @click="toggleSelectedFilePublish">{{ selectedFilePublished ? '撤回学生可见' : '发布给学生' }}</button><button type="button" class="secondary" @click="notify('已展开：版本、移动、重命名、下载、删除')">版本与更多操作</button></template><template v-else><MousePointer2 :size="22" /><strong>选择一个文件</strong><small>查看文件能力、教学关联和发布状态。</small></template></aside>
            </section>
          </template>
        </template>

        <template v-else>
          <section class="student-page">
            <header><div><small>教师发布版 v{{ publishedVersion }}</small><h1>第 06 讲　导数的应用</h1><p>教师内容保持只读，你的笔记、标注与AI记录仅自己可见。</p></div><span><ShieldCheck :size="15" />官方课程</span></header>
            <div class="student-mode-context"><component :is="studentModeContext.icon" :size="17" /><div><small>{{ studentModeContext.eyebrow }}</small><strong>{{ studentModeContext.title }}</strong></div><span>{{ studentModeContext.detail }}</span></div>
            <div v-if="mode === 'A'" class="student-mode-surface student-mode-surface--sequence"><span class="done">01 已学</span><i /><span class="done">02 已学</span><i /><span class="active">06 正在学习 · 发布版 v{{ publishedVersion }}</span><i /><span>07 未发布</span></div>
            <div v-else-if="mode === 'B'" class="student-mode-surface student-mode-surface--lesson"><button class="active" type="button"><Presentation :size="14" />PPT · 38页</button><button type="button"><NotebookPen :size="14" />课堂笔记 · 6</button><button type="button"><ListChecks :size="14" />练习 · 8题</button><span>全部关联第06讲与同一组知识点</span></div>
            <div v-else class="student-mode-surface student-mode-surface--folders"><button type="button"><FolderOpen :size="16" /><span><small>只读</small><strong>教师发布资料</strong></span><em>12 项</em></button><button type="button" class="active"><Folder :size="16" /><span><small>仅自己可见</small><strong>我的学习资料</strong></span><em>{{ noteAdded ? '7 项' : '6 项' }}</em></button><button type="button" @click="noteAdded = true"><Plus :size="14" />从教师课件建立笔记</button></div>
            <nav class="student-lesson-nav"><button type="button">上一讲</button><div><i><b /></i><span>已完成 42%</span></div><button type="button">下一讲</button></nav>
            <div class="student-canvas">
              <article><span class="doc-label">知识点 6.2</span><h2>函数的单调性与极值</h2><p>当函数在某个区间内导数恒为正时，函数在该区间单调递增；导数恒为负时，函数单调递减。</p><div class="formula">f′(x) &gt; 0　⇒　f(x) 单调递增</div><button type="button" @click="noteAdded = true"><NotebookPen :size="15" />{{ noteAdded ? '已加入我的笔记' : '记下这一段' }}</button></article>
              <aside><div class="student-tabs"><button type="button" :class="{ active: studentPanel === 'notes' }" @click="studentPanel = 'notes'">我的笔记</button><button type="button" :class="{ active: studentPanel === 'ai' }" @click="studentPanel = 'ai'">AI教师</button></div><template v-if="studentPanel === 'notes'"><span class="private-note"><LockKeyhole :size="13" />仅自己可见</span><h3>第06讲笔记</h3><div class="note"><small>关联“函数的单调性”</small><p>先确定定义域，再通过导数符号判断单调区间。</p></div><div v-if="noteAdded" class="note new"><small>刚刚记录</small><p>导数正负决定函数在区间内的增减趋势。</p></div><button type="button" class="primary wide" @click="notify('正在整理复习提纲（模拟）')"><Sparkles :size="14" />整理为复习提纲</button></template><template v-else><span class="ai-mark"><Bot :size="21" /></span><h3>围绕当前内容提问</h3><p>回答会结合教师发布内容与你的私人笔记。</p><button type="button" class="prompt">为什么导数为0不一定是极值点？</button><button type="button" class="prompt">给我一道判断单调性的练习</button></template></aside>
            </div>
          </section>
        </template>
      </section>

      <Transition name="drawer">
        <aside v-if="openedAsset" class="asset-drawer">
          <header><div><small>{{ openedAsset.relation }}</small><strong>{{ openedAsset.name }}</strong></div><button type="button" title="关闭" @click="openedAsset = null"><X :size="17" /></button></header>
          <div class="asset-meta"><span>{{ openedAsset.kindLabel }}</span><span>{{ openedAsset.detail }}</span><span v-if="openedAsset.version">{{ openedAsset.id === 'plan-6' ? `v${draftVersion}` : openedAsset.version }}</span></div>
          <div v-if="openedAsset.id === 'plan-6'" class="version-ribbon"><span><small>当前编辑</small><b>v{{ draftVersion }}</b></span><i /><span><small>教师确认</small><b>v{{ Math.max(2, draftVersion - 1) }}</b></span><i /><span><small>学生使用</small><b>v{{ publishedVersion }}</b></span><button type="button" @click="notify('历史版本：v1 初稿、v2 已发布；恢复会创建新草稿')"><History :size="13" />查看历史</button></div>
          <template v-if="openedAsset.kind === 'doc'">
            <div class="document-editor"><p>高等数学 · 2026 秋季</p><h2>{{ openedAsset.name }}</h2><h3>一、教学目标</h3><p>理解本讲核心概念，能够结合函数图像与导数关系完成分析，并将方法应用到实际问题。</p><h3>二、教学过程</h3><p :class="{ 'ai-revised': aiOptimized }">{{ aiOptimized ? '先以“导数为零但不是极值”的反例制造认知冲突，再通过符号表、函数图像和随堂判断题，引导学生区分驻点与极值点。' : '通过问题引入、概念讲解、案例分析和课堂练习，引导学生建立完整的知识联系。' }}</p><div v-if="aiOptimized" class="ai-revision-note"><Sparkles :size="14" /><span><b>AI 建议已应用到当前草稿</b><small>依据：12 条学生主动反馈 · 只修改教师 v{{ draftVersion }} 工作稿</small></span></div><button type="button" @click="optimizeParagraph"><WandSparkles :size="14" />{{ aiOptimized ? '已应用优化建议' : 'AI优化这一段' }}</button></div>
          </template>
          <template v-else-if="openedAsset.kind === 'ppt'">
            <div class="ppt-editor"><aside><button v-for="n in 4" :key="n" type="button" :class="{ active: n === 2 }"><span>{{ n }}</span><i>第 {{ n }} 页</i></button></aside><div><small>第06讲 · 课堂课件</small><h2>函数的单调性与极值</h2><p>从导数符号理解函数变化趋势</p><span>f′(x) &gt; 0　→　单调递增</span></div></div>
          </template>
          <template v-else>
            <div class="file-preview"><component :is="openedAsset.icon" :size="42" /><h2>{{ openedAsset.name }}</h2><p>{{ openedAsset.kind === 'pdf' ? 'PDF文档已按页面大小自适应预览。' : '原始文件已真实保存，可预览、下载、替换或关联到讲次。' }}</p><div class="preview-paper"><span>{{ openedAsset.kindLabel }} PREVIEW</span><strong>{{ openedAsset.name }}</strong><i /></div></div>
          </template>
          <footer><div><CircleCheck :size="14" /><span>{{ saved ? '刚刚已保存' : '所有修改自动保存' }}</span></div><button type="button" class="secondary" @click="notify('历史版本已展开（模拟）')"><History :size="14" />历史版本</button><button type="button" class="primary" @click="saveAsset"><Save :size="14" />保存</button></footer>
        </aside>
      </Transition>
    </section>

    <Transition name="toast"><div v-if="toast" class="toast"><CircleCheck :size="15" />{{ toast }}</div></Transition>
  </main>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import CourseOfferingStatusBadge from '../components/workspace-concept/WorkspaceConceptStatusBadge.vue'
import {
  AlertTriangle, ArrowLeft, ArrowRight, BarChart3, BookOpen, BookOpenCheck, Bot, Check,
  ChevronDown, ChevronRight, CircleCheck, CircleDashed, File, FileImage, FileSpreadsheet,
  FileText, Folder, FolderInput, FolderOpen, FolderPlus, FolderTree, GraduationCap, Grid2X2,
  History, Home, Info, LayoutDashboard, Link2, List, ListChecks, LockKeyhole, MessageSquareText,
  MoreHorizontal, MousePointer2, NotebookPen, Plus, Presentation, Save, ScanSearch, Search,
  Send, ShieldCheck, Sparkles, UserRound, WandSparkles, Workflow, X,
} from 'lucide-vue-next'

type Mode = 'A' | 'B' | 'C'
type Role = 'teacher' | 'student'
type View = 'production' | 'files'
type AssetKind = 'doc' | 'ppt' | 'pdf' | 'sheet' | 'image' | 'file'

interface Asset {
  id: string; name: string; detail: string; kind: AssetKind; kindLabel: string; relation: string;
  updated: string; version?: string; published: boolean; icon: typeof FileText; openLabel: string
}
interface FolderItem { id: string; name: string; count: number; icon: typeof Folder; assets: Asset[] }

const router = useRouter()
const mode = ref<Mode>('B')
const role = ref<Role>('teacher')
const section = ref('content')
const studentSection = ref('home')
const contentView = ref<View>('production')
const selectedFolder = ref('lesson-plans')
const selectedFileId = ref('plan-6')
const openedAsset = ref<Asset | null>(null)
const lessonQuery = ref('')
const toast = ref('')
const saved = ref(false)
const studentPanel = ref<'notes' | 'ai'>('notes')
const noteAdded = ref(false)
const selectedLessonOrder = ref(6)
const draftVersion = ref(3)
const publishedVersion = ref(2)
const flowStage = ref(0)
const feedbackProposal = ref<'idle' | 'suggested' | 'accepted'>('idle')
const folderCreated = ref(false)
const publishedOverrides = ref<Record<string, boolean>>({})
const aiOptimized = ref(false)
const importedCount = ref(0)
const missingChecked = ref(false)
const fileLayout = ref<'list' | 'grid'>('list')
let toastTimer: ReturnType<typeof setTimeout> | undefined

const modes = [
  { id: 'A' as const, short: '双入口', label: '生产与文件并列', title: '方案A · 双入口模式', description: '保留当前结构：课程生产和课程文件都是一级入口。', rule: '生成流程最直观，但两个入口会打开同一内容，需要额外解释。' },
  { id: 'B' as const, short: '双视图', label: '统一内容中心', title: '方案B · 统一内容中心', description: '课程内容是唯一入口，内部切换生产视图和文件视图。', rule: '同一批内容，两种工作视角；这是当前推荐方向。' },
  { id: 'C' as const, short: '文件优先', label: '目录就是工作台', title: '方案C · 文件系统优先', description: '课程资料树是唯一主要入口，生成能力附着在文件和文件夹上。', rule: '最接近教师电脑文件夹习惯，但课程生产进度需要嵌回目录。' },
]
const currentMode = computed(() => modes.find(item => item.id === mode.value)!)
const modeContext = computed(() => ({
  A: { eyebrow:'双入口 · 同一资产', title:'流程负责推进，文件负责组织' },
  B: { eyebrow:'双视图 · 同一对象', title:'当前讲次与版本跨视图保持' },
  C: { eyebrow:'文件优先 · 当前路径', title:'生成、编辑与发布都发生在目录内' },
}[mode.value]))
const studentModeContext = computed(() => ({
  A: { icon: Workflow, eyebrow:'按教师发布顺序学习', title:'第06讲官方课程', detail:`当前使用发布快照 v${publishedVersion.value}` },
  B: { icon: BookOpen, eyebrow:'围绕一讲集中学习', title:'PPT、正文、笔记与练习保持关联', detail:'私人学习层不反写教师内容' },
  C: { icon: FolderTree, eyebrow:'两层资料空间', title:'教师发布资料（只读） / 我的学习资料（私有）', detail:'可从教师课件建立个人笔记副本' },
}[mode.value]))

const assets = {
  outline: { id:'outline', name:'课程教学大纲', detail:'受管文档 · 18页', kind:'doc', kindLabel:'受管文档', relation:'全课程', updated:'今天 14:32', version:'v3', published:true, icon:BookOpenCheck, openLabel:'编辑器' } as Asset,
  plan1: { id:'plan-1', name:'第01讲教案', detail:'受管文档 · 已确认', kind:'doc', kindLabel:'受管文档', relation:'第01讲', updated:'7月22日', version:'v3', published:true, icon:FileText, openLabel:'编辑器' } as Asset,
  plan2: { id:'plan-2', name:'第02讲教案', detail:'受管文档 · 已确认', kind:'doc', kindLabel:'受管文档', relation:'第02讲', updated:'7月25日', version:'v2', published:true, icon:FileText, openLabel:'编辑器' } as Asset,
  plan3: { id:'plan-3', name:'第03讲教案', detail:'受管文档 · 已确认', kind:'doc', kindLabel:'受管文档', relation:'第03讲', updated:'7月29日', version:'v2', published:true, icon:FileText, openLabel:'编辑器' } as Asset,
  plan4: { id:'plan-4', name:'第04讲教案', detail:'受管文档 · 自动保存', kind:'doc', kindLabel:'受管文档', relation:'第04讲', updated:'昨天 17:42', version:'v3', published:true, icon:FileText, openLabel:'编辑器' } as Asset,
  plan5: { id:'plan-5', name:'第05讲教案', detail:'受管文档 · 需要检查', kind:'doc', kindLabel:'受管文档', relation:'第05讲', updated:'昨天 21:06', version:'v2', published:false, icon:FileText, openLabel:'编辑器' } as Asset,
  plan6: { id:'plan-6', name:'第06讲教案', detail:'受管文档 · 编辑中', kind:'doc', kindLabel:'受管文档', relation:'第06讲', updated:'10分钟前', version:'v2', published:false, icon:FileText, openLabel:'编辑器' } as Asset,
  ppt4: { id:'ppt-4', name:'第04讲主课件', detail:'受管课件 · 46页', kind:'ppt', kindLabel:'受管课件', relation:'第04讲', updated:'昨天 17:42', version:'v4', published:true, icon:Presentation, openLabel:'PPT工作台' } as Asset,
  ppt6: { id:'ppt-6', name:'第06讲主课件', detail:'受管课件 · 38页', kind:'ppt', kindLabel:'受管课件', relation:'第06讲', updated:'今天 09:18', version:'v2', published:false, icon:Presentation, openLabel:'PPT工作台' } as Asset,
  assignment: { id:'assignment', name:'第一次作业.docx', detail:'原始文件 · 36KB', kind:'file', kindLabel:'Word文件', relation:'第01-03讲', updated:'8月2日', published:true, icon:FileText, openLabel:'预览' } as Asset,
  calendar: { id:'calendar', name:'2026秋季教学日历.pdf', detail:'原始文件 · 1.2MB', kind:'pdf', kindLabel:'PDF文件', relation:'全课程', updated:'7月28日', published:false, icon:File, openLabel:'预览' } as Asset,
  grades: { id:'grades', name:'成绩明细.xlsx', detail:'原始文件 · 48KB', kind:'sheet', kindLabel:'Excel文件', relation:'未关联', updated:'8月1日', published:false, icon:FileSpreadsheet, openLabel:'预览' } as Asset,
  image: { id:'image', name:'导数几何意义.png', detail:'原始图片 · 246KB', kind:'image', kindLabel:'PNG图片', relation:'第06讲', updated:'今天 08:45', published:true, icon:FileImage, openLabel:'预览' } as Asset,
}

const folders: FolderItem[] = reactive([
  { id:'outline', name:'0、教学大纲', count:1, icon:Folder, assets:[assets.outline] },
  { id:'lesson-plans', name:'1、分讲教案', count:8, icon:Folder, assets:[assets.plan1, assets.plan2, assets.plan3, assets.plan4, assets.plan5, assets.plan6] },
  { id:'slides', name:'2、PPT', count:7, icon:Folder, assets:[assets.ppt4, assets.ppt6, assets.image] },
  { id:'assignments', name:'3、作业与实验', count:4, icon:Folder, assets:[assets.assignment] },
  { id:'calendar', name:'4、教学日历', count:1, icon:Folder, assets:[assets.calendar] },
  { id:'other', name:'5、其他资料', count:3, icon:Folder, assets:[assets.grades] },
])

const lessons = [
  { id:'l1', order:1, title:'函数、极限与连续', knowledge:'极限思想 · 连续性', plan:'教案 v3', planState:'已确认', ppt:'主课件 v4', pptState:'已发布', release:'学生版 v3', releaseState:'published', students:84 },
  { id:'l2', order:2, title:'数列极限与运算法则', knowledge:'数列极限 · 夹逼准则', plan:'教案 v2', planState:'编辑中', ppt:'主课件 v3', pptState:'草稿', release:'待更新', releaseState:'ready', students:81 },
  { id:'l3', order:3, title:'函数极限与重要极限', knowledge:'函数极限 · 等价无穷小', plan:'教案 v2', planState:'已确认', ppt:'主课件 v2', pptState:'已发布', release:'学生版 v2', releaseState:'published', students:79 },
  { id:'l4', order:4, title:'连续函数与间断点', knowledge:'间断点 · 闭区间性质', plan:'教案 v3', planState:'已确认', ppt:'2份课件 · v4', pptState:'教案已更新', release:'学生版 v3', releaseState:'ready', students:76 },
  { id:'l5', order:5, title:'导数概念与求导法则', knowledge:'变化率 · 导数定义', plan:'教案 v2', planState:'需要检查', ppt:'主课件 v2', pptState:'上游已更新', release:'学生版 v2', releaseState:'ready', students:72 },
  { id:'l6', order:6, title:'导数的应用', knowledge:'单调性 · 极值', plan:'教案 v2', planState:'编辑中', ppt:'主课件 v2', pptState:'待更新', release:'未发布', releaseState:'draft', students:0 },
  { id:'l7', order:7, title:'微分中值定理', knowledge:'罗尔 · 拉格朗日', plan:'教案 v1', planState:'已确认', ppt:'生成中 64%', pptState:'生成中', release:'未发布', releaseState:'draft', students:0 },
  { id:'l8', order:8, title:'函数单调性与极值', knowledge:'单调性 · 最值', plan:'生成教案', planState:'尚未开始', ppt:'等待教案', pptState:'未开始', release:'未发布', releaseState:'draft', students:0 },
]

const navByMode = computed(() => ({
  A: [
    { id:'overview', label:'课程概览', icon:LayoutDashboard }, { id:'production', label:'课程生产', icon:Workflow, count:'3' },
    { id:'files', label:'课程文件', icon:FolderTree }, { id:'publish', label:'发布与学生', icon:Send }, { id:'feedback', label:'反馈与数据', icon:BarChart3 },
  ],
  B: [
    { id:'overview', label:'课程概览', icon:LayoutDashboard }, { id:'content', label:'课程内容', icon:BookOpen, count:'3' },
    { id:'publish', label:'发布与学生', icon:Send }, { id:'feedback', label:'反馈与数据', icon:BarChart3 },
  ],
  C: [
    { id:'overview', label:'课程概览', icon:LayoutDashboard }, { id:'materials', label:'课程资料', icon:FolderTree, count:'3' },
    { id:'publish', label:'发布与学生', icon:Send }, { id:'feedback', label:'反馈与数据', icon:BarChart3 },
  ],
}[mode.value]))
const teacherNav = computed(() => navByMode.value)
const studentNav = [
  { id:'home', label:'课程首页', icon:Home }, { id:'content', label:'课程内容', icon:BookOpen }, { id:'notes', label:'我的笔记', icon:NotebookPen },
  { id:'practice', label:'练习与作业', icon:ListChecks }, { id:'progress', label:'学习进度', icon:BarChart3 },
]
const activeNavLabel = computed(() => teacherNav.value.find(item => item.id === section.value)?.label || '课程内容')
const isContentSection = computed(() => ['production','files','content','materials'].includes(section.value))
const activeView = computed<View>(() => mode.value === 'A' ? (section.value === 'files' ? 'files' : 'production') : mode.value === 'B' ? contentView.value : 'files')
const sectionDescription = computed(() => {
  if (section.value === 'overview') return '从下一次授课出发，查看备课进度与需要处理的事项。'
  if (section.value === 'publish') return '明确教师草稿、学生版本与发布范围。'
  if (section.value === 'feedback') return '把学生真实学习情况带回教师备课过程。'
  return activeView.value === 'production' ? '按教学顺序查看每一讲的生产进度。' : '按真实目录管理、打开、导入和导出全部课程文件。'
})
const currentFolder = computed(() => folders.find(item => item.id === selectedFolder.value) || folders[0]!)
const selectedFile = computed(() => currentFolder.value.assets.find(item => item.id === selectedFileId.value) || currentFolder.value.assets[0] || null)
const selectedFilePublished = computed(() => {
  const asset = selectedFile.value
  if (!asset) return false
  return publishedOverrides.value[asset.id] ?? (asset.id === 'plan-6' ? publishedVersion.value >= draftVersion.value : asset.published)
})
const filteredLessons = computed(() => lessons.filter(item => !lessonQuery.value.trim() || `${item.order}${item.title}${item.knowledge}`.includes(lessonQuery.value.trim())))
const selectedLesson = computed(() => lessons.find(item => item.order === selectedLessonOrder.value) || lessons[5]!)
const flowActionLabel = computed(() => ['确认教案 v3','生成主课件 v3','进入发布检查'][flowStage.value] || '查看发布结果')
const flowPlanState = computed(() => ['教案 v3 草稿待确认','教案已确认，PPT 可生成','教案已确认，PPT 新稿已生成'][flowStage.value] || '已进入发布检查')

function setMode(next: Mode) { mode.value = next; section.value = next === 'A' ? 'production' : next === 'B' ? 'content' : 'materials'; openedAsset.value = null }
function setRole(next: Role) { role.value = next; openedAsset.value = null; notify(next === 'student' ? '已进入学生视角：教师草稿与私人笔记不可互见' : '已返回教师工作视角') }
function goToContent() { section.value = mode.value === 'A' ? 'production' : mode.value === 'B' ? 'content' : 'materials' }
function openAsset(asset: Asset) { openedAsset.value = asset; saved.value = false; selectedFileId.value = asset.id; const parent = folders.find(folder => folder.assets.some(item => item.id === asset.id)); if (parent) selectedFolder.value = parent.id }
function selectLesson(order: number) { selectedLessonOrder.value = order; selectedFileId.value = `plan-${order}` }
function openLessonAsset(order: number, kind: 'plan' | 'ppt') {
  selectedLessonOrder.value = order
  const key = `${kind}${order}` as keyof typeof assets
  const found = assets[key]
  const fallback: Asset = { id:`${kind}-${order}`, name:`第${pad(order)}讲${kind === 'plan' ? '教案' : '主课件'}`, detail:kind === 'plan' ? '受管文档 · 已关联讲次' : '受管课件 · 已关联讲次', kind:kind === 'plan' ? 'doc' : 'ppt', kindLabel:kind === 'plan' ? '受管文档' : '受管课件', relation:`第${pad(order)}讲`, updated:'刚刚', version:'v2', published:order < 6, icon:kind === 'plan' ? FileText : Presentation, openLabel:kind === 'plan' ? '编辑器' : 'PPT工作台' }
  openAsset(found || fallback)
}
function switchContentView(next: View) {
  contentView.value = next
  const currentId = openedAsset.value?.id || selectedFileId.value || `plan-${selectedLessonOrder.value}`
  const matchedOrder = Number(currentId.match(/-(\d+)$/)?.[1] || selectedLessonOrder.value)
  if (Number.isFinite(matchedOrder)) selectedLessonOrder.value = matchedOrder
  if (next === 'files') {
    selectedFileId.value = currentId.startsWith('ppt-') ? currentId : `plan-${selectedLessonOrder.value}`
    selectedFolder.value = currentId.startsWith('ppt-') ? 'slides' : 'lesson-plans'
  }
  notify(`同一对象保持选中：第${pad(selectedLessonOrder.value)}讲${currentId.startsWith('ppt-') ? '主课件' : '教案'}`)
}
function advanceFlow() {
  if (flowStage.value === 0) { flowStage.value = 1; openAsset(assets.plan6); notify('教案 v3 已确认；文件入口同步为同一已确认资产') }
  else if (flowStage.value === 1) { flowStage.value = 2; notify('主课件 v3 草稿已生成，并自动归入 2、PPT') }
  else { flowStage.value = 3; section.value = 'publish'; notify('已进入发布检查，学生仍使用 v2') }
}
function publishCurrent() { if (publishedVersion.value === draftVersion.value) { notify('学生已经使用最新发布快照'); return } publishedVersion.value = draftVersion.value; notify(`发布完成：学生版已更新为 v${publishedVersion.value}`) }
function createFeedbackProposal() { feedbackProposal.value = 'suggested'; notify('已基于 12 条主动反馈生成有来源的改进建议') }
function acceptFeedbackProposal() { draftVersion.value += 1; feedbackProposal.value = 'accepted'; selectedLessonOrder.value = 6; notify(`第06讲教案 v${draftVersion.value} 草稿已创建，学生版保持 v${publishedVersion.value}`) }
function createInCurrentFolder() {
  if (!folderCreated.value) {
    const isPptFolder = currentFolder.value.id === 'slides'
    const generated: Asset = { id:'generated-draft', name:isPptFolder ? '第08讲主课件' : '新建受管文档', detail:isPptFolder ? '受管课件 · 1页空白草稿' : '受管文档 · 空白草稿', kind:isPptFolder ? 'ppt' : 'doc', kindLabel:isPptFolder ? '受管课件' : '受管文档', relation:isPptFolder ? '第08讲' : '待关联', updated:'刚刚', version:'v1', published:false, icon:isPptFolder ? Presentation : FileText, openLabel:isPptFolder ? 'PPT工作台' : '编辑器' }
    currentFolder.value.assets.push(generated); selectedFileId.value = generated.id; folderCreated.value = true; notify(`已在 ${currentFolder.value.name} 新建真实列表项`)
  } else notify('草稿已存在，可双击打开继续编辑')
}
function createFolder() {
  const id = `custom-folder-${folders.length + 1}`
  folders.push({ id, name:`${folders.length}、新建目录`, count:0, icon:Folder, assets:[] })
  selectedFolder.value = id; selectedFileId.value = ''; notify('空文件夹已创建，可继续导入或生成内容')
}
function importIntoCurrentFolder() {
  const id = `imported-${Date.now()}`
  const imported: Asset = { id, name:'课堂补充资料.pdf', detail:'原始文件 · 2.4MB', kind:'pdf', kindLabel:'PDF文件', relation:'待关联', updated:'刚刚', published:false, icon:File, openLabel:'预览' }
  currentFolder.value.assets.push(imported); importedCount.value += 1; selectedFileId.value = id; notify(`已导入到 ${currentFolder.value.name}，原目录层级与空文件夹已保留`)
}
function checkMissing() { missingChecked.value = true; notify('检查完成：第07、08讲主课件缺失，可在当前目录生成') }
function optimizeParagraph() { if (aiOptimized.value) { notify('优化建议已在当前草稿中'); return } aiOptimized.value = true; saved.value = false; notify('AI建议已应用，学生发布版没有变化') }
function toggleSelectedFilePublish() { const asset = selectedFile.value; if (!asset) return; const next = !selectedFilePublished.value; publishedOverrides.value = { ...publishedOverrides.value, [asset.id]: next }; notify(next ? `${asset.name}已创建学生只读快照` : `${asset.name}已撤回学生可见，教师文件仍保留`) }
function saveAsset() { saved.value = true; notify(`${openedAsset.value?.name || '内容'}已保存（模拟）`) }
function pad(value: number) { return String(value).padStart(2, '0') }
function notify(message: string) { toast.value = message; if (toastTimer) clearTimeout(toastTimer); toastTimer = setTimeout(() => { toast.value = '' }, 2400) }
</script>

<style scoped>
.mode-lab{--ink:#172033;--muted:#6f7a8d;--line:#e3e7ee;--brand:#4f46e5;height:100%;min-height:0;display:grid;grid-template-rows:70px 58px minmax(0,1fr);overflow:hidden;color:var(--ink);background:#f5f6f9;font-family:var(--font-sans,"Microsoft YaHei",sans-serif)}button,input{font:inherit}.mode-lab button{cursor:pointer}.lab-header{display:grid;grid-template-columns:minmax(220px,1fr) auto minmax(220px,1fr);align-items:center;gap:20px;padding:0 20px;border-bottom:1px solid var(--line);background:#fcfdff}.lab-brand{width:max-content;display:flex;align-items:center;gap:10px;padding:0;border:0;background:transparent;text-align:left}.lab-brand img{width:34px;height:34px}.lab-brand span,.lab-brand strong,.lab-brand small{display:block}.lab-brand strong{font-size:13px}.lab-brand small{margin-top:3px;color:#8b95a5;font-size:9px}.mode-switch{display:flex;align-items:center;gap:5px;padding:4px;border:1px solid #e1e4eb;border-radius:12px;background:#f1f3f7}.mode-switch button{min-width:138px;height:46px;display:grid;grid-template-columns:23px 1fr;grid-template-rows:1fr 1fr;align-items:center;padding:5px 9px;border:0;border-radius:8px;color:#7d8798;background:transparent;text-align:left}.mode-switch button>span{grid-row:1/3;width:23px;height:23px;display:grid;place-items:center;border-radius:7px;color:#737db1;background:#e7e9f5;font-size:9px;font-weight:800}.mode-switch button strong{font-size:10px}.mode-switch button small{font-size:7px}.mode-switch button.active{color:#34398e;background:#fff;box-shadow:0 2px 7px rgba(38,46,65,.09)}.mode-switch button.active>span{color:#fff;background:var(--brand)}.header-actions{justify-self:end;display:flex;align-items:center;gap:8px}.back-button{height:34px;display:flex;align-items:center;gap:5px;padding:0 10px;border:0;border-radius:8px;color:#697489;background:#eef0f4;font-size:9px}.role-switch{display:flex;padding:3px;border:1px solid #dfe3eb;border-radius:9px;background:#f2f4f7}.role-switch button{height:28px;display:flex;align-items:center;gap:5px;padding:0 8px;border:0;border-radius:6px;color:#7d8798;background:transparent;font-size:9px}.role-switch button.active{color:#3e43a0;background:#fff;box-shadow:0 1px 4px rgba(30,40,60,.08)}
.mode-intro{display:flex;justify-content:space-between;align-items:center;gap:24px;padding:0 22px;border-bottom:1px solid var(--line);background:#f9fafc}.mode-intro>div{display:flex;align-items:baseline;gap:10px}.mode-intro>div span{padding:3px 6px;border-radius:6px;color:#4148a0;background:#e9eaff;font-size:8px;font-weight:800}.mode-intro>div strong{font-size:12px}.mode-intro>div small{color:#8791a2;font-size:9px}.mode-intro>p{display:flex;align-items:center;gap:6px;margin:0;color:#6e798b;font-size:9px}.mode-intro>p svg{color:#555cb1}.course-shell{min-height:0;position:relative;display:grid;grid-template-columns:205px minmax(0,1fr);overflow:hidden;background:#fff}.course-rail{min-height:0;display:flex;flex-direction:column;padding:16px 10px;border-right:1px solid var(--line);background:#fafbfc}.course-identity{display:grid;grid-template-columns:36px 1fr auto;align-items:center;gap:9px;padding:0 7px 16px;border-bottom:1px solid var(--line)}.course-identity>span{width:36px;height:36px;display:grid;place-items:center;border-radius:10px;color:#3730a3;background:#e4e7ff;font-weight:850}.course-identity strong,.course-identity small{display:block}.course-identity strong{font-size:12px}.course-identity small{margin-top:3px;color:#929baa;font-size:8px}.course-nav{display:grid;gap:4px;padding:16px 0}.course-nav button{height:38px;display:flex;align-items:center;gap:9px;padding:0 11px;border:0;border-radius:8px;color:#667185;background:transparent;text-align:left;font-size:10px}.course-nav button:hover{background:#f0f2f6}.course-nav button.active{color:#373d9b;background:#eceeff;font-weight:750}.course-nav button small{min-width:18px;margin-left:auto;padding:2px 5px;border-radius:99px;color:#4f55aa;background:#fff;text-align:center;font-size:8px}.rail-foot{margin-top:auto;display:flex;align-items:flex-start;gap:7px;padding:10px;border:1px solid #e5e8ef;border-radius:9px;color:#7c8798;background:#f5f7fa;font-size:8px;line-height:1.55}.rail-foot svg{flex:none}.work-area{min-width:0;min-height:0;padding:20px 22px;overflow:auto;background:#fbfcfd}.work-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;margin-bottom:16px}.work-heading small{color:#7d8798;font-size:8px}.work-heading h1{margin:4px 0 0;font-size:21px;letter-spacing:-.03em}.work-heading p{margin:5px 0 0;color:#7b8698;font-size:9px}.work-actions{display:flex;gap:7px}.primary,.secondary{height:34px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:0 11px;border:0;border-radius:8px;font-size:9px;font-weight:750}.primary{color:#fff;background:var(--brand)}.secondary{color:#59657a;background:#edf0f4}.view-switch{display:flex;align-items:center;gap:4px;margin-bottom:15px;padding:4px;border:1px solid #e1e4ec;border-radius:10px;background:#f1f3f7}.view-switch button{min-width:145px;height:36px;display:grid;grid-template-columns:24px 1fr;grid-template-rows:1fr 1fr;align-items:center;padding:3px 9px;border:0;border-radius:7px;color:#798395;background:transparent;text-align:left}.view-switch button svg{grid-row:1/3}.view-switch button small{font-size:7px}.view-switch button.active{color:#3c4297;background:#fff;box-shadow:0 1px 5px rgba(35,42,61,.09)}.view-switch>span{margin-left:auto;padding-right:9px;color:#969eac;font-size:8px}
.overview-page{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(260px,.7fr);gap:13px}.next-lesson{min-height:190px;padding:28px;border:1px solid #dfe3eb;border-radius:14px;background:#fff}.next-lesson>span{color:#4d55ac;font-size:9px;font-weight:750}.next-lesson h2{margin:12px 0 8px;font-size:25px}.next-lesson p{color:#707b8d;font-size:10px}.next-lesson button{margin-top:18px}.overview-stats{display:grid;gap:7px}.overview-stats>div{padding:15px;border:1px solid #e1e4eb;border-radius:11px;background:#fff}.overview-stats span,.overview-stats strong{display:block}.overview-stats span{color:#8992a2;font-size:8px}.overview-stats strong{margin:6px 0 9px;font-size:16px}.overview-stats i{height:4px;display:block;overflow:hidden;border-radius:99px;background:#e9ebf0}.overview-stats b{height:100%;display:block;background:#6268c4}.overview-list{grid-column:1/-1;border:1px solid #e1e4eb;border-radius:12px;background:#fff}.overview-list header{display:flex;justify-content:space-between;padding:13px 15px;border-bottom:1px solid #eceef2}.overview-list header strong{font-size:10px}.overview-list header small{color:#8c95a4;font-size:8px}.overview-list>button{width:100%;display:grid;grid-template-columns:22px 1fr auto;align-items:center;gap:8px;padding:11px 15px;border:0;border-bottom:1px solid #f0f1f4;color:#80899a;background:transparent;text-align:left}.overview-list>button:hover{background:#f8f9fb}.overview-list>button>svg:first-child{color:#a77327}.overview-list strong,.overview-list small{display:block}.overview-list strong{color:#485469;font-size:9px}.overview-list small{margin-top:3px;color:#969eac;font-size:7px}.simple-page{border:1px solid #e1e4eb;border-radius:13px;background:#fff}.simple-page>header{display:flex;align-items:center;gap:11px;padding:18px;border-bottom:1px solid #e9ebf0}.simple-page>header>svg{width:38px;height:38px;padding:9px;border-radius:10px;color:#4e56ae;background:#eef0ff}.simple-page>header strong,.simple-page>header small{display:block}.simple-page>header strong{font-size:13px}.simple-page>header small{margin-top:4px;color:#8992a2;font-size:8px}.release-table{padding:6px 13px 14px}.release-head,.release-row{display:grid;grid-template-columns:minmax(220px,1.4fr) .7fr .7fr .7fr 70px;align-items:center;gap:10px}.release-head{height:35px;color:#979fac;font-size:8px}.release-row{min-height:48px;border-top:1px solid #edf0f3;font-size:8px}.release-row>strong{font-size:9px}.release-row>span{color:#758094}.release-row>button{padding:5px 7px;border:0;border-radius:6px;color:#4d54aa;background:#eef0ff;font-size:8px}.state-published{color:#19805d!important}.state-ready{color:#a16d1e!important}.state-draft{color:#9199a6!important}.feedback-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#e6e9ee}.feedback-summary>div{padding:20px;background:#fff}.feedback-summary span,.feedback-summary strong,.feedback-summary small{display:block}.feedback-summary span{color:#8992a2;font-size:8px}.feedback-summary strong{margin:8px 0 5px;font-size:24px}.feedback-summary small{color:#8a94a5;font-size:8px}.question-list{padding:17px}.question-list>strong{font-size:10px}.question-list>button{width:100%;display:grid;grid-template-columns:25px 1fr;align-items:center;gap:10px;padding:12px 0;border:0;border-bottom:1px solid #eceef2;background:transparent;text-align:left}.question-list>button>span{width:22px;height:22px;display:grid;place-items:center;border-radius:7px;color:#4d55aa;background:#eef0ff;font-size:8px;font-weight:800}.question-list p{margin:0}.question-list b,.question-list small{display:block}.question-list b{font-size:9px}.question-list small{margin-top:4px;color:#929baa;font-size:8px}
.production-view{display:grid;gap:12px}.stage-line{display:flex;align-items:center;padding:12px 15px;border:1px solid #e1e4eb;border-radius:11px;background:#fff}.stage-line>div{min-width:116px;display:grid;grid-template-columns:25px 1fr;grid-template-rows:1fr 1fr;align-items:center}.stage-line>div>span{grid-row:1/3;width:23px;height:23px;display:grid;place-items:center;border-radius:50%;color:#7e8798;background:#eef0f3;font-size:8px}.stage-line>div b{font-size:9px}.stage-line>div small{color:#939baa;font-size:7px}.stage-line>div.done>span{color:#187a5a;background:#e3f4ed}.stage-line>div.active>span{color:#fff;background:var(--brand)}.stage-line>i{height:1px;flex:1;margin:0 8px;background:#dfe2e8}.outline-card{display:grid;grid-template-columns:34px minmax(0,1fr) auto auto;align-items:center;gap:10px;padding:12px 14px;border:1px solid #dfe3eb;border-radius:11px;background:#fff}.outline-card>svg{width:34px;height:34px;padding:8px;border-radius:9px;color:#4d55ad;background:#eef0ff}.outline-card strong,.outline-card small{display:block}.outline-card strong{font-size:10px}.outline-card small{margin-top:4px;color:#9099a8;font-size:8px}.outline-card em{padding:3px 6px;border-radius:6px;color:#167956;background:#e6f5ee;font-size:7px;font-style:normal}.outline-card button{padding:5px 8px;border:0;color:#4d55aa;background:transparent;font-size:8px}.lesson-toolbar{display:flex;justify-content:space-between;align-items:center;padding:13px 14px 9px}.lesson-toolbar strong,.lesson-toolbar small{display:block}.lesson-toolbar strong{font-size:11px}.lesson-toolbar small{margin-top:3px;color:#929baa;font-size:8px}.lesson-toolbar label{width:190px;height:30px;display:flex;align-items:center;gap:6px;padding:0 8px;border:1px solid #dfe3eb;border-radius:8px;color:#939baa;background:#fff}.lesson-toolbar input{min-width:0;flex:1;border:0;outline:0;background:transparent;font-size:8px}.lesson-table{overflow:hidden;border:1px solid #e1e4eb;border-radius:11px;background:#fff}.lesson-head,.lesson-row{display:grid;grid-template-columns:minmax(190px,1.2fr) minmax(150px,.9fr) minmax(150px,.9fr) minmax(120px,.65fr);align-items:center;gap:8px}.lesson-head{height:33px;padding:0 12px;color:#949dab;background:#f7f8fa;font-size:8px}.lesson-row{min-height:54px;padding:6px 12px;border-top:1px solid #eceef2}.lesson-row>span:first-child{display:grid;grid-template-columns:27px 1fr;grid-template-rows:1fr 1fr;align-items:center}.lesson-row>span:first-child>b{grid-row:1/3;color:#868fa0;font-size:9px}.lesson-row>span strong{font-size:9px}.lesson-row>span small{color:#939baa;font-size:7px}.lesson-row>button{display:flex;align-items:center;gap:7px;padding:7px;border:0;border-radius:7px;color:#5964b1;background:#f6f7ff;text-align:left}.lesson-row>button span,.lesson-row>button b,.lesson-row>button small,.lesson-row>span:last-child b,.lesson-row>span:last-child small{display:block}.lesson-row>button b{color:#475267;font-size:8px}.lesson-row>button small{margin-top:2px}.lesson-row>span:last-child b{font-size:8px}.lesson-row>span:last-child small{margin-top:3px}
.file-view{min-height:440px;display:grid;grid-template-columns:200px minmax(360px,1fr) 210px;overflow:hidden;border:1px solid #e0e3e9;border-radius:12px;background:#fff}.file-tree{padding:10px 7px;border-right:1px solid #e4e7ed;background:#f8f9fb}.file-tree header{height:34px;display:grid;grid-template-columns:20px 1fr 24px;align-items:center;padding:0 8px}.file-tree header strong{font-size:9px}.file-tree header button{display:grid;place-items:center;border:0;color:#9199a7;background:transparent}.file-tree>button{width:100%;height:32px;display:grid;grid-template-columns:14px 17px 1fr auto;align-items:center;gap:5px;padding:0 7px;border:0;border-radius:7px;color:#707b8d;background:transparent;text-align:left;font-size:8px}.file-tree>button:hover,.file-tree>button.active{color:#40479f;background:#e9ecff}.file-tree>button svg.open{transform:rotate(90deg)}.file-tree>button small{color:#9ba3b0}.tree-foot{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:10px;padding-top:9px;border-top:1px solid #e4e7ec}.tree-foot button{height:28px;display:flex;align-items:center;justify-content:center;gap:4px;border:1px solid #e0e3e9;border-radius:6px;color:#717c8e;background:#fff;font-size:7px}.file-list{min-width:0}.file-list>header{height:43px;display:flex;justify-content:space-between;align-items:center;padding:0 12px;border-bottom:1px solid #e7e9ee}.file-list>header nav{display:flex;align-items:center;gap:4px;color:#949ca9;font-size:8px}.file-list>header nav strong{color:#4e596d}.file-list>header>div{display:flex}.file-list>header>div button{width:27px;height:27px;display:grid;place-items:center;border:0;color:#8992a2;background:transparent}.file-first-banner{display:grid;grid-template-columns:24px 1fr auto;align-items:center;gap:8px;margin:9px 10px;padding:9px;border:1px solid #dfe3f2;border-radius:8px;color:#657086;background:#f5f6ff;font-size:7px}.file-first-banner svg{color:#5259b1}.file-first-banner strong{display:block;color:#414897;font-size:8px}.file-first-banner button{padding:4px 6px;border:0;border-radius:5px;color:#fff;background:#5b61b9;font-size:7px}.file-head,.file-row{display:grid;grid-template-columns:minmax(200px,1.4fr) 72px 82px 60px 24px;align-items:center;gap:6px;padding:0 10px}.file-head{height:30px;color:#9aa2af;background:#fafbfc;font-size:7px}.file-row{width:100%;min-height:48px;border:0;border-top:1px solid #eef0f3;color:#6e798b;background:#fff;text-align:left}.file-row:hover{background:#f8f9fc}.file-row>svg{display:none}.file-row>span:nth-child(2){display:flex;align-items:center;gap:8px}.file-row>span:nth-child(2)::before{content:"";width:25px;height:25px;flex:none;border-radius:7px;background:#edf0ff}.file-row strong,.file-row small{display:block}.file-row strong{overflow:hidden;color:#445065;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.file-row small{margin-top:3px;color:#9aa2af;font-size:7px}.file-row em{color:#7c8698;font-size:7px;font-style:normal}.file-row>span:nth-child(4){font-size:7px}.file-row>small{margin:0}.file-row>button{width:22px;height:22px;display:grid;place-items:center;border:0;border-radius:5px;color:#737e90;background:#eef0f4}.file-context{padding:18px 14px;border-left:1px solid #e4e7ed;background:#fafbfc}.file-context-icon{width:40px;height:40px;display:grid;place-items:center;border-radius:10px;color:#4e56ad;background:#eceeff}.file-context>strong,.file-context>small{display:block}.file-context>strong{margin-top:12px;font-size:10px}.file-context>small{margin-top:4px;color:#939baa;font-size:7px}.file-context dl{margin:16px 0}.file-context dl>div{display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid #e8eaf0;font-size:7px}.file-context dt{color:#959daa}.file-context dd{margin:0;color:#596579}.file-context>button{width:100%;margin-top:6px}.file-context>svg{display:block;margin:60px auto 10px;color:#9ba3b0}.file-context>svg~strong,.file-context>svg~small{text-align:center}
.student-page>header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:15px}.student-page>header small{color:#4c55ac;font-size:8px}.student-page>header h1{margin:5px 0;font-size:22px}.student-page>header p{margin:0;color:#7d8798;font-size:9px}.student-page>header>span{display:flex;align-items:center;gap:5px;padding:6px 8px;border-radius:7px;color:#167657;background:#e5f5ed;font-size:8px}.student-lesson-nav{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:15px;margin-bottom:12px}.student-lesson-nav>button{padding:5px 8px;border:0;border-radius:6px;color:#687489;background:#edf0f4;font-size:8px}.student-lesson-nav>div{display:flex;align-items:center;gap:8px}.student-lesson-nav i{height:4px;flex:1;overflow:hidden;border-radius:99px;background:#e5e8ed}.student-lesson-nav b{display:block;width:42%;height:100%;background:#5c62ba}.student-lesson-nav span{color:#8e97a5;font-size:7px}.student-canvas{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(270px,.65fr);min-height:480px;border:1px solid #e1e4eb;border-radius:12px;overflow:hidden;background:#fff}.student-canvas>article{padding:50px clamp(35px,6vw,80px)}.doc-label{color:#7f8999;font-size:8px;letter-spacing:.08em}.student-canvas article h2{margin:11px 0 23px;font-size:25px}.student-canvas article p{color:#4f5b6f;font-size:11px;line-height:1.9}.formula{margin:25px 0;padding:18px;border-radius:9px;color:#3e448e;background:#f0f2ff;text-align:center;font-family:Georgia,serif}.student-canvas article button{display:flex;align-items:center;gap:6px;padding:7px 9px;border:1px solid #dbe0ed;border-radius:7px;color:#59657a;background:#fff;font-size:8px}.student-canvas>aside{padding:20px;border-left:1px solid #e3e6ed;background:#fafbfc}.student-tabs{display:flex;gap:15px;border-bottom:1px solid #e0e3e8}.student-tabs button{padding:0 0 9px;border:0;border-bottom:2px solid transparent;color:#8a94a4;background:transparent;font-size:8px}.student-tabs button.active{border-color:#545bb3;color:#41479b;font-weight:750}.private-note{display:flex;align-items:center;gap:5px;margin-top:18px;color:#8b94a4;font-size:7px}.student-canvas aside h3{margin:8px 0 13px;font-size:14px}.note{padding:11px;border:1px solid #e2e5eb;border-radius:8px;background:#fff}.note small{color:#8e97a6;font-size:7px}.note p{margin:6px 0 0;color:#566176;font-size:9px;line-height:1.6}.note.new{margin-top:7px;border-color:#ccd1f4;background:#f5f6ff}.wide{width:100%;margin-top:12px}.ai-mark{width:40px;height:40px;display:grid;place-items:center;margin-top:20px;border-radius:11px;color:#fff;background:#555bb4}.student-canvas aside>p{color:#707b8d;font-size:9px;line-height:1.6}.prompt{width:100%;margin-top:7px;padding:9px;border:1px solid #e0e3e9;border-radius:7px;color:#536078;background:#fff;text-align:left;font-size:8px}
.asset-drawer{width:min(690px,72%);position:absolute;z-index:20;inset:0 0 0 auto;display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;border-left:1px solid #dce0e8;background:#fcfcfd;box-shadow:-20px 0 45px rgba(28,36,55,.13)}.asset-drawer>header{display:flex;justify-content:space-between;align-items:flex-start;padding:17px 20px;border-bottom:1px solid #e3e6eb}.asset-drawer header small,.asset-drawer header strong{display:block}.asset-drawer header small{color:#8993a4;font-size:8px}.asset-drawer header strong{margin-top:4px;font-size:14px}.asset-drawer header button{width:30px;height:30px;display:grid;place-items:center;border:0;border-radius:7px;color:#7d8798;background:#eef0f4}.asset-meta{display:flex;gap:6px;padding:9px 20px;border-bottom:1px solid #e7e9ee}.asset-meta span{padding:3px 6px;border-radius:5px;color:#606a80;background:#eef0f4;font-size:7px}.document-editor{margin:18px 24px;padding:42px 55px;overflow:auto;border:1px solid #e2e5ea;background:#fff;box-shadow:0 12px 28px rgba(34,42,61,.06)}.document-editor>p:first-child{color:#8c95a4;font-size:8px}.document-editor h2{margin:10px 0 28px;font-size:24px}.document-editor h3{margin:24px 0 8px;font-size:12px}.document-editor p{color:#515d70;font-size:10px;line-height:1.85}.document-editor button{display:flex;align-items:center;gap:5px;margin-top:22px;padding:7px 9px;border:1px dashed #bec4ed;border-radius:7px;color:#4d55ac;background:#f8f8ff;font-size:8px}.ppt-editor{min-height:0;display:grid;grid-template-columns:100px 1fr;padding:17px;overflow:hidden;background:#eef0f4}.ppt-editor>aside{display:grid;align-content:start;gap:6px;padding-right:8px;overflow:auto}.ppt-editor>aside button{aspect-ratio:16/10;position:relative;display:grid;place-items:center;border:1px solid #d7dbe4;border-radius:5px;color:#8992a2;background:#fff;font-size:8px}.ppt-editor>aside button.active{border:2px solid #5960b6}.ppt-editor>aside span{position:absolute;top:4px;left:5px;font-size:6px}.ppt-editor>div{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px;border:1px solid #dce0e7;background:#fff;text-align:center}.ppt-editor>div small{color:#858fa0;font-size:8px}.ppt-editor>div h2{margin:18px 0 8px;font-size:26px}.ppt-editor>div p{color:#697589;font-size:10px}.ppt-editor>div span{margin-top:30px;padding:15px 28px;border-radius:8px;color:#3e448d;background:#eef0ff;font-family:Georgia,serif}.file-preview{display:flex;flex-direction:column;align-items:center;padding:44px;overflow:auto;text-align:center}.file-preview>svg{color:#5a61b6}.file-preview h2{margin:15px 0 7px;font-size:18px}.file-preview p{margin:0;color:#7b8697;font-size:9px}.preview-paper{width:min(430px,100%);min-height:220px;display:flex;flex-direction:column;align-items:flex-start;margin-top:25px;padding:28px;border:1px solid #dfe3e9;background:#fff;box-shadow:0 10px 28px rgba(30,40,60,.06);text-align:left}.preview-paper span{color:#959daa;font-size:7px;letter-spacing:.13em}.preview-paper strong{margin-top:20px;font-size:14px}.preview-paper i{width:100%;height:80px;margin-top:20px;background:repeating-linear-gradient(#eef0f3 0 1px,transparent 1px 15px)}.asset-drawer>footer{display:flex;align-items:center;justify-content:flex-end;gap:7px;padding:10px 16px;border-top:1px solid #e1e4e9}.asset-drawer>footer>div{display:flex;align-items:center;gap:5px;margin-right:auto;color:#7d8798;font-size:7px}.drawer-enter-active,.drawer-leave-active{transition:opacity .22s ease,transform .3s cubic-bezier(.16,1,.3,1)}.drawer-enter-from,.drawer-leave-to{opacity:0;transform:translateX(25px)}.toast{position:fixed;z-index:50;left:50%;bottom:24px;display:flex;align-items:center;gap:6px;padding:9px 12px;border:1px solid #d4e4dc;border-radius:8px;color:#23604d;background:#f1faf6;box-shadow:0 10px 28px rgba(31,52,44,.13);font-size:8px;transform:translateX(-50%)}.toast-enter-active,.toast-leave-active{transition:opacity .2s ease,transform .25s ease}.toast-enter-from,.toast-leave-to{opacity:0;transform:translate(-50%,7px)}

/* Product-quality visual pass: the concept lab should read like a real app, not a compressed wireframe. */
.mode-lab{
  --ink:#15213a;
  --muted:#68758c;
  --line:#e4e8f1;
  --brand:#5752e8;
  width:100vw;
  height:100dvh;
  position:fixed;
  z-index:100;
  inset:0;
  grid-template-rows:82px 64px minmax(0,1fr);
  background:#f4f6fa;
}
.lab-header{padding:0 28px;background:rgba(255,255,255,.96);box-shadow:0 1px 0 rgba(31,42,68,.04)}
.lab-brand img{width:40px;height:40px;filter:drop-shadow(0 6px 10px rgba(79,70,229,.18))}
.lab-brand strong{font-size:16px;letter-spacing:-.02em}.lab-brand small{font-size:11px}
.mode-switch{gap:6px;padding:5px;border-radius:15px;background:#f0f2f7;box-shadow:inset 0 0 0 1px #e1e5ed}
.mode-switch button{min-width:156px;height:54px;grid-template-columns:30px 1fr;padding:7px 11px;border-radius:11px;transition:transform .18s ease,box-shadow .18s ease,background .18s ease}
.mode-switch button:hover{transform:translateY(-1px)}
.mode-switch button>span{width:28px;height:28px;border-radius:9px;font-size:11px}.mode-switch button strong{font-size:12px}.mode-switch button small{font-size:9px}
.mode-switch button.active{box-shadow:0 8px 22px rgba(36,45,74,.11)}
.back-button{height:38px;padding:0 13px;border-radius:10px;font-size:11px}.role-switch{padding:4px;border-radius:11px}.role-switch button{height:32px;padding:0 10px;border-radius:8px;font-size:11px}
.mode-intro{padding:0 28px;background:linear-gradient(90deg,#fbfcff,#f7f8fc)}
.mode-intro>div{gap:12px}.mode-intro>div span{padding:4px 8px;border-radius:7px;font-size:10px}.mode-intro>div strong{font-size:15px}.mode-intro>div small,.mode-intro>p{font-size:11px}
.course-shell{grid-template-columns:238px minmax(0,1fr);background:#f8f9fc}
.course-rail{padding:22px 14px;background:#fff;box-shadow:6px 0 24px rgba(28,39,65,.025)}
.course-identity{grid-template-columns:44px 1fr auto;gap:11px;padding:0 8px 20px}.course-identity>span{width:44px;height:44px;border-radius:13px;font-size:17px;background:linear-gradient(145deg,#eef0ff,#dde1ff)}
.course-identity strong{font-size:14px}.course-identity small{font-size:10px}.course-nav{gap:6px;padding:20px 0}.course-nav button{height:46px;gap:11px;padding:0 13px;border-radius:11px;font-size:12px;transition:background .18s ease,transform .18s ease}.course-nav button:hover{transform:translateX(2px)}.course-nav button.active{background:linear-gradient(90deg,#eceeff,#f3f4ff)}.course-nav button small{font-size:10px}.rail-foot{padding:13px;border-radius:12px;font-size:10px;background:#f7f8fb}
.work-area{padding:28px 32px;background:radial-gradient(circle at 85% 0,rgba(87,82,232,.035),transparent 28%),#f8f9fc}
.work-heading{margin-bottom:22px}.work-heading small{font-size:10px}.work-heading h1{margin-top:6px;font-size:28px}.work-heading p{margin-top:7px;font-size:12px}.work-actions{gap:10px}.primary,.secondary{height:42px;padding:0 16px;border-radius:11px;font-size:11px;transition:transform .18s ease,box-shadow .18s ease}.primary{background:linear-gradient(135deg,#625cf2,#4d46db);box-shadow:0 8px 18px rgba(79,70,229,.2)}.primary:hover,.secondary:hover{transform:translateY(-1px)}
.view-switch{margin-bottom:20px;padding:5px;border-radius:14px}.view-switch button{min-width:180px;height:48px;grid-template-columns:30px 1fr;padding:5px 12px;border-radius:10px}.view-switch button small{font-size:9px}.view-switch>span{font-size:10px}
.production-view{gap:16px}.stage-line{padding:16px 19px;border-radius:15px;box-shadow:0 8px 24px rgba(31,42,68,.035)}.stage-line>div{min-width:145px;grid-template-columns:32px 1fr}.stage-line>div>span{width:30px;height:30px;font-size:10px}.stage-line>div b{font-size:11px}.stage-line>div small{font-size:9px}
.outline-card{grid-template-columns:44px minmax(0,1fr) auto auto;gap:14px;padding:15px 18px;border-radius:15px;box-shadow:0 8px 24px rgba(31,42,68,.035)}.outline-card>svg{width:44px;height:44px;border-radius:12px}.outline-card strong{font-size:13px}.outline-card small,.outline-card button{font-size:10px}.outline-card em{font-size:9px}
.lesson-toolbar{padding:17px 16px 12px}.lesson-toolbar strong{font-size:14px}.lesson-toolbar small{font-size:10px}.lesson-toolbar label{width:220px;height:38px;border-radius:10px}.lesson-toolbar input{font-size:10px}
.lesson-table{border-radius:15px;box-shadow:0 10px 30px rgba(31,42,68,.035)}.lesson-head{height:42px;font-size:10px}.lesson-row{min-height:68px;padding:8px 14px}.lesson-row>span:first-child>b{font-size:11px}.lesson-row>span strong{font-size:11px}.lesson-row>span small{font-size:9px}.lesson-row>button{padding:9px 10px;border-radius:10px}.lesson-row>button b,.lesson-row>span:last-child b{font-size:10px}
.file-view{min-height:540px;grid-template-columns:232px minmax(420px,1fr) 245px;border-radius:16px;box-shadow:0 14px 36px rgba(31,42,68,.05)}.file-tree{padding:14px 10px}.file-tree header{height:42px}.file-tree header strong{font-size:12px}.file-tree>button{height:40px;gap:7px;padding:0 10px;border-radius:9px;font-size:10px}.tree-foot button{height:34px;border-radius:8px;font-size:9px}.file-list>header{height:54px;padding:0 16px}.file-list>header nav{font-size:10px}.file-first-banner{grid-template-columns:30px 1fr auto;gap:10px;margin:12px 14px;padding:12px;border-radius:11px;font-size:9px}.file-first-banner strong{font-size:11px}.file-first-banner button{padding:7px 10px;border-radius:7px;font-size:9px}.file-head,.file-row{grid-template-columns:minmax(210px,1.4fr) 82px 90px 68px 28px;padding:0 14px}.file-head{height:38px;font-size:9px}.file-row{min-height:62px}.file-row>span:nth-child(2)::before{width:34px;height:34px;border-radius:10px}.file-row strong{font-size:11px}.file-row small,.file-row em,.file-row>span:nth-child(4){font-size:9px}.file-row>button{width:28px;height:28px;border-radius:8px}.file-context{padding:24px 18px}.file-context-icon{width:48px;height:48px;border-radius:13px}.file-context>strong{font-size:13px}.file-context>small,.file-context dl>div{font-size:9px}
.file-row.selected{background:#f6f7ff;box-shadow:inset 3px 0 #625cf2}.file-name{min-width:0;display:flex!important;align-items:center;gap:11px}.file-name>i{width:36px;height:36px;flex:none;display:grid;place-items:center;border-radius:10px;color:#5752e8;background:linear-gradient(145deg,#f0f1ff,#e6e8ff)}.file-name>span{min-width:0}.file-row:hover .file-name>i{background:#dfe2ff}.file-row>span:nth-child(3){font-size:9px;color:#68758c}
.overview-page{gap:17px}.next-lesson{min-height:220px;padding:34px;border-radius:17px;box-shadow:0 12px 32px rgba(31,42,68,.04)}.next-lesson>span{font-size:11px}.next-lesson h2{font-size:30px}.next-lesson p{font-size:12px}.overview-stats{gap:10px}.overview-stats>div{padding:19px;border-radius:14px}.overview-stats span,.overview-stats small{font-size:10px}.overview-stats strong{font-size:21px}.overview-list{border-radius:15px}.overview-list header{padding:16px 18px}.overview-list header strong{font-size:12px}.overview-list header small{font-size:10px}.overview-list>button{padding:14px 18px}.overview-list strong{font-size:11px}.overview-list small{font-size:9px}
.simple-page{border-radius:16px;box-shadow:0 12px 32px rgba(31,42,68,.04)}.simple-page>header{padding:22px}.simple-page>header strong{font-size:16px}.simple-page>header small{font-size:10px}.release-head{height:42px;font-size:10px}.release-row{min-height:58px;font-size:10px}.release-row>strong{font-size:11px}.feedback-summary span,.feedback-summary small{font-size:10px}.question-list>strong{font-size:12px}.question-list b{font-size:11px}.question-list small{font-size:10px}
.student-page>header small{font-size:10px}.student-page>header h1{font-size:28px}.student-page>header p{font-size:12px}.student-page>header>span{font-size:10px}.student-lesson-nav>button{font-size:10px}.student-lesson-nav span{font-size:9px}.student-canvas{min-height:560px;border-radius:16px;box-shadow:0 14px 36px rgba(31,42,68,.05)}.doc-label{font-size:10px}.student-canvas article h2{font-size:30px}.student-canvas article p{font-size:13px}.student-canvas article button{font-size:10px}.student-tabs button{font-size:10px}.private-note,.note small{font-size:9px}.student-canvas aside h3{font-size:17px}.note p,.student-canvas aside>p{font-size:11px}.prompt{font-size:10px}
.asset-drawer{width:min(780px,76%)}.asset-drawer header small{font-size:10px}.asset-drawer header strong{font-size:17px}.asset-meta span{font-size:9px}.document-editor{margin:24px 30px;padding:50px 64px;border-radius:4px}.document-editor>p:first-child{font-size:10px}.document-editor h2{font-size:29px}.document-editor h3{font-size:15px}.document-editor p{font-size:12px}.document-editor button{font-size:10px}.ppt-editor{grid-template-columns:120px 1fr}.ppt-editor>aside button{font-size:10px}.ppt-editor>div small{font-size:10px}.ppt-editor>div h2{font-size:31px}.ppt-editor>div p{font-size:12px}.file-preview h2{font-size:22px}.file-preview p{font-size:11px}.asset-drawer>footer>div,.toast{font-size:10px}

/* Deep simulation pass: one Qizhi visual system, three genuinely different interaction models. */
.object-context{min-height:70px;display:flex;align-items:center;gap:18px;margin:0 0 18px;padding:12px 16px;border:1px solid var(--lz-border,#dfe4ee);border-radius:var(--lz-radius-surface,16px);background:rgba(255,255,255,.82);box-shadow:var(--lz-shadow-panel,0 8px 28px rgba(79,70,229,.08))}
.object-context__identity{min-width:255px;display:flex;align-items:center;gap:11px}.object-context__identity>span{width:36px;height:36px;display:grid;place-items:center;border-radius:11px;color:#fff;background:linear-gradient(135deg,#6366f1,#8b5cf6);font-size:13px;font-weight:800;box-shadow:0 6px 14px rgba(99,102,241,.18)}
.object-context__identity small,.object-context__identity strong{display:block}.object-context__identity small{color:var(--lz-text-muted,#94a3b8);font-size:10px}.object-context__identity strong{margin-top:3px;color:var(--lz-text-strong,#1e293b);font-size:12px}
.object-context__facts{min-width:0;display:flex;flex:1;gap:24px}.object-context__facts span{min-width:120px}.object-context__facts small,.object-context__facts b{display:block}.object-context__facts small{color:var(--lz-text-muted,#94a3b8);font-size:10px}.object-context__facts b{margin-top:4px;color:var(--lz-text,#334155);font-size:11px}
.mode-operation{display:grid;grid-template-columns:minmax(260px,1fr) auto auto;align-items:center;gap:20px;padding:17px 18px;border:1px solid var(--lz-border,#dfe4ee);border-radius:16px;background:rgba(255,255,255,.86);box-shadow:0 8px 28px rgba(79,70,229,.055)}
.mode-operation>div:first-child small,.mode-operation>div:first-child strong,.mode-operation>div:first-child span{display:block}.mode-operation>div:first-child small{color:var(--lz-brand-strong,#4f46e5);font-size:10px;font-weight:700}.mode-operation>div:first-child strong{margin-top:4px;color:var(--lz-text-strong,#1e293b);font-size:14px}.mode-operation>div:first-child span{margin-top:4px;color:var(--lz-text-secondary,#64748b);font-size:10px;line-height:1.55}
.mode-operation ol{display:flex;align-items:center;gap:4px;margin:0;padding:0;list-style:none}.mode-operation ol li{min-height:30px;display:flex;align-items:center;gap:4px;padding:0 9px;border-radius:8px;color:var(--lz-text-muted,#94a3b8);background:#f1f5f9;font-size:9px;white-space:nowrap}.mode-operation ol li.done{color:var(--lz-success,#047857);background:var(--lz-success-soft,#ecfdf5)}.mode-operation ol li.active{color:var(--lz-brand-strong,#4f46e5);background:var(--lz-brand-soft,#eef2ff);font-weight:750}
.object-pointers{display:flex!important;gap:6px}.object-pointers span{padding:6px 9px!important;border:1px solid var(--lz-border,#dfe4ee);border-radius:8px;color:var(--lz-text-secondary,#64748b)!important;background:#fff;font-size:9px!important}
.lesson-row{cursor:pointer}.lesson-row.selected{background:#f7f7ff;box-shadow:inset 3px 0 var(--lz-brand,#6366f1)}
.release-summary{display:flex;align-items:center;justify-content:space-between;gap:20px;margin:16px;padding:15px 17px;border:1px solid rgba(165,180,252,.75);border-radius:13px;background:linear-gradient(105deg,#f5f7ff,#fff)}.release-summary small,.release-summary strong,.release-summary span{display:block}.release-summary small{color:var(--lz-brand-strong,#4f46e5);font-size:10px}.release-summary strong{margin-top:4px;color:var(--lz-text-strong,#1e293b);font-size:14px}.release-summary span{margin-top:4px;color:var(--lz-text-secondary,#64748b);font-size:10px}
.question-list button{grid-template-columns:28px minmax(0,1fr) auto}.question-list button em{color:var(--lz-brand-strong,#4f46e5);font-size:10px;font-style:normal}.question-list button.selected{background:var(--lz-brand-soft,#eef2ff)}
.feedback-proposal{display:grid;grid-template-columns:36px minmax(0,1fr) auto;align-items:center;gap:12px;margin:0 20px 20px;padding:15px;border:1px solid rgba(165,180,252,.75);border-radius:13px;background:#f8f8ff}.feedback-proposal>svg{color:var(--lz-brand,#6366f1)}.feedback-proposal small,.feedback-proposal strong{display:block}.feedback-proposal small{color:var(--lz-text-muted,#94a3b8);font-size:9px}.feedback-proposal strong{margin-top:3px;color:var(--lz-text-strong,#1e293b);font-size:12px}.feedback-proposal p{margin:4px 0 0;color:var(--lz-text-secondary,#64748b);font-size:10px}
.path-actions{display:flex;align-items:center;gap:7px;margin:0 14px 12px}.path-actions button{height:32px;display:inline-flex;align-items:center;gap:5px;padding:0 9px;border:1px solid var(--lz-border,#dfe4ee);border-radius:8px;color:var(--lz-text-secondary,#64748b);background:#fff;font-size:9px}.path-actions button:hover{color:var(--lz-brand-strong,#4f46e5);border-color:#c7d2fe;background:#f5f7ff}.path-actions>span{margin-left:auto;color:var(--lz-text-muted,#94a3b8);font-size:9px}
.file-list>header>div button.active{color:var(--lz-brand-strong,#4f46e5);border-radius:7px;background:var(--lz-brand-soft,#eef2ff)}.path-actions button.active{color:var(--lz-warning,#b45309);border-color:#fed7aa;background:var(--lz-warning-soft,#fffbeb)}
.file-list.grid-layout{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));align-content:start;gap:10px;padding:0 14px 14px}.file-list.grid-layout>header,.file-list.grid-layout>.file-first-banner,.file-list.grid-layout>.path-actions,.file-list.grid-layout>.file-head{grid-column:1/-1}.file-list.grid-layout>header{margin:0 -14px}.file-list.grid-layout>.file-head{display:none}.file-list.grid-layout>.file-row{min-height:132px;display:flex;flex-direction:column;align-items:stretch;justify-content:space-between;gap:10px;padding:14px;border:1px solid var(--lz-border,#dfe4ee);border-radius:12px}.file-list.grid-layout>.file-row>em,.file-list.grid-layout>.file-row>span:nth-child(3),.file-list.grid-layout>.file-row>small{display:none}.file-list.grid-layout>.file-row>button{align-self:flex-end}
.file-context>.offering-status-badge{margin-top:10px}
.student-mode-context{display:grid;grid-template-columns:36px minmax(210px,auto) 1fr;align-items:center;gap:11px;margin-bottom:14px;padding:11px 13px;border:1px solid var(--lz-border,#dfe4ee);border-radius:12px;background:rgba(255,255,255,.8)}.student-mode-context>svg{width:36px;height:36px;padding:9px;border-radius:10px;color:var(--lz-brand-strong,#4f46e5);background:var(--lz-brand-soft,#eef2ff)}.student-mode-context small,.student-mode-context strong{display:block}.student-mode-context small{color:var(--lz-text-muted,#94a3b8);font-size:9px}.student-mode-context strong{margin-top:2px;color:var(--lz-text-strong,#1e293b);font-size:11px}.student-mode-context>span{justify-self:end;color:var(--lz-text-secondary,#64748b);font-size:10px}
.student-mode-surface{min-height:46px;display:flex;align-items:center;gap:7px;margin:-4px 0 14px;padding:8px 11px;border:1px solid var(--lz-border,#dfe4ee);border-radius:11px;background:rgba(255,255,255,.72)}
.student-mode-surface--sequence span{padding:6px 8px;border-radius:7px;color:var(--lz-text-muted,#94a3b8);background:#f1f5f9;font-size:9px}.student-mode-surface--sequence span.done{color:var(--lz-success,#047857);background:var(--lz-success-soft,#ecfdf5)}.student-mode-surface--sequence span.active{color:var(--lz-brand-strong,#4f46e5);background:var(--lz-brand-soft,#eef2ff);font-weight:750}.student-mode-surface--sequence i{width:18px;height:1px;background:#cbd5e1}
.student-mode-surface--lesson button{height:30px;display:inline-flex;align-items:center;gap:5px;padding:0 9px;border:1px solid var(--lz-border,#dfe4ee);border-radius:8px;color:var(--lz-text-secondary,#64748b);background:#fff;font-size:9px}.student-mode-surface--lesson button.active{color:var(--lz-brand-strong,#4f46e5);border-color:#c7d2fe;background:var(--lz-brand-soft,#eef2ff)}.student-mode-surface--lesson>span{margin-left:auto;color:var(--lz-text-muted,#94a3b8);font-size:9px}
.student-mode-surface--folders{display:grid;grid-template-columns:1fr 1fr auto}.student-mode-surface--folders button{min-height:42px;display:flex;align-items:center;gap:8px;padding:6px 10px;border:1px solid var(--lz-border,#dfe4ee);border-radius:9px;color:var(--lz-text-secondary,#64748b);background:#fff;text-align:left}.student-mode-surface--folders button.active{border-color:#c7d2fe;background:var(--lz-brand-soft,#eef2ff)}.student-mode-surface--folders button span{flex:1}.student-mode-surface--folders small,.student-mode-surface--folders strong{display:block}.student-mode-surface--folders small{font-size:8px}.student-mode-surface--folders strong{margin-top:2px;color:var(--lz-text-strong,#1e293b);font-size:10px}.student-mode-surface--folders em{font-size:9px;font-style:normal}.student-mode-surface--folders>button:last-child{justify-content:center;color:var(--lz-brand-strong,#4f46e5);font-size:9px;font-weight:700}
.document-editor p.ai-revised{margin-left:-12px;padding:10px 12px;border-left:3px solid var(--lz-brand,#6366f1);background:var(--lz-brand-soft,#eef2ff)}.ai-revision-note{display:flex;align-items:center;gap:8px;margin-top:10px;padding:9px 10px;border:1px solid #c7d2fe;border-radius:8px;color:var(--lz-brand-strong,#4f46e5);background:#f8f8ff}.ai-revision-note b,.ai-revision-note small{display:block}.ai-revision-note b{font-size:10px}.ai-revision-note small{margin-top:2px;color:var(--lz-text-secondary,#64748b);font-size:8px}
.lesson-focus-workbench{min-height:480px;display:grid;grid-template-columns:205px minmax(430px,1fr) 220px;overflow:hidden;border:1px solid var(--lz-border,#dfe4ee);border-radius:16px;background:rgba(255,255,255,.86);box-shadow:var(--lz-shadow-panel,0 8px 28px rgba(79,70,229,.08))}.lesson-focus-list{padding:13px 10px;border-right:1px solid var(--lz-border,#dfe4ee);background:#fafbff}.lesson-focus-list header{padding:4px 8px 12px}.lesson-focus-list header small,.lesson-focus-list header strong{display:block}.lesson-focus-list header small{color:var(--lz-text-muted,#94a3b8);font-size:9px}.lesson-focus-list header strong{margin-top:4px;color:var(--lz-text-strong,#1e293b);font-size:11px}.lesson-focus-list>button{width:100%;min-height:54px;display:grid;grid-template-columns:30px minmax(0,1fr) 7px;align-items:center;gap:8px;margin:3px 0;padding:7px 8px;border:0;border-radius:10px;color:var(--lz-text-secondary,#64748b);background:transparent;text-align:left}.lesson-focus-list>button:hover,.lesson-focus-list>button.active{color:var(--lz-brand-strong,#4f46e5);background:var(--lz-brand-soft,#eef2ff)}.lesson-focus-list>button>span{width:29px;height:29px;display:grid;place-items:center;border-radius:8px;background:#fff;font-size:9px;font-weight:800}.lesson-focus-list button strong,.lesson-focus-list button small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.lesson-focus-list button strong{font-size:10px}.lesson-focus-list button small{margin-top:3px;color:var(--lz-text-muted,#94a3b8);font-size:8px}.lesson-focus-list button>i{width:7px;height:7px;border-radius:50%;background:#cbd5e1}.lesson-focus-list button>i.state-published{background:var(--lz-success,#047857)}.lesson-focus-list button>i.state-ready{background:var(--lz-warning,#b45309)}
.lesson-focus-main{min-width:0;padding:22px}.lesson-focus-main>header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.lesson-focus-main header small{color:var(--lz-brand-strong,#4f46e5);font-size:9px;font-weight:700}.lesson-focus-main h2{margin:5px 0 4px;color:var(--lz-text-strong,#1e293b);font-size:22px}.lesson-focus-main p{margin:0;color:var(--lz-text-secondary,#64748b);font-size:10px}.artifact-board{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:20px}.artifact-board>button{min-height:92px;display:grid;grid-template-columns:38px minmax(0,1fr) auto;align-items:center;gap:10px;padding:14px;border:1px solid var(--lz-border,#dfe4ee);border-radius:13px;color:var(--lz-brand-strong,#4f46e5);background:#fff;text-align:left;transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}.artifact-board>button:hover{transform:translateY(-2px);border-color:#c7d2fe;box-shadow:0 10px 24px rgba(79,70,229,.1)}.artifact-board>button>svg:first-child{width:38px;height:38px;padding:9px;border-radius:10px;background:var(--lz-brand-soft,#eef2ff)}.artifact-board small,.artifact-board strong,.artifact-board em{display:block}.artifact-board small{color:var(--lz-text-muted,#94a3b8);font-size:8px}.artifact-board strong{margin-top:3px;color:var(--lz-text-strong,#1e293b);font-size:11px}.artifact-board em{margin-top:4px;color:var(--lz-text-secondary,#64748b);font-size:9px;font-style:normal}.dependency-line{display:flex;align-items:center;justify-content:center;gap:7px;margin-top:18px;padding:11px;border-radius:10px;background:#f8fafc}.dependency-line span{padding:5px 7px;border-radius:7px;color:var(--lz-text-secondary,#64748b);background:#fff;font-size:9px}.dependency-line span.student{color:var(--lz-success,#047857);background:var(--lz-success-soft,#ecfdf5)}.dependency-line>svg{color:#94a3b8}
.lesson-focus-status{padding:21px 16px;border-left:1px solid var(--lz-border,#dfe4ee);background:#fafbff}.lesson-focus-status>small{display:block;margin-bottom:8px;color:var(--lz-text-muted,#94a3b8);font-size:9px}.lesson-focus-status dl{margin:20px 0}.lesson-focus-status dl div{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--lz-border,#dfe4ee);font-size:9px}.lesson-focus-status dt{color:var(--lz-text-muted,#94a3b8)}.lesson-focus-status dd{margin:0;color:var(--lz-text,#334155);font-weight:700}.lesson-focus-status>button{width:100%;height:34px;display:flex;align-items:center;justify-content:center;gap:6px;margin-top:7px;border:1px solid var(--lz-border,#dfe4ee);border-radius:9px;color:var(--lz-text-secondary,#64748b);background:#fff;font-size:9px}.lesson-focus-status>button:hover{color:var(--lz-brand-strong,#4f46e5);border-color:#c7d2fe;background:var(--lz-brand-soft,#eef2ff)}
.version-ribbon{display:flex;align-items:center;gap:9px;padding:10px 20px;border-bottom:1px solid var(--lz-border,#dfe4ee);background:#f8fafc}.version-ribbon>span{min-width:78px}.version-ribbon small,.version-ribbon b{display:block}.version-ribbon small{color:var(--lz-text-muted,#94a3b8);font-size:8px}.version-ribbon b{margin-top:2px;color:var(--lz-text,#334155);font-size:10px}.version-ribbon>i{width:18px;height:1px;background:#cbd5e1}.version-ribbon button{height:29px;display:inline-flex;align-items:center;gap:5px;margin-left:auto;padding:0 8px;border:1px solid var(--lz-border,#dfe4ee);border-radius:7px;color:var(--lz-text-secondary,#64748b);background:#fff;font-size:9px}
.primary{border:1px solid transparent;background:linear-gradient(135deg,#6366f1,#8b5cf6);box-shadow:0 7px 16px rgba(99,102,241,.2)}.secondary{border-color:rgba(203,213,225,.72);background:rgba(255,255,255,.82);color:var(--lz-text-secondary,#64748b)}
.mode-lab button:focus-visible{outline:3px solid rgba(99,102,241,.24);outline-offset:2px}
@media(max-width:1050px){.lab-header{grid-template-columns:1fr auto}.mode-switch{order:3;grid-column:1/-1;position:absolute;z-index:30;top:74px;left:50%;transform:translateX(-50%)}.mode-intro{padding-top:58px;height:110px}.mode-lab{grid-template-rows:70px 110px minmax(0,1fr)}.file-view{grid-template-columns:180px 1fr}.file-context{display:none}.asset-drawer{width:min(720px,82%)}}
@media(max-width:760px){.mode-lab{overflow:auto}.lab-header{position:sticky;top:0;z-index:40}.lab-brand small,.back-button{display:none}.mode-switch button{min-width:105px}.mode-intro>p{display:none}.course-shell{min-height:800px;grid-template-columns:1fr}.course-rail{display:none}.work-area{padding:16px}.lesson-table{overflow:auto}.lesson-head,.lesson-row{min-width:720px}.file-view{grid-template-columns:155px minmax(360px,1fr);overflow:auto}.asset-drawer{position:fixed;width:100%;max-width:none}.student-canvas{grid-template-columns:1fr}.student-canvas>aside{border-top:1px solid #e3e6ed;border-left:0}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{transition-duration:.01ms!important}}
</style>
