## Context

当前 Babyface 的主入口在 `personal_agent/main.py`，由 Typer 解析 CLI 参数、Rich 渲染终端输出，并把真实交互循环接到 `AgentRuntime`。`AgentRuntime` 使用 LangGraph 组织 `prepare -> llm -> tools -> llm -> finalize` 的基础 Agent Loop，`MemoryStore` 已通过 SQLite 保存 Profile Memory、Task History 和 Tool 调用摘要。

本变更需要在不改变普通模式体验的前提下，给调试模式增加一条横切链路：CLI 负责开启调试模式，Runtime 负责在各节点产生调试事件，独立 Debug Store 负责按日期写入 SQLite。

## Goals / Non-Goals

**Goals:**

- `babyface --debug` 显式开启调试模式，普通 `babyface` 保持现有输出和持久化行为。
- 每次 CLI Session 生成一个 `session_id`，每轮 `run_turn()` 生成一个 `trace_id`。
- 调试事件覆盖接受用户输入后、LLM 调用前后、Tool 调用前后、Skill 调用前后，并统一包含输入、输出、`session_id`、`trace_id`、系统时间。
- 调试事件只写入当天 SQLite 文件，不向命令行输出调用链路调试记录。
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

### 2. 使用切面式记录边界，而不是在业务代码中散落输出和写库逻辑

调试采集采用类似切面的方式：业务流程只在稳定边界调用 recorder 的通用接口，例如 `record_user_input()`、`around_llm_call()`、`around_tool_call()`、`around_skill_call()` 或等价的前后置 helper。helper 内部统一负责：

1. 组装 before/after 调试事件。
2. 补充 `session_id`、`trace_id`、系统时间和阶段名称。
3. 写入当天 SQLite。
4. 捕获调试持久化失败并转成友好提示。

这样 Runtime、LLM、Tool、Skill 代码仍然表达“我要调用谁、传什么参数、拿什么结果”，不会到处出现重复的 SQL insert 或时间格式化代码。

备选方案是在 `_call_llm()`、`_run_tools()`、`_run_post_turn_maintenance()` 中直接拼文本和写 SQLite。它实现最快，但后续每加一个节点都要复制同类逻辑，架构会很快变脏，因此不采用。

### 3. 调试 SQLite 文件默认放在项目本地 `.babyface/debug/`

调试模式下，本地 SQLite 文件默认写入 `.babyface/debug/debug_trace_YYYYMMDD`。例如系统时间为 `2026-08-25 19:06:01` 时，写入 `.babyface/debug/debug_trace_20260825`。

这个位置沿用当前默认 Memory 数据库的项目本地思路，便于用户在同一项目中找到运行数据，也避免写到不透明的系统临时目录。文件名按用户指定不追加扩展名；虽然没有 `.sqlite3` 后缀，但文件内容仍是 SQLite 数据库。

### 4. 时间格式采用本地系统时间字符串

调试事件的 `created_at` 使用当前系统本地时间，格式固定为 `YYYY-MM-DD HH:MM:SS`。该格式直接满足用户给出的示例，也便于终端阅读和按日期分文件。

备选方案是复用 MemoryStore 当前的 UTC ISO 字符串。它更利于跨时区计算，但不符合用户明确给出的展示格式，因此调试记录单独使用本地格式。

### 5. ID 生成使用 UUID 字符串且字段名固定

`session_id` 和 `trace_id` 使用 UUID 字符串。CLI 启动交互式 Session 时生成 `session_id`，并把它注入 Runtime 或 Debug Context；Runtime 每次 `run_turn()` 开始时生成 `trace_id`，并放入 LangGraph state，供 `_prepare`、`_call_llm`、`_run_tools`、`_finalize` 和 post-turn Skill 维护链路复用。

所有调试事件模型和 SQLite schema 都使用蛇形字段名 `session_id` 和 `trace_id`。面向用户的说明可以描述为 Session ID 和 Trace ID，但结构化字段不得使用 `Session ID`、`Trace ID`、`sessionId` 或 `traceId`。

使用 UUID 的好处是无需依赖数据库自增 ID，也不要求跨进程共享状态。备选方案是时间戳加随机数，可读性略好但冲突处理更脆弱。

### 6. 在 LangGraph 节点边界采集事件

调试记录采集点放在现有 Runtime 边界：

- 用户信息：`run_turn()` 收到并清洗用户输入后记录 `user_input_received` 阶段。
- LLM 信息：通过 recorder 的 LLM 切面 helper 包裹 `self.llm.complete(...)`，调用前记录 `llm_before` 阶段，包含 messages 和 tool schema 摘要；调用后记录 `llm_after` 阶段，包含 response content、tool_calls 和模型信息。
- Tool 调用：通过 recorder 的 Tool 切面 helper 包裹 `self.tools.run(...)`，调用前记录 `tool_before` 阶段，包含工具名称和 arguments；调用后记录 `tool_after` 阶段，包含 content、error 和 metadata。
- Skill 调用：当前 Skill 主要体现在 post-turn 的 `AGENTS.md` 维护服务；通过 recorder 的 Skill 切面 helper 包裹维护服务调用，调用前记录 `skill_before` 阶段，调用后记录 `skill_after` 阶段。未来新增 Skill 入口时复用同一切面 helper。

这种方式不依赖 LangGraph 内部 tracing 插件，能保持 V1 简单可测。代价是如果未来引入更多 LangGraph 节点，需要在新增节点处显式接入 recorder。

### 7. 调试模式不输出调用链路到命令行

Debug recorder 只负责把事件写入 Debug Store，不接受 CLI 输出回调，也不格式化调用链路调试文本。CLI 层仍可以展示正常 Agent 回复、Tool 状态和调试写入失败的中文友好错误提示，但不得把用户输入、LLM 输入输出、Tool 输入输出或 Skill 输入输出作为调试链路打印到命令行。

这样可以避免调试模式刷屏，也降低在共享终端或录屏场景中暴露敏感上下文的风险。需要排障时，用户从当天 SQLite 文件读取完整调试记录。

### 8. SQLite schema 保持通用事件表

按日期 SQLite 文件中创建单表 `debug_trace_events`：

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `event_type TEXT NOT NULL`
- `stage TEXT NOT NULL`
- `name TEXT`
- `session_id TEXT NOT NULL`
- `trace_id TEXT NOT NULL`
- `input TEXT NOT NULL`
- `output TEXT NOT NULL`
- `metadata TEXT NOT NULL`
- `created_at TEXT NOT NULL`

`stage` 保存 `user_input_received`、`llm_before`、`llm_after`、`tool_before`、`tool_after`、`skill_before`、`skill_after` 等阶段名称。`metadata` 使用 JSON 字符串保存模型名、tool_call_id、错误类型、节点名等结构化补充字段。使用单表可以减少 V1 schema 复杂度；如果后续需要查询优化，再按事件类型拆表或加索引。

### 9. 本地运行文件按类型分目录保存

Babyface 默认仍使用 `.babyface/` 作为本地运行目录，但不再把所有文件平铺在这个目录下：

- Memory SQLite 默认路径改为 `.babyface/memory/memory.sqlite3`
- 用户级默认配置路径改为 `~/.babyface/config/config.toml`
- Debug trace 继续使用 `.babyface/debug/debug_trace_YYYYMMDD`

显式路径不自动改写：用户通过 `BABYFACE_MEMORY_DB_PATH`、配置文件里的 `memory_db_path`、`--config` 或 `BABYFACE_CONFIG_PATH` 指定的位置仍按原样使用。

为了避免升级后看不到旧数据，MemoryStore 在默认新路径初始化时，如果 `.babyface/memory/memory.sqlite3` 不存在但旧默认 `.babyface/memory.sqlite3` 存在，会先把旧文件迁移到新路径再初始化表结构。用户级配置读取则优先尝试 `~/.babyface/config/config.toml`，如果不存在再回退读取旧的 `~/.babyface/config.toml`。

### 10. Memory 历史表也保存关联 ID

为了让 `.babyface/memory/memory.sqlite3` 中的 Task History 和 Tool 调用摘要能与 debug trace 互相关联，`MemoryStore` 的 `task_history` 和 `tool_calls` 表也保存 `session_id` 和 `trace_id`。

现有数据库需要兼容升级：`MemoryStore._initialize()` 在创建表后检查表字段，缺少 `session_id` 或 `trace_id` 时通过 `ALTER TABLE` 增加可空文本列。旧记录没有这些 ID 时保持 `NULL`，新记录在 Runtime 调用 `save_task_history()` 时写入当前轮的 `session_id` 和 `trace_id`。

`tool_calls` 表也保存同一组 ID，虽然可以通过 `task_id` 关联回 `task_history`，但冗余字段能让用户直接查询工具调用记录时不用每次 join。

### 11. Shell 二次确认和流式输出保持现有体验

Shell Tool 的二次确认仍由 CLI 注入的 `confirm_shell()` 负责。调试模式只记录确认结果和 Tool 输出，不绕过用户确认，也不在确认前执行命令。

当前 Runtime 的 stream 是最终回答拆片后的展示流，不是真正逐 token 的 LLM 流。调试模式先记录最终 LLM 输入输出和最终回复，保持现有流式展示行为；未来如果 LLM 客户端支持真实 streaming，可以把 chunk 作为 metadata 或单独事件追加。

## Risks / Trade-offs

- [Risk] 调试记录可能包含用户隐私、文件内容、命令输出或 system prompt。 → Mitigation：仅在显式 `--debug` 下开启；普通模式不创建调试文件；文档和 help 中提示调试模式会记录输入输出。
- [Risk] LLM messages 或工具输出过长，导致 SQLite 文件快速膨胀。 → Mitigation：V1 先完整记录以满足排障需求；后续如需要再增加保留策略或手动清理命令。
- [Risk] 调试写入失败会干扰正常 Agent Loop。 → Mitigation：recorder 捕获 SQLite 写入异常，可向 CLI 输出中文友好错误提示，并继续当前 Session；该提示不得包含调用链路输入输出。
- [Risk] Skill 调用入口当前不如 Tool 调用集中。 → Mitigation：V1 先覆盖现有 post-turn `AGENTS.md` 维护服务；后续新增 Skill 系统时要求通过统一 recorder 入口记录。
- [Risk] 文件名没有 `.sqlite3` 后缀，用户可能不容易识别格式。 → Mitigation：遵循用户指定文件名格式，并在 README 或 help 文案中说明该文件内容为 SQLite 数据库。

## Migration Plan

1. 新增调试模式默认关闭，不影响现有用户和测试。
2. 实现后补充 CLI help、Runtime、Debug Store 和集成测试。
3. 如果用户不再需要调试数据，可以直接删除 `.babyface/debug/debug_trace_YYYYMMDD` 文件；普通 Memory 数据不受影响。
