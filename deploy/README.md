# 发布目标与代码分流

## 服务器登记

| 登记名 | 名称与归属 | 本仓库部署内容 |
| --- | --- | --- |
| `tuotu` | 拓途服务器，个人服务器 | 灵知；入口 `https://tuotuzju.com/lingzhi/`，拓途主站独立维护 |
| `zju` | 浙大正式服务器，学校服务器 | 启智主平台与同域 `/lingzhi/` 课程应用 |
| `zju-dev` | 浙大开发服务器，学校提供 | 备用开发环境，不作为必须经过的发布阶段 |
| `qwen` | 千问服务器 | 只提供模型服务，不随本仓库发布 |

学校网关 `zju-atrust-idc` 是访问通道。具体地址、账号和认证方式仅存于本机私有服务器登记；学校网站域名以接通后现场核验为准。

## 推送后会发生什么

`main` 上每次提交由 `scripts/release_targets.py` 计算目标，CI 先检查再构建。删除、重命名也计入变更。文档变更不发布应用。

| 更新范围 | 拓途 | 浙大 |
| --- | --- | --- |
| 启智门户前端 | 无发布 | `website` |
| 启智后端、身份、API 或插件 | 无发布 | 联合验证 `server`、`website`、`lingzhi` |
| 灵知课程代码 | 灵知独立实例 | `lingzhi` |
| 共享构建工具 | 灵知 | 主平台与灵知 |
| 仅 Markdown / 产品文档 | 无发布 | 无发布 |

浙大的清单给出受影响服务，发布包始终携带同一提交的完整应用构建上下文，因此身份和调用方可以一起恢复。论文检查源码随仓库保存，现有联合 Compose 通过外部论文服务代理接入；该外部服务尚不在本次自动激活范围。

## 拓途：构建与既有自动发布

`Deploy Lingzhi to Tuotu` 复用 `Lingzhi Checks`，通过后构建 `lingzhi-release-<SHA>`。发布包从 `apps/lingzhi` 子树生成，服务器解包后仍是 `backend/`、`frontend/`、`shared/` 等平铺结构，保持 `/opt/lingzhi`、原 systemd 服务和数据路径兼容。

独立构建固定 `VITE_BASE_PATH=/lingzhi/`、`VITE_API_BASE_URL=/lingzhi`、`VITE_QIZHI_AUTH_REQUIRED=false`。生产路由仍只涉及 `/lingzhi/*`。后端运行配置由拓途私有环境提供。

```bash
./deploy/tuotu/build.sh /tmp/lingzhi-release.tgz
```

正常 `main` 代码推送沿用已有自动发布。仅检查构建时，提交信息包含 `[no deploy]`，或手动运行工作流保持 `deploy=false`；这两种情况下生成产物，但全部 SSH、模型探测和服务器激活步骤跳过。PR 只检查。回滚沿用已有 `github-action-restore.sh` 和上一版本，失败不删除持久数据。

## 浙大：仓库侧准备

`ZJU Release Package` 自动运行启智和灵知检查，另行验证开启正式启智认证的灵知前端构建。随后生成 `zju-source-<SHA>`，内含确定提交的源码、Compose、`release.json` 服务清单和 SHA-256 校验文件。它是供服务器 Docker 构建的源码包，不是已启动的容器或已验收的生产镜像。

```bash
python3 deploy/zju/build.py --commit HEAD --output /tmp/zju-source.tgz
./scripts/qizhi.sh check
```

联合 Compose 位于 `deploy/zju/docker-compose.yml`。启智从 `apps/qizhi` 构建，灵知从 `apps/lingzhi` 构建，启用 `VITE_QIZHI_AUTH_REQUIRED=true`。项目名 `edu-ai-home` 和三个原有数据卷名均保留。

当前工作流只构建产物，不连接学校、不读取学校部署凭据、不激活服务器。当前没有学校网络内的无人值守 runner；手动 H2/aTrust 登录也不等于 GitHub 已经能自动发布。

明日接通依赖如下：

1. 登录学校访问通道，核验 `zju` 当前版本、域名、私有环境、数据卷及运行中任务。
2. 备份并确认恢复方式，在独立发布目录准备本次已通过检查的提交，核对旧卷和现有数据库配置；执行 `scripts/qizhi.sh build` 前保留原运行目录。
3. 在允许切换的时间发布并验收登录、权限、课程、静态资源、SSE/WebSocket 与真实模型调用；恢复演练通过后确定自动激活方案。
4. 接入学校网络中的 runner 或服务器主动拉取通道，再把现有产物和服务清单连接到自动激活步骤。此项需要学校现场，今天没有宣称完成。

Git 推送不迁移用户、课程或数据库，服务器切换也不改写课程 owner。千问模型服务、拓途主站和学校开发服务器均不随这些应用包更新。
