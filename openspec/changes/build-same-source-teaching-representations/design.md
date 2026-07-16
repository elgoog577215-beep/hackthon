# 设计：一份课程语义向外编译多种教学表达

## 1. 真源边界

`CourseDocument / CourseBlock` 继续负责课程结构、顺序和正文语义；`CourseKnowledgeBase / CourseKnowledgeMap` 负责当前课程知识语义和映射；`PracticeTask / MasteryCriterion` 负责正式题目与评分。大纲是课程结构投影，教案、PPT、讲义、图解和动画是 `TeachingRepresentation`，不得复制课程语义所有权。

## 2. 共享修订向量

课程仓库为每次正式发布和命令提交持久化 `CourseRevisionEvent`：

```text
previous_revision_vector
current_revision_vector
changed_source_keys
added_source_keys
removed_source_keys
affected_block_ids
```

修订键第一阶段包括：

```text
course_document
section:<section_id>
block:<block_id>
objective:<objective_id>
```

事件写入现有课程操作日志，派生服务即使暂时不可用也能稍后重放，不阻断课程正式提交。

## 3. 来源绑定

每个表达保存 `SourceBinding`，绑定课程、章节、块、选区、知识、目标、题目、资料及其源修订。课程级表达依赖 `course_document`；小节表达依赖对应 `section:*`；局部表达优先依赖精确 `block:*`，避免一次局部修改使全课程产物全部过期。

## 4. 派生依赖与陈旧传播

`AssetDerivationGraph` 使用有向边连接源对象、表达规格、教学表达和最终产物。课程修订事件到达后：

1. 比较新旧修订向量。
2. 更新源节点修订。
3. 从变化源节点沿依赖边查找下游对象。
4. 将受影响表达标记为 `stale` 并记录原因。
5. 后续构建器只重建受影响单元。

陈旧标记是确定性动作，不依赖大模型。表达构建失败不得回滚已经提交的课程语义。

## 5. 表现与语义编辑

表示编辑分为：

```text
presentation
equivalent_semantic
semantic
ambiguous
```

前两类只改变表示修订；`semantic` 转换为 `CourseAuthoringChange`；`ambiguous` 要求用户决定。只有教师或课程维护者确认后，基础课程领域命令才能覆盖正式语义。个人学习证据和 `PersonalAdaptationPlan` 不进入这条写入链。

## 6. 任务与恢复

表达构建复用现有可恢复任务能力和同一服务端活动状态原则。WebSocket 只提供增量，服务端工作区与检查点是真源。课程提交先完成，表达重建异步进行；最后一个可用表达在新版本质量通过前继续保留。

## 7. 实施顺序

1. P0：修订事件、来源绑定、表示注册表、派生依赖图和陈旧传播。
2. R1：大纲、教案、讲义、题目投影和 `SlideDeckSpec` 最小编译闭环。
3. R2：增量重建、状态恢复、降级和跨产物一致性。
4. R3：结构化 PPT 反向语义编辑。
5. M：图解与结构化动画。
6. I：独立完成同源闭环，再验证与个人覆盖层的受控边界协作。
