## 1. 文本模型路由

- [x] 1.1 在 `AIBase` 集中校验浙大 Qwen 端点与 `qwen3.8-27b`，错误配置在发起网络请求前失败
- [x] 1.2 移除 ModelScope 文本回退的客户端、切换分支与运行时遥测，保留同一自建节点内的有限重试和失败恢复
- [x] 1.3 为 Qwen3 文本角色统一设置兼容请求参数，确保结构化任务不被隐藏 thinking 拖慢

## 2. 配置与发布

- [x] 2.1 实现原子性、脱敏的 `configure_zju_qwen_provider.py`，统一写入通用与 PPT 文本角色并清理 `MODELSCOPE_*`
- [x] 2.2 更新 `deploy-lingzhi.yml`，从 GitHub Secrets 读取私有 Qwen 配置，部署前验证模型列表与真实对话
- [x] 2.3 更新 `production-diagnostics.yml`，让脱敏模型探针在其他诊断失败前独立执行
- [x] 2.4 使用私有服务器登记配置本地 `.env` 与 GitHub Secrets，不输出地址或凭据

## 3. 测试与文档

- [x] 3.1 增加提供方政策回归测试，覆盖指定端点、错误端点、错误模型、PPT 角色和无 ModelScope 网络请求
- [x] 3.2 更新配置脚本测试，验证原子更新、脱敏输出、错误输入不改文件与旧 ModelScope 字段删除
- [x] 3.3 更新 `.env.example`、`README.md`、`docs/系统架构.md`、`docs/产品状态.md`、`docs/事实.md` 和 `AGENTS.md`，写明文本提供方的长期边界与验收方法

## 4. 验证与上线

- [x] 4.1 运行相关后端测试、工作流静态检查、`git diff --check` 和严格 OpenSpec 验证
- [x] 4.2 使用本地私有配置运行真实 `qwen3.8-27b` 最小对话与有代表性灵知文本路径
- [x] 4.3 提交并推送 `origin/main`，等待生产部署，分别验证备份、回滚点、Caddy/服务健康、线上资源和真实模型路由
