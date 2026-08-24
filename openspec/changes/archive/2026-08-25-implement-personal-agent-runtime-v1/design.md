## Context

当前仓库只有 `README.md`、一个 FastAPI 风格的 `main.py` demo，以及中文 V1 需求文档。V1 需要把主路径转为本地 CLI，围绕 `babyface` 命令建立可运行 Agent Runtime。需求中已确认的关键技术决策包括：V1 立即使用 LangGraph、Shell 命令执行前需要用户二次确认、最终回答支持流式输出、SQLite 默认在项目目录内并支持配置覆盖。

## Goals / Non-Goals

**Goals:**

- 建立最小可运行 Python package，暴露 `babyface` console command。
- 用 LangGraph 串联 V1 主 Agent Workflow。
- 接入 OpenAI-compatible LLM，配置从环境变量或本地配置读取。
- 实现 File Tool、Shell Tool、Web Tool 占位和 Tool Registry。
- 实现 SQLite Memory Store，覆盖 Profile Memory、Task History 和未来 RAG 检索接口。
- 使用 Rich 提供中文 CLI 提示、Markdown 渲染、Tool 调用可见性和流式输出体验。
- 添加聚焦测试，优先覆盖 Tools、Memory、配置和 Agent Loop 可替换组件。

**Non-Goals:**

- 不保留 HTTP API 作为 V1 主入口。
- 不实现 Web Search、真实 RAG、Dashboard、Scheduler、Multi-Agent 或生产级权限系统。
- 不在代码中硬编码 API key 或用户私密信息。

## Decisions

### 1. 使用 `src` 之外的轻量 package 结构

V1 采用仓库根目录下的 `personal_agent/` package，而不是引入更复杂的 monorepo 或 src-layout。当前项目体量很小，直接 package 结构更容易快速跑通，也符合需求文档建议。

备选方案是 `src/personal_agent/`。它更适合较大工程，但当前优先减少路径和打包复杂度。

### 2. `main.py` 从 HTTP demo 迁移到 CLI 入口

现有根目录 `main.py` 包含 FastAPI demo 和硬编码 key，后续实现应移除硬编码密钥，并把主入口转为 Typer CLI。实际 console command 建议指向 `personal_agent.main:app`，根目录 `main.py` 可以删除或改为兼容入口，避免用户误以为 HTTP API 是 V1 主路径。

备选方案是同时保留 HTTP API 和 CLI。该方案会扩大 V1 范围，与“不要 HTTP API”的需求冲突。

### 3. 配置分层

配置模块读取环境变量和项目内配置文件，至少覆盖：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- SQLite 文件路径
- Shell Tool 超时时间

默认 SQLite 路径为 `.babyface/memory.sqlite3`。配置缺失时，CLI 应用中文错误说明提示用户补齐，而不是在深层 LLM 调用处失败。

### 4. LangGraph 主流程保持最小

主 Workflow 使用 LangGraph 表达，建议节点为：

- 加载 Memory 上下文
- 调用 LLM
- 执行 Tool
- 生成最终回答
- 持久化任务历史

Tool 调用循环可以先限制最大轮数，避免模型不断请求 Tool 导致 Session 卡住。LangGraph 外部保留简单 Runtime facade，供 CLI 和测试调用。

### 5. Tool Registry 使用统一结构化结果

每个 Tool 暴露统一 schema 和执行接口，返回结构化结果：

- `ok`
- `content`
- `error`
- `metadata`

File Tool 首版只读文本文件。Shell Tool 由 CLI 注入确认回调，执行前必须确认。Web Tool 返回未实现结果，但保持未来扩展接口。

### 6. 流式输出只覆盖最终回答，Tool 阶段展示状态

V1 的流式输出重点覆盖最终自然语言回答。Tool 调用阶段以 Rich 状态提示、面板或日志行展示开始、取消、成功、失败。这样既满足用户体验，又避免把 Tool stdout 流式处理复杂化。

### 7. SQLite Memory 使用标准库实现

V1 使用 Python 标准库 `sqlite3`，避免引入 ORM。建议表结构：

- `profile_memory`：保存长期用户信息。
- `task_history`：保存用户输入、最终回答、时间戳。
- `tool_calls`：可选保存每轮 Tool 调用摘要。

Memory 模块提供 `retrieve_knowledge(query)` 接口，V1 可返回空列表，为后续 RAG 保持调用形状。

### 8. Session 内短期记忆由 Runtime 管理

长期 Memory 负责跨 Session 的 Profile 和 Task History；短期记忆负责同一个 CLI Session 内连续几轮对话的上下文传递。V1 在 `AgentRuntime` 实例内保存当前 Session 的历史 user/assistant messages，并在每轮 `_prepare` 时注入到当前用户输入之前。

这个设计的边界是：重启 CLI 后短期记忆清空，但长期 Profile Memory 会从 SQLite 重新加载。后续可以把 Task History 摘要化后注入，让跨 Session 的上下文也更自然。

### 9. Runtime 输入清洗与 CLI 异常兜底

用户输入可能来自终端、剪贴板或其他外部来源，其中可能混入 Unicode surrogate 这类无法编码为标准 UTF-8 的字符。V1 在 `AgentRuntime.run_turn()` 入口统一清洗用户输入，把非法字符替换为安全占位字符，再进入 Memory、LangGraph 和 LLM 调用流程。

真实交互式 CLI 在调用 Runtime 时增加异常兜底：如果本轮发生未预期异常，CLI 展示中文友好提示，不直接展示 Python traceback，并继续等待下一轮用户输入。可识别的问题给出具体说明，无法识别的问题统一显示为“系统异常”。

### 10. 终端输入行编辑使用 prompt_toolkit，readline 作为兼容补充

V1 使用 `prompt_toolkit.PromptSession` 作为真实 CLI 的输入读取层。相比普通 `input()` 或 Rich `console.input()`，PromptSession 会把 `> ` 作为不可编辑 prompt 区域，用户只能编辑 prompt 后面的输入内容，因此退格键不会删除输入行最开始的 `> `。

PromptSession 同时提供上下键历史浏览、左右键移动光标、Delete 删除光标后的字符，以及在光标位置插入字符。`readline` 初始化仍保留为兼容补充；如果 `prompt_toolkit` 不可用，CLI 可以回退到普通输入，不阻止主流程启动。

### 11. 启动 Banner 与 Help 分离

真实 CLI 启动时使用 Rich `Panel` 展示彩虹色 `BABYFACE` Banner，作为进入 Session 的视觉入口。Banner 只做品牌展示，不再承载退出命令等说明性文案。

Session 内退出命令属于帮助信息，放在 `babyface --help` 中展示。这样启动界面更干净，用户需要查看操作说明时也有稳定入口。

## Risks / Trade-offs

- [Risk] LLM Tool Calling 与 OpenAI-compatible endpoint 的兼容性存在差异 → Mitigation：封装 LLM client，并用 fake client 测试 Agent Loop；真实模型配置在 README 中说明。
- [Risk] Shell Tool 有本地执行风险 → Mitigation：V1 强制二次确认、设置超时、清晰展示命令和取消结果。
- [Risk] LangGraph 可能让最小版本复杂度上升 → Mitigation：图结构保持小，业务逻辑放在可单测的函数和 Runtime facade 中。
- [Risk] 流式输出与 Tool 循环组合复杂 → Mitigation：V1 只要求最终回答流式，Tool 阶段展示状态。
- [Risk] 项目内 SQLite 文件可能被误提交 → Mitigation：实现时添加 `.gitignore` 忽略 `.babyface/`。

## Migration Plan

1. 保留现有中文需求文档作为需求来源。
2. 新增 package、配置、工具、Memory、Agent Runtime 和测试。
3. 将用户主入口切换为 `babyface`。
4. 移除或降级现有 FastAPI demo，确保 README 不再把 HTTP API 作为 V1 使用方式。
5. 更新 README，说明安装、配置、运行和退出方式。

## Open Questions

无。当前剩余细节可以在不改变规格和任务拆分的前提下由实现阶段决定。
