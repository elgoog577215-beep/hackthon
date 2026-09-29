# 启智：主平台与灵知课程应用

本仓库统一维护启智平台。`apps/qizhi` 承担门户、账号、管理和原有业务；`apps/lingzhi` 是其中的课程应用，也能独立部署到拓途服务器。两者使用同一 Git 提交，各自保留运行环境和数据。

GitHub：[elgoog577215-beep/hackthon](https://github.com/elgoog577215-beep/hackthon)，主分支 `main`。普通 `git clone` / `git pull --ff-only` 即可取得全部源码，没有子模块或嵌套仓库。

## 获取仓库

在准备存放项目的父目录执行：

```bash
git clone https://github.com/elgoog577215-beep/hackthon.git 启智
cd 启智
```

直接把此目录作为编辑器和 AI 工具的项目根目录；根目录包含 `.git`、`AGENTS.md`、`README.md`、`apps/`、`deploy/` 和 `scripts/`。本地目录名可自定，无需在项目目录内再嵌套一层 `hackthon/`；个人材料和备份放在仓库外。

已有仓库在根目录运行 `git pull --ff-only` 更新；存在本地改动或分叉时先处理，不覆盖其他任务的工作。


```text
启智/
├── apps/
│   ├── qizhi/             主平台：client/website、server、plugins
│   └── lingzhi/           课程应用：frontend、backend、shared、runner
│       ├── docs/          灵知产品、架构与状态真源
│       └── scripts/       灵知运行、诊断与发布工具
├── deploy/
│   ├── tuotu/            个人服务器：仅发布灵知
│   └── zju/              学校正式服务器：启智 + 灵知
├── scripts/              仓库检查、变更分流和启智启动入口
└── .github/workflows/    检查、构建与发布
```

## 开发入口

- [灵知安装与开发](apps/lingzhi/README.md)：先 `cd apps/lingzhi` 安装依赖、建立本地 `.env`；完成后也可从仓库根运行 `./dev.sh`。前端 5173，后端 8000。
- [启智安装与开发](apps/qizhi/README.md)：从根目录运行 `./scripts/qizhi.sh dev-web` / `dev-server`，分别使用 5174 / 8010。
- [发布目标和明日接通步骤](deploy/README.md)：代码变更如何进入两台服务器。
- [灵知产品状态](apps/lingzhi/docs/产品状态.md)、[灵知系统架构](apps/lingzhi/docs/系统架构.md)、[启智全局图](apps/qizhi/docs/全局图.md)。

执行灵知 Python 测试和应用脚本时，工作目录为 `apps/lingzhi`。仓库结构检查从根运行：

```bash
./scripts/qizhi.sh check
./scripts/check-tracked-ignored.sh
python3 -m unittest discover -s scripts/tests -v
python3 apps/lingzhi/scripts/audit_backend_dependencies.py
```

开发、测试和发布统一使用上述正式路径；仓库根目录不保留 `frontend`、`backend`、`qizhi` 等旧目录的迁移链接。应用脚本从各自的 `apps/` 目录执行。

配置、账号、密钥和运行数据留在私有环境。提交和发布只更新代码，不同步两台服务器的用户或课程数据。

## 项目文档

- [灵知项目文档](apps/lingzhi/docs/README.md)：当前设计、实现与状态，以及开发参考、原型、评测样例和历史证据的统一入口。
- [启智全局图](apps/qizhi/docs/全局图.md)：门户、身份、旧版资源及子应用的关系。

共享资料随仓库同步。教师原始资料、个人研究、内部审计及第三方模板原件保留在本机 `本地资料/`，不纳入 Git 和发布包；恢复备份保存在仓库外。
