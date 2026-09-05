# Assistant Agent — ReAct 实现解析

> 对应源码：`server/agents/assistant/agent.py`
> 本文档面向「需要理解智能对话后端架构、排查流式输出异常、或扩展工具」的开发者。

---

## 1. 总体架构

Assistant Agent 采用 **ReAct（Reasoning + Acting）** 范式：

```
用户提问 → 构建上下文 → ReAct 多轮循环 → SSE 流式返回
                    ↑           ↓
                 工具串行执行 ← 模型推理
```

与单轮 chat 不同，模型可以在一次对话中：
1. **思考**（Thought）——分析用户需求
2. **行动**（Action）——调用一个或多个工具
3. **观察**（Observation）——读取工具返回结果
4. **重复** ——基于新信息继续思考，直到给出最终答案

---

## 2. 模块拆解

### 2.1 `stream()` —— 入口与生命周期管理

```python
async def stream(db, request, current_user) -> AsyncIterator[dict]:
```

**职责**：
- 若 `session_id` 为空，自动创建新 `Session` 记录
- 调用 `build_context()` 组装上下文
- 启动 `react_loop()` 并捕获所有异常
- 在 `finally` 中统一发送 `END` 事件并记录耗时

**SSE 事件总览**：

| 事件 | 触发时机 | 前端表现 |
|------|---------|---------|
| `START` | 上下文构建完成 | 显示"开始处理" |
| `THINKING` | ~~模型输出 thought~~ | ~~展示思考内容~~（已禁用） |
| `LOADING` | 即将调用单个工具 | 显示当前正在执行的工具名称 |
| `MESSAGE` | 输出 final_answer 片段 | 逐字显示回答 |
| `ERROR` | ReAct 循环抛异常 | 显示错误提示 |
| `END` | 无论成功与否都会发送 | 结束流式接收 |

**错误兜底**：即使 `react_loop` 抛异常，也会：
1. 发送 `ERROR` 事件
2. 往 `messages` 表写一条 `status="error"` 的记录
3. 在 `finally` 中发送 `END` 事件

---

### 2.2 `build_context()` —— 上下文组装

```python
async def build_context(db, request, current_user) -> Context
```

**组装内容**：
- `session_id` / `chat_id` —— 会话与消息 ID
- `messages` —— 历史消息（从 DB 拉取）+ 当前用户提问
- `file_paths` / `file_contents` —— 用户上传的附件路径及 Markdown 文本

**副作用**：将当前用户提问写入 `messages` 表（`role="user"`）。

> **注意**：`file_contents` 在构建时就通过 `convert_file_to_markdown()` 完成转换，这意味着大文件会阻塞上下文构建。若后续需要优化，可考虑异步懒加载。

---

### 2.3 `react_loop()` —— 核心 ReAct 循环

```python
async def react_loop(context, db, *, start_time) -> AsyncIterator[dict]:
```

**循环控制**：
- 最多 `context.max_rounds` 轮（默认由 `Context` 类决定，通常 5~10 轮）
- 每轮向模型发送完整对话历史（含之前的 Thought/Action/Observation）

**单轮内部流程**：

#### ① 流式接收模型输出

```python
async for chunk in stream_chat(system_prompt=..., history=context.messages):
    content += chunk
```

`stream_chat` 来自 `agents/llm.py`，底层调用 vLLM/OpenAI 兼容接口。

#### ② 实时提取 `final_answer`

这是本文件**最复杂的设计点**——模型输出的是一整段 JSON，但前端需要**实时看到回答**，不能等 JSON 完全生成。

**解析策略**：
1. 在流式输出中扫描 `"final_answer"` 字符串
2. 找到其后的第一个 `"`（JSON 字符串起始引号）
3. 从该引号后开始，把后续内容作为回答**实时 yield**
4. 同时用 `find_json_string_end()` 检测字符串是否闭合（跳过转义引号 `"`）
5. 一旦检测到闭合引号，停止 yield，本轮结束

```
模型输出片段：
... "final_answer": "这是第一段回答内容...
                         ↑
                    answer_quote_pos
                         ↓
实时 yield 给用户：这是第一段回答内容...
```

**关键状态变量**：

| 变量 | 作用 |
|------|------|
| `answer_quote_pos` | `"final_answer"` 后第一个 `"` 的位置，找到后才进入实时输出模式 |
| `yielded_answer_len` | 已经 yield 给前端的长度，避免重复发送 |
| `answer_closed` | 字符串是否已闭合（遇到未转义的 `"`） |

> **为什么不用 JSON 解析器实时解析？**
> 因为 vLLM 流式返回的是**字节流**，在 JSON 完全生成前，任何标准解析器都会失败。字符串扫描是唯一能"边生成边提取"的策略。

#### ③ 解析完整输出

本轮流式结束后，用 `parse_react_output()` 解析完整 JSON：

```json
{
  "thought": "...",
  "actions": [
    {"tool_name": "...", "args": {...}}
  ],
  "final_answer": "..."
}
```

#### ④ 决策分支

```
if final_answer 且没有 actions:
    → 回答完成，yield MESSAGE，写入 DB，return 结束循环

if 有 actions:
    → 逐个串行执行工具
      每个工具执行前 yield LOADING（展示该工具的名称）
    → 全部完成后将 Thought + Action + Observation 拼接成新消息
    → 进入下一轮

if 既没有 final_answer 也没有 actions:
    → 模型输出无效，break，给出兜底回复
```

**串行执行细节**：

```python
for action in actions:
    tool_name = action.get("tool_name", "")
    # 1. 发送 LOADING，前端显示当前工具名称
    yield build_sse_response(SseEventEnum.LOADING, {"message": loading_msg})
    # 2. 串行 await 执行
    result = await run_tool(context, tool_name, payload)
    # 3. 记录结果（成功/失败）
    observations.append({...})
```

---

### 2.4 `parse_react_output()` —— 输出解析

```python
def parse_react_output(content: str) -> dict:
```

**容错设计**（三层回退）：

1. **去代码块包裹**：若输出被 ` ```json ... ``` ` 包裹，自动去掉
2. **直接 JSON 解析**：尝试 `json.loads(content)`
3. **大括号提取**：若 JSON 解析失败，用 `content.find("{")` 和 `content.rfind("}")` 提取中间部分再解析

---

### 2.5 `execute_actions()` —— 并行工具执行（保留但未使用）

```python
async def execute_actions(context, actions) -> list[dict]:
```

> **注意**：该函数仍保留在源码中，但 `react_loop()` 已不再调用它。当前 `react_loop()` 内联实现了串行执行逻辑。

原实现特点：
- **并行**：所有 action 同时启动 `asyncio.create_task()`
- **容错**：`return_exceptions=True`，单个工具失败不影响其他工具
- **统一返回**：每个工具返回 `{tool_name, status, result}`

若未来需要恢复并行，可将 `react_loop()` 中的串行循环替换回 `await execute_actions(context, actions)`。

---

### 2.6 `run_tool()` —— 单工具执行

```python
async def run_tool(context, tool_name, payload) -> str:
```

**工具注册表**：通过 `tool_registry.get(tool_name)` 查找，工具定义在 `agents/assistant/tools/` 目录。

**流式工具处理**：若工具返回的是异步生成器（`__aiter__`），会收集所有 chunk 后拼接成完整字符串。

---

## 3. 数据流时序图

```
用户提问
    │
    ▼
┌─────────────┐
│   stream()   │  ← 创建 Session（如需）
└─────────────┘
    │
    ▼
┌─────────────┐
│build_context()│ ← 拉历史消息、转换附件
└─────────────┘
    │
    ▼
┌─────────────┐     ┌─────────────┐
│ react_loop  │────→│ stream_chat │ ← 调 vLLM
│   第 1 轮    │     └─────────────┘
└─────────────┘           │
    │                     │ chunk
    │                     ▼
    │              实时扫描 final_answer
    │                     │
    │                     ▼
    │              yield MESSAGE（前端逐字显示）
    │
    ▼
 parse_react_output()
    │
    ├─→ 有 actions ─→ 串行循环
    │                     │
    │                     ▼
    │              yield LOADING("工具1")
    │                     │
    │                     ▼
    │              run_tool(工具1)
    │                     │
    │                     ▼
    │              yield LOADING("工具2")
    │                     │
    │                     ▼
    │              run_tool(工具2)
    │                     │
    │                     ▼
    │              Observation 写入 messages
    │                     │
    │                     ▼
    │              进入第 2 轮 ...
    │
    └─→ 无 actions ─→ yield MESSAGE（完整答案）
                      写入 messages
                      return
```

---

## 4. 关键设计决策

### 4.1 为什么用 `"final_answer"` 字符串扫描，而不是结构化解析？

因为 vLLM 流式返回的是**字节流**，在 JSON 完全生成前，任何标准解析器都会失败。字符串扫描是唯一能"边生成边提取"的策略。

代价：如果模型输出格式异常（如 `final_answer` 不是字符串而是对象），实时提取会失败，但 `parse_react_output()` 会在轮末兜底解析。

### 4.2 为什么不展示 Thought？

当前实现**已禁用** `THINKING` 事件的输出。模型生成的 `thought` 仍会被解析并写入对话历史（用于指导下一轮推理），但不会发送给前端展示。

**原因**：产品层面决定不暴露内部推理过程，保持回答简洁直接。`thought` 的技术价值保留在：
- 指导当前轮 `actions` 的选择
- 作为历史消息的一部分，供下一轮模型参考

### 4.3 工具串行执行

当前 `react_loop()` 使用 `for action in actions:` + `await run_tool()` 串行执行。这意味着：

- **总耗时** = 工具1耗时 + 工具2耗时 + ...（不再是 max）
- **前端体验**：每个工具执行前都会收到一条 `LOADING` 事件，`progressStatus` 会逐个替换，用户能明确看到当前在执行哪个工具
- **顺序保证**：工具按模型给出的 `actions` 列表顺序执行，若有依赖关系（如先查询再修改），自然满足

如果未来需要恢复并行以节省时间，可将串行循环替换回 `execute_actions()`，但前端 loading 体验会变回"一次性展示所有工具名称"。

### 4.4 消息历史膨胀

每轮 ReAct 会把 Thought + Action + Observation 拼成两条消息加入 `context.messages`：

```
assistant: Thought: ...\nAction: [...]
user:      Observation: [...]
```

多轮后上下文会快速增长。当前没有自动截断/摘要机制，若遇到长对话可能需要优化（如滑动窗口、关键信息提取）。

---

## 5. 扩展指南

### 5.1 新增工具

在 `agents/assistant/tools/` 目录下：
1. 创建新文件，实现 `handler(payload, context) -> str | AsyncIterator[str]`
2. 在 `agents/assistant/tools/registry.py` 中注册
3. `tool_registry.planner_specs()` 会自动把工具 schema 注入 system prompt

### 5.2 修改提示词

编辑 `agents/assistant/prompt.md`（主提示词）或 `agents/assistant/tools/xxx.py` 中的 `description`（工具描述）。

`PromptManager.get_prompt("assistant", tools=...)` 会在运行时渲染模板。

### 5.3 调整 ReAct 轮数

修改 `agents/assistant/context.py` 中的 `Context.max_rounds`。

---

## 6. 常见问题排查

| 现象 | 可能原因 | 排查方向 |
|------|---------|---------|
| 前端一直显示"开始处理"但没有内容 | `answer_quote_pos` 一直没找到 | 检查 vLLM 输出是否包含 `"final_answer"` |
| 回答显示一半突然停止 | JSON 字符串闭合检测失败 | 检查模型输出是否有未转义的 `"` |
| 工具调用后没有进入下一轮 | `actions` 解析为空 | 检查 `parse_react_output()` 的容错是否触发 |
| 多轮后回复质量下降 | 消息历史过长 | 观察 `context.messages` 长度 |
| 附件上传后没有引用内容 | `convert_file_to_markdown()` 失败 | 检查 markitdown 依赖（PDF 需要 `[pdf]`） |
| 工具执行很慢，loading 一直不换 | 某个工具阻塞 | 串行执行下，前一个工具慢会导致后一个等待 |
