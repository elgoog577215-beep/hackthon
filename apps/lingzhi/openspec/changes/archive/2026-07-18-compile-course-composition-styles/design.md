# 设计：课程编排画像驱动 CourseBlock 配方

## 1. 概念边界

本变更拆开四个容易混淆的概念：

- **教学结构**回答“这个学科必须怎样教”，例如数学需要直觉、形式化和例题，编程需要最小运行、机制、修改与调试。
- **课程编排偏好**回答“这些教学角色在整门课中怎样分布和形成节奏”，例如案例实战增加例题与真实应用，项目驱动让后半程逐步进入独立项目。
- **难度**回答“学习者需要完成多大挑战、获得多少支架”，并投影到每一个课程块。
- **呈现种类**回答“这个块最终用富文本、公式、代码实验或项目等哪种载体表达”，由学科模块和内容生成决定。

课程编排偏好不控制 AI 老师人格、文案语气或页面视觉排版。

## 2. 输入与兼容

新增请求字段：

```text
composition_style:
  balanced
  theory_driven
  example_driven
  project_driven
  inquiry_driven
```

新前端默认提交 `balanced`。旧 `style` 继续被后端接受，但只在没有 `composition_style` 时映射：

```text
academic   -> theory_driven
industrial -> example_driven
socratic   -> inquiry_driven
humorous   -> balanced
```

规范化后的值写入生成请求、任务恢复快照和课程数据。旧字段不再进入新课程的文案风格 prompt。

## 3. 编译链

```text
学科必要模块
→ 课程编排画像扩展与排序
→ 节级难度投影到模块实例
→ 教学方案确认
→ 正文模块标题与内容生成
→ CourseBlock 结构化落盘
```

### 3.1 基础模块不可被删除

`course_pedagogy` 仍是每节基础模块的唯一来源。编排器只能：

- 为不同预设增加通用编排模块；
- 调整安全范围内的角色顺序；
- 给所有模块补充实例、来源、优先级和难度元数据。

编排器不得删除 `required=true` 的学科模块，也不得产生未登记的模块 ID。

### 3.2 五种预设

- **智能均衡**：保持学科基础配方，以目标—讲解—例子/行动—反馈为默认节奏，不机械增加同一类块。
- **理论推导**：每节增加深入推演；在后续或高阶节点增加边界与反例，优先形成概念—推演—形式化—检验节奏。
- **案例实战**：每节增加补充案例；随节点成熟增加真实场景，形成讲解—案例—应用—反馈节奏。
- **项目驱动**：前段增加真实场景和引导任务，后段节点增加项目实战，形成场景—任务—行动—反馈—迁移节奏。
- **问题探究**：每节增加问题探究；随节点成熟加入边界或反例，形成问题—假设—推演—检验—反思节奏。

扩展规则同时读取节点在全课中的相对位置和难度角色，避免每节产生完全相同的模板。

## 4. 模块实例与块级难度

每个 `module_plan` 项至少增加：

```json
{
  "module_instance_id": "section-id:module-id:ordinal",
  "composition_source": "subject_required | subject_optional | composition_style",
  "composition_style": "example_driven",
  "block_role": "example",
  "block_difficulty_contract": {
    "target_level": "intermediate",
    "node_role": "guided_practice",
    "focus_dimension": "application",
    "scaffold_intensity": "medium",
    "learner_autonomy": "guided",
    "transfer_distance": "near",
    "feedback_timing": "after_attempt"
  }
}
```

块级难度不是把小节难度原样复制。编排器根据块角色做可解释投影：概念和先修块优先提供支架，案例块保留示范或半引导，活动和项目块提高自主性与迁移距离，反馈块明确反馈时机。

## 5. 教学确认与最终 CourseBlock

“教学方案”审核产物增加：

- 当前课程编排画像的名称和解释；
- 计划中的全课块角色计数；
- 每节按顺序展示的模块实例、块角色、来源和块级难度摘要。

正文 prompt 必须逐项消费已确认的模块实例契约。Markdown 转换为 `CourseBlock` 时，按模块标题匹配实例，并把 `module_id`、`module_instance_id`、`composition_source`、`composition_style` 和 `block_difficulty_contract` 写入块 `payload`，保证教学方案与最终课程可对账。

## 6. 失败与降级

- 未提供新旧风格字段时使用 `balanced`。
- 提供非法 `composition_style` 时请求校验失败，不静默猜测。
- 恢复旧任务时使用旧字段确定性映射，映射结果写回运行中的规范请求。
- 某节缺少难度契约时，编排器按课程目标难度生成保守默认块契约，但记录来源为 `fallback`。
- 编排扩展不得绕过资料证据策略；真实场景与项目块仍受当前证据账本和来源约束。

## 7. 验证

- 单元测试覆盖预设规范化、旧值映射、学科必需模块保留、不同预设分布、项目渐进节奏和块级难度投影。
- 服务测试覆盖生成请求、任务恢复、教学审核产物和最终 `CourseBlock` 元数据。
- 前端测试覆盖默认值、五个选项、提交字段、教学方案展示和中英文文案。
- 运行后端完整相关测试、前端完整测试、生产构建和 `openspec validate --all`。
