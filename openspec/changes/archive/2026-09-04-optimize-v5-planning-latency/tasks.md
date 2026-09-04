> **历史归档说明（2026-09-04）**：V5 延迟优化的本地实现已经完成，剩余生产发布与单章 smoke 已被 V6 生成链和当前发布门取代。保留两项未执行记录，但不再作为活动任务。

## 1. Freeze the latency and quality contract

- [x] 1.1 Reproduce serial visual planning with a non-mathematics course fixture
- [x] 1.2 Assert bounded overlap, deterministic page order, and stage diagnostics
- [x] 1.3 Record that latency optimization cannot reduce V5 content or quality gates

## 2. Implement bounded visual planning

- [x] 2.1 Add a conservative configurable concurrency budget
- [x] 2.2 Execute independent chapter batches concurrently
- [x] 2.3 Aggregate accepted, partial, and failed batches in stable order
- [x] 2.4 Record total, peak-concurrency, and per-batch timing diagnostics

## 3. Verify and release

- [x] 3.1 Run focused and cross-subject regression tests
- [x] 3.2 Run the related V5 suite, full backend suite, lint, and OpenSpec validation
- [x] 3.3 Review the diff for course/subject/artifact/chapter hardcoding
- 未执行（历史归档，不再作为当前任务）：3.4 Merge and deploy through the production workflow
- 未执行（历史归档，不再作为当前任务）：3.5 Run exactly one production chapter smoke and inspect the generated PPT
