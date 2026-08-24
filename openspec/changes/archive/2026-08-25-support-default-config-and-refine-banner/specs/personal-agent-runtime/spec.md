## MODIFIED Requirements

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
