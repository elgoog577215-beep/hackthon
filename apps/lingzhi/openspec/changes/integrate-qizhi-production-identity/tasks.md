# 实施任务

- [x] 新增启智 `current-user` 验证器、角色检查、短时缓存和稳定错误。
- [x] 在生产 API 中覆盖客户端 `X-User-Id`，保留健康检查和开发兼容。
- [x] 让生产前端 HTTP、SSE、usage 上报与 WebSocket 携带启智登录态。
- [x] 为 WebSocket 握手、课程订阅与写命令保留身份和课程 owner 边界。
- [x] 在启智首页新版入口前执行既有 teacher/admin 路由守卫。
- [x] 补充身份缺失、身份伪造、角色拒绝、健康检查与开发兼容测试。
- [ ] 在正式服务器备份后部署，并执行登录、课程隔离、API、WebSocket 和旧版回退验收。
