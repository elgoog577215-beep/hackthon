# Multi-lens Review

## Merge-compatibility review (2026-08-15)

### Product / CEO — PASS

“同一产品内的教师端与学生端”比把学生页改造成教师页更符合真实上课关系。教师有独立生产业务，学生保留原学习能力，底层生成引擎共享，产品定位清晰。

### Engineering — NEEDS FIX

当前分支仍存在教师页直连共享 Store、教师课程编排端点放在共享 `courses.py` 以及部分全局策略改动。WP9 必须先收窄这些边界再整合 `origin/main`；否则后续生成能力每次升级都会重新冲突。

### QA — NEEDS FIX

新增双端契约硬门：学生默认路由、续学、练习、AI 对话和学习写入必须保持；教师路由、只读预览、阶段停靠与日历必须通过。只验教师页不能作为合并完成证据。

### Security / CSO — PASS WITH LIMITATION

教师预览必须零学习写入，本地运行数据、API key、`.env`、截图和导出产物不得进入合并 diff。当前没有正式教师 RBAC，因此只能宣称产品面与数据边界，不宣称生产级授权完成。

### Frontend — PASS

`/teacher` 命名空间 + 教师专属 View + 窄 runtime adapter 可以保留现有 UI 与组件，同时将生成 Store 改动的影响收敛到一处。学生 `CourseLibraryView` 与 `LearningView` 必须按上游行为回归。

### Backend — PASS

保留 `GenerationJob / TaskManager / CourseDocument / CourseTeachingPlanV3 / TeachingRepresentation` 为共享能力；分讲资产继续由 `TeacherLessonAuthoringRepository` 持有，教师课程编排路由只转发命令和投影状态。该边界不增加网络跳数，也不引入第二存储引擎。

### Full-stack — PASS

路由与 API 命名空间分开，但仍同域运行、同次调用底层引擎。适配层不会带来可感知性能成本。

### Context Engineer — PASS

WP9 已将所有权、冲突解决顺序、硬门和回滚条件写入唯一 `plan.md`，不依赖另一份临时计划。

### Personal Developer — PASS

当前教师 worktree 继续作为隔离边界；不新建 worktree，不在规划阶段合并或 push 主分支。

### Knowledge Steward — PASS

本轮是项目级架构决策，已写入当前 OpenSpec。未获得用户明确的长期记忆写入授权，不更新用户级 memory。

---

## Product / CEO — PASS

课程工作台 → 教师概览 → 大纲/日历/生产/文件/发布的层级已经与完整讨论对齐；生产按大纲、逐讲教案、按需 PPT 分段推进，当前大纲结构可用且来源未过期后，日历和教案即可并行。当前 change 交付真实生产与日历 alpha；浙江模板导入导出通过 follow-up change 完成产品 V1；文件桥接和学生端后置，范围可控且不混称完成。

## Engineering — QUESTION

生产页只做既有状态聚合；日历使用独立但窄的 owner/course 仓库和稳定 API，不复制课程正文或 PPT。问题是当前“课程概览”仍指向 `LearningView`、“课程文件”丢失 `courseId`，必须在 WP2 修正后才可认为路由真源完整。JSON 仓库是 alpha 取舍，接口可在后续替换持久层。

## QA — NEEDS FIX

Eval Contract 已覆盖持久化、冲突、身份隔离、聚合、刷新恢复、失败路径、多视口和原模拟页回归，但当前 680px 出现竖排导航，生产总览也未符合最终交互，因此 Hard Gate 仍失败。还需生成中、部分失败、已发布三类真实课程证据；真实模型不可用时不得用 mock 宣布完成。

## Security / CSO — QUESTION

当前 `X-User-Id` 只是稳定身份，不是正式教师认证；V1 能保证日历 owner 隔离，不能证明课程级授权。该问题必须记录并限制宣传，不阻塞本地第一版验证。

## Frontend — NEEDS FIX

视觉上下文已明确：教师日常高频工作台，组件与 token 继承原项目，页面网格按功能重组。当前实现固定课程栏、生产阶段栏和状态栏，造成“导航下方空、正文被夹窄”；680px 活动项文字竖排。WP3 必须改为单课程栏 + 顶部状态 + 立即出现课次表，沉浸制作时才增加课次栏；四档浏览器验证前不能 PASS。

## Backend — PASS

新增路由和仓库边界清楚，不修改生成/PPT/发布契约。`base_revision` 和原子写入覆盖单进程并发；横向部署前需迁移共享仓库。

## Full-stack — PASS

沿用现有 API base、身份 header 和端口；无新依赖、环境变量或服务。前端 Store 可通过现有 http 客户端获取明确错误。

## Context Engineer — PASS

产品设计源稿、20 项确认决策和本 change 已建立追踪矩阵。当前 change 承载课程工作台入口、真实生产编排和日历 alpha；模板导入导出明确交给 follow-up change，文件/学生/知识节点不静默扩入。

## Personal Developer — PASS

实现顺序先共享契约后页面，问题统一进当前 run；不碰其他 worktree 和用户已有文件空间改动。

## Knowledge Steward — PASS

本轮重复强调的 UI 原则和“真实状态不能用模拟代替”属于已有项目规则，不新建重复长期经验；新发现的日历权限或持久化失败只记录项目问题，验证后再决定是否沉淀。
