# 设计：启智生产身份桥接

## 决策

启智继续拥有登录、账号与角色真源；灵知只接收已经验证的稳定 actor。生产请求不信任浏览器给出的 `X-User-Id`，而是把 `Authorization: Bearer <token>` 发送到启智内部 `GET /user/current` 验证，取得用户 ID 和角色后注入 `qizhi:<user-id>`。

身份验证结果短时缓存，缓存键为 token 哈希，不保存明文 token。启智返回未登录时灵知返回 401，角色不是 teacher/admin 时返回 403，启智身份服务不可用时返回 503。`/api/health` 不依赖身份服务，避免把登录故障误报为进程故障。

浏览器 WebSocket 不能设置 Authorization header，因此 token 通过 WebSocket subprotocol 请求头传输；服务端只回显固定协议名，不回显 token。握手验证通过后仍按课程 owner 检查订阅和写命令。

## 开发兼容

只有配置 `QIZHI_AUTH_VERIFY_URL` 时启用生产门禁。独立本地开发和测试不配置该变量，继续使用既有本地身份，不改变灵知单仓启动方式。

## 数据边界

新建生产课程 owner 使用 `qizhi:<user-id>`。历史本地共享 actor 的课程不会自动归给任意正式账号；若以后迁移历史课程，必须另行建立显式、可审计的 owner 映射。
