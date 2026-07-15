# course-acceptance-preflight Specification

## Purpose
TBD - created by archiving change add-course-acceptance-preflight. Update Purpose after archive.
## Requirements
### Requirement: 预检必须只读并检查六项课程使用契约

系统 MUST 在不修改课程、版本、资产和学习状态的前提下检查版本、目标、内容、练习、补救和推进六项契约，并输出稳定机器可读报告。

#### Scenario: 标准课程缺少正式题目

- **WHEN** 以 `standard` 口径预检一门能够正常打开但没有正式题目的课程
- **THEN** 练习契约 MUST 返回 blocked
- **AND** 系统 MUST NOT 现场编译题目或修改课程文件

### Requirement: 默认口径不得从资产缺失推断兼容降级

系统 MUST 默认采用 `standard` 口径。`auto` 只可根据生成计划中的显式阅读型声明切换为 `reading_only`；MUST NOT 因版本、题目或补救资产缺失自动选择 `compatibility`。

#### Scenario: 旧课程没有资产计划

- **WHEN** 客户端未指定口径或使用 `auto` 预检旧课程
- **THEN** 系统 MUST 按 `standard` 检查并报告阻断项
- **AND** 只有显式请求 `compatibility` 才可返回兼容降级结果

### Requirement: 内容和目标投影必须与持久资产区分

系统 MAY 在深拷贝上使用现有读取投影判断旧课程是否可阅读，但报告 MUST 区分投影结果和持久生成资产。正式题目、量规、补救资产、版本和推进契约 MUST 只认持久数据。

#### Scenario: 旧正文可以投影内容块

- **WHEN** 旧节点只有 Markdown 正文而没有持久内容块
- **THEN** 内容契约 MAY 通过语义锚点可用性检查并给出投影警告
- **AND** 报告 MUST NOT 声称内容块由生成器持久化

### Requirement: 阅读型课程必须显式声明降级

只有生成计划显式关闭正式题目并声明 `reading_only_degraded` 时，练习与补救契约才可在 `reading_only` 口径下返回 degraded；版本、目标、内容和推进契约仍 MUST 通过。

#### Scenario: 无题课程未声明阅读型

- **WHEN** 一门课程没有正式题目且没有显式阅读型计划
- **THEN** 预检 MUST 将其视为标准课程资产缺失
- **AND** MUST NOT 自动标记为合法阅读型课程

### Requirement: 目录扫描必须报告损坏文件且不得自动恢复

目录扫描 MUST 跳过旧版本快照，读取每个主课程 JSON，并将无效 JSON 作为存储完整性阻断项返回；MUST NOT 调用恢复、迁移或写入逻辑。

#### Scenario: 主课程 JSON 损坏且存在快照

- **WHEN** 目录中存在无法解析的主课程文件
- **THEN** 报告 MUST 包含文件名、课程 ID 和安全错误类型
- **AND** 主文件内容与时间戳 MUST 保持不变

### Requirement: API 与 CLI 必须共享同一检查器

单课程 API、全目录 API 和命令行 MUST 复用同一纯检查器并输出相同 schema。CLI MUST 支持 JSON 输出、课程过滤以及阻断时非零退出。

#### Scenario: CLI 用于自动门禁

- **WHEN** 使用 `--fail-on-blocked` 扫描包含阻断课程的目录
- **THEN** CLI MUST 输出完整 JSON 报告
- **AND** MUST 返回退出码 2
