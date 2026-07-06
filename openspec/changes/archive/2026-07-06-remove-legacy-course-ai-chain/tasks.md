## 1. 删除旧课程 AI 链路

- [x] 1.1 从 `AIService` 中移除 `AICourseService` 继承和导入。
- [x] 1.2 删除无生产调用的 `ai_course_service.py` 和 `ai_course_service_v5.py`。
- [x] 1.3 更新相关注释，避免继续暗示旧文件是可用主链路。

## 2. 验证

- [x] 2.1 增加最小测试，确认 `AIService` 不再暴露旧课程生成方法，同时保留非课程 AI 方法。
- [x] 2.2 运行后端相关测试和 Python 编译检查。
- [x] 2.3 运行 OpenSpec 校验和 `git diff --check`。
