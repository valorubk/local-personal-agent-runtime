# 本地优先个人 Agent Runtime V1 需求说明

## 1. 背景

本项目目标是构建一个运行在本地电脑上的个人 AI 助理运行时。
它的交互体验可以参考 Claude Code，但核心用途不是代码开发，而是作为长期个人助手，帮助用户管理信息、执行任务、辅助学习、整理上下文并提升效率。

V1 的重点是先跑通最小可用的 Agent Runtime，而不是一次性做成完整产品。

## 2. 文档语言规范

工程中的说明性内容统一使用中文书写。

适用范围包括：

- 需求文档
- 设计文档
- 实现计划
- README 中的说明文字
- 面向用户的 CLI 提示语
- 错误说明与帮助信息

以下内容可以保留英文：

- 命令名，例如 `babyface`
- Python 包名、模块名、类名、函数名
- 环境变量名，例如 `OPENAI_API_KEY`
- 依赖库名称，例如 `Typer`、`Rich`、`LangGraph`
- 代码片段、目录结构、配置字段
- 外部产品或协议的正式名称

## 3. V1 目标

实现一个本地交互式 CLI，命令名为 `babyface`。

用户运行：

```bash
babyface
```

后进入一个持续对话 Session：

```text
$ babyface

> 帮我总结最近的 Agent 学习内容
Agent:
...

> 帮我分析我的面试准备情况
Agent:
...
```

V1 成功标准是：用户可以在本地运行 `babyface`，与 LLM 驱动的 Agent 连续对话，看到 Agent 调用工具，并把基础个人记忆持久化到 SQLite。

## 4. V1 非目标

V1 暂不实现以下能力：

- 不提供 HTTP API。
- 不提供前端页面。
- 不引入 Docker 或云部署。
- 不实现生产级认证、权限系统或沙箱隔离。
- 不实现完整 RAG。
- 不实现 Scheduler。
- 不实现 Multi-Agent 编排。
- 不实现 Web Dashboard。
- 不实现复杂插件市场。

当前仓库中的 FastAPI demo 不再作为主路径。V1 的主要产品形态是本地 CLI。

## 5. 命令与 CLI 体验

### 5.1 命令名

用户侧命令必须是：

```bash
babyface
```

实现上可以通过 Python packaging 的 console scripts 暴露，也可以先提供轻量级本地运行方式。
但面向用户的入口命令是 `babyface`，不是 `personal-agent`。

### 5.2 交互式 Session

CLI 必须支持：

- 运行 `babyface` 后启动一个持续 Session。
- 反复接收自然语言输入。
- Session 持续运行，直到用户主动退出。
- 支持 `exit`、`quit`、`/exit` 等退出命令。
- 在终端中渲染 Markdown 格式回答。
- 以类似 Claude Code 的风格展示 Agent 活动：
  - 用户输入提示
  - Agent 回复
  - Tool 调用开始
  - Tool 调用结果或错误
  - 可选的思考或进度提示

### 5.3 流式输出

V1 必须支持流式响应。

CLI 需要在 Agent 生成最终回答时逐步展示内容，避免用户在长回复场景中只能等待完整结果。
如果某些中间 Tool 调用不适合流式展示，也需要至少展示清晰的执行状态。

## 6. Agent 运行时

### 6.1 Agent 循环

运行时必须实现基础 Agent Loop：

1. 读取用户输入。
2. 加载相关 Memory 上下文。
3. 将对话历史、Memory 和可用 Tool 定义发送给 LLM。
4. 由 LLM 判断是否需要调用 Tool。
5. 在本地执行 Tool。
6. 将 Tool 结果返回给 LLM 继续推理。
7. 将最终回答渲染给用户。
8. 持久化任务历史，以及明确需要保存的用户信息。

### 6.2 工作流

V1 必须使用 LangGraph 表达 Agent Workflow，同时保持图结构简单。

可接受的最小图结构包括：

- input node
- LLM node
- tool execution node
- memory persistence node
- final response node

不采用长期手写 Runtime Loop 作为 V1 主实现。
可以在测试或局部封装中保留轻量辅助函数，但主流程需要通过 LangGraph 串联。

### 6.3 LLM Provider 配置

运行时使用 OpenAI SDK 或 OpenAI-compatible endpoint 调用模型。

配置必须来自环境变量或本地配置文件，不能在代码中硬编码 API key。

预期配置项：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`，可选
- `OPENAI_MODEL`，可选，需要有合理默认值

## 7. Tool Calling 能力

V1 必须支持本地 Tool Calling，并提供一个轻量 Tool Registry。

### 7.1 File Tool 文件读取工具

File Tool 用于读取本地文本文件。

必需行为：

- 接收文件路径。
- 读取文件内容。
- 返回文件内容或结构化错误。
- 能处理文件不存在的情况。
- 读取失败时不能导致 Session 崩溃。

V1 只需要支持只读文件访问。

### 7.2 Shell Tool 命令执行工具

Shell Tool 用于执行本地 shell 命令。

必需行为：

- 接收命令字符串。
- 在本地执行命令。
- 返回 `stdout`、`stderr` 和 exit code。
- 命令失败时不能导致 Session 崩溃。
- 必须设置超时时间。

V1 可以默认信任本地用户，不需要实现完整权限模型。
但 Tool 调用必须在终端中可见，用户能看到 Agent 正在执行什么。
Shell 命令执行前必须进行用户二次确认。
用户确认后才允许执行；用户拒绝时，Tool 返回“用户取消执行”的结构化结果，并将该结果交回 Agent 继续推理。

### 7.3 Web Tool 占位

Web Tool 在 V1 中只需要提供接口或 stub。

必需行为：

- 明确返回 Web 能力尚未实现。
- 保持接口形状，方便后续接入 web search 或 browser tool。

## 8. Memory 记忆能力

V1 必须包含基于 SQLite 的简单本地 Memory。

初版 SQLite 文件默认放在项目目录内，建议默认位置为 `.babyface/memory.sqlite3`。
SQLite 文件位置必须支持通过配置文件或环境变量覆盖，方便后续迁移到用户级目录或自定义路径。

### 8.1 Profile Memory

Profile Memory 用于保存长期用户信息。

示例：

- 用户偏好
- 学习目标
- 面试准备状态
- 反复出现的个人上下文

V1 可以采用简单 key-value 或 record-based 结构。

### 8.2 Task History

Task History 用于保存历史任务记录。

必需行为：

- 保存用户输入。
- 保存 Agent 最终回答。
- 保存时间戳。
- 可选保存该轮任务使用过的 Tool 调用。

### 8.3 未来 RAG 接口

Memory 模块需要预留清晰的知识检索接口。

V1 不需要实现 embeddings、vector search、chunking 或文档 ingestion。

## 9. 建议代码结构

实现应保持模块化，但不要过度工程化：

```text
personal_agent/
├── __init__.py
├── main.py              # Typer CLI 入口
├── config.py            # 环境变量与配置加载
├── cli/
│   ├── __init__.py
│   └── session.py       # 交互式终端循环
├── agent/
│   ├── __init__.py
│   ├── runtime.py       # Agent Loop
│   └── workflow.py      # LangGraph Workflow 或兼容占位
├── tools/
│   ├── __init__.py
│   ├── base.py          # Tool 协议与 schema
│   ├── file_tool.py
│   ├── shell_tool.py
│   └── web_tool.py
└── memory/
    ├── __init__.py
    ├── store.py         # SQLite 持久化
    └── models.py
```

项目级文件可以包括：

```text
pyproject.toml
README.md
.env.example
tests/
```

包需要暴露 console command：

```text
babyface = personal_agent.main:app
```

## 10. 依赖

目标技术栈：

- Python 3.12
- OpenAI SDK，用于 LLM 调用
- LangGraph，用于 Agent Workflow，V1 中以简单为优先
- Pydantic，用于数据模型
- Typer，用于 CLI 入口
- Rich，用于终端 UI 和 Markdown 渲染
- SQLite，可使用 Python 标准库或轻量封装

## 11. V1 验收清单

### 11.1 CLI

- [ ] 运行 `babyface` 可以启动交互式 Session。
- [ ] 用户可以连续提交多轮自然语言输入。
- [ ] 用户可以干净退出 Session。
- [ ] Agent 输出可以以 Markdown 格式渲染。
- [ ] Agent 最终回答支持流式输出。
- [ ] 终端中可以看到 Tool 调用过程。

### 11.2 LLM

- [ ] Runtime 可以调用 OpenAI-compatible LLM。
- [ ] API key 从环境变量或配置读取，不能硬编码。
- [ ] 配置缺失时给出清晰错误。

### 11.3 Agent Loop

- [ ] Agent 可以判断是否需要调用 Tool。
- [ ] Agent 主流程由 LangGraph 串联。
- [ ] Tool 结果会进入最终推理。
- [ ] Tool 错误不会导致 Session 崩溃。

### 11.4 Tools

- [ ] File Tool 可以读取存在的本地文本文件。
- [ ] File Tool 可以清晰报告文件缺失或不可读。
- [ ] Shell Tool 可以执行简单命令。
- [ ] Shell Tool 执行前必须请求用户二次确认。
- [ ] 用户拒绝执行 Shell 命令时，Session 不崩溃，并将取消结果返回 Agent。
- [ ] Shell Tool 返回 `stdout`、`stderr` 和 exit code。
- [ ] Shell Tool 有超时机制。
- [ ] Web Tool 占位存在，并返回清晰的未实现结果。

### 11.5 Memory

- [ ] 可以在本地创建 SQLite 数据库。
- [ ] SQLite 默认文件位置在项目目录内。
- [ ] SQLite 文件位置可以通过配置文件或环境变量覆盖。
- [ ] 可以保存用户 Profile 信息。
- [ ] 每轮完成后可以保存 Task History。
- [ ] Memory 模块暴露未来 RAG 检索接口。

### 11.6 Packaging

- [ ] 项目可以在本地安装或运行。
- [ ] Console command 名为 `babyface`。
- [ ] README 说明安装、配置和首次运行方式。

## 12. 推荐实现顺序

建议按以下顺序实现：

1. 创建 Python package skeleton 和 `pyproject.toml`。
2. 添加配置加载与 `.env.example`。
3. 实现基于 Rich 和 Typer 的交互式 CLI。
4. 实现 File Tool、Shell Tool 和 Web Tool 占位。
5. 实现 SQLite Memory Store。
6. 实现 LLM Client 和基础 Agent Loop 节点。
7. 使用 LangGraph 串联 V1 主 Workflow。
8. 将 CLI Session 接入 Agent Runtime。
9. 实现最终回答流式输出。
10. 为 Tools、Memory 和 Runtime 行为添加聚焦测试。
11. 更新 README，说明 `babyface` 的使用方式。

## 13. 后续演进路径

### 13.1 V2：Memory + RAG + Web Search

- 增加文档 ingestion。
- 增加 embeddings 和 vector retrieval。
- 实现真实 Web Search。
- 使用 Memory Retrieval 增强 Agent 上下文。

### 13.2 V3：Dashboard

- 增加 Next.js Dashboard。
- 展示 Task History、Memory 和 Tool 活动。
- 提供个人知识源管理入口。

### 13.3 V4：Scheduler + Multi-Agent + Automation

- 增加定时任务。
- 增加周期性个人自动化。
- 增加专用 Sub-agent。
- 增加更细的本地动作权限与安全控制。

## 14. 已确认技术决策

以下决策已经确认，后续实现需要按此执行：

- V1 立即使用 LangGraph 作为主 Workflow 实现。
- Shell 命令在执行前必须请求用户二次确认。
- V1 包含流式输出。
- SQLite 文件默认放在项目目录内。
- SQLite 文件位置必须支持通过配置文件或环境变量配置。
