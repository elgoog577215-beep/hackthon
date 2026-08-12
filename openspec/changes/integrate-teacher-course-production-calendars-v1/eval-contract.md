# Eval Contract

## Hard Gates

1. `pytest backend/tests/test_teaching_calendar.py` 全部通过，至少覆盖成功与失败路径。
2. 课程生产页没有模拟计时器或静态任务成功状态；真实课程刷新后阶段、进度和失败信息保持一致。
3. 单课程日历保存后刷新和后端重启仍可读取；过期 `base_revision` 返回 409 且不覆盖数据。
4. 不同 `X-User-Id` 的日历互不可见；总日历只聚合当前身份记录。
5. `npm run build` 与相关 Vitest 通过；中英文 JSON 可解析且新增 key 双语齐全。
6. 真实浏览器覆盖 1440、1180、880、680 关键视口，目标页面无不可达操作、遮挡和控制台 error。
7. 原 `/workspace-concept/teacher-course-v1` 不被真实路由改动破坏；现有 PPT 路由和接口不改语义。
8. 课程卡固定进入教师课程概览；“我的课程 / 教学总日历 / 新建课程”层级正确，单课程六项导航均保留 `courseId` 和返回上下文。

## Evidence Mapping

| AC | Direct evidence |
| --- | --- |
| 真实生产状态 | API/Store fixture + 浏览器刷新前后截图/状态文本 + network/console |
| 分阶段隔断 | 浏览器依次选择大纲、教案、PPT、发布并观察阻断/继续动作 |
| 日历持久化 | API 测试 + 浏览器编辑、保存、刷新回读 |
| 大纲派生不覆盖 | 后端测试 + 前端候选差异提示 |
| 总日历聚合 | 两课程 API fixture + 浏览器月/周/列表与跳转 |
| UI 一致性 | 原项目 token/组件 diff + 多视口截图 |
| 问题记录 | 当前 run `issues.md`，每条含原因、影响、状态和下一步 |

## Stop Rule

任一 Hard Gate 未通过时不得声称第一版跑通。若真实生成依赖外部模型而无法在本轮稳定完成，生产 UI 可标记为“代码与模拟后端契约通过、真实模型链未验证”，但整个目标保持未完成并记录明确阻塞。
