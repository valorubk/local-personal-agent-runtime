## Purpose

定义本地优先个人 Agent Runtime V1 的用户可见行为，使用户可以通过 `babyface` 启动持续交互式 CLI，并让 Agent 调用本地工具、保存简单记忆、流式返回结果。

## Requirements

### Requirement: 启动交互式 CLI Session
系统 SHALL 提供用户侧命令 `babyface`，运行后进入持续交互式终端 Session，而不是执行一次性命令后退出。

#### Scenario: 启动 Session
- **WHEN** 用户在项目环境中运行 `babyface`
- **THEN** 系统进入可连续输入自然语言的交互式 Session

#### Scenario: 展示启动 Banner
- **WHEN** 用户启动交互式 Session
- **THEN** CLI 展示带边框的彩虹色 `BABYFACE` Banner，在大字下方居中展示 `- Your Local Personal Agent -`，且 Banner 内不展示退出命令说明

#### Scenario: 多轮对话
- **WHEN** 用户在同一个 Session 中连续输入多个自然语言请求
- **THEN** 系统为每个请求返回 Agent 回答，并保持 Session 继续可用

#### Scenario: Help 展示退出命令
- **WHEN** 用户运行 `babyface --help`
- **THEN** CLI help 展示 `exit`、`quit` 和 `/exit` 的 Session 退出方式

#### Scenario: 内部异常时保持 Session 可用
- **WHEN** 一轮对话内部出现未预期异常
- **THEN** CLI 不展示 Python traceback，改为展示中文友好错误提示，并保持 Session 继续可用

#### Scenario: 输入包含无法直接编码的特殊字符
- **WHEN** 用户输入中包含无法编码为标准 UTF-8 的特殊字符
- **THEN** Agent Runtime 在调用 LLM 和保存 Memory 前将异常字符替换为安全占位字符，避免 Session 崩溃

#### Scenario: 支持终端输入行编辑
- **WHEN** 用户在交互式输入行中按上下左右方向键或 Delete
- **THEN** CLI 尽量使用终端行编辑能力处理这些按键，不应把 `^[[A`、`^[[B`、`^[[D`、`^[[C` 这类 escape sequence 当作普通文本输入

#### Scenario: 输入提示符不可被删除
- **WHEN** 用户在输入行开头按退格键
- **THEN** CLI 保留 `> ` 提示符，用户只能编辑提示符之后的输入内容

#### Scenario: 退出 Session
- **WHEN** 用户输入 `exit`、`quit` 或 `/exit`
- **THEN** 系统干净退出 Session

### Requirement: 渲染 CLI 输出与 Agent 活动
系统 SHALL 在终端中以 Markdown 友好的方式展示 Agent 回复，并展示 Tool 调用过程和执行结果。

#### Scenario: 展示 Markdown 回答
- **WHEN** Agent 返回包含 Markdown 结构的回答
- **THEN** CLI 在终端中以可读格式渲染该回答，并使用 `Babyface:` 作为回复标签

#### Scenario: 回复与用户输入保持上下间距
- **WHEN** Agent 输出最终回复
- **THEN** CLI 在回复标签前和回复正文后输出空行，避免回复与上一轮或下一轮用户输入挤在一起

#### Scenario: 展示 Tool 调用
- **WHEN** Agent 决定调用本地 Tool
- **THEN** CLI 展示 Tool 名称、调用状态、执行结果或错误

### Requirement: 支持流式最终回答
系统 SHALL 在 Agent 生成最终回答时支持流式输出，让用户能逐步看到响应内容。

#### Scenario: 流式展示长回答
- **WHEN** Agent 生成较长最终回答
- **THEN** CLI 在回答生成过程中逐步展示内容，而不是只在完整响应结束后一次性展示

#### Scenario: Tool 阶段状态展示
- **WHEN** Agent 执行无法流式展示内容的 Tool 调用
- **THEN** CLI 至少展示清晰的执行状态，直到 Tool 返回结果

### Requirement: 调用 OpenAI-compatible LLM
系统 SHALL 通过可配置的 OpenAI-compatible LLM 完成 Agent 推理，并在缺少必要配置时给出清晰错误。

#### Scenario: 配置完整时调用 LLM
- **WHEN** 用户配置了有效的 API key、模型和可选 base URL
- **THEN** Agent 使用这些配置调用 LLM 并生成回复

#### Scenario: 读取用户目录配置
- **WHEN** 用户未显式传入配置文件且当前目录不存在 `babyface.toml`
- **THEN** 系统尝试读取用户目录下的 `~/.babyface/config/config.toml`

#### Scenario: 兼容旧用户目录配置
- **WHEN** 用户目录下不存在 `~/.babyface/config/config.toml` 但存在旧路径 `~/.babyface/config.toml`
- **THEN** 系统仍可读取旧路径配置

#### Scenario: 缺少 API key
- **WHEN** 用户未配置 API key
- **THEN** 系统拒绝启动需要 LLM 的 Agent Session，并显示清晰的中文错误说明

### Requirement: 本地运行文件按类型分目录保存
系统 SHALL 将 Babyface 默认创建或读取的本地运行文件按类型放入 `.babyface` 下的子目录，避免全部堆在 `.babyface` 根目录。

#### Scenario: 默认 Memory SQLite 放入 memory 目录
- **WHEN** 用户未通过环境变量或配置文件覆盖 Memory SQLite 路径
- **THEN** 系统默认使用 `.babyface/memory/memory.sqlite3`

#### Scenario: 默认用户配置放入 config 目录
- **WHEN** 用户未通过 `--config` 或 `BABYFACE_CONFIG_PATH` 显式指定配置文件
- **THEN** 系统尝试读取用户目录下的 `~/.babyface/config/config.toml`

#### Scenario: 兼容旧默认用户配置路径
- **WHEN** 用户目录下不存在 `~/.babyface/config/config.toml` 但存在旧路径 `~/.babyface/config.toml`
- **THEN** 系统仍可读取旧路径配置

#### Scenario: 兼容旧默认 Memory SQLite 文件
- **WHEN** 默认新路径 `.babyface/memory/memory.sqlite3` 不存在但旧路径 `.babyface/memory.sqlite3` 存在
- **THEN** 系统复用旧文件中的 Memory 数据并将其迁移到 `.babyface/memory/memory.sqlite3`

### Requirement: 执行基础 Agent Loop
系统 SHALL 针对每轮用户输入执行基础 Agent Loop，包括读取输入、加载 Memory、调用 LLM、按需执行 Tool、把 Tool 结果交回 LLM，并输出最终回答。

#### Scenario: 无需 Tool 的请求
- **WHEN** 用户输入一个不需要本地 Tool 的问题
- **THEN** Agent 直接基于 LLM 推理返回最终回答，并记录任务历史

#### Scenario: 需要 Tool 的请求
- **WHEN** LLM 判断需要读取文件或执行命令才能回答用户请求
- **THEN** 系统执行对应 Tool，并将 Tool 结果纳入 Agent 最终回答

#### Scenario: Tool 失败
- **WHEN** Tool 返回错误
- **THEN** Session 不崩溃，Agent 基于错误信息继续生成可理解的最终回答

### Requirement: 支持分层 AGENTS.md 指令
系统 SHALL 允许用户通过文件系统层级中的 `AGENTS.md` 自定义 Babyface 的长期行为指令，并在 Agent 推理时将这些指令纳入 system prompt。

#### Scenario: 没有 AGENTS.md 时仍可运行
- **WHEN** 用户启动 Babyface 且所有默认位置都不存在 `AGENTS.md`
- **THEN** 系统仍使用内置 Babyface 基础指令运行，不因为缺少 `AGENTS.md` 报错

#### Scenario: 读取用户全局 AGENTS.md
- **WHEN** 用户目录存在 `~/.babyface/AGENTS.md`
- **THEN** 系统将该文件内容纳入 Babyface 的 system prompt

#### Scenario: 按文件系统层级拼接 AGENTS.md
- **WHEN** 用户目录、工作区根目录、当前工作目录的父目录或当前工作目录中存在多个 `AGENTS.md`
- **THEN** 系统按全局层到局部层的顺序拼接这些文件内容，越靠近当前工作目录的内容越晚出现

#### Scenario: 冲突指令不经 LLM 改写
- **WHEN** 多个层级的 `AGENTS.md` 包含互相冲突或重复的行为指令
- **THEN** 系统不得调用 LLM 总结、合并、裁剪或改写这些文件内容，而是保留原文并通过拼接顺序表达优先级

#### Scenario: 保留指令来源边界
- **WHEN** 系统拼接一个或多个 `AGENTS.md`
- **THEN** 最终 system prompt 为每个文件内容标明来源边界，便于用户理解和调试指令来自哪里

#### Scenario: AGENTS.md 与 babyface.toml 职责分离
- **WHEN** 用户配置 LLM、Memory 或 Shell timeout
- **THEN** 系统仍通过环境变量或 `babyface.toml` 读取运行时配置，而不要求这些配置写入 `AGENTS.md`

### Requirement: 支持受控偏好写入
系统 SHALL 允许 Babyface 在用户明示要求记住或长期采用某条偏好后，把长期偏好写入全局 `AGENTS.md` 的受控区域，并避免静默修改项目级指令。

#### Scenario: 每轮任务后判断是否需要写入 AGENTS.md
- **WHEN** Babyface 完成一轮用户请求，且用户输入明示要求记住、以后遵循、每次采用或固定使用某条长期偏好
- **THEN** 系统可以调用 LLM 判断本轮输入、执行结果和最终回答是否产生应沉淀到 `AGENTS.md` 的长期偏好

#### Scenario: 用户未明示长期偏好时不请求写入判断
- **WHEN** Babyface 完成一轮用户请求，但用户没有明示要求记住或长期采用某条偏好
- **THEN** 系统不得调用 `AGENTS.md` 更新判断 LLM
- **AND** 系统不得修改任何 `AGENTS.md`

#### Scenario: 无长期偏好时不请求写入
- **WHEN** 用户明示要求记住或长期采用某条偏好，但 LLM 判断本轮没有稳定、长期、可复用的用户偏好
- **THEN** 系统不修改任何 `AGENTS.md`

#### Scenario: 有长期偏好时后台自动写入
- **WHEN** 用户明示要求记住或长期采用某条偏好，且 LLM 生成一条应写入 `AGENTS.md` 的候选偏好
- **THEN** 系统在后台写入整理后的 managed section，且不向用户展示候选内容、目标文件或冲突处理细节

#### Scenario: 写入前检测目标文件规则冲突
- **WHEN** LLM 生成一条候选偏好
- **THEN** 系统要求 LLM 判断该候选偏好是否与目标 `AGENTS.md` 中已有规则冲突

#### Scenario: 冲突时由 LLM 整理 managed section
- **WHEN** 候选偏好与目标 `AGENTS.md` 中已有规则冲突
- **THEN** 系统要求 LLM 产出解决冲突后的 managed section 规则列表，且不得改写 managed section 外的用户手写内容

#### Scenario: 自动写入全局受控区域
- **WHEN** Babyface 在用户明示长期偏好后发现可沉淀为长期指令的用户偏好
- **THEN** 系统将该偏好写入 `~/.babyface/AGENTS.md` 的 Babyface 受控区域

#### Scenario: 不静默修改项目级 AGENTS.md
- **WHEN** Babyface 在用户明示长期偏好后发现可沉淀为长期指令的用户偏好但用户没有明确要求写入项目文件
- **THEN** 系统不得自动修改工作区或项目目录中的 `AGENTS.md`

#### Scenario: 用户明确要求写入项目指令
- **WHEN** 用户明确要求把某条规则写入当前项目或当前目录的 `AGENTS.md`
- **THEN** 系统可以将该规则写入用户指定层级的 `AGENTS.md`

#### Scenario: 受控区域不存在时可创建
- **WHEN** `~/.babyface/AGENTS.md` 不存在或缺少 Babyface 受控区域，且系统需要写入长期偏好
- **THEN** 系统创建必要文件或区域，并保留用户可编辑的 Markdown 结构

### Requirement: 支持只读 File Tool
系统 SHALL 提供 File Tool，用于读取本地文本文件并返回内容或结构化错误。

#### Scenario: 读取存在的文本文件
- **WHEN** Agent 调用 File Tool 并提供一个存在的文本文件路径
- **THEN** Tool 返回该文件内容

#### Scenario: 文件不存在
- **WHEN** Agent 调用 File Tool 并提供不存在的文件路径
- **THEN** Tool 返回结构化错误，说明文件不存在

### Requirement: 支持需确认的 Shell Tool
系统 SHALL 提供 Shell Tool，用于执行本地命令；执行前必须请求用户二次确认，并返回 stdout、stderr 和 exit code。

#### Scenario: 用户确认执行命令
- **WHEN** Agent 请求执行 shell 命令，并且用户确认执行
- **THEN** Tool 执行命令，并返回 stdout、stderr 和 exit code

#### Scenario: 用户拒绝执行命令
- **WHEN** Agent 请求执行 shell 命令，但用户拒绝执行
- **THEN** Tool 不执行命令，并返回“用户取消执行”的结构化结果

#### Scenario: 命令超时
- **WHEN** Shell Tool 执行命令超过配置的超时时间
- **THEN** Tool 终止该命令并返回结构化超时错误

### Requirement: 提供 Web Tool 占位
系统 SHALL 提供 Web Tool 占位接口，并明确返回 Web 能力尚未实现。

#### Scenario: 调用 Web Tool 占位
- **WHEN** Agent 调用 Web Tool
- **THEN** Tool 返回清晰的未实现结果，且 Session 不崩溃

### Requirement: 保存本地 Memory
系统 SHALL 使用本地 SQLite 保存 Profile Memory 和 Task History，并允许配置 SQLite 文件位置。

#### Scenario: 创建默认 SQLite 数据库
- **WHEN** 用户未显式配置 SQLite 文件位置并启动 Agent Session
- **THEN** 系统在项目目录内默认位置 `.babyface/memory/memory.sqlite3` 创建或复用 SQLite 数据库

#### Scenario: 覆盖 SQLite 文件位置
- **WHEN** 用户通过配置文件或环境变量指定 SQLite 文件位置
- **THEN** 系统使用用户指定的位置创建或复用 SQLite 数据库

#### Scenario: 保存任务历史
- **WHEN** 一轮用户请求完成
- **THEN** 系统保存用户输入、Agent 最终回答、时间戳，并可保存该轮 Tool 调用记录

#### Scenario: 保存用户 Profile 信息
- **WHEN** 用户明确要求 Agent 记住长期个人信息
- **THEN** 系统将该信息保存到 Profile Memory

#### Scenario: 在同一 Session 中传递短期对话历史
- **WHEN** 用户在同一个 CLI Session 中连续进行多轮对话
- **THEN** Agent Runtime 将之前轮次的用户输入和 Agent 回答作为短期记忆传入后续 LLM 推理

#### Scenario: 使用自然语言表达记住偏好
- **WHEN** 用户使用“记住，我不爱吃梅菜扣肉”或“我不爱吃梅菜扣肉，记住它”这类自然语言表达长期记忆请求
- **THEN** 系统将用户希望记住的信息保存到 Profile Memory

### Requirement: 预留未来 RAG 检索接口
系统 SHALL 在 Memory 能力中预留知识检索接口，以支持未来 RAG 迭代，但 V1 不要求实现 embeddings、vector search、chunking 或文档 ingestion。

#### Scenario: 调用 V1 检索接口
- **WHEN** Agent Runtime 调用 Memory 的知识检索接口
- **THEN** 系统返回兼容未来 RAG 的空结果或简单结果，而不是抛出未处理异常

### Requirement: 支持 Babyface 调试模式
系统 SHALL 支持用户通过 `babyface --debug` 启动调试模式，并在未传入该参数时保持普通模式的终端输出和调试持久化行为不变。

#### Scenario: 通过 debug 参数启动调试模式
- **WHEN** 用户运行 `babyface --debug`
- **THEN** 系统进入交互式 Session
- **AND** 系统开启调用链路本地调试记录持久化
- **AND** 系统不在命令行输出调用链路调试记录

#### Scenario: Debug 模式 Banner 标明运行模式
- **WHEN** 用户运行 `babyface --debug`
- **THEN** 启动 Banner 明确展示 `Debug mode`

#### Scenario: 普通模式 Banner 不展示 Debug 标识
- **WHEN** 用户运行 `babyface` 且未传入 `--debug`
- **THEN** 启动 Banner 不展示 `Debug mode`

#### Scenario: 普通模式不写入调试链路
- **WHEN** 用户运行 `babyface` 且未传入 `--debug`
- **THEN** 系统保持现有交互式 Session 行为
- **AND** 系统不创建或写入按日期分隔的调试 SQLite 文件

#### Scenario: Help 展示 debug 参数
- **WHEN** 用户运行 `babyface --help`
- **THEN** CLI help 展示 `--debug` 参数及中文说明

### Requirement: 为 Session 和 Trace 生成唯一 ID
系统 SHALL 在 Babyface 运行期间生成并传播 `session_id` 和 `trace_id`，用于关联调试模式下的调用链路记录。

#### Scenario: 启动时生成 Session ID
- **WHEN** 用户启动 Babyface 交互式 Session
- **THEN** 系统为本次 Session 生成一个唯一 `session_id`
- **AND** 同一 Session 内的所有对话轮次使用相同 `session_id`

#### Scenario: 每轮对话生成 Trace ID
- **WHEN** 用户在 Babyface Session 中提交一次自然语言输入
- **THEN** 系统为该轮对话生成一个唯一 `trace_id`
- **AND** 该轮对话中的用户信息、LLM 信息、工具调用、Skill 调用和最终输出记录使用相同 `trace_id`

#### Scenario: 不同轮次 Trace ID 不同
- **WHEN** 用户在同一个 Babyface Session 中连续提交两次自然语言输入
- **THEN** 系统为两轮对话生成不同的 `trace_id`
- **AND** 两轮对话共享同一个 `session_id`

#### Scenario: Task History 保存 Session 和 Trace ID
- **WHEN** 一轮用户请求完成并写入 Task History
- **THEN** `task_history` 记录保存该轮的 `session_id` 和 `trace_id`

#### Scenario: Tool 调用摘要保存 Session 和 Trace ID
- **WHEN** 一轮用户请求发生 Tool 调用并写入 Tool 调用摘要
- **THEN** `tool_calls` 记录保存该轮的 `session_id` 和 `trace_id`
- **AND** Tool 调用摘要中的 `session_id` 和 `trace_id` 与所属 Task History 记录一致

### Requirement: 通过切面式记录保持调试架构整洁
系统 SHALL 通过统一的调试记录边界采集调用链路信息，避免在 CLI、LLM、Tool 和 Skill 业务逻辑中重复实现 SQLite 持久化逻辑。

#### Scenario: 业务逻辑通过统一调试边界记录事件
- **WHEN** Agent Runtime、LLM 调用、Tool 调用或 Skill 调用需要产生调试记录
- **THEN** 系统通过统一调试记录边界提交调试事件
- **AND** 业务逻辑不直接写入调试 SQLite 表

#### Scenario: 调试模式不输出链路到命令行
- **WHEN** 系统在调试模式下产生任意调用链路调试记录
- **THEN** 系统将该记录写入本地 SQLite
- **AND** 系统不向命令行打印该调用链路调试记录

### Requirement: 持久化调试链路记录
系统 SHALL 在调试模式下把 Agent 内部调用链路的每个关键阶段记录持久化到本地 SQLite 文件，并按系统日期分隔文件。

#### Scenario: 按日期创建调试 SQLite 文件
- **WHEN** 系统日期为 2026 年 8 月 25 日且用户以调试模式启动 Babyface
- **THEN** 系统创建或复用名称为 `debug_trace_20260825` 的本地 SQLite 文件
- **AND** 该文件只保存 2026 年 8 月 25 日产生的调试记录

#### Scenario: 日期变化后写入新文件
- **WHEN** 调试模式下新的调试记录产生时系统日期与当前调试文件日期不同
- **THEN** 系统将新记录写入对应日期名称的调试 SQLite 文件
- **AND** 系统不把新日期记录追加到旧日期文件中

#### Scenario: 持久化用户信息记录
- **WHEN** 调试模式下用户提交一轮输入
- **THEN** 系统在当天调试 SQLite 文件中保存用户信息类型记录
- **AND** 记录包含输入、输出、`session_id`、`trace_id` 和系统时间
- **AND** 记录的阶段名称表示已接受用户输入

#### Scenario: 持久化 LLM 调用前记录
- **WHEN** 调试模式下一轮对话即将触发 LLM 调用
- **THEN** 系统在当天调试 SQLite 文件中保存 LLM 信息类型记录
- **AND** 记录包含 LLM 输入、LLM 模型相关信息、`session_id`、`trace_id` 和系统时间
- **AND** 记录的阶段名称表示 LLM 调用前

#### Scenario: 持久化 LLM 调用后记录
- **WHEN** 调试模式下一轮对话完成 LLM 调用
- **THEN** 系统在当天调试 SQLite 文件中保存 LLM 信息类型记录
- **AND** 记录包含 LLM 输出、LLM 模型相关信息、Tool 调用请求摘要、`session_id`、`trace_id` 和系统时间
- **AND** 记录的阶段名称表示 LLM 调用后

#### Scenario: 持久化 Tool 调用前记录
- **WHEN** 调试模式下一轮对话即将触发 Tool 调用
- **THEN** 系统在当天调试 SQLite 文件中保存工具调用类型记录
- **AND** 记录包含 Tool 名称、输入、`session_id`、`trace_id` 和系统时间
- **AND** 记录的阶段名称表示 Tool 调用前

#### Scenario: 持久化 Tool 调用后记录
- **WHEN** 调试模式下一轮对话完成 Tool 调用
- **THEN** 系统在当天调试 SQLite 文件中保存工具调用类型记录
- **AND** 记录包含 Tool 名称、输出或错误、`session_id`、`trace_id` 和系统时间
- **AND** 记录的阶段名称表示 Tool 调用后

#### Scenario: 持久化 Skill 调用前记录
- **WHEN** 调试模式下一轮对话即将触发 Skill 调用
- **THEN** 系统在当天调试 SQLite 文件中保存 Skill 调用类型记录
- **AND** 记录包含 Skill 名称、输入、`session_id`、`trace_id` 和系统时间
- **AND** 记录的阶段名称表示 Skill 调用前

#### Scenario: 持久化 Skill 调用后记录
- **WHEN** 调试模式下一轮对话完成 Skill 调用
- **THEN** 系统在当天调试 SQLite 文件中保存 Skill 调用类型记录
- **AND** 记录包含 Skill 名称、输出或错误、`session_id`、`trace_id` 和系统时间
- **AND** 记录的阶段名称表示 Skill 调用后

#### Scenario: 调试记录使用固定 ID 字段名
- **WHEN** 系统在调试模式下持久化任意调试记录
- **THEN** 该记录使用 `session_id` 字段保存 Session ID
- **AND** 该记录使用 `trace_id` 字段保存 Trace ID
- **AND** 该记录不得使用 `Session ID`、`Trace ID`、`sessionId` 或 `traceId` 作为字段名

#### Scenario: 调试记录写入失败时 Session 保持可用
- **WHEN** 调试模式下本地 SQLite 调试记录写入失败
- **THEN** CLI 展示中文友好错误提示
- **AND** 当前 Babyface Session 不因调试记录写入失败而崩溃

### Requirement: 保持中文说明性内容
系统 SHALL 使用中文书写工程中的说明性内容，必要的命令名、包名、环境变量名、依赖库名称和代码标识可以保留英文。

#### Scenario: 查看面向用户的说明
- **WHEN** 用户查看 README、需求文档、错误说明或 CLI 帮助信息
- **THEN** 说明性内容以中文为主，技术标识按需保留英文

### Requirement: 保持 Babyface 命名规范
系统 SHALL 在面向用户的说明性内容中统一使用 `Babyface` 或 `BABYFACE`，不得使用其他 camel-case 变体。

#### Scenario: 展示 Agent 名称
- **WHEN** CLI、README、OpenSpec 或错误提示展示 Agent 品牌名称
- **THEN** 系统使用 `Babyface` 或 `BABYFACE`，不展示其他 camel-case 变体
