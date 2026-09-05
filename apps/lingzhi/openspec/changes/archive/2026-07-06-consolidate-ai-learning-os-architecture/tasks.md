## 1. 架构扫描与规格

- [x] 1.1 扫描后端事件、状态、决策、上下文、导师、复习、学习路径和课程生成链路
- [x] 1.2 扫描前端导师卡、画像、统计、AI 助手、课程 block 操作和本地测验链路
- [x] 1.3 写清理想前后端分层和旧功能归并矩阵
- [x] 1.4 `openspec validate consolidate-ai-learning-os-architecture --strict`

## 2. 后端统一快照

- [x] 2.1 新增轻量 `learning_os.py`，组合 `LearnerState`、`TeachingDecision`、课程轨迹和旧导师信号
- [x] 2.2 新增 `/api/learning-os/snapshot` 统一读取接口
- [x] 2.3 改造 `/api/tutor/learning-state` 为快照兼容包装，保持旧字段
- [x] 2.4 扩展 `RecordLearningRequest` 兼容 `course_id`，让测验结果可进入课程级事件

## 3. 前端收敛

- [x] 3.1 `learning-insights` 优先读取后端快照洞察，保留旧 state/decision 兼容
- [x] 3.2 测验提交后调用导师学习记录接口，回写答题结果事件
- [x] 3.3 修复节点扩展响应字段兼容
- [x] 3.4 保持导师卡、画像、统计、AI 助手的分层展示，不新增重复 UI

## 4. 测试与文档

- [x] 4.1 增加后端快照聚合测试
- [x] 4.2 更新导师学习状态接口兼容测试
- [x] 4.3 更新前端学习洞察测试
- [x] 4.4 更新架构文档说明统一主链路和旧功能归并策略

## 5. 验证

- [x] 5.1 运行相关后端 pytest
- [x] 5.2 运行相关前端测试
- [x] 5.3 运行 Python 编译检查
- [x] 5.4 运行 OpenSpec 校验
- [x] 5.5 运行 `git diff --check`
