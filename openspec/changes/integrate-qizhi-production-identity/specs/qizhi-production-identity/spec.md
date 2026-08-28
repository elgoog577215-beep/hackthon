# Qizhi Production Identity Specification

## Purpose

让启智统一登录成为灵知正式部署的唯一账号与角色 authority，同时保留灵知内部稳定 actor 合同和独立本地开发能力。

## ADDED Requirements

### Requirement: 生产请求必须由启智验证身份

启用生产身份桥接后，灵知 MUST 验证启智 bearer token，MUST NOT 信任浏览器提供的 `X-User-Id`。验证成功后 MUST 使用 `qizhi:<user-id>` 作为灵知 actor。

#### Scenario: 浏览器伪造教师身份

- **WHEN** 已登录教师请求携带伪造的 `X-User-Id`
- **THEN** 服务端 MUST 覆盖该值并使用启智验证得到的用户 ID

#### Scenario: 请求没有登录态

- **WHEN** 生产 API 请求没有有效启智 token
- **THEN** 系统 MUST 返回 401 和稳定身份错误
- **AND** MUST NOT 读取或写入课程数据

### Requirement: 新版课程必须服从启智教师角色

正式新版课程 MUST 只允许 teacher 或 admin 角色进入。学生角色 MUST 返回 403，不得通过直接访问灵知地址绕过启智入口权限。

#### Scenario: 学生直接访问新版 API

- **WHEN** 启智确认当前账号角色为 student
- **THEN** 灵知 MUST 拒绝请求

### Requirement: HTTP 与 WebSocket 必须使用同一身份

前端 HTTP、SSE 与 WebSocket MUST 使用同一个启智登录 token。WebSocket 握手失败时 MUST NOT 建立课程订阅；建立连接后，私有课程订阅和写命令 MUST 继续检查课程 owner。

#### Scenario: 外部教师订阅私有课程

- **WHEN** 已登录教师订阅不属于自己的未发布课程
- **THEN** 系统 MUST 拒绝订阅或命令
- **AND** MUST NOT 返回该课程的任务进度或内容

### Requirement: 身份故障必须可区分且可恢复

登录缺失或失效、角色不足、启智身份服务不可用 MUST 分别返回 401、403、503。健康检查 MUST 不依赖登录态，开发环境未配置身份桥接时 MUST 保持原有本地身份行为。

#### Scenario: 启智身份服务暂时不可用

- **WHEN** 灵知无法连接启智验证接口
- **THEN** 业务请求 MUST 返回 503 并提示稍后重试
- **AND** `/api/health` MUST 继续反映灵知进程自身状态
