---
name: 教师 PPT 工作台
description: 选择来源、编辑确认、渲染成品的安静桌面工作区
colors:
  surface: "#ffffff"
  foreground: "var(--lz-text-primary)"
  primary: "var(--lz-brand-strong)"
  secondary: "var(--lz-text-secondary)"
  divider: "var(--lz-border)"
  selected: "var(--lz-bg-page)"
typography:
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif'
    fontSize: "15px"
    lineHeight: 1.5
rounded:
  control: "7px"
---

## Overview

仅适用于 PptProjectWorkspace.vue 及其嵌入的 PPT 编辑区。按用户最新确认，PPT 复用大纲、教案与讲义的工作台页面逻辑，不保留独立 macOS/Codex 视觉方案。其他页面和学生预览不重设计。

## Colors

直接消费现有教师工作台语义颜色，正文、主操作、分隔和状态不另设配色。

## Typography

系统字体，正文与主要操作 15px，工作区标题 24px。完整显示讲次、文件名，以字号、字重、间距建立层级。

## Layout

复用既有左侧备课导航、主区文档和右侧内容信息栏。主区选择来源或阅读编辑内容稿、查看成品；右侧使用真实 PPT 状态，承载来源、确认、生成与导出。编辑操作仍由共享 TeacherDocumentCommandBar 承载。仅独立兼容路由保留视图切换；嵌入工作台不另设步骤条。桌面端验收，不扩展移动端。

## Elevation & Depth

浅色分隔区分导航、内容与操作；主体不使用装饰阴影、光效或多层卡片。

## Shapes

控件 7px 圆角，普通内容不加独立圆角容器。

## Components

主操作与次操作复用工作台控件和样式。保留悬停、焦点、加载与禁用状态。未保存时保护输入；任务暂停可重试，来源过期需重新选择，最后成功成品仍可导出。

## Do's and Don'ts

讲义生成不触发 PPT 规划；第一步仅选择和上传，下一步才解析规划。教师确认后渲染不重写内容。原版 PPT 审阅保留独立入口。不使用渐变标题、装饰图标或密集小字。
