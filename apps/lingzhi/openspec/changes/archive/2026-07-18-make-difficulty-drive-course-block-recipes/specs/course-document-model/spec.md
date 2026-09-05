## MODIFIED Requirements

### Requirement: 正式课程块必须保留生成编排追溯

首次课程生成将已确认模块实例转换为 `CourseBlock` 时，块 `payload` MUST 保留模块 ID、模块实例 ID、有效编排来源、全部选择原因、课程编排偏好和块级难度契约。块类型与块角色 MUST 继续由正式课程文档模型表达，追溯元数据 MUST NOT 建立第二份课程正文或替代稳定块 ID。

#### Scenario: 已确认的补充案例生成正式课程块

- **WHEN** `composition_style` 增加的案例模块完成正文生成并转换为 `CourseBlock`
- **THEN** 该块 MUST 使用 `example` 角色和适合内容的正式块类型
- **AND** `payload` MUST 引用原模块实例及其块级难度契约
- **AND** 教学方案与正式课程块 MUST 可按模块实例对账

#### Scenario: 课程块由学科必要模块生成

- **WHEN** 正式课程块来自学科教学结构要求的必要模块
- **THEN** 该块 MUST 标记来源为学科必要模块
- **AND** 课程编排偏好或难度 MUST NOT 冒充该模块的基础来源或删除其追溯

#### Scenario: 高阶难度选择证明模块

- **WHEN** 高阶数学难度配方选择的证明模块生成正式课程块
- **THEN** `payload.selection_reasons` MUST 包含 `difficulty_level`
- **AND** `payload.block_difficulty_contract.target_level` MUST 为 `advanced`
