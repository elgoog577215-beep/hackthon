---
name: 教师 PPT 工作台
description: 选择来源、编辑确认、渲染成品的安静桌面工作区
colors:
  surface: "#ffffff"
  foreground: "#252525"
  primary: "#292929"
  secondary: "#666666"
  divider: "#e6e6e6"
  selected: "#efefef"
typography:
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif'
    fontSize: "15px"
    lineHeight: 1.5
rounded:
  control: "7px"
---

## Overview

仅适用于 PptProjectWorkspace.vue 及其嵌入的 PPT 编辑区，其他页面沿用现有体系。操作模式：教师按“选择内容 → 内容与排版 → 生成成品”完成一次制作。用户指定 macOS/Codex 风格。

## Colors

白色内容面、石墨色文字和主操作、浅灰分隔。状态色仅用于必要的错误或焦点反馈。

## Typography

系统字体，正文与主要操作 15px，主标题 26px。完整显示讲次、文件名，以字号、字重、间距建立层级。

## Layout

顶部紧凑步骤导航；选源页采用讲义多选列表与资料列表，下一步位于页尾。第二步复用逐页编辑器，第三步采用页列表与画布。不重复工作台讲次侧栏或生产右栏。桌面端验收，不扩展移动端。

## Elevation & Depth

浅色分隔区分导航、内容与操作；主体不使用装饰阴影、光效或多层卡片。

## Shapes

控件 7px 圆角，普通内容不加独立圆角容器。

## Components

主操作使用石墨色实心按钮，次操作有轻边界或分组边界。保留悬停、焦点、加载与禁用状态。未保存时保护输入；任务暂停可重试，来源过期需重新选择，最后成功成品仍可导出。

## Do's and Don'ts

讲义生成不触发 PPT 规划；第一步仅选择和上传，下一步才解析规划。教师确认后渲染不重写内容。原版 PPT 审阅保留独立入口。不使用渐变标题、装饰图标或密集小字。
