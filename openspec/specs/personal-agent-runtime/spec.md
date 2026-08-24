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
- **THEN** 系统尝试读取用户目录下的 `~/.babyface/config.toml`

#### Scenario: 缺少 API key
- **WHEN** 用户未配置 API key
- **THEN** 系统拒绝启动需要 LLM 的 Agent Session，并显示清晰的中文错误说明

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
- **THEN** 系统在项目目录内默认位置 `.babyface/memory.sqlite3` 创建或复用 SQLite 数据库

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

### Requirement: 保持中文说明性内容
系统 SHALL 使用中文书写工程中的说明性内容，必要的命令名、包名、环境变量名、依赖库名称和代码标识可以保留英文。

#### Scenario: 查看面向用户的说明
- **WHEN** 用户查看 README、需求文档、错误说明或 CLI 帮助信息
- **THEN** 说明性内容以中文为主，技术标识按需保留英文
