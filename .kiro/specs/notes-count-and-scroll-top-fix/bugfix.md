# 缺陷修复需求文档

## 简介

本文档涉及两个 UI 缺陷的修复：

1. **SmartBar 笔记数量显示错误**：底部 SmartBar 的笔记徽章将错题（`sourceType === 'wrong'`）也计入了笔记数量，导致外层显示的数字大于笔记面板内部的实际笔记数。
2. **"回到顶部"按钮定位问题**：该按钮在不同面板状态下与 AI 助手按钮位置重叠，且未随面板开关同步调整水平位置。

## 缺陷分析

### 当前行为（缺陷）

1.1 WHEN 用户同时拥有普通笔记和错题记录时 THEN SmartBar 的笔记徽章显示的数量是所有非 `format` 类型笔记的总和（包含 `user`、`ai`、`wrong` 三种类型），而非仅计算真正的笔记数量

1.2 WHEN 用户有 2 条普通笔记和 3 条错题时 THEN SmartBar 笔记徽章显示 5，但打开笔记面板后实际笔记数为 2，内外数量不一致

1.3 WHEN 右侧笔记面板关闭且页面滚动超过阈值时 THEN "回到顶部"按钮出现在右下角固定位置（`right: 1rem; bottom: 5.5rem`），遮挡内容区域，且与 AI 助手按钮（`right: 1.5rem; bottom: 5rem`）位置重叠

1.4 WHEN 右侧笔记面板打开时 THEN "回到顶部"按钮通过 CSS 媒体查询偏移到 `right: 300px/320px`，但 AI 助手按钮偏移到 `right: 340px`，两者在垂直方向上仍然重叠

1.5 WHEN 侧边 AI 面板打开时 THEN AI 助手按钮隐藏，但"回到顶部"按钮仅通过 `backToTopStyle` 偏移到 `calc(33vw + 1rem)`，未与其他浮动元素协调定位

### 期望行为（正确）

2.1 WHEN 用户同时拥有普通笔记和错题记录时 THEN SmartBar 的笔记徽章 SHALL 仅计算 `sourceType` 为 `user` 或 `ai`（或未定义）的笔记数量，排除 `wrong` 和 `format` 类型

2.2 WHEN 用户有 2 条普通笔记和 3 条错题时 THEN SmartBar 笔记徽章 SHALL 显示 2，与笔记面板内部显示的实际笔记数一致

2.3 WHEN "回到顶部"按钮可见时 THEN 该按钮 SHALL 始终定位在 AI 助手按钮的正上方，两者不重叠

2.4 WHEN 右侧笔记面板开关状态变化时 THEN "回到顶部"按钮 SHALL 与 AI 助手按钮同步调整水平位置（笔记面板关闭时靠右，打开时向左偏移）

2.5 WHEN 侧边 AI 面板打开时（AI 助手按钮隐藏）THEN "回到顶部"按钮 SHALL 偏移到 AI 面板左侧，保持不遮挡面板内容

### 不变行为（回归防护）

3.1 WHEN 用户只有普通笔记（`sourceType` 为 `user` 或 `ai`）没有错题时 THEN SmartBar 笔记徽章 SHALL CONTINUE TO 正确显示笔记数量

3.2 WHEN 错题数量变化时 THEN SmartBar 的错题徽章 SHALL CONTINUE TO 正确显示错题数量（不受笔记计数修复影响）

3.3 WHEN 页面滚动未超过阈值（scrollTop ≤ 500）时 THEN "回到顶部"按钮 SHALL CONTINUE TO 保持隐藏

3.4 WHEN 页面滚动超过阈值后点击"回到顶部"按钮时 THEN 页面 SHALL CONTINUE TO 平滑滚动到顶部

3.5 WHEN AI 助手按钮被点击时 THEN 侧边 AI 面板 SHALL CONTINUE TO 正常打开，不受按钮定位调整影响
