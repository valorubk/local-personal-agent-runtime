## 1. 调试数据模型与存储

- [ ] 1.1 新增调试事件数据模型，字段覆盖事件类型、名称、输入、输出、metadata、`Session ID`、`Trace ID` 和系统时间。
- [ ] 1.2 新增本地系统时间格式化工具，输出格式固定为 `YYYY-MM-DD HH:MM:SS`，并补充单元测试。
- [ ] 1.3 新增按日期生成调试 SQLite 文件路径的函数，默认目录为 `.babyface/debug/`，文件名为 `debug_trace_YYYYMMDD`，并补充单元测试。
- [ ] 1.4 新增 `DebugTraceStore`，负责创建 `debug_trace_events` 表并写入调试事件。
- [ ] 1.5 为 `DebugTraceStore` 补充 SQLite 写入、按日期换文件和 JSON metadata 保存测试。

## 2. 调试记录器与命令行输出

- [ ] 2.1 新增 `DebugTraceRecorder`，统一接收调试事件并分发到命令行输出和 SQLite store。
- [ ] 2.2 新增普通模式下的空调试记录器或禁用路径，确保未开启 `--debug` 时不会输出或写入调试记录。
- [ ] 2.3 实现调试事件终端格式化，稳定输出事件类型、输入、输出、`Session ID`、`Trace ID` 和系统时间。
- [ ] 2.4 补充调试记录器在 SQLite 写入失败时输出中文友好提示且不中断调用方的测试。

## 3. CLI Session 接入

- [ ] 3.1 为 Typer CLI 新增 `--debug` 参数，并在 `babyface --help` 中展示中文说明。
- [ ] 3.2 在 Babyface Session 启动时生成唯一 `Session ID`，并传入 Runtime 或调试上下文。
- [ ] 3.3 在真实 Rich CLI 中接入调试记录器，调试模式下输出调试事件，普通模式保持现有输出。
- [ ] 3.4 在可测试的 `CLISession` 抽象中补充调试依赖注入能力，便于单元测试验证调试输出。

## 4. Agent Runtime 链路埋点

- [ ] 4.1 在每次 `run_turn()` 开始时生成唯一 `Trace ID`，并确保同一轮调用链路复用该 ID。
- [ ] 4.2 在用户输入清洗后记录用户信息类型调试事件，并在最终回答生成后记录对应输出。
- [ ] 4.3 在 LLM 调用前后记录 LLM 信息类型调试事件，包含 messages、tool schema 摘要、模型信息、输出内容和 tool calls。
- [ ] 4.4 在 Tool 执行前后记录工具调用类型调试事件，包含 Tool 名称、arguments、content、error 和 metadata。
- [ ] 4.5 在 post-turn Skill 维护服务调用前后记录 Skill 调用类型调试事件，包含 Skill 名称、输入上下文、输出或错误。
- [ ] 4.6 确认 Shell Tool 二次确认流程不被调试模式绕过，并记录确认后的 Tool 结果。

## 5. 集成验证与文档

- [ ] 5.1 补充 Runtime 单元测试，验证同一 Session 多轮对话共享 `Session ID` 且每轮 `Trace ID` 不同。
- [ ] 5.2 补充 CLI 测试，验证 `babyface --debug` 开启调试输出，普通 `babyface` 不输出调试链路。
- [ ] 5.3 补充 SQLite 集成测试，验证系统日期为 2026 年 8 月 25 日时写入 `debug_trace_20260825`。
- [ ] 5.4 补充 README 或配置说明，提示调试模式会记录内部输入输出，并说明本地 SQLite 文件位置。
- [ ] 5.5 运行完整测试套件，并记录验证命令和结果。
