## Context

参见 `proposal.md` 的动机说明。当前代码已经有 `Settings`、`Tool` 协议、`ToolRegistry`、LangGraph Agent Loop、CLI Tool 调用展示、SQLite Task History 和 Debug Trace。外部 MCP 能力应复用这些扩展点，避免绕开现有 File/Shell/Web Tool 的执行与记录路径。

## Goals / Non-Goals

**Goals:**

- 通过 JSON 或 YAML 文件声明 stdio 或 Streamable HTTP MCP Server，并在 Babyface Session 启动时加载，其中 README 优先推荐 JSON。
- 把 MCP Server 暴露的 Tool 适配为现有 `Tool` 协议，让 Runtime 不关心 Tool 来自内置实现还是外部 MCP。
- 在 LangGraph `tools` 节点中复用现有 Tool 调用闭环、Debug Trace、Task History 和 CLI 展示。
- 保持 Shell Tool 二次确认逻辑只作用于内置 Shell Tool；MCP Tool 的风险在 V1 中通过“显式配置启用”表达。
- 保持 Memory SQLite 默认位置 `.babyface/memory/memory.sqlite3` 不变；MCP 配置使用独立路径。

**Non-Goals:**

- 不实现通用 HTTP Tool。Agent 不能在本次需求中任意 GET/POST 用户给出的 URL；HTTP 只作为 MCP 协议传输使用。
- 不实现 HTTP API 服务端、远程 MCP 管理平台、插件市场或插件安装器。
- 不提供前端或交互式配置向导。
- 不实现细粒度权限策略、每次 MCP Tool 调用前确认、审计后台或 Multi-Agent。
- 不改变现有内置 Tool 的 OpenAI schema 与行为。

## Decisions

### Decision: MCP 配置使用独立 JSON/YAML 文件

在 `Settings` 中新增 `mcp_config_path: Path | None`，读取优先级为：`BABYFACE_MCP_CONFIG_PATH` 环境变量、TOML 运行配置中的 `mcp_config_path`、项目默认 `.babyface/config/mcp.json`、项目默认 `.babyface/config/mcp.yaml`。如果默认文件不存在，则视为未配置 MCP，不报错。

README 优先建议使用 JSON，因为现有 MCP 客户端生态常见 `mcp.json`、`.cursor/mcp.json`、`.vscode/mcp.json` 和 `cline_mcp_settings.json` 这类注册方式，用户从第三方 MCP Server 页面复制配置时摩擦更小。JSON 建议结构：

```json
{
  "mcpServers": {
    "filesystem": {
      "enabled": true,
      "transport": "stdio",
      "command": "uvx",
      "args": ["mcp-server-filesystem", "."],
      "env": {
        "EXAMPLE_ENV": "value"
      },
      "timeout_seconds": 10
    },
    "docs": {
      "enabled": true,
      "transport": "streamable_http",
      "url": "https://example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${DOCS_MCP_TOKEN}"
      },
      "timeout_seconds": 30
    }
  }
}
```

YAML 作为等价兼容格式，适合用户手写较长配置或需要注释的场景：

```yaml
mcp_servers:
  filesystem:
    enabled: true
    transport: stdio
    command: "uvx"
    args: ["mcp-server-filesystem", "."]
    env:
      EXAMPLE_ENV: "value"
    timeout_seconds: 10
  docs:
    enabled: true
    transport: streamable_http
    url: "https://example.com/mcp"
    headers:
      Authorization: "Bearer ${DOCS_MCP_TOKEN}"
    timeout_seconds: 30
```

同时兼容 `mcpServers` / `mcp_servers` 和 `disabled` / `enabled`。备选方案是只支持 YAML，但这会让用户难以直接复用 MCP 生态页面给出的 JSON 注册片段；另一个备选方案是把 MCP 配置塞进 `babyface.toml`，但这会让 LLM/API key 等运行配置与外部工具清单混在一起，也不利于未来单独分享 MCP 配置。

### Decision: 新增 MCP 配置解析与客户端边界

新增 `personal_agent/mcp/config.py` 解析 JSON 或 YAML，并用 Pydantic 或 dataclass 做字段校验：server 名称、`enabled`、`disabled`、`transport`、`command`、`args`、`url`、`headers`、`env`、`timeout_seconds`。配置错误抛出 `ConfigError`，CLI 继续以中文友好错误展示。

新增 `personal_agent/mcp/client.py` 管理 MCP Server 的生命周期：对 stdio Server 启动子进程并初始化会话；对 Streamable HTTP Server 创建 HTTP transport、执行 MCP 初始化、保存必要 session 状态；统一负责列出 Tool、执行 Tool、关闭连接。该模块是唯一直接依赖 MCP SDK 与 HTTP transport 的地方，降低外部协议变化对 Runtime 的影响。

备选方案是在 CLI 入口直接启动 MCP Server，但那会让配置、生命周期和 Tool 适配散落在 Session 层，后续测试也会更难。

### Decision: HTTP 能力只服务于 MCP 协议

V1 支持 MCP Streamable HTTP transport，但不暴露独立的 `http_request` 或类似通用 HTTP Tool。HTTP URL、headers、session id、超时和协议错误都由 MCP 客户端层处理，Agent Runtime 只看到已经适配好的 MCP Tool。

这样可以满足接入外部 HTTP MCP Server 的需求，同时避免一次性引入任意 HTTP 请求带来的 SSRF、鉴权泄漏、响应裁剪、用户确认和网络访问策略问题。通用 HTTP Tool 可以在后续以独立 OpenSpec change 设计。

### Decision: MCP Tool 适配为现有 Tool 协议

新增 `McpToolAdapter`，对每个外部 MCP Tool 暴露：

- `name`：采用 `server_name__tool_name` 这类只包含字母、数字、下划线和连字符的命名空间格式，降低与内置 Tool 冲突概率，并兼容 OpenAI tool/function name 约束。
- `description`：来自 MCP Tool 描述，并追加来源说明。
- `to_openai_tool()`：把 MCP Tool input schema 转成 OpenAI tool calling schema。
- `run(arguments)`：调用对应 MCP Tool，并返回统一 `ToolResult`。

`ToolResult.metadata` 记录 `source: "mcp"`、`server`、`tool`、耗时、超时或底层错误摘要。这样 CLI、Memory 和 Debug Trace 可以展示来源，而不需要理解 MCP 协议细节。

### Decision: ToolRegistry 显式处理名称冲突

当前 `ToolRegistry` 通过 dict 直接按 name 建索引，重复名称会被后注册 Tool 覆盖。实现时应改为显式校验重复名称，并返回或抛出中文配置错误，说明冲突 Tool 名称和来源。

备选方案是自动重命名冲突 Tool，但 LLM 看到的工具名称会变得不可预测，不利于用户调试 JSON/YAML 配置。

### Decision: LangGraph Agent Loop 基本保持不变

Runtime 仍使用：

`prepare -> llm -> (tools -> llm)* -> finalize`

外部 MCP Tool 在进入 Runtime 前就已经被注册进 `ToolRegistry`，所以 `_call_llm()` 继续通过 `list_openai_tools()` 把所有 Tool 暴露给 LLM，`_run_tools()` 继续通过 `run(name, arguments)` 执行。这样 Tool 成功、失败、达到迭代上限、Debug Trace 和 Task History 都复用现有路径。

外部 MCP Tool 调用期间不流式输出 Tool 结果；完成 Tool 调用并进入最终 LLM 回答后，继续复用当前最终回答流式展示策略。后续若 LLM SDK 支持更细粒度流式事件，可单独扩展。

### Decision: CLI Session 负责打开和关闭 MCP Runtime

CLI Session 创建 `AgentRuntime` 前，先根据 `Settings.mcp_config_path` 初始化 MCP 管理器，获得外部 Tool 列表后与内置 Tool 一起构造 `ToolRegistry`。Session 退出时在 `finally` 中关闭 MCP 管理器，避免 stdio 子进程残留。

如果某个 MCP Server 启动或连接失败，管理器记录错误并跳过该 Server；只要仍有可用内置 Tool 或其他 MCP Tool，Session 继续运行，并在启动阶段向用户展示降级提示。

## Risks / Trade-offs

- MCP Server 可能执行高风险本地操作 → V1 通过用户显式 JSON/YAML 配置、默认不启用和清晰来源展示降低误用风险；细粒度权限放到后续迭代。
- MCP SDK 或协议细节变化 → 把 MCP 依赖隔离在 `personal_agent/mcp/`，Runtime 只依赖现有 `Tool` 协议。
- 外部 Tool input schema 可能不兼容 OpenAI tool schema → 适配层在注册时校验并拒绝不可转换 Tool，提示用户具体 Server 和 Tool。
- stdio 子进程或 HTTP MCP 请求可能挂起 → 每个 Server 和 Tool 调用使用 `timeout_seconds`，Session 退出时统一关闭连接和本地子进程。
- Streamable HTTP MCP Server 可能需要鉴权或 session 头 → JSON/YAML 支持 headers 配置，客户端层负责保存和复用 MCP session 状态，错误时只展示摘要，不把敏感 header 打印到 CLI。
- YAML 增加新依赖 → JSON 优先用标准库解析；YAML 选择维护良好的轻量解析库，并用配置解析单元测试锁定错误信息。

## Migration Plan

1. 增加依赖与配置字段后，默认行为保持不变：没有 MCP JSON/YAML 文件时只加载内置 Tool。
2. 新增 MCP 配置解析、Tool 适配器和管理器，并用 fake MCP client 覆盖 stdio 与 Streamable HTTP 单元测试。
3. 在 CLI Session 构造 Runtime 前接入 MCP 管理器，确保异常降级和退出关闭都可测试。
4. 更新 README，优先给出 JSON 配置示例，同时给出 YAML 等价示例，并明确本次不提供通用 HTTP Tool。
5. 回滚时删除 MCP JSON/YAML 配置或取消 `BABYFACE_MCP_CONFIG_PATH` 即可恢复到内置 Tool 模式。
