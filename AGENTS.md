# 启智统一仓库

1. **入口**：[README](README.md)说明仓库；灵知任务读取 [apps/lingzhi/AGENTS.md](apps/lingzhi/AGENTS.md)，启智门户见 [apps/qizhi/README.md](apps/qizhi/README.md)，部署见 [deploy/README.md](deploy/README.md)。
2. **应用边界**：源码入口只有 `apps/qizhi` 与 `apps/lingzhi`，各自数据和运行环境独立；不建重复源码或子模块。灵知命令从应用目录执行，仓库脚本和工作流留在根目录；身份、权限或 API 变化同时验证消费者。
3. **数据与配置**：迁移前核对运行任务、持久数据并建立可恢复备份；数据库、课程、用户数据、密钥和会话不进 Git。只用项目批准的服务，配置见应用 README。
4. **提交与发布**：只提交本任务改动，检查暂存差异后安全推送主分支；文档或构建检查提交带 `[no deploy]`，手动检查保持 `deploy=false`。构建绑定确定提交，拓途保留平铺运行目录、浙大使用联合 Compose；失败保留上一版本与数据，浙大自动激活待通道、任务保护和恢复验收后接通。推送、构建与生产验证分别报告。
