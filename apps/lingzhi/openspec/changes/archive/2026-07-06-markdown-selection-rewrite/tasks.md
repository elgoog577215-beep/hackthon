## 1. OpenSpec

- [x] 1.1 写清楚 Markdown 作为正文主链路、选区修改和旧 block 兼容边界
- [x] 1.2 严格校验 OpenSpec change

## 2. Backend

- [x] 2.1 增加选区修改请求/响应模型
- [x] 2.2 在 `CourseService` 增加选区修改 prompt 编排，保留学科章法和 AI Learning Context
- [x] 2.3 增加节点选区修改 API，返回候选替换文本但不直接保存
- [x] 2.4 记录 `markdown_selection_rewrite_requested` 学习事件
- [x] 2.5 保持旧节点更新、整节重写和 block 接口兼容

## 3. Frontend

- [x] 3.1 新增 Markdown 标题树解析和选区替换工具
- [x] 3.2 在课程正文中展示文档式标题父子关系和折叠控制
- [x] 3.3 支持选中文字后的轻量浮动工具条
- [x] 3.4 增加 AI 局部修改侧面板，展示选中文本、上下文、修改要求和候选结果
- [x] 3.5 用户确认后只替换原 Markdown 选区并保存完整节点正文

## 4. Tests

- [x] 4.1 测试 Markdown 标题树解析、折叠范围和选区替换
- [x] 4.2 测试后端选区修改上下文、事件记录和旧接口兼容
- [x] 4.3 跑后端 pytest、前端 vitest、构建、Python 编译、OpenSpec 校验和 `git diff --check`
