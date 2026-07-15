# 设计：课程学习版本变化确认

## 1. 真源与协调边界

版本协调服务不保存第八份业务状态。它读取当前课程版本、`LearningSnapshot`、`PracticeAttempt`、诊断工作流和 `LearningRecord`，生成确定性迁移计划；确认后只调用各领域仓库已有写能力，并追加事实事件。

## 2. 迁移分类

- 阅读快照：`exact`、`updated_block`、`fingerprint_remap` 可以迁移到当前版本；`node_fallback` 只能在本次显式确认后采用；`course_fallback` 或 `unavailable` 必须要求用户指定目标节点，不能随机落点。
- 活动任务：旧版本的 `in_progress/submitted/grading` Attempt 必须 invalidated 并保留旧答案；旧诊断和补救工作流必须 stale。快照任务退回当前映射节点的 reading，不复制旧任务修订。
- 学习记录：记录本体继续保留原课程版本和原锚点，只通过当前课程投影 `current/content_updated/needs_confirmation/orphaned`。
- 历史证据：阅读事实可以在稳定目标修订下继续投影；正式掌握只接受当前目标、题目和标准修订，旧 Attempt 不得证明新修订。

## 3. 并发与幂等

确认请求必须携带 `expected_projection_revision_id`。服务端在写入前重建连续性投影；修订不一致返回 409 和当前投影。协调操作按用户与课程串行执行，领域对象各自原子写入。已完成的失效操作允许重试，确认事件使用请求幂等键避免重复事实。

## 4. 前端交互

`confirm_version_change` 不再只切换到版本页。课程页根据运行时迁移计划展示目标版本、阅读位置处理、将失效的活动任务和保留的记录；用户确认后调用正式命令。成功时重新载入课程、服务端快照、学习记录和运行时，再按新的 `primary_action` 返回 reading 或正式任务。

## 5. 验收

真实课程 `cv1 -> cv2` 的正文与目标保持稳定、21 项正式资产修订变化。验收必须证明阅读锚点可以迁移，旧记录得到迁移状态，旧活动任务退出主线，旧题/旧标准证据不进入当前掌握投影，确认后不再反复出现版本阻断。
