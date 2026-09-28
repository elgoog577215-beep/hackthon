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

## 团队开发参考

以下资料随仓库同步，保留历史基线及适用范围；当前产品定义仍以上述正式设计文档为准。

- [师生一体课程开发分析](apps/lingzhi/docs/研究/师生一体课程开发分析-2026-09-28/README.md)：项目关系、后端问题、实施顺序和验收要求。
- [师生课程闭环历史审计](apps/lingzhi/docs/验收/2026-07-23-师生课程闭环审计.md)：联动修改、真实差异与学习证据闭环的历史问题清单。
- [教案工作区原型](apps/lingzhi/docs/归档/教案工作区设计-2026-09-03/README.md)：静态原型与桌面截图。
- [课程与课件评测样例](apps/lingzhi/docs/评测/课程与课件样例/README.md)：可打开的课件、跨学科正文与生成质量反例。
- [PPT 模板参考](apps/lingzhi/docs/研究/PPT模板参考/README.md)：39 套模板的来源、校验值、质量判断和授权边界。
- [灵知品牌命名补丁](apps/lingzhi/docs/研究/灵知品牌命名-未采用.patch)：历史提议，尚未采用；不是当前运行代码，也不应自动套用。

教师原始资料、个人研究、内部审计及第三方模板原件保留在本机 `本地资料/`，不纳入 Git 和发布包。仓库外恢复备份也不上传。
