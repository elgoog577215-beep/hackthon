## 设计原则

本次只做链路合并，不做平台重构。

统一后的课程生成主链路为：

```text
/api/generate_course
→ CourseService.generate_course
→ prompt_engine_v5 生成课程蓝图
→ CourseContextManager.create_from_plan
→ 返回蓝图契约节点
→ /api/courses/{course_id}/auto_generate
→ TaskManager._schedule_nodes
→ CourseService.generate_node_content_stream
→ node_finalized
```

## 接口对齐

### `/api/generate_course`

路由层保留原请求模型和响应字段，但内部改用 `get_course_service()`。

字段映射：

- `keyword` → `topic`
- `difficulty` → `depth`
- `requirements` → 课程元数据，暂不塞进 prompt 链路
- `style` → 课程元数据，暂不塞进 prompt 链路

`style` 不强行接入新版 `CourseService`，因为新版 prompt 使用的是学科、难度、受众三轴。为了小而美，本次先不增加第四套风格分支。

### 手动子节点接口

`/api/courses/{course_id}/nodes/{node_id}/subnodes` 改用 `CourseService.generate_sub_nodes`，与后台任务保持同一服务来源。

## 兼容边界

- 旧 `AIService` 继续服务 quiz、问答、图谱、学习路径、画像等接口。
- 不删除 `ai_course_service.py`。
- 不修改前端请求路径。
- 不引入新依赖。

## 风险与处理

- 风险：旧课程节点使用 UUID，新课程节点使用 `L1/L2` 稳定 ID。
  - 处理：只保证新生成课程使用统一链路，旧课程通过现有兜底逻辑继续可读可生成。
- 风险：`requirements` 暂不影响新版 prompt。
  - 处理：先保留元数据；如果用户确实依赖自定义要求，再把它作为 `custom_instruction` 接入正文或蓝图 prompt。
