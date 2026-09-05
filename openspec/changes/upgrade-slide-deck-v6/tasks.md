> 2026-09-05 三阶段增强规划：第 1—8 节保留历史基座的实施记录，不作为新内容、模板和关系验收合同已完成的证明。当前施工入口为第 9—14 节，按依赖顺序执行；新代码和真实模型验收未完成前保持未勾选。工具与验收口径以本 change 的新版 design/specs 为准。

## 1. Baseline and contracts

- [x] 1.1 Finish the current template-pack implementation on a clean commit and verify backend, frontend contract tests and production build.
- [x] 1.2 Create the V6 branch from the template baseline and merge the latest deployed progress work without overwriting other changes.
- [x] 1.3 Add failing contract tests for source freeze, course graph coverage/order, template layout closure, story validation, visual degradation and final V6 states.
- [x] 1.4 Add a non-math/non-programming synthetic course fixture and hardcoding guard.

## 2. Course presentation graph and template registry

- [x] 2.1 Implement `ppt_source_contract_v2` and immutable digest checks.
- [x] 2.2 Implement `course_presentation_graph_v1` from canonical ordered course blocks and formal teaching roles without character-based story splitting.
- [x] 2.3 Implement `template_layout_contract_v1` with slots, capacities, intentions, artifact kinds, safe continuations and renderer adapters.
- [x] 2.4 Reject unknown, legacy or unmapped layouts and validate personal-template V6 publication coverage.

## 3. AI story and visual planning

- [x] 3.1 Implement `slide_story_plan_v3` schemas, chapter batching, AIBase invocation and persisted diagnostics.
- [x] 3.2 Enforce 100% primary-block coverage, order/dependency preservation, known IDs and grounded factual tokens; fail the whole candidate on any story-batch failure.
- [x] 3.3 Implement `slide_visual_plan_v2` schemas, bounded concurrency, source-backed decisions and page-level degradations.
- [x] 3.4 Mark allowed degradations `v6_needs_manual_edit`; hard-fail subject, source, capacity and template loss.
- [x] 3.5 Make source-grounded, Markdown-free page summaries an explicit LLM output contract bounded by the selected template slot.
- [x] 3.6 Add selective visual replanning that targets only degraded pages and preserves healthy decisions inside partially resumed chapter batches.

## 4. Final compiler and orchestration

- [x] 4.1 Implement `slide_deck_v6`, dynamic template-safe unit page allocation, typed slot materialization and full-source speaker notes.
- [x] 4.2 Make Web and PPTX adapters consume only the resolved V6 template contract.
- [x] 4.3 Implement final fidelity, subject, grammar, capacity, render and export gates with structured failures.
- [x] 4.4 Route all build entries through one durable V6 orchestrator and atomically retain the last published version on failure.
- [x] 4.5 Compile Markdown, code and tables into template-safe visible projections while retaining complete source text in speaker notes.
- [x] 4.6 Preserve complete table-cell semantics with full-width/wide selection, row pagination with repeated headers, oversized-row detail pages and a no-generated-ellipsis gate.
- [x] 4.7 Compile source-bound full-course agenda pages from ordered top-level sections without distorting formal block coverage.
- [x] 4.8 Preserve semantic paragraph boundaries in body projection and add a vertical numbered practice-sequence composition for Web/PPTX.
- [x] 4.9 Select the full-width table family for dense three-column evidence and size exported rows from measured wrapped text.
- [x] 4.10 Add atomic published-V6 visual repair with frozen story/template/source checks, race protection and last-good-version retention.
- [x] 4.11 Remove the teaching page-count cap, paginate code/steps/tables/prose without semantic loss, preserve sole-body and artifact-support source text, and gate visible artifact/prose fidelity plus generated ellipses.
- [x] 4.12 Compile source-derived two-level agenda entries, cap each agenda page at the sample-backed readable density and keep Web/PPTX agenda hierarchy identical.
- [x] 4.13 Persist code language/line-range metadata, keep adjacent declarations together when capacity permits, and render language, continuation and line-number reading aids without changing source code.
- [x] 4.14 Add a post-export region visibility gate so missing title, prose, steps, table cells or code fails before atomic publication.

## 5. Adaptive progress

- [x] 5.1 Add failing tests for weighted progress, monotonic discovery, 99% publication cap, heartbeat and restart recovery.
- [x] 5.2 Implement persisted `slide_build_progress_v2` manifests and five-second events.
- [x] 5.3 Replace frontend stage inference with server-owned work counts, provider wait/retry and failure details.
- [x] 5.4 Add the degraded-page repair API, durable task monitoring and workbench action without triggering a full rebuild.

## 6. Validation and rollout

- [x] 6.1 Run focused and full backend/frontend regressions, build, OpenSpec validation and hardcoding scan.
- [x] 6.2 Render/export cross-subject fixtures and verify notes, overflow, Web/PPTX parity and PPTX openability.
- [ ] 6.3 历史三课影子验收尚未全部完成；其新合同验收由 14.1—14.3 的三类真实讲义和教师路径接续，不再另起旧目标任务。
- [ ] 6.4 历史默认开关验收未完成；由 14.4 统一核对当前部署状态、新合同独立灰度与回滚，不能根据历史任务直接宣称已上线。
- [x] 6.5 Compare the full-course V6 output against the published Qizhi sample for agenda hierarchy, source-region visibility and code readability, then render every page and run overflow/export audits.

## 7. Teacher PPT Agent convergence

- [x] 7.1 Audit PPTAgent/DeepPresenter, Presenton and PptxGenJS for planning, editing, rendering and license boundaries.
- [x] 7.2 Remove the deterministic teacher story/visual adapter and route the teacher workbench through the shared V6 AI planners.
- [x] 7.3 Reject the retired deterministic planner identities if they are ever reported as completed AI planning.
- [x] 7.4 Persist and display a compact source-bound storyboard summary for teacher inspection.
- [ ] 7.5 Regenerate the accepted teacher test lesson with the live provider and compare page rhythm, title uniqueness, layout diversity and visual decisions against the 41-page baseline. The measured 2026-08-25 attempt reached the shared story planner, then correctly reported the non-retryable `story_ai_batch_balance_unavailable` boundary; the published 41-page baseline remained intact.
- [x] 7.6 Add durable PPT planning call/token/time metrics, remove repeated per-unit layout contracts from the story prompt, and stop model fan-out after a provider-wide balance failure. The measured first-batch failed-path input fell from 108,051 to 25,418 estimated tokens while preserving the last published deck.
- [ ] 7.7 旧外部模型余额/主备凭据方案已退出；由 14.1 使用永久指定的私有 `qwen3.8-27b` 完成真实调用证据，不恢复外部文本模型兜底。
- [x] 7.8 Split each confirmed teacher-script block into a compact learner-canvas projection and an exact full-text speaker-note binding; reject teacher delivery cues from every visible page.
- [x] 7.9 Add source-role classroom page policies for objectives, concepts, derivations, examples, practice, feedback and summaries, plus visible-density and screen-to-notes quality metrics.
- [x] 7.10 Compile common formula notation into editable portable glyphs, distinguish decimal values from numbered-list markers during PPTX export validation, and keep Web/PPTX chapter-opening content in the same declared body region.
- [x] 7.11 Use formal section titles for lesson openings and generate distinct, source-backed teaching titles for every compiler continuation instead of repeating the parent heading.

## 8. Page manuscript teaching contract and teacher control

- [x] 8.1 Expand the story response and `ppt_manuscript_v1` contracts so AI returns a lesson narrative brief plus concrete page goals, claims, learner questions/actions, expected responses, observable evidence, semantic reveal steps and transitions; remove compiler boilerplate substitutes and add hard teaching-content tests.
- [x] 8.2 Add page-scoped teaching quality validation for source traceability, goal/claim usefulness, question-to-response alignment, semantic reveal order and adjacent-page transitions, including deterministic source-bound cover, agenda, recap and continuation behavior.
- [x] 8.3 Add revision-checked manuscript draft editing and lock APIs, synchronize editable visible copy with materialized regions, invalidate confirmation on edits and preserve the last confirmed/last-good manuscript on conflicts or validation failure.
- [x] 8.4 Add targeted page regeneration and source-block impact calculation that preserve non-target and source-current locked pages, surface stale-lock conflicts and reuse only confirmed current question-bank/shared-expression inputs.
- [x] 8.5 Replace the read-only manuscript viewer with a compact continuous-document editor for page teaching fields, save state, page locks, validation diagnostics and selected-page regeneration; keep the independent whole-manuscript confirmation gate and maintain Chinese/English copy.
- [ ] 8.6 Run focused backend/frontend contracts, OpenSpec strict validation, production frontend build and one representative real-provider manuscript/deck inspection; verify that editing visible copy changes Web/PPTX regions and that locked/non-target pages remain unchanged.

## 9. 三阶段合同与固定验收样本（当前入口）

- [x] 9.1 对照当前代码定位内容投影、比较结构、模板对象绑定、图解边丢失及共享素材装配缺口；在 design 中区分代码事实、历史证据与目标能力。
- [x] 9.2 按用户三步更新 proposal、design、四份 capability specs 和任务依赖；明确生产工具、离线工具、内容确认边界与迁移方式。
- [ ] 9.3 从未被其他任务占用的真实讲义中选一个比较任务及一个分支关系任务，冻结来源；建立“正常/缺维度/对象换位/边错误/长中文/来源过期”的固定样本，先复现旧输出关系偏差。
- [ ] 9.4 显式锁定 `python-pptx`、`lxml`、字体、Pillow/FreeType、LibreOffice 与 PDF 渲染工具的部署依赖；验证原生文字、形状、连线、表格和字体可用，记录公式与复杂原生对象的真实支持边界。

## 10. 第一步：内容准备与审阅

依赖：9.3—9.4。完成标志是内容稿能明确表达关系和屏幕信息，尚不代表最终 PPT 已通过。

- [ ] 10.1 在 `ppt_manuscript_v1` 中实现 `page_teaching_v2`：类型化屏幕元素、comparison/process/causal/hierarchy 等表达结构、来源片段、`must_show`、来源去向及展示状态；旧版本不伪造新字段。
- [ ] 10.2 拆分原文备注完整性与屏幕教学完整性；允许来源忠实的概括、图解和明确摘录，删除新合同路径中的全文强制上屏、sole-body 逐字规则和最低字数填充；保留上屏公式、代码片段、数据及引文的准确性。
- [ ] 10.3 用私有 `qwen3.8-27b` 实现整讲路径与有界逐页表达规划，提供模板能力摘要；关系/来源/容量错误只触发受影响页修复，记录真实调用与耗时。
- [ ] 10.4 接入当前稿件编辑、保存、锁定和局部重生路径，让教师审阅比较维度、屏幕元素和展示状态；修改失效确认，保留非目标页与最后可用稿，同步中文/英文文案。
- [ ] 10.5 通过来源缺失、关系不完整、题目答案错配、有效锁/过期锁、并发保存和选定代码/引文片段测试；客观错误与教学改进建议分别呈现。

## 11. 第二步：模板制作、标注与认证

依赖：9.4、10.1。先完成对比模板，再扩展页面库；不等待全部页面做好才验证首个闭环。

- [ ] 11.1 扩展现有模板 manifest，加入 `teaching_layout_v2` 能力版本、表达约束、`native_fill`/`component_render`、源对象/组路径/单元格绑定、字体下限、资产/组件版本和认证结果。
- [ ] 11.2 实现模板检查与认证 CLI：原生对象清单、缺失/歧义目标诊断、短/标准/长中文及图形样本填充、真实渲染检查；几何推断只保存为待校对草稿。
- [ ] 11.3 制作并认证图形对比、矩阵对比两个模板；校验共同条件、左右身份、维度对齐、同尺度图形和超容量行为。
- [ ] 11.4 在首个对比闭环通过后，完成同一主题下的问题引入、概念图解、流程/因果、逐步推演、例题/练习与总结，加公共封面/导航壳；逐个保存真实填充证据。
- [ ] 11.5 实现运行时版式选择、槽位绑定与统一字体测量；不兼容时返回内容稿修复，确认后不换模板或缩字；个人模板保留能力报告与维护者校对。

## 12. 第三步：确定性生成与首个完整闭环

依赖：10.1—10.3、11.1—11.3；12.1—12.3 优先打通首个对比样板，再执行 11.4 的扩展。

- [ ] 12.1 提取单一页面执行计划，冻结元素、槽位、几何、关系、资产、字体、工具与物理页映射；预检、Web 与 PPTX 读取同一计划，不各自猜布局。
- [ ] 12.2 原生填充按对象 ID 替换，受控组件按类型绘制；去除个人图解按数组横排连接、通用图解强制 `process` 和未声明重绘，原生连线保留真实端点/方向/条件。
- [ ] 12.3 从 9.3 的真实讲义经私有模型生成对比内容稿，完成教师路径中的保存确认、模板填充、预览与 PPTX 导出；核对图形对比/矩阵对比和对象编辑能力，保存首个闭环证据。
- [ ] 12.4 接通已采用共享图解/插图的实际装配和不可变摘要；实现静态展示状态页，在确认前确定物理页数，验证问题先于答案及完整备注归属，不启用动画。
- [ ] 12.5 对已确认稿重复导出，证明语义对象、关系、数据、页序和来源相同且内容/视觉模型调用为零；最终生成发现容量错误时返回诊断，不自动改稿。

## 13. 质量、局部修复与可恢复执行

依赖：12.1—12.5。执行故障修输出器；可见内容变化回到草稿确认。

- [ ] 13.1 增加导出关系/身份审计：分支图 A→B、A→C 不得变成 A→B→C；比较单元格不能换位；图表单位/数据、图片摘要与状态可见集合一致。
- [ ] 13.2 将真实 PPTX 文字/对象回读、LibreOffice 全页渲染、字体/越界/遮挡检查接入原质量链；分开报告公式符号编辑与矢量对象编辑能力，禁止整页贴图冒充可编辑。
- [ ] 13.3 原 TaskManager 工作清单增加三阶段工作类型与正确终态，内容稿就绪不等于 PPT 已生成；缓存与恢复同时校验来源、内容稿、模板、字体、编译器、渲染器和质量合同版本。
- [ ] 13.4 验证模型失败、模板对象缺失、字体缺失、资产失败、渲染失败、并发发布和重启恢复；只重试失败依赖，保留非目标稿件与最后可用 PPT；内容变化重新确认。

## 14. 跨学科验收、灰度与后续扩展

依赖：首批八类模板与第 10—13 节完成。每项按实际证据勾选，缺模型、字体或渲染工具时报告未验收。

- [ ] 14.1 用数学/数据、编程/工程、人文/社会三类真实讲义运行相同私有模型与生成路径；记录模型身份、调用次数、tokens、耗时、页数、人工修改与失败原因，禁止课程 ID 特判。
- [ ] 14.2 全部物理页通过来源、结构、模板与输出硬检查；PowerPoint 抽检对比、分支、公式与练习状态；教师评阅页面任务、图解价值、阅读密度与讲授节奏，并处理严重问题。
- [ ] 14.3 中文桌面端完成“当前讲义 → 内容稿 → 修改/确认 → 生成/导出 → 局部修复/失败恢复”；验证上传已有 PPT 的原件审阅路径仍可使用，同步所涉英文。
- [ ] 14.4 配置新合同独立灰度开关，验证关闭后旧稿/新稿仍可读取与导出、运行任务不被替换；完成生产观察和回滚证据后再开放新建默认，并回写产品状态、系统架构和事实。
- [ ] 14.5 在首批通过后补认证的层级、数据图表、证据材料页，再用第二主题验证内容/版式/风格解耦；复杂原生公式和个人模板按真实样本扩展，未支持能力保持明确。
