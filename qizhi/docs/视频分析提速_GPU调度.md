# 视频分析提速 & GPU 资源调度（任务③交接）

> 目标：解决「本地视频分析只能单队列、第二个视频排队等待」「90 分钟视频约 6 分钟」的问题。
> 本文分两部分：**已落地的代码改动**（可直接生效）和**需手动执行的 GPU 运维**（在 221 平台控制台）。

## 一、现状与瓶颈

- 单个视频内部**已并发**：`LocalVideoAnalysisHandler.execute` 用 `asyncio.to_thread(run_local_analysis, workers=8)`，
  ASR 分块转写与 LLM 维度分析并发请求（见 `server/service/video/analysis_task.py`、`_LOCAL_ANALYSIS_WORKERS=8`）。
- **跨视频串行**（瓶颈）：任务框架 `poll_and_execute` 原本用 `for task: await execute()` 逐个执行，
  多个视频排队——第二个视频要等第一个跑完。
- **根因瓶颈在 GPU/LLM**：ASR 与 LLM 跑在两台独立 GPU 任务上，吞吐受限；提速核心是 GPU 资源调度。

## 二、已落地的代码改动（默认不改变行为，需配置开启）

新增**应用层并发**：多个本地分析任务可同时执行，并发度由信号量限到 `LOCAL_ANALYSIS_MAX_CONCURRENCY`。

| 文件 | 改动 |
|---|---|
| `server/infra/task_queue/framework.py` | `poll_and_execute(max_concurrency=1)`：>1 时并发执行，**每个任务独立 DB 会话**（AsyncSession 不可并发共享），信号量限流 |
| `server/infra/task_queue/worker.py` | handler 支持三元组 `(handler, interval, max_concurrency)` |
| `server/main.py` | 本地分析 handler 传入 `settings.LOCAL_ANALYSIS_MAX_CONCURRENCY` |
| `server/common/config.py` | 新增 `LOCAL_ANALYSIS_MAX_CONCURRENCY`（默认 **1**） |

**默认 `=1` 即保持原串行行为**，零风险上线。GPU 合卡后开启并行：

```bash
# 例：GPU 有 4 个可用槽位
export LOCAL_ANALYSIS_MAX_CONCURRENCY=4
```

> 注意：该值**不要超过 vLLM 的 `--max-num-seqs`** 实际可承载并发，否则只会在模型侧排队、无提速。
> 建议从 2 起步压测，逐步上调。

## 三、需手动执行的 GPU 运维（221 超算平台控制台）

> 这部分无法由代码自动完成，需在控制台操作。来自交接会议要点。

1. **合卡**：当前 ASR 任务占 2 卡、LLM 任务占 4 卡，分属两个任务。
   先**新建一个 6 卡（或 8 卡）任务**，再停掉原来的两个任务（先建后停，便于回滚）。
2. **在合并后的多卡任务上**做动态分配：ASR、LLM、PPT 生成等共享卡池。
   论文分析当前无人用，分配少量 GPU 即可。
3. **端口转发**：模型任务跑在容器内部端口（如 ASR `7890`），外部端口由平台**自动分配**。
   创建完成后在控制台查看「内部端口 → 外部端口」映射，更新到后端配置：
   - `LOCAL_ANALYSIS_ASR_BASE_URL`（当前 `http://127.0.0.1:30219/v1`）
   - `LOCAL_ANALYSIS_TEXT_BASE_URL`（当前 `http://127.0.0.1:30964/v1`）
4. **SSH 连接**：IP 必须用 **221 开头（公网）**，不要用 `10.` 开头（内网，连不上）。
5. **提高单任务吞吐**：在合并卡上把 vLLM 的 `--max-num-seqs`、张量并行调大，
   再相应上调 `LOCAL_ANALYSIS_MAX_CONCURRENCY` 与 `_LOCAL_ANALYSIS_WORKERS`。

## 四、压力测试建议

- 同时提交 2~4 个本地分析任务，观察是否并行（日志 `[worker] local_video_analysis 开始轮询` + 多个 `开始执行本地视频分析`）。
- 记录单视频耗时随 `--max-num-seqs` / 并发的变化，校准 `server/service/video/eta.py` 的预估。
- 压测脚本目录：`server/tests/stress/`。
