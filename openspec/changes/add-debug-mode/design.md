## Context

当前 Babyface 的主入口在 `personal_agent/main.py`，由 Typer 解析 CLI 参数、Rich 渲染终端输出，并把真实交互循环接到 `AgentRuntime`。`AgentRuntime` 使用 LangGraph 组织 `prepare -> llm -> tools -> llm -> finalize` 的基础 Agent Loop，`MemoryStore` 已通过 SQLite 保存 Profile Memory、Task History 和 Tool 调用摘要。

本变更需要在不改变普通模式体验的前提下，给调试模式增加一条横切链路：CLI 负责开启调试和展示调试事件，Runtime 负责在各节点产生调试事件，独立 Debug Store 负责按日期写入 SQLite。

## Goals / Non-Goals

**Goals:**

- `babyface --debug` 显式开启调试模式，普通 `babyface` 保持现有输出和持久化行为。
- 每次 CLI Session 生成一个 `Session ID`，每轮 `run_turn()` 生成一个 `Trace ID`。
- 调试事件覆盖用户信息、LLM 信息、Tool 调用、Skill 调用，并统一包含输入、输出、`Session ID`、`Trace ID`、系统时间。
- 调试事件同时输出到命令行和写入当天 SQLite 文件。
- 调试持久化失败时只影响调试记录，不导致 Agent Session 崩溃。

**Non-Goals:**

- 不新增远程 Trace 服务、Web UI、导出功能或日志检索命令。
- 不把调试记录上传到任何外部服务。
- 不改变 MemoryStore 现有 Profile Memory 和 Task History 语义。
- 不要求 V1 实现 LangGraph 原生 tracing 后端；先在现有节点边界采集调试事件。

## Decisions

### 1. 新增独立 Debug Trace 组件，而不是扩展 MemoryStore

新增 `DebugTraceRecorder`、`DebugTraceStore` 和 `DebugTraceEvent` 一类的独立调试模块。CLI 根据 `--debug` 创建启用状态的 recorder；普通模式传入空 recorder 或 `None`，Runtime 调用时无需到处判断终端参数。

选择独立组件的原因是 MemoryStore 表达“用户记忆”和“任务历史”，而 Debug Trace 表达“内部排障记录”。两者数据量、生命周期和隐私风险不同，混在一个 store 会让职责变糊。

备选方案是把调试表追加到 `.babyface/memory.sqlite3`。这可以少建一个文件，但不满足用户要求的按日期文件分隔，也会让长期记忆数据库承载大量临时排障数据，因此不采用。

### 2. 调试 SQLite 文件默认放在项目本地 `.babyface/debug/`

调试模式下，本地 SQLite 文件默认写入 `.babyface/debug/debug_trace_YYYYMMDD`。例如系统时间为 `2026-08-25 19:06:01` 时，写入 `.babyface/debug/debug_trace_20260825`。

这个位置沿用当前默认 Memory 数据库的项目本地思路，便于用户在同一项目中找到运行数据，也避免写到不透明的系统临时目录。文件名按用户指定不追加扩展名；虽然没有 `.sqlite3` 后缀，但文件内容仍是 SQLite 数据库。

### 3. 时间格式采用本地系统时间字符串

调试事件的 `created_at` 使用当前系统本地时间，格式固定为 `YYYY-MM-DD HH:MM:SS`。该格式直接满足用户给出的示例，也便于终端阅读和按日期分文件。

备选方案是复用 MemoryStore 当前的 UTC ISO 字符串。它更利于跨时区计算，但不符合用户明确给出的展示格式，因此调试记录单独使用本地格式。

### 4. ID 生成使用 UUID 字符串

`Session ID` 和 `Trace ID` 使用 UUID 字符串。CLI 启动交互式 Session 时生成 `Session ID`，并把它注入 Runtime 或 Debug Context；Runtime 每次 `run_turn()` 开始时生成 `Trace ID`，并放入 LangGraph state，供 `_prepare`、`_call_llm`、`_run_tools`、`_finalize` 和 post-turn Skill 维护链路复用。

使用 UUID 的好处是无需依赖数据库自增 ID，也不要求跨进程共享状态。备选方案是时间戳加随机数，可读性略好但冲突处理更脆弱。

### 5. 在 LangGraph 节点边界采集事件

调试记录采集点放在现有 Runtime 边界：

- 用户信息：`run_turn()` 收到并清洗用户输入后记录输入；最终回答生成后补充或另记用户轮次输出。
- LLM 信息：`_call_llm()` 调用前记录 messages 和 tool schema 摘要，调用后记录 response content、tool_calls 和模型信息。
- Tool 调用：`_run_tools()` 每个 tool call 执行前后记录工具名称、arguments、content、error 和 metadata。
- Skill 调用：当前 Skill 主要体现在 post-turn 的 `AGENTS.md` 维护服务；在 `_run_post_turn_maintenance()` 周围记录 Skill 名称、输入上下文、输出或错误。未来新增 Skill 入口时复用同一事件类型。

这种方式不依赖 LangGraph 内部 tracing 插件，能保持 V1 简单可测。代价是如果未来引入更多 LangGraph 节点，需要在新增节点处显式接入 recorder。

### 6. 命令行调试输出由 recorder 统一格式化

Debug recorder 同时负责把事件交给 CLI 输出端和 Debug Store。CLI 层提供 `write_debug` 或 Rich console 适配器，保证真实 CLI 和测试版 `CLISession` 都能注入轻量输出函数。

调试输出建议使用稳定前缀，例如 `[Debug]`，并按事件块展示：

- `type`
- `session_id`
- `trace_id`
- `created_at`
- `name`
- `input`
- `output`

这样测试可以断言关键字段，用户也能在终端中快速扫到链路。

### 7. SQLite schema 保持通用事件表

按日期 SQLite 文件中创建单表 `debug_trace_events`：

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `event_type TEXT NOT NULL`
- `name TEXT`
- `session_id TEXT NOT NULL`
- `trace_id TEXT NOT NULL`
- `input TEXT NOT NULL`
- `output TEXT NOT NULL`
- `metadata TEXT NOT NULL`
- `created_at TEXT NOT NULL`

`metadata` 使用 JSON 字符串保存模型名、tool_call_id、错误类型、节点名等结构化补充字段。使用单表可以减少 V1 schema 复杂度；如果后续需要查询优化，再按事件类型拆表或加索引。

### 8. Shell 二次确认和流式输出保持现有体验

Shell Tool 的二次确认仍由 CLI 注入的 `confirm_shell()` 负责。调试模式只记录确认结果和 Tool 输出，不绕过用户确认，也不在确认前执行命令。

当前 Runtime 的 stream 是最终回答拆片后的展示流，不是真正逐 token 的 LLM 流。调试模式先记录最终 LLM 输入输出和最终回复，保持现有流式展示行为；未来如果 LLM 客户端支持真实 streaming，可以把 chunk 作为 metadata 或单独事件追加。

## Risks / Trade-offs

- [Risk] 调试记录可能包含用户隐私、文件内容、命令输出或 system prompt。 → Mitigation：仅在显式 `--debug` 下开启；普通模式不创建调试文件；文档和 help 中提示调试模式会记录输入输出。
- [Risk] LLM messages 或工具输出过长，导致终端刷屏和 SQLite 文件快速膨胀。 → Mitigation：V1 先完整记录以满足排障需求；实现时为格式化输出保留截断辅助函数，但 SQLite 持久化默认保存完整 JSON 文本。
- [Risk] 调试写入失败会干扰正常 Agent Loop。 → Mitigation：recorder 捕获 SQLite 写入异常，向 CLI 输出中文友好提示，并继续当前 Session。
- [Risk] Skill 调用入口当前不如 Tool 调用集中。 → Mitigation：V1 先覆盖现有 post-turn `AGENTS.md` 维护服务；后续新增 Skill 系统时要求通过统一 recorder 入口记录。
- [Risk] 文件名没有 `.sqlite3` 后缀，用户可能不容易识别格式。 → Mitigation：遵循用户指定文件名格式，并在 README 或 help 文案中说明该文件内容为 SQLite 数据库。

## Migration Plan

1. 新增调试模式默认关闭，不影响现有用户和测试。
2. 实现后补充 CLI help、Runtime、Debug Store 和集成测试。
3. 如果用户不再需要调试数据，可以直接删除 `.babyface/debug/debug_trace_YYYYMMDD` 文件；普通 Memory 数据不受影响。
