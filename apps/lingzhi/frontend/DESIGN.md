---
name: 当前讲次 PPT 工作台
description: 讲义同步内容稿、编辑内容、快速渲染的安静桌面编辑器
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
    lineHeight: 1.6
rounded:
  control: "8px"
---

## Overview

仅适用于 LessonPptWorkspace.vue 及其嵌入的 PPT 内容稿与渲染区。PPT 环节继承当前讲次讲义同步生成的内容稿，不再以独立项目创建、来源选择和人工确认门作为主路径。其他页面和学生预览不重设计。

## Colors

保持浅色教师工作台语义，借用 macOS/Codex 式克制层级：浅灰工作区、白色正文纸面、紫色只用于当前选择与主要状态。

## Typography

系统字体，正文与主要操作不低于 15px。顶部讲次标题紧凑显示，内容稿正文以 17px 左右的阅读尺度承载连续讲课内容。

## Layout

复用既有左侧备课导航，并在该二级导航中切换不同讲次。主区顶部只有当前讲次标题、内容与渲染两个同级 Tab，以及右上角编辑、导出、原件审阅等轻量按钮。PPT 工作台不显示右侧栏；内容稿默认连续阅读和逐页编辑，渲染页显示横向页面选择与画布。桌面端验收，不扩展移动端。

## Elevation & Depth

浅色分隔区分导航、内容与操作。顶部用轻微模糊和底部分隔形成悬浮工具条；内容纸面使用少量圆角与细分隔，不堆叠卡片。

## Shapes

控件 8px 左右圆角，内容纸面 14px 左右圆角。圆角服务于编辑器亲和感，不把普通状态拆成多层卡片。

## Components

主操作与次操作复用 TeacherDocumentCommandBar、UiSegmentedControl 和现有图标体系。保留悬停、焦点、加载与禁用状态。未保存时保护输入；内容稿过期只在已有稿件时提示同步；旧讲义缺稿时显示补齐内容稿入口。

## Do's and Don'ts

讲义生成同步形成 PPT 内容稿；进入 PPT 环节直接编辑内容或查看渲染。渲染不重写内容。原版 PPT 审阅保留独立入口，不作为主路径。不显示历史项目入口，不显示右侧栏，不使用渐变标题、装饰图标或密集小字。
