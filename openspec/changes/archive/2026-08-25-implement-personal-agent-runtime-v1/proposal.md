## Why

当前项目只有一个简单的 HTTP demo，尚未具备本地长期个人助手所需的交互式运行时。现在需要先建立一个最小可运行的本地优先 Agent Runtime，为后续 RAG、Web Search、Dashboard、Scheduler 和 Multi-Agent 演进打基础。

## What Changes

- 新增用户侧命令 `babyface`，运行后进入持续交互式 CLI Session。
- 将 V1 主产品形态从 FastAPI HTTP demo 转为本地 CLI，不提供 HTTP API。
- 新增基于 OpenAI-compatible LLM 的 Agent Loop，并通过 LangGraph 串联主 Workflow。
- 新增 Tool Calling 能力，首版包含 File Tool、Shell Tool 和 Web Tool 占位。
- Shell Tool 执行前必须请求用户二次确认，用户拒绝时返回结构化取消结果。
- 新增基于 SQLite 的本地 Memory，支持 Profile Memory、Task History，并预留未来 RAG 检索接口。
- 新增配置加载能力，API key、模型、base URL、SQLite 文件位置不能硬编码。
- 新增流式输出能力，Agent 最终回答需要在 CLI 中逐步展示。
- 更新项目文档，所有说明性内容统一使用中文。

## Capabilities

### New Capabilities

- `personal-agent-runtime`: 定义本地优先个人 Agent Runtime 的用户可见行为，包括 `babyface` 交互式 CLI、LLM 调用、LangGraph Agent Workflow、Tool Calling、Shell 二次确认、SQLite Memory、流式输出和配置约束。

### Modified Capabilities

- 无。

## Impact

- 影响现有 `main.py` 的主入口定位：后续实现会迁移或替换当前 FastAPI demo，使项目主路径变为本地 CLI。
- 新增 Python package 结构、`pyproject.toml`、`.env.example`、测试目录和中文 README 说明。
- 引入或确认依赖：OpenAI SDK、LangGraph、Pydantic、Typer、Rich、SQLite。
- 新增本地持久化目录，默认 SQLite 文件位置为项目内 `.babyface/memory.sqlite3`，并支持通过配置覆盖。
