## ADDED Requirements

### Requirement: 学习资产必须复用节点证据契约

题目、知识关系和通用误区 MUST 从 EvidenceCoveragePlan 与 NodeGroundingContract 编译资产级证据绑定，不得建立独立摘要或第二套来源标识。资产引用 MUST 使用有效 EvidenceUnit ID，风格资料不得越权支持事实。

#### Scenario: 为节点生成配套题目

- **WHEN** 节点具有 required、optional 和 question evidence
- **THEN** AssetGenerationContract MUST 引用对应 EvidenceUnit ID
- **AND** 题干事实、答案和解析 MUST 通过 grounding annotation 或结构化绑定追溯

#### Scenario: 资料证据失效

- **WHEN** EvidenceUnit 被删除、替换或权威策略变化
- **THEN** 系统 MUST 通过资产依赖标记相关题目、关系和误区过期
- **AND** MUST NOT 使未引用该证据的资产失效
