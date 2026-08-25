## ADDED Requirements

### Requirement: 通过 YAML 配置外部 MCP Server
系统 SHALL 允许用户通过 YAML 配置文件声明外部 MCP Server，并在启动 Babyface Session 时加载该配置。

#### Scenario: 读取默认 MCP YAML 配置
- **WHEN** 用户未显式指定 MCP 配置路径，且当前项目存在 `.babyface/config/mcp.yaml`
- **THEN** 系统读取该 YAML 文件作为外部 MCP Server 配置

#### Scenario: 通过环境变量覆盖 MCP 配置路径
- **WHEN** 用户设置 `BABYFACE_MCP_CONFIG_PATH` 指向一个 YAML 文件
- **THEN** 系统优先读取该文件作为外部 MCP Server 配置

#### Scenario: 通过运行配置覆盖 MCP 配置路径
- **WHEN** 用户在 Babyface 运行配置中设置 MCP YAML 配置路径
- **THEN** 系统使用该路径读取外部 MCP Server 配置

#### Scenario: 没有 MCP YAML 配置时仍可运行
- **WHEN** 用户未提供任何 MCP YAML 配置文件
- **THEN** 系统仅注册内置 Tool 并正常启动 Session

#### Scenario: MCP YAML 配置格式错误
- **WHEN** 用户提供的 MCP YAML 配置无法解析或缺少必要字段
- **THEN** 系统拒绝启动外部 MCP Server，并展示中文友好错误说明

#### Scenario: 配置 stdio MCP Server
- **WHEN** 用户在 MCP YAML 配置中声明 `transport: stdio`，并提供启动命令和参数
- **THEN** 系统将该配置识别为本地 stdio MCP Server

#### Scenario: 配置 Streamable HTTP MCP Server
- **WHEN** 用户在 MCP YAML 配置中声明 `transport: streamable_http`，并提供 HTTP URL
- **THEN** 系统将该配置识别为 MCP over HTTP Server，而不是通用 HTTP Tool

### Requirement: 管理外部 MCP Server 生命周期
系统 SHALL 在 Babyface Session 生命周期内启动、使用并关闭已启用的外部 MCP Server，且单个 Server 异常不应导致整个 Session 崩溃。

#### Scenario: 启动已启用的 stdio MCP Server
- **WHEN** MCP YAML 配置中存在启用状态的 stdio MCP Server
- **THEN** 系统按配置启动该 Server，并发现其可用 Tool

#### Scenario: 连接已启用的 Streamable HTTP MCP Server
- **WHEN** MCP YAML 配置中存在启用状态的 Streamable HTTP MCP Server
- **THEN** 系统按配置连接该 Server，并发现其可用 Tool

#### Scenario: Streamable HTTP MCP Server 使用请求头
- **WHEN** MCP YAML 配置为 Streamable HTTP MCP Server 声明请求头或鉴权 token
- **THEN** 系统在连接和调用该 MCP Server 时带上对应请求头

#### Scenario: 忽略禁用的 MCP Server
- **WHEN** MCP YAML 配置中存在 `enabled: false` 的 MCP Server
- **THEN** 系统不启动该 Server，也不注册它提供的 Tool

#### Scenario: MCP Server 启动失败
- **WHEN** 某个已启用的 MCP Server 启动失败
- **THEN** 系统展示该 Server 的中文友好失败信息，并继续使用其他可用 Tool 运行 Session

#### Scenario: Streamable HTTP MCP Server 连接失败
- **WHEN** 某个已启用的 Streamable HTTP MCP Server 无法连接、返回非成功 HTTP 状态或握手超时
- **THEN** 系统展示该 Server 的中文友好失败信息，并继续使用其他可用 Tool 运行 Session

#### Scenario: Session 退出时关闭 MCP Server
- **WHEN** 用户输入 `exit`、`quit` 或 `/exit` 退出 Session
- **THEN** 系统关闭本次 Session 打开的 MCP Server 连接和本地子进程

### Requirement: 将外部 MCP Tool 暴露给 Agent 调用
系统 SHALL 将已发现的外部 MCP Tool 注册到 Agent 可用 Tool 列表中，使 LLM 可以按需选择调用。

#### Scenario: LLM 选择调用外部 MCP Tool
- **WHEN** LLM 返回一个指向外部 MCP Tool 的 Tool 调用
- **THEN** 系统执行该 MCP Tool，并将执行结果交回 LLM 生成最终回答

#### Scenario: 外部 MCP Tool 调用成功
- **WHEN** 外部 MCP Tool 返回成功结果
- **THEN** Agent 最终回答可以基于该结果回答用户请求，并在任务历史中保存该 Tool 调用摘要

#### Scenario: 外部 MCP Tool 调用失败
- **WHEN** 外部 MCP Tool 返回错误或调用超时
- **THEN** Session 不崩溃，Agent 基于结构化错误信息继续生成可理解的最终回答

#### Scenario: Streamable HTTP MCP Tool 调用失败
- **WHEN** Streamable HTTP MCP Tool 调用返回 HTTP 错误、协议错误或超时
- **THEN** Session 不崩溃，Agent 基于结构化错误信息继续生成可理解的最终回答

#### Scenario: 外部 MCP Tool 与内置 Tool 名称冲突
- **WHEN** 外部 MCP Tool 的注册名称与已有内置 Tool 或其他外部 Tool 冲突
- **THEN** 系统拒绝注册冲突的外部 Tool，并展示冲突来源说明

### Requirement: 展示外部 MCP Tool 调用过程
系统 SHALL 在 CLI 中展示外部 MCP Tool 的调用状态、来源、结果摘要或错误信息，并与内置 Tool 调用展示保持一致。

#### Scenario: 展示外部 Tool 调用状态
- **WHEN** Agent 调用外部 MCP Tool
- **THEN** CLI 展示 Tool 名称、所属 MCP Server、调用状态和完成结果

#### Scenario: 外部 Tool 调用期间保持最终回答流式输出
- **WHEN** Agent 完成外部 MCP Tool 调用并开始生成最终回答
- **THEN** CLI 继续以流式方式展示最终回答内容

#### Scenario: 外部 Tool 调用错误可读
- **WHEN** 外部 MCP Tool 调用失败
- **THEN** CLI 展示中文友好的错误摘要，且不展示 Python traceback
