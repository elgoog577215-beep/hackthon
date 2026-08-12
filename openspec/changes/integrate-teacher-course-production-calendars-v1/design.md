## Context

真实课程生产已经由 `courseStore`、`generationStore`、`CourseOutlineReview`、`GenerationLessonPlan`、`CourseGenerationGate`、`CourseTaskCenter` 和 `PptWorkspaceView` 承载。当前新增的 `TeacherCourseProductionView.vue` 已开始把这些能力放入教师壳，但路由、阶段归位、失败展示和 UI 规范尚未完整验证，教学日历则完全没有后端领域对象。

教师的首要工作不是一次生成整门课，而是在真实授课周期中反复停靠、确认、恢复和发布。因此本轮以三个连续但可单独验收的交付面为边界：真实课程生产编排、单课程教学日历、教师教学总日历。模拟页 `/workspace-concept/teacher-course-v1` 只保留为视觉参考，不参与真实状态。

## Goals / Non-Goals

**Goals:**

1. 课程库进入真实生产页后，所有状态来自现有 Store/API，刷新后不丢失，不使用模拟计时器。
2. 大纲、教案、PPT 和发布被明确隔断；完成任一阶段可以离开，教师显式继续下一阶段。
3. 课程日历使用稳定、可持久化的 `ClassSession`，一个教学单元可对应多个班组或重复场次。
4. 总日历只聚合当前身份拥有的日历记录，不复制和反向同步第二份数据。
5. UI 继承当前课程界面的蓝紫色、组件、按钮、字体、间距与反馈，满足高密度、强分类、少打扰、正文优先。
6. 失败必须显示可理解原因、影响范围和可执行恢复动作，并写入问题记录。

**Non-Goals:**

1. 不改课程生成、任务、PPT 构建或发布接口语义。
2. 不实现学校校历导入、节假日自动调课、复杂实验轮转和教务系统同步。
3. 不实现正式浙江大学 DOCX/PDF 模板导出；本轮只冻结后续导出所需字段。
4. 不把课程文件空间升级为课程真源，不做文件夹自动识别和受管文档回导。
5. 不重构学生端内容流程、私人笔记或 AI 对话权限。

## Decisions

### 1. 生产页是现有领域状态的聚合投影，不建立第二套 Store

`TeacherCourseProductionView` 继续调用 `courseStore.loadCourse(courseId)` 和 `generationStore.observeCourse(courseId)`，阶段状态从任务 `guidedWorkflow/review_step/current_step`、课程 projection 和现有工作台数据确定。页面只保存当前阶段、当前讲次和临时展开状态。

**拒绝方案：**复制 `LearningView` 的完整状态到新 Store，或使用本地数组模拟讲次进度。两者都会形成双真源。

### 2. 隔断是显式确认门与可继续动作，不是把全部阶段锁成线性向导

大纲未确认时教案和 PPT 显示来源阻断；大纲确认后，教学日历和分讲教案可以并行。教案按教学单元独立保存和确认；PPT 只有在满足现有 canonical source 要求时才能进入现有工作台。教师可以只完成大纲或若干教案后离开。

**拒绝方案：**保存即自动确认、确认教案即自动构建 PPT、一次按钮整课发布。

### 3. `LessonUnit` 与 `ClassSession` 分层

课程大纲/节点承担“讲什么”，日历场次承担“哪天、几点、在哪里、由谁、面向哪组”。日历只保存 `lesson_unit_id` 引用与必要的内容快照，不复制课程正文。

```text
TeachingCalendarV1
  course_id
  owner_id (仅持久化，不返回)
  revision
  status: draft | confirmed
  academic_year / term / timezone
  source_outline_revision
  sessions[]

ClassSessionV1
  session_id (稳定)
  lesson_unit_id (可空)
  sequence
  date / start_time / end_time
  content_summary / requirements
  location / teacher_name / teaching_type / group_code
  credit_hours / notes / status
  source: manual | outline
```

### 4. 文件 JSON 仓库作为 V1 持久化边界

沿用 `teacher_course_space` 的原子 JSON 写入模式，新增 `backend/data/teaching_calendars/`。按 `owner_id/course_id` 隔离，写入使用临时文件加 `os.replace`，更新要求匹配 `base_revision`，冲突返回 409。

**原因：**仓库当前没有统一关系数据库迁移系统；第一版要求真实持久化但不应引入新服务或 lockfile。该边界可测试、可回滚，后续可在不改变 API 的前提下替换仓库。

### 5. 课程存在校验与身份隔离分开处理

路由先通过现有课程仓库校验 `course_id` 存在，再以稳定 `X-User-Id` 作为日历 owner。当前课程本身尚无正式教师 ownership，因此 V1 只能保证日历数据隔离，不能证明课程授权关系；该缺口必须进入问题记录，不能宣称已完成教师权限体系。

### 6. 从大纲派生只创建候选，不覆盖已有日历

派生读取当前课程节点，优先选择叶子节点并保留稳定节点 ID；若日历为空则创建按顺序排列的未排期场次，若已有日历则返回新增/缺失候选和来源修订，不覆盖日期、地点或教师手工字段。教师提交保存后才形成新日历修订。

### 7. 总日历是只读聚合视图

`GET /api/teachers/me/teaching-calendar` 按日期范围读取当前 owner 的全部课程日历，返回课程稳定颜色键、课程标题和场次。点击事件跳转到 `/course/:courseId/teaching-calendar?session=...` 或课程生产对应教学单元。第一版不在总日历修改场次。

### 8. 页面层级与课程生产交互

产品层级固定为：课程工作台层承载“我的课程 / 教学总日历 / 新建课程”；单课程一级边栏固定为“课程概览 / 教学大纲 / 教学日历 / 课程生产 / 课程文件 / 发布管理”。学生与反馈不进入 V1 教师一级导航，现有偏学生端的课程正文也不迁入教师生产页。

课程生产默认进入横向课次总表，列出课次、教学主题、教案状态、PPT 状态、学生发布版和下一步。点击状态先打开大尺寸快速预览，教师再显式进入沉浸式课次制作；只有进入制作后才出现教学单元窄栏，中间在教案与 PPT 之间切换。教学大纲和发布管理是独立专业页面，不在课程生产内部再建立重复步骤导航。

桌面使用产品栏、课程一级边栏、顶部单行状态和正文主体；教学日历主体默认表格，可切月视图；总日历与“我的课程”同级。生产总览不常驻第二根阶段边栏或右侧状态栏，二级分类进入正文顶部，版本/来源进入抽屉，任务进入浮窗；只有沉浸式课次制作才增加课次栏。

组件与布局分开决策：按钮、Badge、表单、表格交互、Drawer、Dialog、Toast、Confirm、Lucide 图标及真实业务复合组件继承现有实现；页面网格、栏宽、间距与响应式根据当前任务重组。页面间距使用现有 `--space-*` 与 `--lz-*` token，不能因复用组件照搬学生页或模拟页的拥挤骨架，也不能因调整布局另造一套视觉组件。

### 9. 模拟页的使用边界

`/workspace-concept/teacher-course-v1` 只提供颜色、字体、按钮、边框、紧凑尺度和总体气质参考。信息架构、页面层级、生产流程与数据状态以本 design 和产品规划文档为准；不得为了“像模拟页”保留与方案冲突的双层导航、假进度或学生端流程。

## Risks / Trade-offs

- **当前课程没有正式教师 ownership** → 日历按稳定身份隔离，同时在问题记录标记权限欠账；不以此扩大本轮到完整 RBAC。
- **生成 preview 与 published 课程形态不同** → 生产页沿用 `loadCourse` 的 projection 门，PPT 继续遵守 canonical source 门，不把 preview 当正式课程。
- **大纲节点可能没有理想的讲次层级** → 派生算法使用叶子节点和顺序，并允许教师手工删除/新增；保留来源节点 ID 便于后续改进。
- **JSON 文件并发** → `base_revision` + 原子写入，冲突明确返回 409；第一版单进程足够，横向扩展前必须换共享仓库。
- **总日历事件过密** → 默认月视图只显示课程色点与短标题，悬停/点击再展示细节；周/列表承载时间和地点。
- **新真实页和模拟页视觉漂移** → 模拟页只读保留，真实页复用 token/组件，并用浏览器在 1440、1180、880、680 宽度验证。

## Migration Plan

1. 保留现有模拟路由不变，新增真实生产与日历路由。
2. 先完成生产页真实状态与课程库入口，验证现有生成任务、确认门和 PPT 跳转。
3. 增加日历仓库、API 与后端测试，再接前端 Store 和单课程日历。
4. 增加总日历聚合与页面，验证跨课程跳转。
5. 关闭新路由即可回滚 UI；删除路由不会删除已有日历 JSON。日历仓库不自动迁移或覆盖课程数据。

## Open Questions

1. 课程所有权何时由正式教师身份模型承载，而不是借用当前 `X-User-Id`？本轮记录但不阻塞 V1。
2. 学校模板导出、校历冲突和外部日历双向同步进入下一变更，不影响本轮保存和聚合闭环。
