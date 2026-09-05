## 1. 课程上下文账本

- [x] 1.1 扩展 `course_context.py`，支持从课程蓝图初始化章节/小节元数据
- [x] 1.2 在 `CourseService.generate_course` 创建账本
- [x] 1.3 在正文生成时注入账本上下文
- [x] 1.4 正文生成完成后更新节点摘要和概念索引

## 2. 依赖感知调度

- [x] 2.1 将 prompt 生成的依赖字段写入节点
- [x] 2.2 调度器按依赖满足情况分批生成
- [x] 2.3 死锁或无效依赖时安全退化

## 3. 流式 final 事件

- [x] 3.1 WebSocket 新增 `node_finalized`
- [x] 3.2 后端在最终内容确定后推送 final 内容
- [x] 3.3 前端 store 消费 final 内容并覆盖草稿

## 4. Prompt 与问答事件流

- [x] 4.1 大纲 prompt 增加依赖、误区、验收标准、边界字段
- [x] 4.2 正文 prompt 使用课程账本上下文并约束重复/提前展开
- [x] 4.3 新增 `/api/ask_events`，把回答与 metadata 拆成事件帧

## 5. 验证

- [x] 5.1 增加最小后端测试
- [x] 5.2 运行相关 pytest
- [x] 5.3 运行 OpenSpec validate
