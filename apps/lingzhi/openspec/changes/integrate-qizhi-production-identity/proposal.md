# 变更：接入启智生产身份

## Why

灵知目前使用浏览器提供的 `X-User-Id` 作为本地身份边界，它不是登录鉴权。启智正式环境已经由浙大 OAuth、JWT 与角色权限管理用户；若直接把灵知挂到“我的课程”，浏览器可以伪造教师身份，无法满足正式环境的课程隔离要求。

## What Changes

1. 灵知生产构建读取同域启智登录 token，并在 HTTP 与 WebSocket 请求中携带该 token。
2. 灵知后端通过启智 `current-user` 接口验证 token 和教师/管理员角色，不复制 JWT 密钥。
3. 验证成功后由服务端覆盖浏览器的 `X-User-Id`，统一映射为 `qizhi:<user-id>`。
4. 未登录、登录失效、非教师角色和身份服务不可用分别返回稳定错误；健康检查保持独立可用。
5. 未配置身份验证地址的本地开发环境保持原有运行方式。

## Capabilities

### New Capabilities

- `qizhi-production-identity`：定义启智登录态成为灵知生产身份 authority 的验证、映射、角色、失败和开发兼容合同。

## Impact

- 后端：新增启智身份验证中间件；WebSocket 握手要求同一登录态。
- 前端：生产请求自动携带启智 token；无登录态时返回启智登录页。
- 部署：灵知容器通过内部地址调用启智 `current-user`，不新增公开端口或共享密钥。
