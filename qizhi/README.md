# 启智（edu_ai_home）

启智是面向高校教师的 AI 教学助手平台，提供账号与权限、旧版课程及版本化教学资源、课堂视频分析、论文检查和运营管理，并通过同域 `/lingzhi/` 接入灵知新版课程体验。

启智与灵知统一在 [elgoog577215-beep/hackthon](https://github.com/elgoog577215-beep/hackthon) 维护。启智代码位于本目录；灵知代码位于仓库根目录。普通 `git clone` / `git pull --ff-only` 即可取得两部分代码，不再维护子模块或单独同步版本。

## 代码与文档入口

| 内容 | 位置 |
| --- | --- |
| 启智桌面端前端 | [`client/website/`](./client/website/) |
| 启智后端、身份和旧版课程资源 | [`server/`](./server/) |
| 论文检查子应用 | [`plugins/`](./plugins/) |
| 已有移动客户端源码 | [`mobile/`](./mobile/) |
| 灵知新版课程应用 | [仓库根目录](../README.md) |
| 启智对象、功能和代码地图 | [全局图](./docs/全局图.md) |
| 联合构建、身份与数据边界 | [灵知新版课程接入与部署](./docs/灵知新版课程接入与部署.md) |
| 二期需求 | [PRD](./docs/PRD_二期需求.md) |

## 本地开发

以下命令从整个仓库根目录执行。启智使用 Python 3.12+、Node.js 22+ 和 PostgreSQL；现有后端 Dockerfile 使用 Python 3.14。灵知保留自己的运行环境与依赖。

```bash
python3 -m venv qizhi/server/.venv
qizhi/server/.venv/bin/python -m pip install -r qizhi/server/requirements.txt
npm --prefix qizhi/client/website ci
cp -n qizhi/server/.env.example qizhi/server/.env
cp -n qizhi/client/website/.env.example qizhi/client/website/.env.local
```

在私有 `.env` 中填写数据库、OAuth 和模型配置后，分别启动：

```bash
./scripts/qizhi.sh dev-server  # 127.0.0.1:8010
./scripts/qizhi.sh dev-web     # localhost:5174
```

两个命令各占一个终端。灵知独立开发继续使用根目录 `./dev.sh`（前端 5173、后端 8000）。正式身份联调使用下面的同域 Compose 入口，本地分端口启动不代表已经通过正式登录和权限验收。

## 联合构建与发布

```bash
./scripts/qizhi.sh check
cp -n qizhi/deploy/.env.example qizhi/deploy/.env
# 填写部署配置；Compose 内的数据库主机应设为 db。
./scripts/qizhi.sh build
./scripts/qizhi.sh up -d
./scripts/qizhi.sh ps
```

Compose 直接从仓库根目录构建灵知。项目名仍为 `edu-ai-home`，原有 `postgres_data`、`uploads_data`、`lingzhi_data` 卷名保持不变；合仓不迁移数据库、课程 owner 或线上运行数据。服务器切换到新代码目录前，按[部署说明](./docs/灵知新版课程接入与部署.md)备份并核对环境与卷。

GitHub 的 `Qizhi Checks` 检查源码结构和两个 Web 前端构建。只修改 `qizhi/` 不触发灵知独立生产发布；启智服务器发布仍需使用经过验收的整个仓库提交。

## 导入基线

2026-09-06 从启智本地 `67d946089dd3f7f97975d610a714925a3f7dc151` 及当时的源码工作区导入，保留了已有未提交源码改动。旧 Git 历史和完整工作区快照在仓库外备份；公开仓库只导入整理后的当前源码，排除 `.env.local`、构建缓存、机器配置和重复子模块。

模型凭据、数据库地址、云服务密钥和压力测试 Token 已改为环境配置。移动客户端源码随项目保留，本次合仓没有开展移动端适配或运行验收。
