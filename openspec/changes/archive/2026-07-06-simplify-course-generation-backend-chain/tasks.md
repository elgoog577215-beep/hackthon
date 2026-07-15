## 1. 统一课程生成入口

- [x] 1.1 将 `backend/routers/courses.py` 的 `/generate_course` 改为调用 `CourseService`
- [x] 1.2 保留原响应兼容字段 `difficulty`、`style`、`requirements`
- [x] 1.3 确认返回节点包含蓝图契约字段

## 2. 对齐子节点接口

- [x] 2.1 将 `backend/routers/nodes.py` 的 `generate_subnodes` 改为调用 `CourseService`
- [x] 2.2 保留已有“已有子节点则直接返回”的行为

## 3. 测试

- [x] 3.1 增加路由级测试，证明 `/api/generate_course` 使用统一课程服务并保存课程
- [x] 3.2 增加字段测试，证明 L2 节点保留学习目标、依赖、误区、验收和边界
- [x] 3.3 增加子节点接口测试，证明手动子节点生成也走统一服务

## 4. 验证与收束

- [x] 4.1 运行相关 pytest
- [x] 4.2 运行 Python 编译检查
- [x] 4.3 运行 OpenSpec validate
- [x] 4.4 完成后 archive change 并再次 validate
