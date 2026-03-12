# Requirements Document

## Introduction

重新设计"划线引用提问"功能，将当前的全屏浮动 AI 助手对话框替换为右侧滑出式 AI 面板（Side AI Panel）。用户选中文本后点击"引用提问"，自动打开右侧面板并展示引用内容、智能建议按钮和对话区域，模仿豆包（Doubao）的交互设计。面板打开时主布局自动调整，关闭后恢复原始布局。

## Glossary

- **Side_AI_Panel**: 右侧滑出式 AI 对话面板组件，占据屏幕右侧约 1/3 宽度，包含引用卡片、智能建议按钮、对话区域和输入区域
- **Quote_Card**: 输入区域上方的单行引用卡片，展示用户选中的文本内容（超长截断），带有关闭按钮
- **Suggestion_Button**: 引用卡片下方的智能建议按钮，提供预设的快捷提问选项（如"解释一下"、"详细展开"、"深入研究"）
- **Selection_Menu**: ContentArea 中用户选中文本后弹出的操作菜单
- **Content_Area**: 课程内容主显示区域
- **Course_Tree**: 左侧课程目录树组件
- **Notes_Column**: 右侧笔记栏
- **Layout_Manager**: CourseView 中负责管理各面板可见性和宽度的布局逻辑

## Requirements

### Requirement 1: 面板触发与打开

**User Story:** As a learner, I want to select text and ask AI about it in one click, so that I can get contextual explanations without leaving the reading flow.

#### Acceptance Criteria

1. WHEN the user clicks the "引用提问" button in the Selection_Menu, THE Side_AI_Panel SHALL open on the right side of the screen with the selected text displayed in the Quote_Card.
2. WHEN the Side_AI_Panel opens, THE Layout_Manager SHALL collapse the Course_Tree (left sidebar) and the Notes_Column (right notes) to maximize content space.
3. WHEN the Side_AI_Panel opens, THE Content_Area SHALL adjust its width to occupy the remaining horizontal space to the left of the Side_AI_Panel.
4. THE Side_AI_Panel SHALL occupy approximately one-third of the viewport width on desktop screens (≥1024px).
5. WHEN the Side_AI_Panel opens, THE Side_AI_Panel SHALL apply a slide-in-from-right transition with a duration between 250ms and 350ms.

### Requirement 2: 引用卡片展示

**User Story:** As a learner, I want to see the quoted text clearly above the input area, so that I know what context the AI conversation is about.

#### Acceptance Criteria

1. THE Quote_Card SHALL be displayed as a single-line element directly above the input area at the bottom of the Side_AI_Panel.
2. THE Quote_Card SHALL truncate the selected text with an ellipsis when it exceeds the available width, keeping the display to one line only.
3. THE Quote_Card SHALL include a dismiss button on the right side, displayed as a "返回箭头" (↩ / undo arrow) icon, that removes the quote from the current conversation context.
4. WHEN the user clicks the Quote_Card dismiss button, THE Quote_Card SHALL be dismissed and the Suggestion_Buttons hidden, without closing the Side_AI_Panel.
5. THE Quote_Card SHALL display a left border accent and a subtle background color to visually distinguish it from the input area.

### Requirement 3: 智能建议按钮

**User Story:** As a learner, I want quick suggestion buttons for common questions, so that I can get AI explanations with a single click instead of typing.

#### Acceptance Criteria

1. WHEN a Quote_Card is displayed, THE Side_AI_Panel SHALL show three Suggestion_Buttons between the Quote_Card and the input area: "解释一下 →", "详细展开 →", "深入研究 →".
2. WHEN the user clicks a Suggestion_Button, THE Side_AI_Panel SHALL send a pre-composed prompt combining the quoted text and the suggestion action to the AI backend.
3. WHEN a Suggestion_Button is clicked, THE Suggestion_Buttons SHALL be hidden for the current quote context to avoid duplicate submissions.
4. THE Suggestion_Buttons SHALL be styled as pill-shaped clickable elements with hover feedback, consistent with the application design system.

### Requirement 4: 对话区域

**User Story:** As a learner, I want to have a full conversation with the AI in the side panel, so that I can ask follow-up questions about the quoted content.

#### Acceptance Criteria

1. THE Side_AI_Panel SHALL display a scrollable chat conversation area between the panel header and the bottom input section (Quote_Card + Suggestion_Buttons + input area).
2. WHEN the AI responds, THE Side_AI_Panel SHALL render the response using the existing Markdown rendering pipeline (markdown-it + KaTeX).
3. WHEN a new message is added to the conversation, THE Side_AI_Panel SHALL auto-scroll to the latest message.
4. THE Side_AI_Panel SHALL support streaming AI responses, displaying tokens incrementally as the backend sends them.
5. WHILE the AI is generating a response, THE Side_AI_Panel SHALL display a loading indicator and provide a stop/cancel button.

### Requirement 5: 输入区域

**User Story:** As a learner, I want to type follow-up questions in the side panel, so that I can continue the conversation without switching contexts.

#### Acceptance Criteria

1. THE Side_AI_Panel SHALL display a text input area at the bottom with a send button.
2. WHEN the user presses Enter (without Shift), THE Side_AI_Panel SHALL send the input message to the AI backend.
3. WHEN the user presses Shift+Enter, THE Side_AI_Panel SHALL insert a newline in the input area.
4. WHILE the AI is generating a response, THE Side_AI_Panel SHALL disable the send button and the input area.
5. IF the input area is empty, THEN THE Side_AI_Panel SHALL disable the send button.

### Requirement 6: 面板关闭与布局恢复

**User Story:** As a learner, I want to close the AI panel and return to my original reading layout, so that I can resume studying without manual layout adjustments.

#### Acceptance Criteria

1. THE Side_AI_Panel SHALL include a close button in the panel header.
2. WHEN the user closes the Side_AI_Panel, THE Layout_Manager SHALL restore the Course_Tree and Notes_Column to their previous visibility state before the panel was opened.
3. WHEN the Side_AI_Panel closes, THE Content_Area SHALL expand to fill the space previously occupied by the panel.
4. WHEN the user presses the Escape key while the Side_AI_Panel is open, THE Side_AI_Panel SHALL close.
5. WHEN the Side_AI_Panel closes, THE Side_AI_Panel SHALL apply a slide-out-to-right transition with a duration between 200ms and 300ms.

### Requirement 7: 对话上下文管理

**User Story:** As a learner, I want the AI to understand which section I'm reading when I ask a question, so that the answers are relevant to my current study context.

#### Acceptance Criteria

1. WHEN the user triggers "引用提问", THE Side_AI_Panel SHALL detect the course node that contains the selected text and include the node context in the AI request.
2. WHEN the Side_AI_Panel is already open and the user selects new text and clicks "引用提问", THE Side_AI_Panel SHALL replace the current Quote_Card with the new selection and reset the Suggestion_Buttons.
3. THE Side_AI_Panel SHALL maintain the conversation history for the current session until the user explicitly clears the chat or closes the panel.

### Requirement 8: 响应式布局适配

**User Story:** As a learner using different screen sizes, I want the AI panel to adapt to my screen, so that the experience remains usable on smaller displays.

#### Acceptance Criteria

1. WHILE the viewport width is less than 1024px, THE Side_AI_Panel SHALL display as a full-width overlay panel instead of a side panel.
2. WHILE the viewport width is 1024px or greater, THE Side_AI_Panel SHALL display as a side panel occupying approximately one-third of the viewport width.
3. WHEN the viewport is resized across the 1024px breakpoint while the Side_AI_Panel is open, THE Layout_Manager SHALL transition the panel between overlay and side-panel modes.
