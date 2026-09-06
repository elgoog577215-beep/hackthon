# PPT 三阶段运行依赖

`ubuntu-24.04-amd64.json` 固定 Ubuntu 24.04 amd64 上的 LibreOffice、Poppler 安装包版本、官方路径和 SHA-256，以及项目中文字体摘要。Python 库版本由 `backend/requirements.txt` 固定。`ppt_runtime_identity.py` 同时记录实际 Python、Pillow/FreeType、字体和原生工具身份，确认稿导出时必须匹配。

只读检查：

```sh
python3 scripts/provision_ppt_runtime.py
```

显式安装（仅在目标平台，需 root）：

```sh
sudo python3 scripts/provision_ppt_runtime.py --install
```

安装器下载官方安装包、核对摘要再安装，并把项目字体安装到系统字体目录。平台、版本或摘要不符即失败，不自动接受替代版本；脚本不启动或重启服务。普通发布脚本不调用此安装器，生产安装应安排在独立的运行依赖变更中。

安装后，用项目虚拟环境运行 `scripts/ppt_template_tool.py certify` 对实际填充样本做原生回读和全页渲染。只有在相同运行环境中完成认证，才能用 `--publish` 写入当前模板认证及不可变版本。个人原生模板使用 `certify-native`，带图片样本时显式传 `--asset-repository`；人工校对绑定后通过 `register-native --reviewed --publish` 进入原模板仓库。

独立工作流 `ppt-three-stage-validation.yml` 已在 Ubuntu 24.04 验证安装、测试与真实渲染。CI 产物是合成认证证据，不能替代生产安装、真实课程和教师评阅。`PPT_THREE_STAGE_ENABLED` 默认关闭；关闭入口仍保留已有稿件的读取与导出，但不会放宽其已冻结的工具、字体、模板和来源检查。

当前公式输出为可编辑符号文字，保留原 LaTeX 与引用范围；不是 Office 原生公式对象。数据图表当前只支持 2—6 个同单位非负小数的横向条形图，导出为原生文字和形状；不支持混合单位、负值、对数轴或隐式统计计算。缩放/旋转组合对象、跨组和表格单元格端点连接器仍明确拒绝。
