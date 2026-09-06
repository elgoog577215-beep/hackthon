## Why

当前课程生成虽然已经拥有唯一 `GenerationJob`、资料卡、资料摘要和资料覆盖报告，但 PDF/PPT 并未真正上传，纯文本仍内嵌在生成请求中，资料摘要依赖正则提取，节点又会默认引用同一批资料。因此系统无法证明课程正文实际使用了哪些资料，也无法在重启、冲突、解析失败和局部再生成时恢复可信证据链。

课程生成的学科和难度契约已经稳定，现在需要把资料层升级为真实、可定位、可缓存和可验证的生产输入，让后续蓝图、正文和质量闸门都建立在同一份证据真源上。

## What Changes

- 新增真实资料上传与独立资产存储，保存文件哈希、MIME、大小、版本和解析状态；课程请求只保存资料绑定引用，不再内嵌完整文件文本。
- 建立解析器无关的 `ParsedDocument`，通过项目自有适配器接入成熟文档解析器，并保存标题、段落、表格、公式、图片和页码/幻灯片等来源位置。
- 建立不可伪造来源文本的 `EvidenceUnit`，把资料用途、权威等级、优先级和使用策略编译为课程级证据目录。
- 在课程蓝图之前生成 `EvidenceCoveragePlan`，将学习目标、节点和证据映射起来；删除给所有节点默认挂载同一批资料的逻辑。
- 节点正文读取 `NodeGroundingContract` 和限定证据包，输出可解析来源标记；质量闸门检查引用有效性、证据覆盖、冲突、缺口和未支持陈述。
- 继续使用唯一 `GenerationJob`。资料解析、证据编译、蓝图、正文、检查和保存全部作为同一任务的阶段与检查点，不新增第二套用户任务。
- 前端展示真实上传、逐文件解析进度、降级/失败状态、资料用途和最终覆盖报告，不再宣称尚未实现的 PDF/PPT 支持。
- **BREAKING**：新前端改用 `material_bindings` 引用已上传资产；旧 `materials[].content` 只通过兼容适配器读取，新课程不再写入该字段。
- **BREAKING**：新课程不再以 `material_digests` 和 `material_refs` 作为资料使用真源；旧字段仅供旧课程读取兼容。

## Capabilities

### New Capabilities

- `material-evidence-pipeline`: 定义资料上传、资产存储、统一解析、证据单元、冲突/缺口处理、来源定位和解析降级行为。

### Modified Capabilities

- `ai-generation-control`: 将课程蓝图、节点正文、质量闸门、进度和恢复升级为证据接地的课程生成 V3，同时继续使用唯一 GenerationJob。

## Impact

- 后端：`models.py`、课程与资料路由、`CourseService`、`TaskManager`、`course_generation_workflow.py`、prompt 编排、质量检查、文件存储和依赖配置。
- 前端：课程创建资料区、资料上传状态、GenerationJob 阶段详情、最终质量/覆盖报告和中英文文案。
- 数据：新增 `backend/data/materials/` 资产目录和 V3 资料契约；旧课程通过读取适配器降级为 `legacy_unverified`。
- 依赖：默认使用 Docling 适配器；MarkItDown 只作为无来源坐标的降级提取器。高资源 OCR 和 MinerU 保留为可选适配器，不进入默认核心链路。
- 部署：解析器必须在生产 Python 3.10 容器验证，上传资料目录不得进入 Git 自动同步或静态资源目录。
