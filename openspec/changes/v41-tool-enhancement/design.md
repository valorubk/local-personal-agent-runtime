## Context

当前内置 Tool 通过 `ToolRegistry` 注入 `AgentRuntime`，CLI 在启动时注册 `FileTool`、`ShellTool` 和 `WebTool`。Tool 返回统一的 `ToolResult`，Runtime 只负责把 Tool schema 交给 LLM、执行工具并将结果回传给 LLM；因此本次迭代应继续保持“工具内部处理参数校验与错误隔离，Runtime 不关心具体工具”的边界。

## Goals / Non-Goals

**Goals:**

- 新增三个内置本地 Tool，并在 CLI 启动时默认注册。
- 让每个 Tool 都能被单元测试独立覆盖，不依赖真实 LLM。
- Shell Tool 增加安全只读命令自动放行逻辑，同时保留风险命令确认。
- HTTP Request Tool 优先使用 Python 标准库完成请求和解析，减少依赖面。

**Non-Goals:**

- 不实现跨平台打开 App；非 macOS 明确返回不支持。
- 不把 Web Tool 占位替换成搜索能力。
- 不引入浏览器控制、后台调度、MCP 服务端或 HTTP API 服务端。
- 不支持复杂 HTTP 会话、Cookie 持久化、重试队列或流式下载。

## Decisions

### 1. 新工具保持“一类一文件”的结构

新增 `os_config_tool.py`、`app_tool.py` 和 `http_tool.py`，每个类实现现有 Tool 协议。这样注册表、Runtime 和 CLI 不需要理解工具细节，只需在内置工具列表中追加实例。

备选方案是把多个小工具合并到一个 `system_tool.py` 中，通过 action 参数分派。该方案文件数更少，但 schema 更粗，模型更难选择正确工具，测试也更容易耦合；本次选择独立工具。

### 2. 操作系统配置读取只返回低敏摘要

OS Config Tool 返回平台、版本、架构、主机名、用户目录、当前目录、Shell、语言区域等基础信息。环境变量只允许返回白名单项，或者返回敏感变量已隐藏的摘要；任何名称包含 `KEY`、`TOKEN`、`SECRET`、`PASSWORD`、`CREDENTIAL` 的变量值都不得进入结果。

备选方案是返回完整 `os.environ` 后让模型自行判断，但这会把敏感信息暴露给 LLM，不符合本地优先的安全边界。

### 3. macOS 打开 App 使用系统 `open -a`

App Open Tool 在 macOS 上使用系统命令打开 App，并捕获 exit code、stdout、stderr。工具参数只接收 App 名称，不暴露任意 shell 命令字符串，从接口层减少注入风险。非 macOS 直接返回不支持。

备选方案是复用 Shell Tool 执行 `open -a`，但这会让 App 打开能力混入 Shell 确认策略，也让 LLM 更容易生成任意命令；独立 Tool 的用户意图和安全边界更清楚。

### 4. HTTP Request Tool 使用标准库并限制协议

HTTP Request Tool 使用 `urllib.request` 发送请求，只允许 `http` 和 `https`。请求参数支持 method、url、headers、body、timeout_seconds。响应体按字节读取后尝试 UTF-8 解码和 JSON 解析；JSON 成功时返回格式化 JSON，失败时返回文本摘要。响应内容需要设置最大字符数，避免把超大响应塞进 LLM 上下文。

备选方案是引入 `requests` 或 `httpx`。它们更易用，但本项目目前依赖面较小，本次能力用标准库足够。

### 5. Shell 安全策略用显式分类器

Shell Tool 增加一个独立可测试的命令分类函数：只对明确的只读命令自动放行，例如 `pwd`、`ls`、`cat`、`sed -n`、`head`、`tail`、`wc`、`rg`、`find` 的非删除形式、`git status`、`git diff`、`git log`、`git show`、`python -m pytest` 等。含有重定向写入、管道到风险命令、`rm`、`mv`、`cp`、`touch`、`mkdir`、`chmod`、`chown`、`sudo`、包管理安装、`git commit`、`git push` 等命令时要求确认。

备选方案是通过 denylist 判断风险命令，未命中就放行。该方案漏判风险的概率更高；本次采用 allowlist 优先，未知命令默认确认。

### 6. LangGraph 与 CLI 装配保持不变

LangGraph Agent Loop 不需要新增节点；工具 schema 会随 `ToolRegistry.list_openai_tools()` 自动传给 LLM。CLI 仍只展示工具名称、成功失败和错误，工具详情由 `ToolResult.content` 与 metadata 承载。Shell 二次确认仍由 CLI 注入回调，安全只读命令会在 Tool 内部绕过该回调。

### 7. 流式输出与 SQLite 位置不受影响

本次只扩展工具执行层。最终回答仍由现有 Runtime 在 Tool 调用结束后生成并流式展示；Memory SQLite 路径继续沿用现有配置与迁移逻辑，不新增存储字段。

## Risks / Trade-offs

- [Risk] Shell 安全分类过宽会带来误操作风险。→ Mitigation：使用 allowlist 优先，未知命令默认走确认；测试覆盖典型安全和风险命令。
- [Risk] Shell 安全分类过窄会让部分只读命令仍需确认。→ Mitigation：先覆盖项目开发常用只读命令，后续按实际使用逐步扩展 allowlist。
- [Risk] HTTP Tool 可能读取到过大的响应。→ Mitigation：限制返回内容长度，并在 metadata 中记录是否截断。
- [Risk] HTTP Tool 访问内网或本机地址可能产生安全争议。→ Mitigation：本次保持为用户本机主动请求能力，不持久化凭证；未来如需要可增加 host denylist 或确认策略。
- [Risk] macOS App 名称可能不存在或系统返回错误。→ Mitigation：捕获 exit code 与 stderr，返回结构化失败，不让 Session 崩溃。

## Migration Plan

1. 新增工具类和 Shell 安全分类器。
2. 在 CLI 内置工具列表注册新工具。
3. 更新单元测试覆盖新工具和 Shell 确认策略。
4. 运行工具层与 Runtime 相关测试确认现有行为不回退。

回滚时可移除新工具注册并恢复 Shell Tool 始终确认的行为；由于不涉及数据迁移，回滚不需要处理 SQLite。
