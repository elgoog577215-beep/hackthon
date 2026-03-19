# Requirements Document

## Introduction

优化做题界面的用户体验。当前测验对话框（ContentArea.vue 中的 Quiz Dialog）一次性显示所有题目，缺少辅助思考工具。本次增强将实现单题显示模式、文字草稿面板、图画草稿覆盖层，并将草稿与错题本关联，帮助用户在答题时记录思路、在复习时回顾解题过程。

## Glossary

- **Quiz_Dialog**: ContentArea.vue 中的测验弹窗（el-dialog），用于展示 AI 生成的测验题目
- **Question_Navigator**: 题目导航组件，用于在单题显示模式下切换上一题/下一题，并显示当前进度
- **Text_Draft_Panel**: 文字草稿面板，从屏幕右侧滑出的可编辑纯文本区域，每道题独立存储
- **Drawing_Overlay**: 图画草稿覆盖层，覆盖在 Quiz_Dialog 上方的半透明画布，用户可用鼠标绑定的画笔工具在上面绘图
- **Drawing_Toolbar**: 绘图工具栏，包含颜色选择、线条粗细、画笔/橡皮擦切换和一键清空按钮
- **Draft_Store**: 草稿存储模块，负责管理每道题的文字草稿和图画草稿数据
- **Review_Store**: 复习 Store（frontend/src/stores/review.ts），管理错题记录、测验历史
- **Wrong_Answers_View**: NotesPanel.vue 中的错题本视图，展示所有错题记录及复习功能

## Requirements

### Requirement 1: 单题显示模式

**User Story:** 作为学习者，我希望做题时一次只看到一道题，这样我可以专注于当前题目而不被其他题目干扰。

#### Acceptance Criteria

1. WHEN Quiz_Dialog 打开并加载题目后，THE Quiz_Dialog SHALL 仅显示当前索引对应的单道题目，隐藏其余题目
2. THE Question_Navigator SHALL 显示当前题号和总题数（格式：第 X 题 / 共 Y 题）
3. WHEN 用户点击"下一题"按钮，THE Question_Navigator SHALL 将当前索引加 1 并显示下一道题目
4. WHEN 用户点击"上一题"按钮，THE Question_Navigator SHALL 将当前索引减 1 并显示上一道题目
5. WHILE 当前索引为 0，THE Question_Navigator SHALL 禁用"上一题"按钮
6. WHILE 当前索引等于总题数减 1，THE Question_Navigator SHALL 禁用"下一题"按钮
7. WHEN 用户切换题目，THE Quiz_Dialog SHALL 保留用户已选择的答案不丢失
8. WHILE 测验已提交（quizSubmitted 为 true），THE Quiz_Dialog SHALL 允许用户通过导航浏览所有题目的答案和解析

### Requirement 2: 文字草稿面板

**User Story:** 作为学习者，我希望在做题时能打开一个文字编辑区域记录解题思路，这样我可以整理思路辅助解题。

#### Acceptance Criteria

1. THE Quiz_Dialog SHALL 在题目区域下方显示一个"文字草稿"按钮
2. WHEN 用户点击"文字草稿"按钮，THE Text_Draft_Panel SHALL 从 Quiz_Dialog 右侧滑出显示
3. WHEN 用户再次点击"文字草稿"按钮或点击关闭按钮，THE Text_Draft_Panel SHALL 收起隐藏
4. THE Text_Draft_Panel SHALL 提供一个可自由编辑的纯文本输入区域（textarea）
5. THE Draft_Store SHALL 为每道题独立存储文字草稿内容
6. WHEN 用户切换到另一道题目，THE Text_Draft_Panel SHALL 加载该题目对应的文字草稿内容
7. WHEN 用户在文字草稿中输入内容，THE Draft_Store SHALL 实时保存该题目的文字草稿

### Requirement 3: 图画草稿覆盖层

**User Story:** 作为学习者，我希望在做题时能直接在屏幕上画图辅助思考，这样我可以画示意图、标注关键信息。

#### Acceptance Criteria

1. THE Quiz_Dialog SHALL 在题目区域下方显示一个"图画草稿"按钮（与"文字草稿"按钮并列）
2. WHEN 用户点击"图画草稿"按钮，THE Drawing_Overlay SHALL 以半透明背景覆盖在 Quiz_Dialog 上方显示
3. THE Drawing_Overlay SHALL 使用 HTML5 Canvas 元素作为绘图表面
4. THE Drawing_Toolbar SHALL 提供至少 5 种固定颜色供用户选择（黑色、红色、蓝色、绿色、橙色）
5. THE Drawing_Toolbar SHALL 提供至少 3 种固定线条粗细供用户选择（细、中、粗）
6. THE Drawing_Toolbar SHALL 仅提供画笔和橡皮擦两种绘图工具
7. WHEN 用户选择画笔工具并在 Drawing_Overlay 上按住鼠标拖动，THE Drawing_Overlay SHALL 沿鼠标轨迹绘制选定颜色和粗细的线条
8. WHEN 用户选择橡皮擦工具并在 Drawing_Overlay 上按住鼠标拖动，THE Drawing_Overlay SHALL 擦除鼠标轨迹经过区域的绘图内容
9. THE Drawing_Toolbar SHALL 提供一个"清空"按钮
10. WHEN 用户点击"清空"按钮，THE Drawing_Overlay SHALL 清除当前画布上的所有绘图内容
11. THE Draft_Store SHALL 为每道题独立存储图画草稿数据（Canvas 导出为 dataURL）
12. WHEN 用户切换到另一道题目，THE Drawing_Overlay SHALL 加载该题目对应的图画草稿
13. WHEN 用户点击关闭按钮或再次点击"图画草稿"按钮，THE Drawing_Overlay SHALL 隐藏并保存当前画布内容

### Requirement 4: 草稿与错题关联保存

**User Story:** 作为学习者，我希望做错的题目能自动保存我的草稿，这样我复习时可以回顾当时的解题思路。

#### Acceptance Criteria

1. WHEN 用户提交测验且某道题回答错误，THE Draft_Store SHALL 将该题的文字草稿和图画草稿数据附加到错题记录中
2. WHEN 用户提交测验且某道题回答正确，THE Draft_Store SHALL 丢弃该题的草稿数据（不保存到错题记录）
3. THE Review_Store 的 wrongAnswers 数据结构 SHALL 扩展包含 textDraft（string 类型，可选）和 drawingDraft（string 类型，dataURL 格式，可选）两个字段
4. WHEN 错题记录包含草稿数据，THE Review_Store SHALL 将草稿数据一并持久化到 localStorage
5. WHEN Quiz_Dialog 关闭，THE Draft_Store SHALL 清空当前测验的所有临时草稿数据

### Requirement 5: 错题本查看草稿

**User Story:** 作为学习者，我希望在错题本中能查看之前做题时的文字笔记和图画笔记，这样我可以回顾解题思路帮助复习。

#### Acceptance Criteria

1. WHILE 错题记录包含 textDraft 数据，THE Wrong_Answers_View SHALL 在该错题的展开区域显示"查看文字笔记"按钮
2. WHILE 错题记录包含 drawingDraft 数据，THE Wrong_Answers_View SHALL 在该错题的展开区域显示"查看图画笔记"按钮
3. WHEN 用户点击"查看文字笔记"按钮，THE Wrong_Answers_View SHALL 展开显示该错题保存的文字草稿内容（只读模式）
4. WHEN 用户点击"查看图画笔记"按钮，THE Wrong_Answers_View SHALL 以弹窗或内嵌图片形式展示该错题保存的图画草稿（只读模式，渲染 dataURL 为图片）
5. WHILE 错题记录不包含 textDraft 数据，THE Wrong_Answers_View SHALL 隐藏"查看文字笔记"按钮
6. WHILE 错题记录不包含 drawingDraft 数据，THE Wrong_Answers_View SHALL 隐藏"查看图画笔记"按钮
