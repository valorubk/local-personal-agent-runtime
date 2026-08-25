## 1. 配置与依赖

- [x] 1.1 在项目依赖中加入 YAML 解析和 MCP 客户端所需依赖，并确认锁文件更新；JSON 解析优先使用 Python 标准库。
- [x] 1.2 扩展 `Settings` 和配置加载逻辑，支持 `BABYFACE_MCP_CONFIG_PATH`、TOML 字段 `mcp_config_path`、默认 `.babyface/config/mcp.json` 和默认 `.babyface/config/mcp.yaml`。
- [x] 1.3 为 MCP JSON/YAML 配置解析新增单元测试，覆盖默认缺省、环境变量覆盖、TOML 覆盖、无文件不报错、stdio 配置、Streamable HTTP 配置、生态常见 `mcpServers`/`disabled` 字段和格式错误。

## 2. MCP 配置模型与 Server 生命周期

- [x] 2.1 新增 MCP 配置模型，校验 server 名称、启用状态、transport、command、args、url、headers、env 和 timeout 字段。
- [x] 2.2 新增 MCP Server 管理器，支持 stdio Server 启动、Streamable HTTP Server 连接、跳过禁用 Server、收集失败信息和关闭连接。
- [x] 2.3 使用 fake MCP client 为 Server 管理器编写单元测试，覆盖 stdio 启动成功、HTTP 连接成功、启动或连接失败、禁用 Server 和退出关闭。

## 3. 外部 Tool 适配与注册

- [x] 3.1 新增 MCP Tool 适配器，将 MCP Tool 描述和 input schema 转换为现有 `Tool` 协议。
- [x] 3.2 调整 `ToolRegistry`，显式检测重复 Tool 名称并返回中文可读冲突错误。
- [x] 3.3 为 MCP Tool 适配器和 Tool 名称冲突编写单元测试，覆盖 stdio 调用成功、HTTP 调用成功、调用失败、调用超时和 schema 不可转换。

## 4. Agent Runtime 与 CLI 接入

- [x] 4.1 在 CLI Session 创建 Runtime 前加载 MCP 配置并初始化 MCP 管理器，把外部 MCP Tool 与内置 Tool 一起注册。
- [x] 4.2 确保外部 MCP Tool 调用复用现有 LangGraph Tool Loop、Debug Trace、Task History 和最终回答流式展示。
- [x] 4.3 在 CLI 中展示 MCP Server 启动降级提示、外部 Tool 来源、调用状态、结果摘要和中文错误信息。
- [x] 4.4 为 CLI 接入编写测试，覆盖无 MCP 配置仍可启动、stdio Server 启动失败后降级运行、HTTP Server 连接失败后降级运行、外部 Tool 调用结果进入最终回答。

## 5. 文档与验证

- [x] 5.1 更新 README，说明 MCP JSON/YAML 默认路径和覆盖方式，优先推荐 JSON 配置文件，并分别给出 JSON 与 YAML 的 stdio、Streamable HTTP 示例，明确 V1 不提供通用 HTTP Tool。
- [x] 5.2 运行配置、Tool、Runtime、CLI 相关单元测试并修复失败。
- [x] 5.3 运行 OpenSpec 校验，确认 `add-agent-tool-calling` 的 proposal、spec、design 和 tasks 都可通过验证。
