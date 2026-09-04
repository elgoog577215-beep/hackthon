# 设计：讲义块同源视觉表达

## 1. 正式对象与边界

```text
当前讲义修订 + 教学块
        ↓
表达建议（不写正式内容）
        ↓ 教师选择图解 / 插图 / 动画
TeachingRepresentation candidate
        ↓ 教师采用
RepresentationSet accepted member
        ├── 讲义原位展示
        ├── PPT 消费接口读取
        └── 学生端消费接口读取
```

讲义文字仍由 `TeacherLessonAuthoringRepository` 保存。视觉表达只保存来源绑定、可检查规格和不可变资产引用，不把媒体 URL、二进制内容或动画代码写回讲义正文。
本变更的共享范围是让三类消费者获得相同的 `representation_id / spec_id`；PPT 编译器和学生页面尚不在本变更中自动渲染它。

## 2. 来源绑定

每个候选必须保存：

- `course_id`
- `lesson_unit_id`
- `script_revision_id`
- `section_node_id`
- `block_id`
- 归一化块内容指纹

来源修订键为 `teacher_script:{lesson_unit_id}`。读取、生成和确认时都与当前工作讲义修订核对；不一致的候选和已采用表达进入 `stale`，不能被重新采用。新候选不会恢复或覆盖旧表达。

## 3. 三类规格

### 3.1 图解

`diagram_spec_v1` 以教学块标题或目标为中心节点，从正文中的有意义句子提取 2–5 个内容节点，关系只使用现有的 `supports / prepares`。首版使用确定性编译器，保证没有文本模型时也能生成可审阅候选。

### 3.2 插图

规格先保存来源摘要、视觉风格、提示词、提供方状态和可重试状态。提供方可用时生成图片，经过现有图片有效性检查后写入 `SlideAssetRepository`；不可用或调用失败时分别返回 `provider_unavailable / provider_failed`。只有真实资产存在时才允许采用。

### 3.3 动画

`scene_spec_v1` 保存画布、对象、动作、时间、焦点、检查点和静态图降级。前端通过 SVG/DOM 执行，不执行模型返回的 JavaScript。播放器支持播放、暂停、上一步、下一步、重新播放，并尊重 `prefers-reduced-motion`。

## 4. 生命周期

```text
candidate ──采用──> accepted ──来源变化──> stale
    │                   │
    ├──放弃────────────> archived
    └──重生成──────────> archived + new candidate
```

同一教学块同一类型只保留一个活动候选；重生成归档旧候选。同类型采用新候选时归档旧的已采用版本。一个教学块可以同时采用图解、插图和动画，它们共同进入一个 `RepresentationSet`。

## 5. 接口

```text
GET  /api/teacher/courses/{course_id}/lessons/{lesson_unit_id}/script/visuals
POST /api/teacher/courses/{course_id}/lessons/{lesson_unit_id}/script/visuals
POST /api/teacher/courses/{course_id}/lessons/{lesson_unit_id}/script/visuals/{representation_id}/resolve
GET  /api/courses/{course_id}/teaching-representations/{representation_id}/assets/{asset_id}
```

所有写接口校验当前讲义修订。图片读取沿用教学表达资产接口，并验证表达类型、规格清单、资产所属课程与 SHA-256。

## 6. 失败与恢复

- 图解或动画规格校验失败：不发布候选，返回结构化错误。
- 图片提供方未配置：发布带提示词的候选状态，教师可在服务配置后重试。
- 图片调用失败：保留提示词、错误代码与可重试状态，不把占位图当成功。
- 任何视觉失败：讲义正文和最后一个已采用表达保持可读。
- 讲义变化：旧表达显示过期，教师从当前块重新生成。
