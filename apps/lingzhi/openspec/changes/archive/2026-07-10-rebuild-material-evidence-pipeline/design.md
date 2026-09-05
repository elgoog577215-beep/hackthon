## Context

课程生成 V2 已经把入口、任务、教学画像、难度契约、蓝图、正文和质量报告统一到 `CourseService + TaskManager + GenerationJob`。当前资料层仍是过渡实现：浏览器只读取文本文件，PDF/PPT 只提交文件名；后端把文本内嵌在请求和课程 JSON 中，再通过正则构造 `MaterialDigest`。节点未经过证据选择就默认引用核心资料，最终报告也只能检查资料 ID 是否出现。

生产容器是 Python 3.10 slim，本地虚拟环境目前是 Python 3.14。解析能力必须通过项目自有适配器隔离，默认链路不能依赖未固定的模型缓存、外部网络或进程内状态。上传文件属于用户资产，不能进入静态目录或 Git 自动同步。

## Goals / Non-Goals

**Goals:**

- 建立真实文件上传、独立持久化、哈希去重和安全校验。
- 建立解析器无关、可保留页码/幻灯片/区块位置的 `ParsedDocument`。
- 将资料编译为有原文来源、用途和权威边界的 `EvidenceUnit`。
- 先形成证据覆盖计划，再生成课程蓝图和节点正文。
- 让资料解析、证据编译和接地质量进入同一个可恢复 GenerationJob。
- 让用户在前端看见上传、解析、降级、覆盖、冲突、缺口和未使用资料。
- 保持无资料生成、旧课程读取和旧内联文本请求的诚实降级。

**Non-Goals:**

- 不新增默认联网搜索、网页抓取或自动下载资料。
- 不引入第二个用户可见任务系统、Celery、Redis 或新的课程生成服务。
- 不在第一版引入向量数据库；先用文档层级、关键词候选和模型重排完成证据选择。
- 不保证一次性解决所有扫描件、手写稿、复杂嵌套表格和图片语义理解。
- 不把资料中心扩展成通用网盘或权限管理产品。

## Decisions

### 1. 资产、绑定、解析文档和证据分层

核心对象固定为四类：

- `MaterialAsset`：文件事实。包含 `asset_id`、原始文件名、安全文件名、MIME、扩展名、字节数、SHA-256、存储路径、上传时间和状态。
- `MaterialBinding`：本次课程怎样使用资产。包含 `asset_id`、`purpose`、`priority`、`authority`、`usage_policy` 和用户说明。
- `ParsedDocument`：解析器无关文档。包含文档版本、解析器、解析器版本、区块、层级、页/幻灯片、坐标、表格、公式、图片占位和解析质量。
- `EvidenceUnit`：可引用证据。包含不可改写的 `source_text`、类型、摘要、关键词、来源区块、定位、置信度、资料绑定和内容哈希。

课程和任务只保存资产/证据引用与小型报告。原文件、完整解析文档和完整证据目录保存在 `backend/data/materials/{asset_id}/`，避免课程 JSON 和 `tasks.json` 膨胀。

替代方案是继续把文本写入课程 JSON。该方案无法承载二进制文件、缓存、版本和来源定位，予以否决。

### 2. 独立上传接口，不创建第二任务

新增 `POST /api/materials` multipart 接口，只负责校验、流式写盘、计算哈希和返回资产，不做长时间解析。前端在创建课程前上传文件，再把 `material_bindings` 交给现有 `/api/course-generation/generate`。

解析发生在 GenerationJob 的 `material_processing` 阶段。上传状态是表单 I/O 状态，不是另一个后台任务。未绑定资产记录上传批次和过期时间，后续可清理孤儿文件。

### 3. Docling 轻量格式后端与诚实降级

项目定义 `DocumentParser` 协议和统一错误类型。默认适配器直接使用 Docling 的 PDF/Office 格式后端，避免统一 `DocumentConverter` 导入 Torch 模型链；DOCX/PPTX/XLSX 转为统一 DoclingDocument，PDF 从文本层提取并保留页码。MarkItDown 只作为降级提取器；降级结果必须标记 `degraded`，不得声称具有页级或布局级完整来源。

文本/Markdown 使用内置解析器，Docling 通过固定依赖和延迟导入启用。第一版不安装 Torch/OCR 模型链；图片型 PDF 没有文本层时必须失败并提示需要 OCR。生产镜像在 Python 3.10 下单独安装并运行解析集成测试。MinerU 仅保留未来外部适配器接口，Unstructured 和 Marker 不进入默认依赖。

### 4. 原文不可由模型创造

区块切分和证据原文来自解析器输出。模型可以为证据分类、生成摘要、关键词和标准化陈述，但 `source_text`、`block_ids`、`locator` 和 `content_hash` 只能由确定性代码产生。模型返回不存在的区块或改写后的“原文”时必须拒绝。

### 5. 资料用途与权威分开

`purpose` 表示用途：`content_source/style_reference/question_source/supplement/weak_context`。

`authority` 表示事实可信级别：`primary/secondary/context_only`。

`usage_policy` 表示强制程度：`must_use/prefer/optional/style_only`。

`style_reference` 和 `style_only` 只能生成抽象风格画像，不能进入事实证据包；`weak_context` 不能支撑需要引用的事实。发生冲突时先比较 authority，再比较用户 priority 和资料版本；无法解决时形成 `EvidenceConflict`，不得静默择一。

### 6. 两阶段蓝图

在现有课程蓝图之前新增 `EvidenceCoveragePlan`：

1. 根据 brief、教学画像、难度契约和证据目录形成课程学习目标与必讲主题。
2. 为每个目标选择 `required_evidence_ids` 和 `optional_evidence_ids`，并记录缺口、冲突和通用知识许可。
3. 再由现有 prompt 编排器生成 CourseBlueprint，并把证据选择编译为每个节点的 `NodeGroundingContract`。

模型只从给定证据目录选择 ID；后端确定性校验 ID、用途、权威和节点覆盖。删除 `_default_material_refs` 式全节点广播。

### 7. 正文来源标记和接地检查

节点 prompt 只接收自己的 grounding contract 与紧凑证据包。资料事实使用稳定标记 `[[evidence:<id>]]`；生成完成后，后端提取标记并保存 `grounding_annotations`，展示层把它渲染为可读来源，不把内部 ID 当正文内容展示。

质量检查分为：引用 ID 有效性、必用证据覆盖、证据与相邻陈述一致性、style-only 越权、冲突处理和允许通用知识边界。确定性问题直接修正；语义问题最多进行一次定向节点修复，不整课重生。

### 8. 进度与恢复

`progress` 表示全局 0-100，`phase_progress` 表示当前阶段 0-100，二者不再共用同一个数。`phase_detail` 保存当前 asset、文件序号、文件总数、页数、状态和警告。仍通过现有 `progress_update` WebSocket 事件和 HTTP 轮询传递。

资产以 `sha256 + parser_name + parser_version + parse_options_hash` 作为缓存键。服务重启后，`parsed` 直接复用，遗留 `parsing` 重置为 `pending`，已生成 EvidenceUnit 不重复生成。修改资料绑定只失效证据覆盖及其下游，不重复解析原文件。

### 9. 文件安全与存储边界

- 文件名只作显示，磁盘文件使用资产 ID；禁止路径穿越。
- 校验扩展名、声明 MIME、探测 MIME 和大小；默认拒绝宏文件和不支持的压缩格式。
- 文件写入临时路径并原子替换，设置单文件、单批次和 Office 解压上限。
- 原文件不挂载到 `/assets`，资料目录加入 `.gitignore`，API 不接受任意本地路径或远程 URL。
- 删除资产前检查课程绑定；第一版只允许删除未绑定资产。

## Risks / Trade-offs

- [Docling 完整模型链较重] → 只安装 `docling-slim` 的转换核心与 PDF/Office 格式后端，不安装 Torch 模型链；延迟导入并用 Python 3.10 容器验证。
- [扫描 PDF 解析质量不稳定] → 显示解析质量，允许降级或失败，不把空 OCR 当已解析；后续用真实样本评估 RapidOCR/MinerU。
- [来源标记影响正文流畅度] → 内部保存稳定标记，前端渲染为来源入口，质量修复只处理缺失或越权引用。
- [证据目录过大] → 按文档层级先选章节/区块，再加载证据正文；第一版不把全部原文塞进 prompt。
- [旧课程字段与新契约混杂] → 新写入升级为 `course_generation_v3`；旧 digest 和 material_refs 不再进入生产，旧元数据只读并标记 `legacy_unverified`。
- [本地 3.14 与生产 3.10 漂移] → 解析器验收以 Docker Python 3.10 为准，普通单元测试继续使用适配器 fake。

## Migration Plan

1. 新增契约、资产存储和上传接口，保持旧 JSON `materials` 可读。
2. 接入内置文本解析器和 Docling 适配器，增加资产缓存与检查点。
3. 新增证据编译、覆盖计划和节点 grounding contract；新课程写 V3。
4. 切换 prompt、质量报告和前端到 V3 字段。
5. 旧内联正文请求在任务创建时迁移为真实资产；旧课程 card/digest 只读，不转成事实证据。
6. 验证新前后端和旧课程后，删除生产链中的内联 digest、默认资料引用和旧覆盖统计。
7. 归档 OpenSpec，并再次运行全量规范、后端、前端和 Docker 解析 smoke。

回滚时可关闭 V3 上传入口并继续无资料生成；已写入的资料资产独立存在，不影响旧课程读取。不得通过恢复旧默认引用逻辑回滚。

## Open Questions

- 当前没有真实教材、课件和扫描试卷样本，第一轮只能用合成文档验证结构正确性；解析质量阈值需要在用户提供真实资料后校准。
- 默认单文件和单批次大小先采用保守配置，后续根据部署磁盘与课程规模调整。
