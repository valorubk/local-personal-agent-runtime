## Why

当前 Babyface 已具备基础 Agent Loop 和内置 File/Shell/Web Tool 占位，但 Tool 来源仍固定在代码内，用户无法通过配置接入自己已有的外部能力。支持外部 Tool 调用与 YAML 配置 MCP Server，可以让本地个人 Agent Runtime 连接文件系统、知识库、业务系统或其他本地服务，同时保持 V1 的本地优先和 CLI 优先形态。

## What Changes

- Agent Runtime 支持从统一 Tool Registry 中发现并调用外部 Tool，并把调用过程、结果和错误纳入现有 CLI 展示与 Agent Loop。
- 新增 YAML 配置文件能力，用于声明一个或多个外部 MCP Server，包括 server 名称、传输方式、启动命令或 HTTP URL、环境变量、请求头、启用状态和超时等基础字段。
- 启动 Babyface Session 时加载 YAML MCP 配置，初始化已启用的 MCP Server，拉取其可用 Tool，并将这些 Tool 暴露给 LLM 选择调用。
- 外部 Tool 调用失败、MCP Server 启动失败、配置文件格式错误或 Tool 名称冲突时，系统给出中文友好错误或降级提示，Session 不因单个外部 Tool 问题崩溃。
- V1 目标聚焦本地 CLI 中的 MCP Server 接入，支持 `stdio` 和 MCP Streamable HTTP 传输；非目标包括通用 HTTP Tool、HTTP API 服务端、远程托管 MCP 管理平台、前端配置页面、复杂权限策略、Scheduler 和 Multi-Agent。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `personal-agent-runtime`: 扩展现有 Agent Loop、Tool 调用展示和配置读取行为，使 Babyface 可以通过 YAML 配置接入外部 MCP Server 并调用其 Tool。

## Impact

- 影响配置加载模块：需要在现有 TOML 运行时配置之外读取 YAML MCP 配置，并定义清晰的默认路径和显式覆盖方式。
- 影响 Agent Runtime 和 LangGraph 节点：需要把外部 MCP Tool 注册到现有 Tool 调用流程，并把 Tool 结果交回 LLM。
- 影响 CLI 渲染：需要复用现有 Tool 调用状态展示，区分内置 Tool 与外部 MCP Tool 的来源。
- 影响依赖：可能需要增加 YAML 解析库、MCP 客户端和 HTTP transport 相关依赖。
- 影响测试：需要覆盖 YAML 配置解析、stdio 与 Streamable HTTP MCP Server 生命周期、Tool Registry、Tool 调用成功/失败、配置错误和 CLI 降级行为。
