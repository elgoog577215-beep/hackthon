# 启智：主平台与灵知课程应用

本仓库统一维护启智平台。`apps/qizhi` 承担门户、账号、管理和原有业务；`apps/lingzhi` 是其中的课程应用，也能独立部署到拓途服务器。两者使用同一 Git 提交，各自保留运行环境和数据。

GitHub：[elgoog577215-beep/hackthon](https://github.com/elgoog577215-beep/hackthon)，主分支 `main`。普通 `git clone` / `git pull --ff-only` 即可取得全部源码，没有子模块或嵌套仓库。

```text
hackthon/
├── apps/
│   ├── qizhi/             主平台：client/website、server、plugins
│   └── lingzhi/           课程应用：frontend、backend、shared、runner
│       ├── docs/          灵知产品、架构与状态真源
│       ├── openspec/      灵知功能合同
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

执行灵知 Python 测试、OpenSpec 和应用脚本时，工作目录为 `apps/lingzhi`。仓库结构检查从根运行：

```bash
./scripts/qizhi.sh check
./scripts/check-tracked-ignored.sh
python3 -m unittest discover -s scripts/tests -v
python3 apps/lingzhi/scripts/audit_backend_dependencies.py
```

旧本机工作区为保护运行中的进程可以保留根目录 `frontend`、`backend` 等本地符号链接；它们不进入 Git，不是另一份源码。新 clone 使用上面的正式路径。

配置、账号、密钥和运行数据留在私有环境。提交和发布只更新代码，不同步两台服务器的用户或课程数据。
