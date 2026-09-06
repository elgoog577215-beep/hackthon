## Why

课程正文目前主要保存为单个 `node_content` Markdown 字符串。它可以展示整节内容，但无法稳定支持“只重写应用部分”“折叠某个段落”“保持局部重写和整课上下文一致”等能力。

## What Changes

- 为课程节点增加 `content_blocks`，把小节正文拆成少量固定教学块。
- 保留 `node_content` 作为兼容渲染结果，由 `content_blocks` 拼接得到。
- 新增 block 级重新生成接口，由后端构造课程上下文，不再依赖前端拼接上下文。
- 前端优先展示 `content_blocks`，无 blocks 时继续展示旧 Markdown。

## Impact

- Affected backend: `models.py`, `course_service.py`, `routers/nodes.py`, new block helper.
- Affected frontend: node types, course store, `CourseNode.vue`.
- Affected tests: node API tests and block helper tests.
