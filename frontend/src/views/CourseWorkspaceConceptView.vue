<template>
  <main class="workspace-concept">
    <header class="concept-header">
      <div class="concept-title">
        <span class="concept-mark"><BookOpenCheck :size="20" /></span>
        <div>
          <p>课程工作台</p>
          <h1>{{ activeProduct === 'course' ? '把一门课从想法做到发布' : '视频分析' }}</h1>
        </div>
      </div>

      <nav class="product-switch" aria-label="工作台功能">
        <button type="button" :class="{ active: activeProduct === 'course' }" @click="activeProduct = 'course'">
          <PanelsTopLeft :size="16" />课程管理
        </button>
        <button type="button" :class="{ active: activeProduct === 'video' }" @click="activeProduct = 'video'">
          <Video :size="16" />视频分析
        </button>
      </nav>

      <div v-if="activeProduct === 'course'" class="role-switch" aria-label="切换演示角色">
        <button type="button" :class="{ active: role === 'teacher' }" @click="setRole('teacher')"><GraduationCap :size="15" />教师端</button>
        <button type="button" :class="{ active: role === 'student' }" @click="setRole('student')"><UserRound :size="15" />学生端</button>
      </div>
    </header>

    <section v-if="activeProduct === 'video'" class="video-placeholder">
      <div class="video-placeholder__visual"><Video :size="34" /><span>VIDEO REPORT</span></div>
      <div class="video-placeholder__copy">
        <p>工作台内的独立入口</p>
        <h2>视频分析不要求先选择课程</h2>
        <span>上传视频后进入既有分析能力并获得报告。本原型只确认入口位置，不重新设计分析流程。</span>
        <div class="video-actions"><button type="button" class="primary-action"><UploadCloud :size="16" />选择视频</button><button type="button" class="quiet-action"><FileBarChart :size="16" />历史报告</button></div>
      </div>
    </section>

    <section v-else class="course-shell">
      <aside class="course-rail">
        <div class="course-picker">
          <small>{{ role === 'teacher' ? '正在备课' : '正在学习' }}</small>
          <button type="button" :aria-expanded="coursePickerOpen" @click="coursePickerOpen = !coursePickerOpen">
            <span class="course-avatar">高</span>
            <span><strong>高等数学</strong><em>2026 秋季</em></span>
            <ChevronDown :size="15" :class="{ rotated: coursePickerOpen }" />
          </button>
          <Transition name="picker">
            <div v-if="coursePickerOpen" class="course-picker-menu">
              <div class="course-picker-menu__heading"><span>课程空间</span><button type="button" @click="notify('已返回课程空间（模拟）')">查看全部</button></div>
              <button type="button" class="course-option active" @click="coursePickerOpen = false"><span class="course-avatar">高</span><span><strong>高等数学</strong><small>2026 秋季 · 正在备课</small></span><CircleCheck :size="15" /></button>
              <button type="button" class="course-option" @click="notify('已切换到《线性代数》（模拟）')"><span class="course-avatar is-green">线</span><span><strong>线性代数</strong><small>2026 春季 · 已归档</small></span></button>
              <button type="button" class="new-course-option" @click="notify('打开新建课程流程（模拟）')"><Plus :size="15" />新建课程</button>
            </div>
          </Transition>
        </div>

        <nav class="course-nav" aria-label="课程功能">
          <template v-if="role === 'teacher'">
            <button type="button" :class="{ active: teacherSection === 'overview' }" @click="teacherSection = 'overview'"><LayoutDashboard :size="17" />课程概览</button>
            <button type="button" :class="{ active: teacherSection === 'production' }" @click="teacherSection = 'production'"><Sparkles :size="17" />课程生产<span class="nav-count">3</span></button>
            <button type="button" :class="{ active: teacherSection === 'files' }" @click="teacherSection = 'files'"><FolderTree :size="17" />课程文件</button>
            <button type="button"><Send :size="17" />发布与学生</button>
            <button type="button"><BarChart3 :size="17" />反馈与数据</button>
          </template>
          <template v-else>
            <button type="button" class="active"><LayoutDashboard :size="17" />课程首页</button>
            <button type="button"><BookOpen :size="17" />课程内容</button>
            <button type="button"><NotebookPen :size="17" />我的笔记<span class="nav-count">12</span></button>
            <button type="button"><ListChecks :size="17" />练习与作业</button>
            <button type="button"><Bot :size="17" />AI 教师</button>
            <button type="button"><BarChart3 :size="17" />学习进度</button>
          </template>
        </nav>

        <div class="rail-note">
          <LockKeyhole :size="15" />
          <span>{{ role === 'teacher' ? '草稿只有教师可见，发布后学生才会收到新版本。' : '教师原文只读；笔记和 AI 记录仅属于你。' }}</span>
        </div>
      </aside>

      <template v-if="role === 'teacher'">
        <section v-if="teacherSection !== 'overview'" class="teacher-stage" :class="{ 'teacher-stage--production': teacherSection === 'production' }">
          <header class="stage-heading">
            <div>
              <p>{{ teacherSection === 'production' ? 'COURSE PRODUCTION' : 'COURSE FILES' }}</p>
              <h2>{{ teacherSection === 'production' ? '课程生产' : '课程文件' }}</h2>
              <span>{{ teacherSection === 'production' ? '大纲统领全课，按讲次持续生成教案、课件与发布版本。' : '保留真实目录层级；受管文档、上传文件与导出版本都在这里。' }}</span>
            </div>
            <div v-if="teacherSection === 'production'" class="stage-actions">
              <button type="button" class="quiet-action" @click="notify('生产清单已准备，可导出为 Excel（模拟）')"><FileOutput :size="16" />导出生产清单</button>
              <button type="button" class="primary-action" @click="selectProductionArtifact(lessons[5]!, 'lesson')"><Plus :size="16" />继续备课</button>
            </div>
            <button v-else type="button" class="quiet-action"><MoreHorizontal :size="17" />更多</button>
          </header>

          <div v-if="teacherSection === 'production'" class="production-workspace" :class="{ 'inspector-open': selectedLesson }">
            <div class="production-main">
              <section class="production-track" aria-label="课程生产阶段">
                <div v-for="(stage, index) in stages" :key="stage.id" class="track-step" :class="stage.state">
                  <span><CircleCheck v-if="stage.state === 'done'" :size="15" /><template v-else>{{ index + 1 }}</template></span>
                  <div><strong>{{ stage.name }}</strong><small>{{ stage.label }}</small></div>
                  <i v-if="index < stages.length - 1" />
                </div>
              </section>

              <section class="outline-source">
                <div class="outline-source__mark"><BookOpenCheck :size="19" /></div>
                <div class="outline-source__copy">
                  <div><strong>课程教学大纲</strong><span class="version-chip">v3</span><span class="state-chip is-ready">已确认</span></div>
                  <p>16 讲 · 32 学时 · 6 个课程目标 · 更新于今天 14:32</p>
                </div>
                <div class="outline-source__knowledge"><span>知识结构</span><strong>42 个节点</strong><small>本轮先展示来源，不自动级联覆盖</small></div>
                <button type="button" class="text-action" @click="notify('将打开现有大纲编辑器（模拟）')">编辑大纲<ChevronRight :size="14" /></button>
              </section>

              <section class="production-summary" aria-label="课程生产概况">
                <div><span>分讲教案</span><strong>8<small>/16</small></strong><em><i style="width:50%" /></em></div>
                <div><span>课堂课件</span><strong>5<small>/16</small></strong><em><i style="width:31%" /></em></div>
                <div><span>配套练习</span><strong>3<small>/16</small></strong><em><i style="width:19%" /></em></div>
                <div class="is-release"><span>已发布讲次</span><strong>4<small>/16</small></strong><em><i style="width:25%" /></em></div>
              </section>

              <section class="lesson-board">
                <header class="lesson-board__toolbar">
                  <div>
                    <h3>分讲生产</h3>
                    <span>每一行是一讲；课件数量和同一课件的版本分别显示。</span>
                  </div>
                  <div class="board-tools">
                    <label class="lesson-search"><Search :size="14" /><input v-model="lessonQuery" placeholder="搜索讲次或知识点" /></label>
                    <div class="filter-switch">
                      <button v-for="filter in productionFilters" :key="filter.id" type="button" :class="{ active: productionFilter === filter.id }" @click="productionFilter = filter.id">{{ filter.label }}</button>
                    </div>
                  </div>
                </header>

                <div class="lesson-table" role="table" aria-label="分讲课程生产状态">
                  <div class="lesson-table__head" role="row">
                    <span>讲次与主题</span><span>教案</span><span>PPT</span><span>学生版本</span><span />
                  </div>
                  <div
                    v-for="lesson in filteredLessons"
                    :key="lesson.id"
                    class="lesson-row"
                    :class="{ selected: selectedLesson?.id === lesson.id }"
                    role="row"
                  >
                    <div class="lesson-identity">
                      <span class="lesson-index">{{ String(lesson.order).padStart(2, '0') }}</span>
                      <div><strong>{{ lesson.title }}</strong><small>{{ lesson.knowledge.join(' · ') }}</small></div>
                    </div>
                    <button type="button" class="artifact-cell" :class="`is-${lesson.lessonPlan.state}`" @click="selectProductionArtifact(lesson, 'lesson')">
                      <span v-if="lesson.lessonPlan.version" class="artifact-icon"><FileText :size="15" /></span>
                      <span v-else class="artifact-empty"><Plus :size="14" /></span>
                      <span><strong>{{ lesson.lessonPlan.version ? `教案 ${lesson.lessonPlan.version}` : '生成教案' }}</strong><small>{{ lesson.lessonPlan.label }}</small></span>
                      <AlertTriangle v-if="lesson.lessonPlan.state === 'stale'" :size="14" />
                    </button>
                    <button type="button" class="artifact-cell" :class="`is-${lesson.pptState}`" @click="selectProductionArtifact(lesson, 'ppt')">
                      <span v-if="lesson.decks.length" class="artifact-icon is-ppt"><Presentation :size="15" /></span>
                      <span v-else class="artifact-empty"><Plus :size="14" /></span>
                      <span>
                        <strong>{{ lesson.decks.length ? `${lesson.decks.length}份课件 · ${lesson.decks[0]?.version || ''}` : '生成 PPT' }}</strong>
                        <small>{{ lesson.pptLabel }}</small>
                      </span>
                      <AlertTriangle v-if="lesson.pptState === 'stale'" :size="14" />
                      <span v-else-if="lesson.pptState === 'building'" class="building-dot" />
                    </button>
                    <div class="release-cell">
                      <span :class="`release-status is-${lesson.release.state}`"><CircleCheck v-if="lesson.release.state === 'published'" :size="13" /><Clock3 v-else-if="lesson.release.state === 'pending'" :size="13" />{{ lesson.release.label }}</span>
                      <small>{{ lesson.release.detail }}</small>
                    </div>
                    <button type="button" class="row-menu" title="更多操作"><MoreHorizontal :size="16" /></button>
                  </div>
                  <div v-if="!filteredLessons.length" class="lesson-empty"><Search :size="20" /><strong>没有找到对应讲次</strong><span>试试课程主题或知识点名称。</span></div>
                </div>
              </section>
            </div>

            <Transition name="inspector">
              <aside v-if="selectedLesson" class="artifact-inspector" aria-label="产物详情">
                <header>
                  <div><small>第 {{ selectedLesson.order }} 讲</small><h3>{{ selectedLesson.title }}</h3></div>
                  <button type="button" class="inspector-close" title="关闭" @click="selectedLessonId = ''"><X :size="17" /></button>
                </header>

                <div class="inspector-kind-switch">
                  <button type="button" :class="{ active: selectedArtifactType === 'lesson' }" @click="selectedArtifactType = 'lesson'">分讲教案</button>
                  <button type="button" :class="{ active: selectedArtifactType === 'ppt' }" @click="selectedArtifactType = 'ppt'">PPT <span>{{ selectedLesson.decks.length }}</span></button>
                </div>

                <template v-if="selectedArtifactType === 'ppt'">
                  <div v-if="selectedLesson.decks.length" class="deck-list">
                    <button v-for="deck in selectedLesson.decks" :key="deck.id" type="button" :class="{ active: selectedDeck?.id === deck.id }" @click="selectedDeckId = deck.id">
                      <span class="deck-thumb"><Presentation :size="17" /></span>
                      <span><strong>{{ deck.name }}</strong><small>{{ deck.version }} · {{ deck.statusLabel }}</small></span>
                      <CircleCheck v-if="deck.status === 'published'" :size="14" />
                    </button>
                    <button type="button" class="add-deck" @click="notify('请选择主课件、补充案例或练习讲解模板（模拟）')"><Plus :size="15" />新增一份课件</button>
                  </div>
                  <div v-else class="inspector-empty">
                    <span><Presentation :size="22" /></span><h4>这一讲还没有课件</h4><p>先确认教案，再使用现有 PPT 生成能力创建第一版。</p>
                    <button type="button" class="primary-action" @click="simulateGeneration"><Sparkles :size="15" />从教案生成 PPT</button>
                  </div>

                  <template v-if="selectedDeck">
                    <div v-if="selectedDeck.stale" class="upstream-alert"><AlertTriangle :size="16" /><span><strong>上游教案已有新版本</strong>当前课件基于教案 {{ selectedDeck.sourceVersion }}，不会被自动覆盖。</span></div>
                    <section class="current-version">
                      <div class="version-heading"><div><small>当前工作版本</small><h4>{{ selectedDeck.name }} <span>{{ selectedDeck.version }}</span></h4></div><span :class="`state-chip is-${selectedDeck.status}`">{{ selectedDeck.statusLabel }}</span></div>
                      <dl><div><dt>生成依据</dt><dd>教案 {{ selectedDeck.sourceVersion }}</dd></div><div><dt>最近更新</dt><dd>{{ selectedDeck.updatedAt }}</dd></div><div><dt>页面</dt><dd>{{ selectedDeck.pages }} 页</dd></div></dl>
                      <div class="version-actions"><button type="button" class="primary-action" @click="notify('将进入现有 PPT 工作台，生成接口保持不变（模拟）')"><Eye :size="15" />打开课件</button><button type="button" class="quiet-action" @click="notify('开始导出当前 PPTX（模拟）')"><Download :size="15" />下载</button><button type="button" class="icon-action" title="更多"><MoreHorizontal :size="16" /></button></div>
                      <button v-if="selectedDeck.stale" type="button" class="regenerate-action" :disabled="generationPending" @click="simulateGeneration"><RefreshCw :size="15" :class="{ spinning: generationPending }" />{{ generationPending ? '正在创建新版本…' : `基于教案 ${selectedLesson.lessonPlan.version} 生成新版本` }}</button>
                    </section>
                    <section class="version-history">
                      <button type="button" class="history-toggle" @click="historyOpen = !historyOpen"><span><History :size="15" />历史版本（{{ selectedDeck.history.length }}）</span><ChevronRight :size="15" :class="{ rotated: historyOpen }" /></button>
                      <div v-if="historyOpen" class="history-list">
                        <div v-for="version in selectedDeck.history" :key="version.version"><span class="history-node" /><div><strong>{{ version.version }}</strong><small>{{ version.time }}</small></div><em>{{ version.label }}</em><button type="button" @click="notify(`正在预览 ${version.version}（模拟）`)">预览</button></div>
                      </div>
                      <p>恢复历史版本时会创建一个新版本，不覆盖当前内容。</p>
                    </section>
                  </template>
                </template>

                <template v-else>
                  <div v-if="selectedLesson.lessonPlan.version" class="lesson-plan-inspector">
                    <div class="document-mark"><FileText :size="21" /></div>
                    <small>当前工作版本</small><h4>第 {{ selectedLesson.order }} 讲教案 <span>{{ selectedLesson.lessonPlan.version }}</span></h4>
                    <p>目标、课堂活动、案例、理解检查和课后任务都维护在同一份受管教案中。</p>
                    <div class="knowledge-tags"><span v-for="knowledge in selectedLesson.knowledge" :key="knowledge">{{ knowledge }}</span></div>
                    <div v-if="selectedLesson.lessonPlan.state === 'stale'" class="upstream-alert"><AlertTriangle :size="16" /><span><strong>大纲内容有更新</strong>请检查受影响段落，再确认本讲教案。</span></div>
                    <button type="button" class="primary-action wide-inspector-action" @click="notify('将打开现有教案编辑器（模拟）')"><FileText :size="15" />打开教案编辑器</button>
                    <button type="button" class="history-toggle lesson-history"><span><History :size="15" />历史版本（{{ selectedLesson.lessonPlan.historyCount }}）</span><ChevronRight :size="15" /></button>
                  </div>
                  <div v-else class="inspector-empty"><span><FileText :size="22" /></span><h4>这一讲还没有教案</h4><p>可从大纲中的教学目标和知识结构生成初稿。</p><button type="button" class="primary-action" @click="simulateGeneration"><Sparkles :size="15" />生成教案初稿</button></div>
                </template>
              </aside>
            </Transition>
          </div>

          <div v-else class="file-system">
            <div class="file-toolbar">
              <nav><Home :size="13" /><span>课程资料</span><ChevronRight :size="13" /><strong>高等数学</strong></nav>
              <div><button type="button"><FolderPlus :size="14" />新建文件夹</button><button type="button"><Upload :size="14" />上传</button></div>
            </div>
            <div class="file-columns"><span>名称</span><span>状态</span></div>
            <div class="file-tree" role="tree" aria-label="高等数学课程文件">
              <template v-for="folder in fileFolders" :key="folder.id">
                <button type="button" class="file-row file-row--folder" role="treeitem" :aria-expanded="openFolders.includes(folder.id)" @click="toggleFolder(folder.id)">
                  <ChevronRight :size="14" :class="{ rotated: openFolders.includes(folder.id) }" />
                  <FolderOpen v-if="openFolders.includes(folder.id)" :size="17" /><Folder v-else :size="17" />
                  <strong>{{ folder.name }}</strong><span>{{ folder.children.length }} 项</span>
                </button>
                <div v-if="openFolders.includes(folder.id)" class="file-children" role="group">
                  <button v-for="file in folder.children" :key="file.name" type="button" class="file-row file-row--file" :class="{ active: file.artifact === activeArtifact }" role="treeitem" @click="file.artifact && openArtifact(file.artifact)">
                    <span class="tree-spacer" /><Presentation v-if="file.kind === 'ppt'" :size="16" /><FileText v-else :size="16" />
                    <span><strong>{{ file.name }}</strong><em>{{ file.detail }}</em></span>
                    <span v-if="file.managed" class="managed-tag">受管文档</span><span v-else>{{ file.status }}</span>
                  </button>
                </div>
              </template>
              <button v-for="file in rootFiles" :key="file.name" type="button" class="file-row file-row--file file-row--root" role="treeitem">
                <span class="tree-spacer" /><FileSpreadsheet v-if="file.kind === 'sheet'" :size="16" /><CalendarDays v-else :size="16" />
                <span><strong>{{ file.name }}</strong><em>{{ file.detail }}</em></span><span>{{ file.status }}</span>
              </button>
            </div>
            <footer class="file-system-note"><Link2 :size="14" /><span>带“受管文档”的内容由课程生产生成；点击后仍打开右侧唯一原稿。其他文件保持真实文件形态。</span></footer>
          </div>
        </section>

        <section v-if="teacherSection === 'overview'" class="teacher-overview">
          <div class="overview-copy"><p>下午好，张老师</p><h2>下一步，完善第 9 讲教案</h2><span>大纲已经确认，课程内容会沿着同一条生产链继续生长。</span><button type="button" class="primary-action" @click="teacherSection = 'production'; activeArtifact = 'lesson'">继续备课<ArrowRight :size="16" /></button></div>
          <div class="overview-progress"><span>本学期准备度</span><strong>62%</strong><div><i /></div><small>8 / 16 讲已具备教案</small></div>
        </section>

        <article v-if="teacherSection === 'files'" class="artifact-editor">
          <header class="editor-toolbar">
            <div><small>在线内容 · {{ activeArtifactLabel }}</small><strong>{{ activeArtifactTitle }}</strong></div>
            <div class="editor-actions"><button type="button" class="icon-action" title="历史版本"><History :size="16" /></button><button type="button" class="quiet-action"><WandSparkles :size="15" />AI 优化</button><button type="button" class="primary-action" @click="saved = true"><Save :size="15" />{{ saved ? '已保存' : '保存' }}</button></div>
          </header>
          <div class="single-source-note"><Link2 :size="15" /><span><strong>这是唯一原稿。</strong> 从“课程生产”或“课程文件”进入，打开的都是这里。</span></div>
          <div class="document-canvas">
            <p class="doc-kicker">2026 秋季 · 高等数学</p>
            <h3>{{ activeArtifactTitle }}</h3>
            <p>本课程面向一年级本科生，帮助学生建立微积分的核心概念、方法与应用能力。</p>
            <h4>一、教学目标</h4>
            <ol><li>理解函数、极限和连续性的基本思想；</li><li>掌握微分与积分的核心方法；</li><li>能够将数学工具用于真实问题建模。</li></ol>
            <button type="button" class="inline-ai"><WandSparkles :size="14" />让 AI 继续完善这一段</button>
          </div>
          <footer class="editor-status"><span><CircleCheck :size="14" />自动保存于 14:32</span><span>内容编号 DOC-OUTLINE-01</span></footer>
        </article>
      </template>

      <template v-else>
        <section class="student-reader">
          <header class="reader-heading">
            <div><p>第 6 讲</p><h2>导数的应用</h2></div>
            <span class="published-badge"><CircleCheck :size="14" />教师发布版 v3</span>
          </header>
          <div class="lesson-progress"><span><PlayCircle :size="15" />继续上次位置</span><div><i /></div><small>42%</small></div>
          <article class="lesson-paper">
            <p class="doc-kicker">知识点 6.2</p><h3>函数的单调性与极值</h3>
            <p>当函数在某个区间内导数恒为正时，函数在该区间单调递增；导数恒为负时，函数单调递减。</p>
            <div class="formula">f′(x) &gt; 0 ⇒ f(x) 单调递增</div>
            <button type="button" class="annotation-trigger" @click="noteAdded = true"><NotebookPen :size="15" />{{ noteAdded ? '已加入我的笔记' : '记下这一段' }}</button>
          </article>
          <footer><button type="button" class="quiet-action">上一节</button><button type="button" class="primary-action">完成并继续<ArrowRight :size="15" /></button></footer>
        </section>

        <aside class="student-companion">
          <div class="companion-tabs"><button type="button" :class="{ active: studentPanel === 'notes' }" @click="studentPanel = 'notes'">我的笔记</button><button type="button" :class="{ active: studentPanel === 'ai' }" @click="studentPanel = 'ai'">AI 教师</button></div>
          <template v-if="studentPanel === 'notes'">
            <div class="private-label"><LockKeyhole :size="13" />仅自己可见</div>
            <h3>第 6 讲笔记</h3>
            <div class="note-card"><small>关联“函数的单调性”</small><p>判断单调区间时，需要先找定义域，再求导数符号。</p></div>
            <div v-if="noteAdded" class="note-card new-note"><small>刚刚记录</small><p>f′(x) 的正负决定函数在区间内的增减趋势。</p></div>
            <button type="button" class="wide-action"><Sparkles :size="15" />整理为复习提纲</button>
          </template>
          <template v-else>
            <div class="ai-orb"><Bot :size="22" /></div><h3>围绕当前内容提问</h3><p>我会结合教师发布内容和你的个人笔记回答，不会修改课程原文。</p>
            <button type="button" class="prompt-chip">为什么导数为 0 不一定是极值点？</button><button type="button" class="prompt-chip">给我一道判断单调性的练习</button>
          </template>
        </aside>
      </template>
    </section>

    <Transition name="toast">
      <div v-if="toastMessage" class="concept-toast" role="status"><CircleCheck :size="16" /><span>{{ toastMessage }}</span></div>
    </Transition>
  </main>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  AlertTriangle, ArrowRight, BarChart3, BookOpen, BookOpenCheck, Bot, CalendarDays, ChevronDown,
  ChevronRight, CircleCheck, Clock3, Download, Eye, FileBarChart, FileOutput, FileSpreadsheet,
  FileText, Folder, FolderOpen, FolderPlus, FolderTree, GraduationCap, History, Home,
  LayoutDashboard, Link2, ListChecks, LockKeyhole, MoreHorizontal, NotebookPen, PanelsTopLeft,
  PlayCircle, Plus, Presentation, RefreshCw, Save, Search, Send, Sparkles, Upload, UploadCloud,
  UserRound, Video, WandSparkles, X,
} from 'lucide-vue-next'

type Role = 'teacher' | 'student'
type TeacherSection = 'overview' | 'production' | 'files'

const activeProduct = ref<'course' | 'video'>('course')
const role = ref<Role>('teacher')
const teacherSection = ref<TeacherSection>('production')
const activeArtifact = ref('outline')
const saved = ref(false)
const noteAdded = ref(false)
const studentPanel = ref<'notes' | 'ai'>('notes')
const openFolders = ref(['outline', 'lesson-plans', 'slides'])
const lessonQuery = ref('')
const productionFilter = ref<'all' | 'attention' | 'unpublished'>('all')
const selectedLessonId = ref('lesson-4')
const selectedArtifactType = ref<'lesson' | 'ppt'>('ppt')
const selectedDeckId = ref('deck-4-main')
const historyOpen = ref(false)
const coursePickerOpen = ref(false)
const toastMessage = ref('')
const generationPending = ref(false)
let toastTimer: ReturnType<typeof setTimeout> | undefined

const stages = [
  { id: 'requirements', name: '课程要求', detail: '培养目标、学时与考核约束', state: 'done', label: '已确认' },
  { id: 'outline', name: '教学大纲', detail: '16 讲结构与知识关系', state: 'done', label: '已完成' },
  { id: 'lesson', name: '分讲教案', detail: '继续完善第 9 讲', state: 'active', label: '8 / 16' },
  { id: 'slides', name: '课件与练习', detail: '从已确认教案生成', state: 'todo', label: '5 / 16' },
  { id: 'publish', name: '发布准备', detail: '检查缺项并生成学生版本', state: 'todo', label: '未开始' },
]

const productionFilters = [
  { id: 'all' as const, label: '全部讲次' },
  { id: 'attention' as const, label: '需要处理' },
  { id: 'unpublished' as const, label: '未发布' },
]

type ArtifactState = 'ready' | 'draft' | 'stale' | 'building' | 'empty'
type ReleaseState = 'published' | 'pending' | 'draft' | 'empty'

interface DeckVersion {
  version: string
  time: string
  label: string
}

interface LessonDeck {
  id: string
  name: string
  version: string
  status: 'published' | 'draft' | 'building'
  statusLabel: string
  sourceVersion: string
  updatedAt: string
  pages: number
  stale?: boolean
  history: DeckVersion[]
}

interface ProductionLesson {
  id: string
  order: number
  title: string
  knowledge: string[]
  lessonPlan: { version: string; label: string; state: ArtifactState; historyCount: number }
  decks: LessonDeck[]
  pptState: ArtifactState
  pptLabel: string
  release: { state: ReleaseState; label: string; detail: string }
}

const lessons: ProductionLesson[] = [
  {
    id: 'lesson-1', order: 1, title: '函数、极限与连续', knowledge: ['函数关系', '极限思想', '连续性'],
    lessonPlan: { version: 'v3', label: '已确认', state: 'ready', historyCount: 2 },
    decks: [{ id: 'deck-1-main', name: '主课件', version: 'v4', status: 'published', statusLabel: '已发布', sourceVersion: 'v3', updatedAt: '8 月 4 日 16:20', pages: 38, history: [{ version: 'v3', time: '8 月 2 日', label: '已发布' }, { version: 'v2', time: '7 月 28 日', label: '课堂版' }, { version: 'v1', time: '7 月 25 日', label: '初始生成' }] }],
    pptState: 'ready', pptLabel: '主课件已发布', release: { state: 'published', label: '已发布', detail: '学生版本 v3' },
  },
  {
    id: 'lesson-2', order: 2, title: '数列极限与运算法则', knowledge: ['数列极限', '夹逼准则'],
    lessonPlan: { version: 'v2', label: '编辑中', state: 'draft', historyCount: 1 },
    decks: [{ id: 'deck-2-main', name: '主课件', version: 'v3', status: 'draft', statusLabel: '草稿', sourceVersion: 'v2', updatedAt: '今天 09:18', pages: 34, history: [{ version: 'v2', time: '8 月 1 日', label: '已发布' }, { version: 'v1', time: '7 月 29 日', label: '初始生成' }] }],
    pptState: 'draft', pptLabel: '主课件草稿', release: { state: 'pending', label: '待发布', detail: '有新草稿' },
  },
  {
    id: 'lesson-3', order: 3, title: '函数极限与两个重要极限', knowledge: ['函数极限', '等价无穷小'],
    lessonPlan: { version: 'v2', label: '已确认', state: 'ready', historyCount: 1 },
    decks: [{ id: 'deck-3-main', name: '主课件', version: 'v2', status: 'published', statusLabel: '已发布', sourceVersion: 'v2', updatedAt: '8 月 3 日 11:06', pages: 41, history: [{ version: 'v1', time: '7 月 31 日', label: '初始生成' }] }],
    pptState: 'ready', pptLabel: '主课件已发布', release: { state: 'published', label: '已发布', detail: '学生版本 v2' },
  },
  {
    id: 'lesson-4', order: 4, title: '连续函数与间断点', knowledge: ['连续性', '间断点', '闭区间性质'],
    lessonPlan: { version: 'v3', label: '已确认', state: 'ready', historyCount: 2 },
    decks: [
      { id: 'deck-4-main', name: '主课件', version: 'v4', status: 'published', statusLabel: '已发布', sourceVersion: 'v2', updatedAt: '昨天 17:42', pages: 46, stale: true, history: [{ version: 'v3', time: '8 月 3 日', label: '已发布' }, { version: 'v2', time: '7 月 30 日', label: '课堂精简版' }, { version: 'v1', time: '7 月 26 日', label: '初始生成' }] },
      { id: 'deck-4-case', name: '补充案例', version: 'v2', status: 'published', statusLabel: '已发布', sourceVersion: 'v3', updatedAt: '今天 10:12', pages: 12, history: [{ version: 'v1', time: '8 月 2 日', label: '初始生成' }] },
    ],
    pptState: 'stale', pptLabel: '教案已更新', release: { state: 'published', label: '已发布', detail: '学生仍看 v3' },
  },
  {
    id: 'lesson-5', order: 5, title: '导数概念与求导法则', knowledge: ['变化率', '导数定义', '求导法则'],
    lessonPlan: { version: 'v2', label: '大纲已更新', state: 'stale', historyCount: 1 },
    decks: [{ id: 'deck-5-main', name: '主课件', version: 'v2', status: 'published', statusLabel: '已发布', sourceVersion: 'v1', updatedAt: '8 月 1 日 14:26', pages: 39, stale: true, history: [{ version: 'v1', time: '7 月 29 日', label: '初始生成' }] }],
    pptState: 'stale', pptLabel: '上游内容已更新', release: { state: 'published', label: '已发布', detail: '学生版本 v2' },
  },
  {
    id: 'lesson-6', order: 6, title: '微分与高阶导数', knowledge: ['微分', '高阶导数'],
    lessonPlan: { version: 'v1', label: '编辑中', state: 'draft', historyCount: 0 },
    decks: [], pptState: 'empty', pptLabel: '等待教案确认', release: { state: 'draft', label: '草稿', detail: '尚未发布' },
  },
  {
    id: 'lesson-7', order: 7, title: '微分中值定理', knowledge: ['罗尔定理', '拉格朗日定理'],
    lessonPlan: { version: 'v1', label: '已确认', state: 'ready', historyCount: 0 },
    decks: [{ id: 'deck-7-main', name: '主课件', version: 'v1', status: 'building', statusLabel: '生成中 64%', sourceVersion: 'v1', updatedAt: '刚刚', pages: 0, history: [] }],
    pptState: 'building', pptLabel: '正在生成 64%', release: { state: 'empty', label: '未开始', detail: '等待课件' },
  },
  {
    id: 'lesson-8', order: 8, title: '函数单调性与极值', knowledge: ['单调性', '极值', '最值问题'],
    lessonPlan: { version: '', label: '尚未生成', state: 'empty', historyCount: 0 },
    decks: [], pptState: 'empty', pptLabel: '等待教案', release: { state: 'empty', label: '未开始', detail: '尚无材料' },
  },
]

const filteredLessons = computed(() => {
  const query = lessonQuery.value.trim().toLowerCase()
  return lessons.filter((lesson) => {
    const matchesQuery = !query || `${lesson.order}${lesson.title}${lesson.knowledge.join('')}`.toLowerCase().includes(query)
    const matchesFilter = productionFilter.value === 'all'
      || (productionFilter.value === 'attention' && (lesson.lessonPlan.state === 'stale' || lesson.pptState === 'stale'))
      || (productionFilter.value === 'unpublished' && lesson.release.state !== 'published')
    return matchesQuery && matchesFilter
  })
})

const selectedLesson = computed(() => lessons.find(item => item.id === selectedLessonId.value) || null)
const selectedDeck = computed(() => {
  if (!selectedLesson.value) return null
  return selectedLesson.value.decks.find(item => item.id === selectedDeckId.value) || selectedLesson.value.decks[0] || null
})

const fileFolders = [
  { id: 'outline', name: '0、教学大纲', children: [
    { name: '课程教学大纲', detail: '更新于 14:32', managed: true, artifact: 'outline', kind: 'doc', status: '' },
  ] },
  { id: 'lesson-plans', name: '1、教案', children: [
    { name: '第 1 讲教案', detail: '已确认', managed: true, artifact: 'lesson', kind: 'doc', status: '' },
    { name: '第 9 讲教案', detail: '正在编辑', managed: true, artifact: 'lesson', kind: 'doc', status: '' },
  ] },
  { id: 'slides', name: '2、PPT', children: [
    { name: '第 01 讲 · 主课件', detail: '受管课件 · v4 · 已发布', managed: true, artifact: 'slides', kind: 'ppt', status: '' },
    { name: '第 04 讲 · 主课件', detail: '受管课件 · v4 · 上游已更新', managed: true, artifact: 'slides', kind: 'ppt', status: '' },
    { name: '第 04 讲 · 补充案例', detail: '受管课件 · v2 · 已发布', managed: true, artifact: 'slides', kind: 'ppt', status: '' },
    { name: '第01讲主课件-已导出.pptx', detail: '导出快照 · 8.4 MB', managed: false, artifact: '', kind: 'ppt', status: '普通文件' },
  ] },
  { id: 'assignments', name: '3、作业与实验', children: [
    { name: '第一次作业.docx', detail: '上传文件 · 36 KB', managed: false, artifact: '', kind: 'doc', status: '原文件' },
  ] },
]
const rootFiles = [
  { name: '4、教学日历.pdf', detail: '上传文件 · 1.2 MB', kind: 'calendar', status: '原文件' },
  { name: '5、成绩明细.xlsx', detail: '上传文件 · 48 KB', kind: 'sheet', status: '原文件' },
]

const artifactNames: Record<string, string> = {
  requirements: '课程要求', outline: '教学大纲', lesson: '第 9 讲教案', slides: '第 9 讲课件', publish: '发布检查',
}
const activeArtifactTitle = computed(() => artifactNames[activeArtifact.value] || '教学大纲')
const activeArtifactLabel = computed(() => activeArtifact.value === 'outline' ? '大纲' : '课程材料')

function setRole(next: Role) {
  role.value = next
  saved.value = false
  coursePickerOpen.value = false
}

function openArtifact(id: string) {
  activeArtifact.value = id
  saved.value = false
  if (id === 'slides') {
    teacherSection.value = 'production'
    selectedLessonId.value = 'lesson-4'
    selectedArtifactType.value = 'ppt'
    selectedDeckId.value = 'deck-4-main'
  }
}

function selectProductionArtifact(lesson: ProductionLesson, type: 'lesson' | 'ppt') {
  selectedLessonId.value = lesson.id
  selectedArtifactType.value = type
  selectedDeckId.value = lesson.decks[0]?.id || ''
  historyOpen.value = false
}

function toggleFolder(id: string) {
  openFolders.value = openFolders.value.includes(id)
    ? openFolders.value.filter(item => item !== id)
    : [...openFolders.value, id]
}

function notify(message: string) {
  toastMessage.value = message
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toastMessage.value = ''
  }, 2400)
}

function simulateGeneration() {
  if (generationPending.value) return
  generationPending.value = true
  notify('任务已提交，沿用现有生成链路（模拟）')
  window.setTimeout(() => {
    generationPending.value = false
    notify('新版本草稿已生成，旧发布版保持不变（模拟）')
  }, 1600)
}
</script>

<style scoped>
.workspace-concept {
  --concept-ink: #172033;
  --concept-muted: #68748a;
  --concept-line: #e5e9f2;
  --concept-soft: #f5f7fb;
  --concept-brand: var(--color-primary-600, #4f46e5);
  --concept-brand-soft: var(--color-primary-50, #eef2ff);
  height: 100%; min-height: 0; display: grid; grid-template-rows: 74px minmax(0, 1fr); overflow: hidden;
  color: var(--concept-ink); background: #f4f5f8; border-radius: 16px;
  font-family: var(--font-sans, "Microsoft YaHei", sans-serif);
}
button { font: inherit; }
.concept-header { display: grid; grid-template-columns: minmax(250px,1fr) auto minmax(250px,1fr); align-items:center; gap:20px; padding:0 24px; border-bottom:1px solid var(--concept-line); background:#fbfcfe; }
.concept-title { display:flex; align-items:center; gap:12px; }
.concept-mark { width:38px; height:38px; display:grid; place-items:center; color:#fff; background:var(--concept-brand); border-radius:11px; box-shadow:0 8px 18px rgba(79,70,229,.2); }
.concept-title p,.stage-heading p,.reader-heading p,.overview-copy p { margin:0 0 3px; color:var(--concept-brand); font-size:11px; font-weight:750; letter-spacing:.08em; }
.concept-title h1 { margin:0; font-size:17px; line-height:1.2; letter-spacing:-.02em; }
.product-switch,.role-switch { display:flex; align-items:center; gap:4px; padding:4px; border:1px solid var(--concept-line); border-radius:11px; background:#f2f4f8; }
.product-switch button,.role-switch button { height:34px; display:flex; align-items:center; gap:7px; padding:0 13px; border:0; border-radius:8px; color:#657086; background:transparent; cursor:pointer; }
.product-switch button.active,.role-switch button.active { color:var(--concept-brand); background:#fff; box-shadow:0 1px 4px rgba(28,36,55,.08); font-weight:650; }
.role-switch { justify-self:end; }

.course-shell { min-height:0; display:grid; grid-template-columns:220px minmax(310px,.82fr) minmax(430px,1.18fr); gap:1px; overflow:hidden; background:var(--concept-line); }
.course-rail,.teacher-stage,.artifact-editor,.teacher-overview,.student-reader,.student-companion { min-width:0; min-height:0; background:#fbfcfe; }
.course-rail { display:flex; flex-direction:column; padding:18px 12px 14px; }
.course-picker { position:relative; padding:0 6px 18px; border-bottom:1px solid var(--concept-line); }
.course-picker small { display:block; margin:0 0 8px; color:#8a94a7; font-size:11px; }
.course-picker > button { width:100%; display:grid; grid-template-columns:36px 1fr auto; align-items:center; gap:10px; padding:0; border:0; text-align:left; background:transparent; cursor:pointer; }
.course-avatar { width:36px; height:36px; display:grid; place-items:center; border-radius:10px; color:#3730a3; background:#e0e7ff; font-weight:800; }
.course-picker strong,.course-picker em { display:block; font-style:normal; }
.course-picker strong { font-size:14px; }.course-picker em { margin-top:3px; color:#8791a4; font-size:11px; }
.course-picker > button svg { transition:transform .2s cubic-bezier(.16,1,.3,1); }.course-picker > button svg.rotated { transform:rotate(180deg); }
.course-picker-menu { position:absolute; z-index:12; top:63px; left:0; width:252px; padding:8px; border:1px solid #dfe3ec; border-radius:11px; background:#fcfcfe; box-shadow:0 18px 45px rgba(30,39,59,.16); }
.course-picker-menu__heading { display:flex; justify-content:space-between; align-items:center; padding:5px 6px 8px; color:#8993a4; font-size:9px; }.course-picker-menu__heading button { border:0; color:#555fba; background:transparent; font-size:9px; cursor:pointer; }
.course-option { width:100%; display:grid; grid-template-columns:32px minmax(0,1fr) 16px; align-items:center; gap:9px; padding:7px; border:1px solid transparent; border-radius:8px; color:#7d8798; background:transparent; text-align:left; cursor:pointer; }.course-option:hover,.course-option.active { border-color:#e0e3f1; background:#f5f6ff; }.course-option .course-avatar { width:32px; height:32px; border-radius:8px; font-size:11px; }.course-avatar.is-green { color:#176e54; background:#e2f4ec; }.course-option strong,.course-option small { display:block; }.course-option strong { color:#3e495e; font-size:10px; }.course-option small { margin-top:3px; color:#939baa; font-size:8px; }.new-course-option { width:100%; height:32px; display:flex; align-items:center; justify-content:center; gap:6px; margin-top:5px; border:1px dashed #cfd4e0; border-radius:8px; color:#5660b4; background:#fafaff; font-size:9px; cursor:pointer; }
.picker-enter-active,.picker-leave-active { transition:opacity .18s ease, transform .22s cubic-bezier(.16,1,.3,1); }.picker-enter-from,.picker-leave-to { opacity:0; transform:translateY(-5px) scale(.98); }
.course-nav { display:grid; gap:5px; padding:18px 0; }
.course-nav button { height:40px; display:flex; align-items:center; gap:10px; padding:0 12px; border:0; border-radius:9px; color:#5d687b; background:transparent; cursor:pointer; text-align:left; }
.course-nav button:hover { background:#f2f4f8; }.course-nav button.active { color:#3730a3; background:#eef2ff; font-weight:700; }
.nav-count { margin-left:auto; min-width:20px; padding:2px 6px; border-radius:999px; color:#4f46e5; background:#fff; font-size:10px; text-align:center; }
.rail-note { margin-top:auto; display:flex; gap:8px; padding:12px; border:1px solid #e6e9f2; border-radius:10px; color:#788397; background:#f7f8fb; font-size:11px; line-height:1.55; }

.teacher-stage { padding:24px 20px; overflow:auto; }
.teacher-stage--production { grid-column:2 / -1; padding:22px 24px 0; overflow:hidden; }
.stage-heading { display:flex; justify-content:space-between; gap:18px; margin-bottom:22px; }
.stage-heading h2,.reader-heading h2 { margin:0; font-size:23px; letter-spacing:-.03em; }.stage-heading span { display:block; margin-top:6px; color:var(--concept-muted); font-size:12px; line-height:1.5; }
.stage-actions { display:flex; align-items:flex-start; gap:8px; }
.quiet-action,.primary-action,.icon-action,.wide-action { border:0; cursor:pointer; }
.quiet-action,.primary-action { height:36px; display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:0 13px; border-radius:9px; font-weight:650; }
.quiet-action { color:#536079; background:#eef0f5; }.primary-action { color:#fff; background:var(--concept-brand); box-shadow:0 7px 16px rgba(79,70,229,.16); }
.production-list { display:grid; gap:8px; }
.production-step { display:grid; grid-template-columns:32px minmax(0,1fr) auto 16px; align-items:center; gap:11px; width:100%; padding:13px 12px; border:1px solid transparent; border-radius:11px; color:#59657a; background:transparent; text-align:left; cursor:pointer; }
.production-step:hover { background:#f5f6fa; }.production-step.active { border-color:#cbd3ff; color:#2f3183; background:#f0f2ff; }.production-step.done .step-number { color:#15835d; background:#e4f7ef; }
.step-number { width:30px; height:30px; display:grid; place-items:center; border-radius:9px; color:#667085; background:#eef0f4; font-size:12px; font-weight:800; }
.step-copy strong,.step-copy em { display:block; font-style:normal; }.step-copy strong { color:var(--concept-ink); font-size:13px; }.step-copy em { margin-top:4px; color:#8791a4; font-size:11px; }.step-state { color:#6d7789; font-size:11px; white-space:nowrap; }

.production-workspace { position:relative; min-height:0; height:calc(100% - 82px); display:grid; grid-template-columns:minmax(0,1fr); margin:0 -24px; overflow:hidden; border-top:1px solid var(--concept-line); background:#f6f7fa; }
.production-workspace.inspector-open { grid-template-columns:minmax(660px,1fr) 330px; }
.production-main { min-width:0; overflow:auto; padding:20px 24px 34px; }
.production-track { display:flex; align-items:center; padding:4px 2px 18px; }
.track-step { min-width:0; display:flex; align-items:center; flex:1; color:#8a94a7; }
.track-step > span { width:26px; height:26px; flex:none; display:grid; place-items:center; border-radius:50%; color:#7b8496; background:#e8eaf0; font-size:10px; font-weight:800; }
.track-step > div { min-width:0; margin-left:8px; }.track-step strong,.track-step small { display:block; white-space:nowrap; }.track-step strong { color:#687287; font-size:11px; }.track-step small { margin-top:2px; color:#9aa3b2; font-size:9px; }
.track-step > i { height:1px; flex:1; margin:0 10px; background:#dfe2e9; }.track-step.done > span { color:#fff; background:#238763; }.track-step.done strong { color:#3d4b5d; }.track-step.active > span { color:#fff; background:var(--concept-brand); box-shadow:0 0 0 4px #e5e7ff; }.track-step.active strong { color:#36388c; }

.outline-source { display:grid; grid-template-columns:auto minmax(250px,1fr) auto auto; align-items:center; gap:14px; padding:15px 16px; border:1px solid #dfe3ec; border-radius:11px; background:#fcfcfd; box-shadow:0 3px 10px rgba(32,41,61,.035); }
.outline-source__mark { width:38px; height:38px; display:grid; place-items:center; border-radius:9px; color:#3f46a7; background:#edf0ff; }
.outline-source__copy > div { display:flex; align-items:center; gap:7px; }.outline-source__copy strong { font-size:13px; }.outline-source__copy p { margin:5px 0 0; color:#818b9e; font-size:10px; }
.version-chip { padding:2px 6px; border-radius:5px; color:#545ec4; background:#eef0ff; font-size:9px; font-weight:750; }
.state-chip { display:inline-flex; align-items:center; padding:3px 7px; border-radius:6px; font-size:9px; font-weight:700; }.state-chip.is-ready,.state-chip.is-published { color:#167152; background:#e9f7f0; }.state-chip.is-draft { color:#755d18; background:#f8f0d9; }.state-chip.is-building { color:#3f56a9; background:#e8efff; }
.outline-source__knowledge { min-width:190px; padding-left:16px; border-left:1px solid var(--concept-line); }.outline-source__knowledge span,.outline-source__knowledge strong,.outline-source__knowledge small { display:block; }.outline-source__knowledge span { color:#8d96a6; font-size:9px; }.outline-source__knowledge strong { margin-top:2px; font-size:12px; }.outline-source__knowledge small { margin-top:3px; color:#a0a7b4; font-size:8px; }
.text-action { display:flex; align-items:center; gap:3px; padding:7px 3px; border:0; color:#4c54b5; background:transparent; font-size:10px; font-weight:700; cursor:pointer; }

.production-summary { display:grid; grid-template-columns:repeat(4,1fr); gap:1px; margin:14px 0 18px; overflow:hidden; border:1px solid var(--concept-line); border-radius:10px; background:var(--concept-line); }
.production-summary > div { padding:12px 14px; background:#fbfcfd; }.production-summary span { display:block; color:#7d8799; font-size:9px; }.production-summary strong { display:block; margin:4px 0 8px; font-size:21px; line-height:1; letter-spacing:-.04em; }.production-summary strong small { margin-left:2px; color:#9ca4b2; font-size:10px; font-weight:550; }.production-summary em { display:block; height:3px; overflow:hidden; border-radius:99px; background:#e7e9ee; }.production-summary em i { display:block; height:100%; border-radius:inherit; background:#666ad1; }.production-summary .is-release em i { background:#2b8b68; }

.lesson-board { overflow:hidden; border:1px solid #dfe3eb; border-radius:11px; background:#fff; box-shadow:0 8px 24px rgba(33,42,62,.045); }
.lesson-board__toolbar { display:flex; justify-content:space-between; align-items:flex-end; gap:16px; padding:15px 16px 13px; border-bottom:1px solid #e8eaf0; }.lesson-board__toolbar h3 { margin:0; font-size:14px; }.lesson-board__toolbar > div > span { display:block; margin-top:4px; color:#8a94a6; font-size:9px; }
.board-tools { display:flex; align-items:center; gap:8px; }.lesson-search { width:176px; height:30px; display:flex; align-items:center; gap:6px; padding:0 9px; border:1px solid #e0e3ea; border-radius:7px; color:#929baa; background:#fafbfc; }.lesson-search input { min-width:0; width:100%; border:0; outline:0; color:#465165; background:transparent; font-size:9px; }.lesson-search input::placeholder { color:#a4abb7; }
.filter-switch { display:flex; gap:2px; padding:3px; border-radius:7px; background:#f0f2f5; }.filter-switch button { height:24px; padding:0 8px; border:0; border-radius:5px; color:#818a9a; background:transparent; font-size:8px; cursor:pointer; }.filter-switch button.active { color:#3f468f; background:#fff; box-shadow:0 1px 3px rgba(28,36,52,.08); font-weight:700; }
.lesson-table { min-width:720px; }.lesson-table__head,.lesson-row { display:grid; grid-template-columns:minmax(190px,1.2fr) minmax(140px,.85fr) minmax(170px,1fr) 110px 28px; align-items:center; column-gap:10px; }.lesson-table__head { min-height:33px; padding:0 12px; color:#9ba3b0; background:#fafbfc; font-size:8px; }.lesson-row { min-height:64px; padding:0 12px; border-top:1px solid #edf0f4; transition:background .18s ease; }.lesson-row:hover,.lesson-row.selected { background:#fafaff; }.lesson-row.selected { box-shadow:inset 2px 0 #5b5fc7; }
.lesson-identity { min-width:0; display:flex; align-items:center; gap:9px; }.lesson-index { width:27px; height:27px; flex:none; display:grid; place-items:center; border-radius:7px; color:#687287; background:#f0f2f5; font-size:9px; font-weight:800; }.lesson-identity > div { min-width:0; }.lesson-identity strong,.lesson-identity small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.lesson-identity strong { color:#354055; font-size:10px; }.lesson-identity small { margin-top:4px; color:#929baa; font-size:8px; }
.artifact-cell { min-width:0; display:grid; grid-template-columns:28px minmax(0,1fr) auto; align-items:center; gap:7px; padding:6px; border:1px solid transparent; border-radius:8px; color:#687287; background:transparent; text-align:left; cursor:pointer; }.artifact-cell:hover { border-color:#dfe3ef; background:#fff; box-shadow:0 3px 9px rgba(37,46,68,.06); }.artifact-icon,.artifact-empty { width:27px; height:27px; display:grid; place-items:center; border-radius:7px; color:#4f5aa8; background:#eef0ff; }.artifact-icon.is-ppt { color:#b75151; background:#fff0ef; }.artifact-empty { border:1px dashed #cbd0da; color:#9ba3b0; background:#fafbfc; }.artifact-cell > span:nth-child(2) { min-width:0; }.artifact-cell strong,.artifact-cell small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.artifact-cell strong { color:#475267; font-size:9px; }.artifact-cell small { margin-top:3px; color:#929baa; font-size:8px; }.artifact-cell.is-stale { color:#b27822; background:#fffaf0; }.artifact-cell.is-stale strong,.artifact-cell.is-stale small { color:#916c2c; }.artifact-cell.is-building { background:#f5f7ff; }.building-dot { width:7px; height:7px; border-radius:50%; background:#6670d8; box-shadow:0 0 0 4px #e6e9ff; animation:pulse-dot 1.4s ease-in-out infinite; }
.release-cell span,.release-cell small { display:flex; align-items:center; gap:4px; }.release-cell span { font-size:9px; font-weight:700; }.release-cell small { margin-top:4px; color:#9aa2af; font-size:8px; }.release-status.is-published { color:#1c7a5a; }.release-status.is-pending { color:#976d22; }.release-status.is-draft,.release-status.is-empty { color:#8992a1; }.row-menu { width:28px; height:28px; display:grid; place-items:center; border:0; border-radius:7px; color:#929baa; background:transparent; cursor:pointer; }.row-menu:hover { background:#eef0f4; }.lesson-empty { min-height:180px; display:flex; flex-direction:column; align-items:center; justify-content:center; color:#9aa3b2; }.lesson-empty strong { margin-top:8px; color:#59657a; font-size:11px; }.lesson-empty span { margin-top:4px; font-size:9px; }

.artifact-inspector { min-width:0; overflow:auto; border-left:1px solid #dde1e9; background:#fcfcfd; box-shadow:-12px 0 24px rgba(26,34,52,.045); }.artifact-inspector > header { position:sticky; top:0; z-index:2; display:flex; justify-content:space-between; align-items:flex-start; padding:18px 18px 14px; border-bottom:1px solid #e4e7ed; background:#fcfcfd; }.artifact-inspector > header small { color:#7f899b; font-size:9px; }.artifact-inspector > header h3 { margin:4px 0 0; font-size:15px; }.inspector-close { width:30px; height:30px; display:grid; place-items:center; border:0; border-radius:7px; color:#818b9d; background:#f0f2f5; cursor:pointer; }
.inspector-kind-switch { display:grid; grid-template-columns:1fr 1fr; margin:14px 16px 0; padding:3px; border-radius:8px; background:#eff1f5; }.inspector-kind-switch button { height:30px; border:0; border-radius:6px; color:#7e8798; background:transparent; font-size:10px; cursor:pointer; }.inspector-kind-switch button.active { color:#383e83; background:#fff; box-shadow:0 2px 5px rgba(34,42,61,.08); font-weight:750; }.inspector-kind-switch button span { display:inline-grid; place-items:center; min-width:17px; height:17px; margin-left:3px; border-radius:99px; color:#5b60b7; background:#eef0ff; font-size:8px; }
.deck-list { display:grid; gap:5px; padding:14px 16px; border-bottom:1px solid #e6e8ed; }.deck-list > button { display:grid; grid-template-columns:34px minmax(0,1fr) 16px; align-items:center; gap:8px; padding:7px; border:1px solid transparent; border-radius:8px; color:#80899a; background:transparent; text-align:left; cursor:pointer; }.deck-list > button.active { border-color:#d8dcf3; background:#f4f5ff; }.deck-thumb { width:33px; height:28px; display:grid; place-items:center; border-radius:6px; color:#ae4f50; background:#ffefef; }.deck-list strong,.deck-list small { display:block; }.deck-list strong { color:#495468; font-size:10px; }.deck-list small { margin-top:3px; color:#919aa9; font-size:8px; }.deck-list .add-deck { display:flex; justify-content:center; padding:7px; border:1px dashed #d7dbe4; color:#626bb5; background:#fafaff; font-size:9px; }
.upstream-alert { display:flex; align-items:flex-start; gap:8px; margin:14px 16px 0; padding:10px; border:1px solid #eadbbd; border-radius:8px; color:#8c672a; background:#fff9ed; font-size:9px; line-height:1.5; }.upstream-alert svg { flex:none; margin-top:1px; }.upstream-alert strong { display:block; color:#77551f; }
.current-version { margin:14px 16px; padding:15px; border:1px solid #e0e3e9; border-radius:9px; background:#fff; }.version-heading { display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }.version-heading small { color:#929baa; font-size:8px; }.version-heading h4 { margin:4px 0 0; font-size:13px; }.version-heading h4 span,.lesson-plan-inspector h4 span { color:#5963bf; }.current-version dl { margin:15px 0; display:grid; gap:8px; }.current-version dl div { display:flex; justify-content:space-between; padding-bottom:7px; border-bottom:1px solid #eef0f3; font-size:9px; }.current-version dt { color:#929baa; }.current-version dd { margin:0; color:#4d586b; font-weight:650; }.version-actions { display:grid; grid-template-columns:1fr auto 36px; gap:6px; }.version-actions .quiet-action { padding:0 10px; }.regenerate-action { width:100%; min-height:35px; display:flex; align-items:center; justify-content:center; gap:6px; margin-top:8px; border:0; border-radius:8px; color:#fff; background:#b77a22; font-size:9px; font-weight:700; cursor:pointer; }.regenerate-action:disabled { cursor:wait; opacity:.75; }.spinning { animation:spin .9s linear infinite; }
.version-history { margin:0 16px 20px; }.history-toggle { width:100%; display:flex; justify-content:space-between; align-items:center; padding:9px 2px; border:0; color:#525d71; background:transparent; cursor:pointer; }.history-toggle > span { display:flex; align-items:center; gap:6px; font-size:10px; font-weight:700; }.history-toggle .rotated { transform:rotate(90deg); }.history-list { display:grid; margin:3px 0 8px 6px; padding-left:10px; border-left:1px solid #dfe2e9; }.history-list > div { min-height:42px; display:grid; grid-template-columns:8px minmax(0,1fr) auto auto; align-items:center; gap:7px; position:relative; }.history-node { width:7px; height:7px; position:absolute; left:-14px; border:2px solid #fff; border-radius:50%; background:#9ba3b1; box-shadow:0 0 0 1px #cbd0d8; }.history-list strong,.history-list small { display:block; }.history-list strong { font-size:9px; }.history-list small { margin-top:2px; color:#999fac; font-size:8px; }.history-list em { color:#7e8797; font-size:8px; font-style:normal; }.history-list button { padding:3px 5px; border:0; color:#5660b4; background:transparent; font-size:8px; cursor:pointer; }.version-history > p { margin:5px 0 0; color:#9aa2af; font-size:8px; line-height:1.5; }
.inspector-empty { display:flex; flex-direction:column; align-items:center; padding:44px 24px; text-align:center; }.inspector-empty > span,.document-mark { width:46px; height:46px; display:grid; place-items:center; border-radius:12px; color:#656cc3; background:#eef0ff; }.inspector-empty h4 { margin:13px 0 6px; font-size:13px; }.inspector-empty p { margin:0 0 18px; color:#8a94a5; font-size:9px; line-height:1.6; }
.lesson-plan-inspector { padding:22px 18px; }.lesson-plan-inspector > small { display:block; margin-top:15px; color:#939baa; font-size:8px; }.lesson-plan-inspector h4 { margin:4px 0 10px; font-size:14px; }.lesson-plan-inspector > p { color:#778194; font-size:9px; line-height:1.65; }.knowledge-tags { display:flex; flex-wrap:wrap; gap:5px; margin:13px 0; }.knowledge-tags span { padding:4px 7px; border-radius:6px; color:#5861af; background:#f0f1ff; font-size:8px; }.lesson-plan-inspector .upstream-alert { margin:13px 0; }.wide-inspector-action { width:100%; margin-top:10px; }.lesson-history { margin-top:10px; padding:10px 2px; border-top:1px solid #e7e9ee; }
.inspector-enter-active,.inspector-leave-active { transition:opacity .22s ease, transform .28s cubic-bezier(.16,1,.3,1); }.inspector-enter-from,.inspector-leave-to { opacity:0; transform:translateX(18px); }
@keyframes pulse-dot { 0%,100% { opacity:.55; } 50% { opacity:1; } }
.file-system { display:grid; grid-template-rows:auto auto minmax(0,1fr) auto; min-height:430px; overflow:hidden; border:1px solid var(--concept-line); border-radius:12px; background:#fff; }
.file-toolbar { display:flex; justify-content:space-between; align-items:center; gap:10px; padding:11px 12px; border-bottom:1px solid var(--concept-line); background:#fafbfc; }.file-toolbar nav,.file-toolbar > div { display:flex; align-items:center; gap:6px; }.file-toolbar nav { min-width:0; color:#8a94a7; font-size:10px; }.file-toolbar nav strong { overflow:hidden; color:#4c586d; text-overflow:ellipsis; white-space:nowrap; }.file-toolbar button { display:flex; align-items:center; gap:5px; padding:6px 8px; border:1px solid #dde1eb; border-radius:7px; color:#59657a; background:#fff; font-size:10px; cursor:pointer; }
.file-columns { display:grid; grid-template-columns:minmax(0,1fr) 72px; padding:8px 12px 7px 40px; border-bottom:1px solid #edf0f5; color:#9aa3b2; font-size:9px; }
.file-tree { min-height:0; padding:6px; overflow:auto; }.file-row { width:100%; min-height:35px; display:grid; grid-template-columns:16px 18px minmax(0,1fr) 72px; align-items:center; gap:6px; padding:5px 7px; border:0; border-radius:7px; color:#6d7789; background:transparent; text-align:left; cursor:pointer; }.file-row:hover { background:#f5f6fa; }.file-row.active { color:#3f46a7; background:#eef0ff; }.file-row > strong { overflow:hidden; color:#344054; font-size:11px; text-overflow:ellipsis; white-space:nowrap; }.file-row > span:last-child { justify-self:end; font-size:9px; white-space:nowrap; }.file-row svg { flex:none; }.file-row .rotated { transform:rotate(90deg); }.file-children { padding-left:20px; }.file-row--file > span:nth-child(3) { min-width:0; }.file-row--file strong,.file-row--file em { display:block; overflow:hidden; font-style:normal; text-overflow:ellipsis; white-space:nowrap; }.file-row--file strong { color:#3d475b; font-size:10px; }.file-row--file em { margin-top:2px; color:#98a1b1; font-size:8px; }.file-row--root { margin-top:2px; }.tree-spacer { width:14px; }.managed-tag { padding:3px 5px; border-radius:6px; color:#3764a9!important; background:#e8f1ff; font-size:8px!important; white-space:nowrap; }
.file-system-note { display:flex; align-items:flex-start; gap:7px; padding:10px 12px; border-top:1px solid var(--concept-line); color:#737e91; background:#f7f8fb; font-size:9px; line-height:1.55; }.file-system-note svg { flex:none; margin-top:1px; color:#4f46e5; }

.artifact-editor { display:grid; grid-template-rows:auto auto minmax(0,1fr) auto; overflow:hidden; }
.editor-toolbar { display:flex; justify-content:space-between; align-items:center; gap:15px; padding:18px 22px; border-bottom:1px solid var(--concept-line); }.editor-toolbar small,.editor-toolbar strong { display:block; }.editor-toolbar small { margin-bottom:4px; color:#8c96a8; font-size:10px; }.editor-toolbar strong { font-size:15px; }
.editor-actions { display:flex; gap:7px; }.icon-action { width:36px; height:36px; display:grid; place-items:center; border-radius:9px; color:#657086; background:#f0f2f6; }
.single-source-note { display:flex; align-items:center; gap:8px; margin:14px 22px 0; padding:10px 12px; border:1px solid #dce2f5; border-radius:9px; color:#5f6c84; background:#f5f7ff; font-size:11px; }.single-source-note strong { color:#39428d; }
.document-canvas { margin:14px 22px 18px; padding:34px clamp(24px,5vw,56px); overflow:auto; border:1px solid #e7e9ef; border-radius:4px; background:#fff; box-shadow:0 10px 28px rgba(35,43,64,.07); }
.doc-kicker { margin:0 0 12px!important; color:#7e8798!important; font-size:10px!important; letter-spacing:.08em; text-transform:uppercase; }.document-canvas h3,.lesson-paper h3 { margin:0 0 22px; font-size:25px; letter-spacing:-.035em; }.document-canvas h4 { margin:28px 0 12px; font-size:15px; }.document-canvas p,.document-canvas li { color:#4e596d; font-size:13px; line-height:1.85; }.document-canvas ol { padding-left:20px; }
.inline-ai { display:flex; align-items:center; gap:6px; margin-top:24px; padding:8px 10px; border:1px dashed #c6ccf4; border-radius:8px; color:#4f46e5; background:#fafaff; font-size:11px; cursor:pointer; }
.editor-status { display:flex; justify-content:space-between; padding:10px 22px; border-top:1px solid var(--concept-line); color:#8b95a6; font-size:10px; }.editor-status span { display:flex; align-items:center; gap:5px; }

.teacher-overview { grid-column:2 / -1; display:grid; grid-template-columns:1.45fr .75fr; gap:30px; align-items:center; padding:clamp(34px,6vw,78px); }.overview-copy h2 { max-width:620px; margin:8px 0 14px; font-size:clamp(30px,4vw,54px); line-height:1.05; letter-spacing:-.055em; }.overview-copy > span { display:block; max-width:580px; color:#667085; line-height:1.7; }.overview-copy .primary-action { margin-top:28px; }.overview-progress { padding:28px; border:1px solid var(--concept-line); border-radius:16px; background:#f6f7fa; }.overview-progress > span,.overview-progress strong,.overview-progress small { display:block; }.overview-progress > span { color:#7a8496; font-size:12px; }.overview-progress strong { margin:16px 0; font-size:42px; letter-spacing:-.05em; }.overview-progress div { height:7px; overflow:hidden; border-radius:999px; background:#e3e6ed; }.overview-progress i { display:block; width:62%; height:100%; border-radius:inherit; background:var(--concept-brand); }.overview-progress small { margin-top:12px; color:#7e889a; }

.student-reader { grid-column:2; display:grid; grid-template-rows:auto auto minmax(0,1fr) auto; padding:24px 28px 18px; overflow:hidden; }.reader-heading { display:flex; justify-content:space-between; align-items:start; }.published-badge { display:flex; align-items:center; gap:5px; padding:6px 9px; border-radius:8px; color:#147a58; background:#e8f7f0; font-size:10px; }
.lesson-progress { display:grid; grid-template-columns:auto minmax(80px,1fr) auto; align-items:center; gap:10px; margin:18px 0; color:#768195; font-size:10px; }.lesson-progress span { display:flex; align-items:center; gap:5px; }.lesson-progress div { height:4px; border-radius:99px; background:#e6e8ed; }.lesson-progress i { display:block; width:42%; height:100%; border-radius:inherit; background:var(--concept-brand); }
.lesson-paper { overflow:auto; padding:clamp(28px,5vw,54px); border:1px solid var(--concept-line); border-radius:5px; background:#fff; box-shadow:0 12px 30px rgba(36,43,60,.06); }.lesson-paper > p:not(.doc-kicker) { color:#4e596d; font-size:14px; line-height:1.9; }.formula { margin:26px 0; padding:20px; border-radius:10px; color:#343b7d; background:#f2f3ff; font-family:Georgia,serif; font-size:19px; text-align:center; }.annotation-trigger { display:flex; align-items:center; gap:6px; padding:8px 10px; border:1px solid #d9dded; border-radius:8px; color:#59657a; background:#fff; cursor:pointer; }.student-reader > footer { display:flex; justify-content:space-between; padding-top:16px; }
.student-companion { grid-column:3; padding:24px 22px; overflow:auto; }.companion-tabs { display:flex; gap:18px; border-bottom:1px solid var(--concept-line); }.companion-tabs button { padding:0 0 11px; border:0; border-bottom:2px solid transparent; color:#8a94a7; background:transparent; cursor:pointer; }.companion-tabs button.active { border-color:var(--concept-brand); color:#343b7d; font-weight:700; }.private-label { display:flex; align-items:center; gap:5px; margin-top:20px; color:#8c96a7; font-size:10px; }.student-companion h3 { margin:10px 0 16px; font-size:19px; }.note-card { margin-bottom:10px; padding:14px; border:1px solid var(--concept-line); border-radius:10px; background:#fff; }.note-card small { color:#8c96a7; }.note-card p { margin:7px 0 0; color:#4e596d; font-size:12px; line-height:1.65; }.new-note { border-color:#cad2ff; background:#f7f8ff; animation:note-in .38s cubic-bezier(.16,1,.3,1); }.wide-action { width:100%; height:38px; display:flex; align-items:center; justify-content:center; gap:7px; margin-top:16px; border-radius:9px; color:#3f46a7; background:#eef0ff; }.ai-orb { width:46px; height:46px; display:grid; place-items:center; margin-top:28px; border-radius:14px; color:#fff; background:#4f46e5; }.student-companion > p { color:#6d7789; font-size:12px; line-height:1.7; }.prompt-chip { display:block; width:100%; margin-top:9px; padding:11px 12px; border:1px solid var(--concept-line); border-radius:9px; color:#4d586e; background:#fff; text-align:left; cursor:pointer; }

.video-placeholder { display:grid; grid-template-columns:minmax(280px,.8fr) minmax(380px,1.2fr); place-items:center; gap:clamp(40px,8vw,120px); padding:clamp(40px,8vw,110px); background:#f9fafc; }.video-placeholder__visual { aspect-ratio:4/3; width:min(100%,430px); display:flex; flex-direction:column; justify-content:space-between; padding:28px; border-radius:20px; color:#dfe3ff; background:#242a3b; box-shadow:0 28px 60px rgba(24,29,46,.18); }.video-placeholder__visual span { color:#7f89aa; font-size:11px; letter-spacing:.18em; }.video-placeholder__copy p { color:#4f46e5; font-size:12px; font-weight:750; }.video-placeholder__copy h2 { max-width:560px; margin:12px 0 18px; font-size:clamp(30px,4vw,52px); line-height:1.05; letter-spacing:-.05em; }.video-placeholder__copy > span { display:block; max-width:560px; color:#657086; line-height:1.7; }.video-actions { display:flex; gap:10px; margin-top:28px; }
.concept-toast { position:fixed; z-index:40; left:50%; bottom:28px; display:flex; align-items:center; gap:8px; max-width:min(440px,calc(100vw - 32px)); padding:10px 14px; border:1px solid #d8e5df; border-radius:9px; color:#245f4d; background:#f2faf6; box-shadow:0 12px 30px rgba(32,61,51,.15); font-size:11px; transform:translateX(-50%); }.concept-toast svg { flex:none; color:#23805e; }.toast-enter-active,.toast-leave-active { transition:opacity .2s ease, transform .26s cubic-bezier(.16,1,.3,1); }.toast-enter-from,.toast-leave-to { opacity:0; transform:translate(-50%,8px); }
button:focus-visible,input:focus-visible { outline:2px solid #6b6fd6; outline-offset:2px; }
@keyframes note-in { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
@keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:1100px) { .production-workspace.inspector-open { grid-template-columns:minmax(0,1fr); }.artifact-inspector { position:absolute; z-index:8; inset:0 0 0 auto; width:340px; max-width:92%; }.outline-source { grid-template-columns:auto minmax(220px,1fr) auto; }.outline-source__knowledge { display:none; } }
@media (max-width:1050px) { .course-shell { grid-template-columns:190px minmax(280px,.85fr) minmax(360px,1.15fr); }.concept-header { grid-template-columns:1fr auto; }.role-switch { display:none; }.concept-title { display:none; } }
@media (max-width:820px) { .workspace-concept { overflow:auto; }.concept-header { position:sticky; top:0; z-index:5; grid-template-columns:1fr auto; padding:0 12px; }.product-switch button { padding:0 9px; }.course-shell { min-height:900px; grid-template-columns:1fr; }.course-rail { display:none; }.teacher-stage,.artifact-editor,.student-reader,.student-companion { grid-column:1; }.teacher-stage { max-height:420px; }.teacher-stage--production { max-height:none; padding:18px 16px 0; }.production-workspace { height:auto; min-height:760px; margin:0 -16px; }.production-main { padding:16px; }.production-track { overflow:auto; }.track-step { min-width:118px; }.outline-source { grid-template-columns:auto minmax(0,1fr); }.outline-source .text-action { grid-column:2; justify-self:start; }.production-summary { grid-template-columns:1fr 1fr; }.lesson-board__toolbar { align-items:flex-start; flex-direction:column; }.board-tools { width:100%; }.lesson-search { flex:1; }.lesson-table { overflow:auto; }.artifact-inspector { position:absolute; width:100%; max-width:none; }.teacher-overview { grid-column:1; grid-template-columns:1fr; }.student-companion { min-height:380px; }.video-placeholder { grid-template-columns:1fr; }.video-placeholder__visual { display:none; } }
@media (prefers-reduced-motion:reduce) { *,*::before,*::after { scroll-behavior:auto!important; animation-duration:.01ms!important; animation-iteration-count:1!important; transition-duration:.01ms!important; } }
</style>
