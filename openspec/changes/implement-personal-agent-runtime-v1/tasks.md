## 1. 项目骨架与配置

- [ ] 1.1 创建 `personal_agent/` package 结构，包含 CLI、agent、tools、memory 模块目录。
- [ ] 1.2 新增 `pyproject.toml`，声明 Python 3.12、依赖和 `babyface` console command。
- [ ] 1.3 新增 `.env.example`，覆盖 LLM 配置、SQLite 路径和 Shell 超时时间示例。
- [ ] 1.4 新增 `.gitignore` 规则，忽略 `.env`、`.babyface/`、Python 缓存和测试缓存。
- [ ] 1.5 实现配置加载模块，支持环境变量和项目内配置文件，并在缺少 API key 时返回中文错误。

## 2. CLI Session

- [ ] 2.1 使用 Typer 创建 `babyface` CLI 入口。
- [ ] 2.2 使用 Rich 实现持续交互式 Session、中文欢迎提示和退出命令。
- [ ] 2.3 实现 Markdown 格式回答渲染。
- [ ] 2.4 实现 Agent 活动展示，包括 Tool 调用开始、成功、失败和取消状态。
- [ ] 2.5 实现最终回答流式输出的 CLI 展示路径。

## 3. Tool Calling

- [ ] 3.1 定义 Tool 基础协议、输入 schema、结构化结果模型和 Tool Registry。
- [ ] 3.2 实现只读 File Tool，覆盖成功读取、文件不存在和读取失败。
- [ ] 3.3 实现 Shell Tool，返回 `stdout`、`stderr`、exit code，并支持超时。
- [ ] 3.4 为 Shell Tool 接入用户二次确认回调，拒绝时返回结构化取消结果。
- [ ] 3.5 实现 Web Tool 占位，返回中文未实现结果。
- [ ] 3.6 为 File Tool、Shell Tool、Web Tool 添加单元测试。

## 4. Memory

- [ ] 4.1 实现 SQLite 初始化逻辑，默认使用 `.babyface/memory.sqlite3`。
- [ ] 4.2 支持通过配置文件或环境变量覆盖 SQLite 文件位置。
- [ ] 4.3 实现 Profile Memory 保存与读取。
- [ ] 4.4 实现 Task History 保存，记录用户输入、最终回答、时间戳和可选 Tool 调用摘要。
- [ ] 4.5 实现未来 RAG 使用的 `retrieve_knowledge(query)` 接口，V1 返回兼容的空结果或简单结果。
- [ ] 4.6 为 Memory Store 添加单元测试。

## 5. Agent Runtime 与 LangGraph Workflow

- [ ] 5.1 实现 OpenAI-compatible LLM client 封装，支持普通调用和流式输出。
- [ ] 5.2 实现可测试的 Agent Runtime facade，接收用户输入、配置、Memory Store 和 Tool Registry。
- [ ] 5.3 使用 LangGraph 串联加载 Memory、调用 LLM、执行 Tool、生成最终回答、持久化历史的主 Workflow。
- [ ] 5.4 实现 Tool 调用循环的最大轮数限制，避免无限循环。
- [ ] 5.5 将 Tool 结果和 Tool 错误交回 LLM 继续推理。
- [ ] 5.6 使用 fake LLM client 覆盖无需 Tool、需要 Tool、Tool 失败和用户取消 Shell 的 Agent Loop 测试。

## 6. 入口迁移与文档

- [ ] 6.1 移除或降级现有 FastAPI demo，确保 V1 主路径是 `babyface` CLI。
- [ ] 6.2 确认代码中不存在硬编码 API key。
- [ ] 6.3 更新 README，使用中文说明安装、配置、运行、退出和 Shell 二次确认行为。
- [ ] 6.4 保留 `docs/requirements/personal-agent-runtime-v1.md` 作为中文需求源，并与 OpenSpec artifact 互相引用。

## 7. 验证

- [ ] 7.1 运行单元测试并修复失败。
- [ ] 7.2 本地安装或以 editable 方式运行项目，确认 `babyface` 命令可用。
- [ ] 7.3 验证无 API key 时 CLI 给出中文错误。
- [ ] 7.4 使用 fake 或测试配置验证多轮交互、Tool 展示、Shell 拒绝执行和 Memory 写入。
- [ ] 7.5 运行 OpenSpec 校验，确认 change artifact 通过验证。
