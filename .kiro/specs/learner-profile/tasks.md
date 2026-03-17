# Tasks

- [x] 1. 后端 AI 服务和路由
  - [x] 1.1 在 `backend/prompts.py` 添加 GENERATE_LEARNER_PROFILE 和 GENERATE_AGENT_COMMENTARY prompt 模板
  - [x] 1.2 在 `backend/models.py` 添加 GenerateProfileRequest 和 ProfileResponse 模型
  - [x] 1.3 新建 `backend/ai_profile_service.py`（继承 AIBase，3 个方法）
  - [x] 1.4 修改 `backend/ai_service.py` 添加 AIProfileService 到继承链
  - [x] 1.5 新建 `backend/routers/profile.py`（POST /api/profile/generate 端点）
  - [x] 1.6 修改 `backend/main.py` 注册 profile 路由
- [x] 2. 前端 Profile Store
  - [x] 2.1 新建 `frontend/src/stores/profile.ts`（状态、actions、localStorage 持久化、防抖队列）
- [x] 3. 前端 LearnerProfile 组件
  - [x] 3.1 新建 `frontend/src/components/LearnerProfile.vue`（画像展示、自评输入、重新生成）
  - [x] 3.2 修改 `frontend/src/components/SideAIPanel.vue` 底部嵌入 LearnerProfile 组件
- [x] 4. 增量自动更新
  - [x] 4.1 在 LearnerProfile.vue 中设置 watch 监听错题/笔记/聊天变化触发增量更新
- [x] 5. Prompt 上下文注入
  - [x] 5.1 修改 `frontend/src/stores/course.ts` 添加 effectivePersona 并替换所有 userPersona 引用
