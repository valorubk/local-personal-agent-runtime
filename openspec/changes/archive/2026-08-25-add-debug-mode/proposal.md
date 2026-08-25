## Why

Babyface 目前可以执行交互式 Agent Loop，但当 LLM、Tool、Skill 或记忆链路出现异常时，用户很难回溯每一步输入、输出和关联 ID。新增调试模式可以让本地开发和排障具备完整链路记录能力，并把关键节点持久化到本地 SQLite，便于按会话和单轮对话回溯。

## What Changes

- 为 `babyface` CLI 新增 `--debug` 参数；用户运行 `babyface --debug` 时进入调试模式，未传入该参数时保持现有普通交互体验。
- 在每次启动 Babyface 交互式 Session 时生成唯一 `session_id`，同一进程内所有对话轮次共享该 ID。
- 在每次用户与 Babyface 对话时生成唯一 `trace_id`，用于关联该轮对话中的用户输入、LLM 调用、Tool 调用、Skill 调用和最终输出。
- 调试模式下，Agent 内部调用链路的每个关键阶段都持久化到本地 SQLite 文件，至少覆盖接受用户输入后、LLM 调用前、LLM 调用后、Tool 调用前、Tool 调用后、Skill 调用前和 Skill 调用后。
- 调试 SQLite 文件按日期分隔，名称格式为 `debug_trace_YYYYMMDD`，例如 `debug_trace_20260825` 仅保存 2026 年 8 月 25 日的调试记录。
- 调试记录类型至少覆盖用户信息、LLM 信息、工具调用和 Skill 调用。
- 调试采集采用类似切面的方式封装在统一调试记录器中，避免在业务流程中散落重复的持久化代码。
- 调试模式不在命令行输出调用链路调试记录；CLI 仍保持现有 Agent 交互输出。
- V1 非目标：不提供远程调试服务、不实现可视化 Trace UI、不上传调试数据、不改变普通模式下的输出和持久化行为。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `personal-agent-runtime`: 新增 Babyface 调试模式的启动参数、`session_id`/`trace_id` 生成和按日期 SQLite 持久化行为。

## Impact

- 影响 CLI 入口、交互式 Session 生命周期、Agent Runtime 调用链路、LLM 封装、Tool 执行入口、Skill 调用入口和本地 SQLite 存储模块。
- 可能新增调试记录模型、调试 SQLite store、调试事件采集接口和对应测试。
- 需要确保调试模式只在用户显式传入 `--debug` 时开启，不泄露到默认运行路径。
