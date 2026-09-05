## MODIFIED Requirements

### Requirement: 大型工具必须临时介入并准确返回

正式任务、学习记录总览、统计、知识图谱和代码工作台 MUST 通过统一覆盖层临时展开。正式任务在桌面 MUST 从正文预览块或并行工具入口进入居中弹窗，在移动端 MAY 全屏展开；MUST NOT 使用右侧半屏抽屉替代正文任务关系。打开前 MUST 保存来源引用和语义锚点，关闭后 MUST 返回原位置和最新正式状态。

#### Scenario: 用户从正文练习预览块打开正式任务

- **WHEN** 用户点击正文中可见的正式练习预览块
- **THEN** 系统 MUST 将同一正式任务从块态过渡为桌面居中弹窗或移动端全屏任务
- **AND** 预览块与弹窗 MUST 读取同一题目资产与 `PracticeAttempt`
- **AND** 系统 MUST NOT 在正文预览块创建第二份答案或进度状态

#### Scenario: 用户关闭正在进行的任务

- **WHEN** 活动 Attempt 已保存草稿且用户关闭覆盖层
- **THEN** 系统 MUST 返回来源任务块并显示继续状态
- **AND** MUST NOT 重载课程、跳到页面顶部或创建新 Attempt

#### Scenario: 用户偏好减少动态效果

- **WHEN** 系统检测到 `prefers-reduced-motion: reduce`
- **THEN** 正式任务 MUST 仍可正常打开、关闭和返回来源
- **AND** 系统 MUST NOT 依赖位移或缩放动画完成状态切换
