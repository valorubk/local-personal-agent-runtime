## Why

Babyface 现在只有文件读取、需确认的 Shell 和 Web 占位工具，无法稳定处理读取本机环境、打开本机 App、访问 HTTP 接口这类常见本地助理任务。这个小迭代补齐低风险本地工具能力，并降低只读 Shell 操作的确认摩擦。

## What Changes

- 增加读取操作系统配置的本地工具，用于返回平台、系统版本、CPU 架构、用户目录、主机名、语言区域等基础信息；不读取当前工作目录、默认 Shell 或环境变量相关信息。
- 增加打开操作系统 App 的本地工具，V1 仅支持 macOS；当用户输入无法直接打开 App 时，枚举现存 App 并选择最接近用户描述的候选。
- 增加发送 HTTP 请求并解析响应的本地工具，支持常见 HTTP 方法、headers、body、timeout，对 JSON 响应自动解析为结构化摘要，并支持有限读取和解析 SSE 响应。
- 调整 Shell Tool 的确认策略：明确只读、安全命令默认不需要用户手动确认；涉及编辑、删除、写入、安装、网络提交或权限提升等风险操作仍必须确认。
- 保持 V1 非目标：不实现跨平台 App 打开、不提供 HTTP API 服务端、不引入浏览器自动化或长期后台任务。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `personal-agent-runtime`: 扩展内置本地 Tool 的用户可见行为，并调整 Shell Tool 对安全只读命令的确认规则。

## Impact

- 影响 `personal_agent/tools/` 下的内置工具实现与工具注册。
- 影响 CLI 启动时注册的内置工具列表。
- 影响 Shell Tool 的安全判定与确认路径。
- 需要新增或更新工具层单元测试，覆盖新工具成功、失败、解析和安全确认场景。
- 可能新增标准库依赖使用；优先不增加第三方运行时依赖。
