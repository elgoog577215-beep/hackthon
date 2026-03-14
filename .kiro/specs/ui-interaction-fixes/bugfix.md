# Bugfix Requirements Document

## Introduction

本文档涵盖 5 个 UI 交互缺陷的修复需求。这些缺陷影响了 AI 助手的可访问性、布局调节、UI 元素冲突、文字格式化操作以及知识图谱导航的准确性。

---

## Bug 1: AI 助手图标缺失

### Bug Analysis

#### Current Behavior (Defect)

1.1 WHEN 用户没有选取文字时 THEN 系统不显示任何 AI 助手入口图标，用户无法主动发起 AI 提问

1.2 WHEN 用户没有选取文字时 THEN `SideAIPanel` 只能通过文字选取后的 `quote-ask` 事件打开，右下角没有浮动 AI 助手按钮

#### Expected Behavior (Correct)

2.1 WHEN 用户没有选取文字时 THEN 系统 SHALL 在内容区域右下角显示一个浮动的 AI 助手图标按钮

2.2 WHEN 用户点击浮动 AI 助手图标时 THEN 系统 SHALL 打开 `SideAIPanel`，显示与选取文字后相同的界面与功能（但无引用卡片）

#### Unchanged Behavior (Regression Prevention)

3.1 WHEN 用户选取文字后点击"提问"按钮时 THEN 系统 SHALL CONTINUE TO 打开 `SideAIPanel` 并显示引用卡片和建议按钮

3.2 WHEN `SideAIPanel` 已经打开时 THEN 浮动 AI 助手图标 SHALL 隐藏，避免重复入口

---

## Bug 2: 左侧目录占比过大且边界不可调节

### Bug Analysis

#### Current Behavior (Defect)

1.3 WHEN 页面加载时 THEN 左侧目录默认宽度为 300px，占比偏大

1.4 WHEN 用户尝试拖动目录与正文之间的分隔条调节宽度时 THEN 分隔条的拖拽交互区域过窄（仅 1px 宽的 `w-1` div），实际难以抓取和拖动

#### Expected Behavior (Correct)

2.3 WHEN 页面加载时 THEN 左侧目录默认宽度 SHALL 缩小为当前的约六分之五（即约 250px）

2.4 WHEN 用户拖动目录与正文之间的分隔条时 THEN 分隔条 SHALL 具有足够的可交互区域，能够正常拖拽调节左侧目录宽度

#### Unchanged Behavior (Regression Prevention)

3.3 WHEN 用户双击分隔条时 THEN 系统 SHALL CONTINUE TO 重置左侧目录宽度为默认值

3.4 WHEN 在移动端（屏幕宽度 < 768px）时 THEN 左侧目录 SHALL CONTINUE TO 以覆盖层模式显示，不受桌面端宽度调整影响

---

## Bug 3: "回到顶部"按钮与 AI 助手面板 UI 冲突

### Bug Analysis

#### Current Behavior (Defect)

1.5 WHEN `SideAIPanel` 打开时 THEN "回到顶部"按钮使用 `position: fixed` 定位在视口右侧，与 AI 助手面板区域重叠遮挡

1.6 WHEN 笔记面板折叠且 `SideAIPanel` 打开时 THEN "回到顶部"按钮的 CSS 媒体查询仅考虑了笔记面板的偏移（`right: 300px`），未考虑 AI 助手面板

#### Expected Behavior (Correct)

2.5 WHEN `SideAIPanel` 打开时 THEN "回到顶部"按钮 SHALL 定位在正文内容区域的右下角，不与 AI 助手面板重叠

2.6 WHEN `SideAIPanel` 关闭时 THEN "回到顶部"按钮 SHALL 恢复到正常位置（考虑笔记面板偏移）

#### Unchanged Behavior (Regression Prevention)

3.5 WHEN 滚动距离超过 500px 时 THEN "回到顶部"按钮 SHALL CONTINUE TO 正常显示

3.6 WHEN 点击"回到顶部"按钮时 THEN 系统 SHALL CONTINUE TO 平滑滚动到内容顶部

---

## Bug 4: 文字格式化操作无法取消

### Bug Analysis

#### Current Behavior (Defect)

1.7 WHEN 用户选取已有加粗/下划线/波浪线格式的文字并再次点击相同格式按钮时 THEN 系统创建一个新的重复格式笔记，而不是取消已有格式

1.8 WHEN `applyFormat` 被调用时 THEN 函数始终创建新的 `sourceType: 'format'` 笔记，不检查选区内是否已存在相同格式

#### Expected Behavior (Correct)

2.7 WHEN 用户选取已有某种格式（加粗/下划线/波浪线）的文字并再次点击相同格式按钮时 THEN 系统 SHALL 移除该格式（toggle 行为），删除对应的格式笔记并移除 DOM 高亮

2.8 WHEN 用户选取没有格式的文字并点击格式按钮时 THEN 系统 SHALL CONTINUE TO 正常应用格式（创建格式笔记）

#### Unchanged Behavior (Regression Prevention)

3.7 WHEN 用户对文字应用高亮颜色时 THEN 系统 SHALL CONTINUE TO 正常创建高亮笔记，高亮不受 toggle 逻辑影响

3.8 WHEN 用户删除格式笔记（通过笔记面板删除按钮）时 THEN 系统 SHALL CONTINUE TO 正常移除格式和 DOM 高亮

---

## Bug 5: 知识图谱跳转不准确

### Bug Analysis

#### Current Behavior (Defect)

1.9 WHEN 用户在知识图谱中点击"前往学习"按钮时 THEN 系统使用 `selectedNode.chapter_id` 调用 `courseStore.scrollToNode()`，但 `chapter_id` 的匹配逻辑（`ai_graph_service.py` 中的子串匹配和 fallback）可能映射到错误的课程节点

1.10 WHEN LLM 生成的知识图谱节点的 `chapter_id` 无效时 THEN 后端 fallback 逻辑使用子串匹配或直接取第一个课程节点，导致跳转到不相关的章节

#### Expected Behavior (Correct)

2.9 WHEN 用户在知识图谱中点击"前往学习"按钮时 THEN 系统 SHALL 准确跳转到与该知识点最相关的课程节点

2.10 WHEN `chapter_id` 匹配失败时 THEN 系统 SHALL 使用更精确的匹配策略（如模糊匹配评分、多级候选排序），而非简单的子串包含或 fallback 到第一个节点

#### Unchanged Behavior (Regression Prevention)

3.9 WHEN 知识图谱节点的 `chapter_id` 已经正确匹配到有效课程节点时 THEN 系统 SHALL CONTINUE TO 直接使用该 `chapter_id` 进行跳转

3.10 WHEN 用户点击知识图谱中笔记条目时 THEN 系统 SHALL CONTINUE TO 跳转到笔记所属的课程节点
