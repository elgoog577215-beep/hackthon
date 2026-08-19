## ADDED Requirements

### Requirement: 课程文件包必须绑定稳定课程身份
嵌入统一课程工作区的文件包 MUST 保存 `course_id`，并以 `owner_id + course_id` 作为默认查找边界。课程标题仅用于显示，不得作为长期关联键。

#### Scenario: 课程改名后打开资料
- **WHEN** 已绑定文件包的课程名称发生变化
- **THEN** 系统仍通过 `course_id` 打开原文件包
- **AND** 不创建新的空文件包或丢失原目录

#### Scenario: 创建课程文件包
- **WHEN** 用户在一门课程的资料子模块创建文件包
- **THEN** 创建请求携带当前 `course_id`
- **AND** 返回清单保存该课程 ID 与当前 owner

### Requirement: 旧文件包绑定必须可控且可恢复
系统 MUST 继续读取没有 `course_id` 的旧文件包。只有当前 owner 下存在唯一课程标题候选时，界面 MAY 提示并绑定到当前课程；有多个候选时 MUST 要求显式选择，不得静默绑定或删除数据。

#### Scenario: 唯一旧文件包候选
- **WHEN** 当前课程没有已绑定包且当前 owner 只有一个同名旧包
- **THEN** 系统可将其作为兼容候选显示
- **AND** 完成绑定后保留原 package ID、目录、文件和导入历史
