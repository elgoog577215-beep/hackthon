# 学生学习 Agent 调研与历史界面基线

核查日期：2026-10-05。项目源码基线：`84c92c3e`。本轮完成官方资料、部分源码、Git 历史及历史截图审查，没有运行外部产品，也没有证明其在本项目自建模型上的质量、成本或效果。产品正文见[学生学习](../功能设计/学生学习.md)，实施任务见[学生学习空间](../../../../changes/学生学习空间.md)。

## 结论

学生端面向系统学习、期末备考和项目实践，拥有独立入口与任务流程。成熟阅读界面继续承担系统学习和复习材料的使用；项目实践需要任务、提交与反馈工作区。共享课程、材料、题目、保存和恢复能力，不强制师生共用同一个生成控制台页面。学生内部生成方式后续单独讨论。

优先借鉴 OpenMAIC 的项目活动设计和 DeepTutor 的学习工作区，再吸收 Tutor CoPilot 的引导方法。STORM 适合参考探究过程的来源与问题组织，Google Learn Your Way 适合参考同源内容的多种表达。借鉴的是学习功能与交互，不整套搬入对方框架或多 Agent 调度。

## 外部候选与取舍

星数与最近推送时间为当日 GitHub REST API 快照，随时间变化；星数反映关注度，不代表学习效果。最近推送不等于发布或稳定性保证。下面链接均为官方仓库或机构页面。

| 项目与归属 | 热度、维护与公开范围 | 值得借鉴 | 在灵知怎样采用、边界是什么 |
| --- | --- | --- | --- |
| [OpenMAIC](https://github.com/THU-MAIC/OpenMAIC)，清华 MAIC 团队；仓库提供清华联系信息 | 39,974 stars；最近推送 2026-10-05；MIT，内含第三方包各有许可 | 互动实验、项目里程碑、任务与阶段反馈 | 项目页呈现目标、当前任务、提交物、反馈及下一步；先选一种互动实验验证。AI 同学、多人圆桌、语音课堂不进入首版 |
| [DeepTutor](https://github.com/HKUDS/DeepTutor)，HKUDS | 40,812 stars；最近推送 2026-10-04；Apache-2.0；公开完整工作区源码 | 学习资料、阅读、练习、引导学习在同一工作区连续使用 | 资料选择贯穿讲义、出题和答疑；复用当前材料与题目修订。暂不引入其多检索引擎、插件市场和多渠道助手体系 |
| [Tutor CoPilot](https://github.com/rosewang2008/tutor-copilot)／[Stanford EduNLP](https://edunlp.stanford.edu/projects/tutor-copilot) | 35 stars；最近推送 2024-10-28；Apache-2.0；公开研究演示 Notebook，不是热门完整学生应用 | 引导问题、给提示、解释学生卡在哪里 | AI 助手增加“给一点提示、检查我的思路、看完整解释”等动作，由学生控制帮助程度；研究对象是帮助人类导师，不能直接外推为灵知自学效果 |
| [STORM / Co-STORM](https://github.com/stanford-oval/storm)，Stanford OVAL | 31,570 stars；最近推送 2025-09-30；MIT；研究与知识整理系统 | 多角度提问、带来源的探究、用户调整问题方向 | 项目中的“待验证问题—证据—结论”可参考；当前只用用户上传或已有授权材料，不启用项目冻结的联网来源，不照搬多轮研究生成 |
| [Learn Your Way](https://research.google/blog/learn-your-way-reimagining-textbooks-with-generative-ai/)，Google Research | 机构研究与产品实验；本轮未找到可直接集成的官方完整产品源码，不列作开源仓库 | 同一内容的阅读、分节测验与不同表达形式 | 优先做正文就地自测、针对错误返回相关段落；音频、视频及丰富多模态后置，其模型依赖与效果不直接迁入本项目 |

补充筛选了 [kevinnio/tutor](https://github.com/kevinnio/tutor)：6 stars、MIT、最近推送 2026-09-22，是个人 Skill 项目，不冠以大学或硅谷机构背书。可参考让学习者自己操作、AI 检查过程的做法；无需安装该 Skill，也不把“不代做”变成用户无法获得完整讲解的硬限制。

### 源码层核对

- OpenMAIC 的 [PBL 评价接口](https://github.com/THU-MAIC/OpenMAIC/blob/main/app/api/pbl/v2/evaluate/route.ts)区分 task、milestone、final；[里程碑组件](https://github.com/THU-MAIC/OpenMAIC/blob/main/components/scene-renderers/pbl/v2/eval-cards/milestone-card.tsx)把阶段回顾与继续下一阶段连接起来。可借鉴状态和学生行动关系，不移植其服务。
- DeepTutor 的 [出题配置组件](https://github.com/HKUDS/DeepTutor/blob/main/web/components/quiz/QuizConfigPanel.tsx)包含题量、难度、题型配比；[学习提问提示](https://github.com/HKUDS/DeepTutor/blob/main/deeptutor/services/mastery_hints.py)围绕当前学习位置提供问题，并缓存结果。灵知已有出题与提示能力，应先补学生可用入口，避免新建一套题库或每次切页重新生成。
- Tutor CoPilot 仓库主要提供 Demo Notebook，不能据 README 宣称可直接获得学生前端、权限与持久化能力。

源码链接指向可变化的分支，实施复用前应固定具体提交、检查依赖及保留适用许可。本轮未复制第三方代码或引入新依赖。机构背书、功能演示、研究效果与本项目验收分别判断。

## 本项目历史界面基线

以下是当前 Git 对象中可复查的代表性快照，不证明某日线上部署。历史路径均位于当时仓库的 `frontend/src`，现正式路径为 `apps/lingzhi/frontend/src`。

| 基线 | 已检查证据 | 保留什么 | 不直接恢复什么 |
| --- | --- | --- | --- |
| 2026-03-20，`9ae4cc7a` | `router/index.ts`、`views/CourseView.vue`；根页面和课程页均使用 CourseView | 左目录、中正文、侧边 AI；可收起侧栏、聚焦阅读和引用提问的关系 | 整套历史路由、旧层级和旧状态管理；尚未启动该版本，不能宣称完成像素对照 |
| 2026-08-03，`ffd2bad7` | `views/CourseLibraryView.vue`、`views/LearningView.vue`、路由；查看仓库留存的 `design-qa-course-shell.png` 与 `design-qa-learning-tools-implementation.png` | 独立课程库、新建/导入/继续学习、连续阅读、底部学习工具与练习现场 | 当时混入阅读页的教师教案/PPT入口、旧生成器；截图仅是留存设计/验收材料，不代表当前运行 |
| 当前 `84c92c3e` | `LearnerCourseView.vue`、`LearningView.vue`、路由和教师跳转 | 当前阅读笔记侧栏、笔记/AI 切换、保存及课程修订机制；练习与错题组件 | 默认教师首页不能冒充学生课程库；预览入口不能冒充持久学习入口 |

可用 `git show 9ae4cc7a:frontend/src/views/CourseView.vue`、`git show ffd2bad7:frontend/src/views/LearningView.vue` 复查源码；`git show ffd2bad7:design-qa-course-shell.png > /tmp/student-reference.png` 提取历史图片。无需回退主分支或恢复旧后端。

建议以 8 月的页面分工为骨架，吸收 3 月的阅读体验，保留当前成熟组件。新页面完成后要与这两份历史基线逐项核对；当前只完成源码和部分历史图片审查，尚未完成新页面视觉验收。

## 当前可复用能力与真实缺口

| 能力 | 当前证据 | 判断 |
| --- | --- | --- |
| 学生阅读 | `LearningView.vue` 加载 `LearnerCourseView.vue`；目录、正文、笔记、AI、练习、错题已有组件 | 继续改现有页面，无需新建第二个阅读器；运行闭环仍需验收 |
| 学生首页 | `CourseLibraryView.vue` 文件仍在，但当前 `/courses` 绑定 `TeacherTeachingCalendarView.vue` | 恢复学生专属路由与用途；旧文件含生产/题库管理操作，不能原样挂回即称完成 |
| 右上角入口 | `CourseWorkspaceView.vue::openCoursePreview`、教师日历入口携带 `teacherPreview=1` | 目前为教师临时预览；新增正式学习空间入口时必须与预览明确区分 |
| 学生身份 | `qizhi_auth.py::DEFAULT_ALLOWED_ROLES` 默认仅 teacher/admin，可受配置影响 | 必须完成真实学生身份和课程授权验收，不能仅改默认白名单就放开全部接口；未读取生产配置 |
| 学生创建 | `routers/courses.py::create_course_generation_job` 拒绝非 `lesson_assets_v1` 请求，返回 410 | 旧学生生成按钮不能直接复活；内部生成待讨论，前端可先接通已有可访问内容及合法导入路径，但导入权限也须核验 |
| 练习与错题 | `routers/practice.py` 已有作答、草稿、提示、提交；`MistakeNotebookPanel.vue` 已在 | 补用户可见出题配置和练习入口，复用现有作答修订；完成学生权限和再练验收后才能称可用 |
| 复习 | `routers/review.py::get_review_schedule` 仍筛选 `node_level == 2` | 新课程为课程→讲次，需要按合法学习内容身份确定范围 |
| 项目实践 | 已有文件、个人记录及课程任务能力；未验证项目里程碑—学生提交—反馈完整闭环 | 要新增/补齐个人项目状态与提交关联，不能把聊天结束或文档生成算项目完成 |

## 教师端收敛结论

目标链路已在[生成链路收敛](../../../../changes/生成链路收敛.md)明确，完成状态不能混淆：G1 大纲原路径已替换，完整质量和发布证据未关闭；G2 教案/整讲讲义、G3 PPT、G4 题库、G5 旧执行路径退出尚待完成。

教师后续仍按真实产物依赖分步，完整产物内部尽量一次输出；学生页面研究与现有阅读闭环可先做，不等待全部教师阶段。学生题目生成最终须接 G4 共用题目合同，个人材料须接正式保存与授权；不以学生开发名义重启旧整课生成。

## 建议采用顺序

1. 恢复学生正式入口、课程库和现有阅读—笔记—练习—错题—继续学习闭环，先解决身份与持久化。
2. 在同一学生空间中提供系统学习和期末备考：材料、出题、练习与错题紧密连接。出题支持来源范围、题型、题量、难度，先保证题目可用和反馈可追溯。
3. 项目实践先完成一个真实小项目：任务说明、分步提示、本人提交、依据反馈和阶段回顾。首版接受文本、附件或作品链接，浏览器执行代码与动态实验按具体学科另行验收。
4. 在真实使用证明价值后，再增加互动实验、多种表达及更主动的引导；不因外部项目功能多而一次搬入语音、多人 Agent、知识图谱或长期记忆体系。

这些是基于调研形成的实施建议；三类需求已确认，具体布局和新增形态仍需通过代表页面、真实学习任务验证。学生内部生成不在本轮确定。
