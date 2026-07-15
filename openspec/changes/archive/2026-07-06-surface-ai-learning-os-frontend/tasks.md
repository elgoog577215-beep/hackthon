## 1. 规划与现状扫描

- [x] 1.1 读取课程内容、画像、AI 助手、导师建议相关前端组件和 stores。
- [x] 1.2 确认已有 block 折叠、重写、画像、测验提醒和 tutor store 能力。
- [x] 1.3 创建并校验 OpenSpec change。

## 2. 结构化课程文档

- [x] 2.1 优化 `CourseNode` block 展示，突出父子结构、类型、摘要、选中态和折叠状态。
- [x] 2.2 为 block 增加快捷操作菜单：简化、扩展、补例子、生成练习、重写、问 AI。
- [x] 2.3 在 `ContentArea` 接收 block 动作，复用现有 block 重写、测验和 AI 侧栏能力。

## 3. 学习状态与画像显性化

- [x] 3.1 增强 `LearnerProfile`，把画像、动态状态、薄弱点、证据和 AI 判断分区展示。
- [x] 3.2 复用 tutor/profile/note/review/course store，不新建重复画像状态源。

## 4. AI 导师行动卡片

- [x] 4.1 新增轻量 AI 导师行动卡片组件或区块。
- [x] 4.2 读取 `tutorStore.getSuggestion`，展示可执行建议。
- [x] 4.3 将建议动作接到测验、复习、AI 侧栏或内容定位，保持低打扰。

## 5. 验证与收束

- [x] 5.1 更新必要类型和测试。
- [x] 5.2 运行前端构建/测试、OpenSpec 校验和 `git diff --check`。
