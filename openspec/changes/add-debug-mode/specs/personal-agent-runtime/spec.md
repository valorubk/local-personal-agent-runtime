## ADDED Requirements

### Requirement: 支持 Babyface 调试模式
系统 SHALL 支持用户通过 `babyface --debug` 启动调试模式，并在未传入该参数时保持普通模式的终端输出和调试持久化行为不变。

#### Scenario: 通过 debug 参数启动调试模式
- **WHEN** 用户运行 `babyface --debug`
- **THEN** 系统进入交互式 Session
- **AND** 系统开启调用链路本地调试记录持久化
- **AND** 系统不在命令行输出调用链路调试记录

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
