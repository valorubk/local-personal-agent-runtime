## ADDED Requirements

### Requirement: 支持读取操作系统配置 Tool
系统 SHALL 提供本地操作系统配置读取 Tool，用于返回非敏感的系统与运行环境摘要，帮助 Agent 回答与当前设备和系统基础配置相关的问题。

#### Scenario: 读取基础系统配置
- **WHEN** Agent 调用操作系统配置读取 Tool
- **THEN** Tool 返回操作系统名称、系统版本、CPU 架构、用户目录、主机名、语言区域和是否为 macOS 的结构化文本摘要

#### Scenario: 不读取目录 Shell 和环境变量
- **WHEN** Agent 调用操作系统配置读取 Tool
- **THEN** Tool 不得返回当前工作目录、默认 Shell 或任何环境变量相关信息

#### Scenario: 操作系统配置读取失败
- **WHEN** Tool 无法读取某项操作系统配置
- **THEN** Tool 不应导致 Session 崩溃，并在结果中标明该项不可用

### Requirement: 支持打开操作系统 App Tool
系统 SHALL 提供打开操作系统 App 的本地 Tool，允许 Agent 根据用户意图请求系统打开本机应用；V1 仅支持 macOS。

#### Scenario: 在 macOS 直接打开命中的 App
- **WHEN** Agent 调用打开 App Tool 并提供 App 名称，且当前系统是 macOS
- **THEN** Tool 请求系统打开对应 App，并返回包含 App 名称和执行状态的结构化结果

#### Scenario: 按描述打开最接近的 App
- **WHEN** Agent 调用打开 App Tool 并提供 App 描述，且该输入无法直接打开任何 App
- **THEN** Tool 枚举当前系统已安装 App，选择与用户描述最接近且达到匹配阈值的 App，并请求系统打开该 App

#### Scenario: 没有足够接近的 App 候选
- **WHEN** Agent 调用打开 App Tool 并提供 App 描述，但已安装 App 中没有达到匹配阈值的候选
- **THEN** Tool 不打开任何 App，并返回结构化错误说明没有找到足够接近的应用

#### Scenario: 非 macOS 系统拒绝打开 App
- **WHEN** Agent 调用打开 App Tool，且当前系统不是 macOS
- **THEN** Tool 不执行打开动作，并返回清晰说明当前仅支持 macOS 的结构化错误

#### Scenario: 缺少 App 名称
- **WHEN** Agent 调用打开 App Tool 但未提供 App 名称
- **THEN** Tool 返回结构化错误，说明缺少 App 名称

#### Scenario: 打开 App 失败
- **WHEN** 系统无法打开指定 App
- **THEN** Tool 返回结构化错误，并保留可用于排查的状态信息

### Requirement: 支持 HTTP Request Tool
系统 SHALL 提供 HTTP Request Tool，用于发送一次 HTTP 请求并返回状态码、响应头摘要和响应体解析结果。

#### Scenario: 发送 GET 请求
- **WHEN** Agent 调用 HTTP Request Tool 并提供 HTTP 或 HTTPS URL
- **THEN** Tool 发送请求并返回 HTTP 状态码、响应头摘要和响应体内容摘要

#### Scenario: 解析 JSON 响应
- **WHEN** HTTP 响应体是合法 JSON
- **THEN** Tool 返回可读的 JSON 格式化内容，并在 metadata 中标明响应类型为 JSON

#### Scenario: 返回文本响应
- **WHEN** HTTP 响应体不是合法 JSON 但可作为文本读取
- **THEN** Tool 返回文本内容摘要，并在 metadata 中标明响应类型为文本

#### Scenario: 解析 SSE 响应
- **WHEN** HTTP 响应 Content-Type 是 `text/event-stream`
- **THEN** Tool 按 SSE 格式读取有限数量的事件，返回事件摘要，并在 metadata 中标明响应类型为 SSE

#### Scenario: SSE 响应达到事件或时间限制
- **WHEN** HTTP Request Tool 读取 SSE 响应达到最大事件数、最大读取时长或连接中断
- **THEN** Tool 返回已经收集到的事件摘要，并在 metadata 中标明停止原因

#### Scenario: URL 协议不受支持
- **WHEN** Agent 调用 HTTP Request Tool 并提供非 HTTP/HTTPS URL
- **THEN** Tool 不发送请求，并返回结构化错误，说明仅支持 HTTP 和 HTTPS

#### Scenario: HTTP 请求超时或网络失败
- **WHEN** HTTP 请求超时或发生网络错误
- **THEN** Tool 返回结构化错误，且 Session 不崩溃

## MODIFIED Requirements

### Requirement: 支持需确认的 Shell Tool
系统 SHALL 提供 Shell Tool，用于执行本地命令；安全的只读命令无需用户手动确认，风险命令执行前必须请求用户二次确认，并返回 stdout、stderr 和 exit code。

#### Scenario: 安全只读命令无需用户确认
- **WHEN** Agent 请求执行被判定为安全只读的 shell 命令
- **THEN** Tool 直接执行命令，并返回 stdout、stderr 和 exit code

#### Scenario: 用户确认执行命令
- **WHEN** Agent 请求执行涉及编辑、删除、写入、安装、网络提交或权限提升等风险操作的 shell 命令，并且用户确认执行
- **THEN** Tool 执行命令，并返回 stdout、stderr 和 exit code

#### Scenario: 用户拒绝执行命令
- **WHEN** Agent 请求执行风险 shell 命令，但用户拒绝执行
- **THEN** Tool 不执行命令，并返回“用户取消执行”的结构化结果

#### Scenario: 命令超时
- **WHEN** Shell Tool 执行命令超过配置的超时时间
- **THEN** Tool 终止该命令并返回结构化超时错误
