## 1. 契约与存储

- [x] 1.1 新增 MaterialAsset、MaterialBinding、ParsedDocument、DocumentBlock、EvidenceUnit 与覆盖/接地报告契约
- [x] 1.2 新增资料资产仓库，完成原子文件写入、manifest、解析产物、证据产物和哈希缓存
- [x] 1.3 将资料目录排除出 Git 与静态资源，并增加文件类型、大小和路径安全限制
- [x] 1.4 将旧 `materials[].content` 迁移为真实资产，旧 card/digest 仅作只读元数据

## 2. 上传与解析

- [x] 2.1 新增 multipart 资料上传、查询和未绑定资料删除接口
- [x] 2.2 实现内置文本/Markdown 解析器和统一 DocumentParser 协议
- [x] 2.3 实现延迟导入的 Docling 轻量格式后端与 MarkItDown 降级状态
- [x] 2.4 为解析缓存、失败、降级和重启恢复补充后端测试

## 3. 证据编译与课程蓝图

- [x] 3.1 从 ParsedDocument 确定性构建带来源定位的 EvidenceUnit
- [x] 3.2 编译资料用途、权威、优先级、must-use、冲突和覆盖缺口
- [x] 3.3 生成 EvidenceCoveragePlan 并将 NodeGroundingContract 写入课程蓝图与节点
- [x] 3.4 删除新生产链中的全节点默认资料引用和 source-level 伪覆盖逻辑

## 4. 正文接地与质量闸门

- [x] 4.1 将节点 grounding contract 和限定证据包接入唯一 prompt 编排器
- [x] 4.2 提取 `[[evidence:<id>]]` 标记并保存 grounding annotations
- [x] 4.3 增加资料解析、证据覆盖、引用有效性、越权和未使用资料质量检查
- [x] 4.4 将 GroundingQualityReport 聚合进最终 GenerationQualityReport
- [x] 4.5 保持节点语义问题最多一次定向修复，解析/覆盖/正文失败分别局部重试

## 5. 唯一任务、进度与恢复

- [x] 5.1 将资料绑定写入唯一 GenerationJob 快照，避免保存完整文件文本
- [x] 5.2 在 material_processing 内执行解析与证据检查点，不创建第二任务
- [x] 5.3 分离全局 progress 与 phase_progress，并增加逐文件 phase_detail
- [x] 5.4 验证暂停、重启、多课程并发和解析缓存复用

## 6. 前端资料体验

- [x] 6.1 抽取资料输入面板并实现真实文件上传、移除、失败和重试状态
- [x] 6.2 支持资料用途、权威和使用策略，提交 material_bindings
- [x] 6.3 显示逐文件解析阶段、真实进度、警告和动态耗时状态
- [x] 6.4 展示最终资料覆盖、冲突、缺口、未使用资料和解析失败报告
- [x] 6.5 同步中英文文案并删除静态耗时与不真实的格式承诺

## 7. 验证、迁移与清理

- [x] 7.1 补充上传、解析、证据、覆盖、接地、质量、恢复和旧数据兼容测试
- [x] 7.2 运行后端测试、前端测试与构建、OpenSpec、diff 检查和 Python 3.10 Docker smoke
- [x] 7.3 更新产品蓝图和项目决策，记录资料驱动生成 V3 的稳定边界
- [x] 7.4 删除所有消费者迁移完成后的旧内联 digest、默认资料引用和旧覆盖统计
- [x] 7.5 归档 OpenSpec 并再次执行全量规范验证
