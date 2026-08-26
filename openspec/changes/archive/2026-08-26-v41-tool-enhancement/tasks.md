## 1. 测试准备

- [x] 1.1 为 OS Config Tool 增加单元测试，覆盖基础字段、不包含当前工作目录/默认 Shell/环境变量，以及缺省项容错。
- [x] 1.2 为 App Open Tool 增加单元测试，覆盖 macOS 直接命中、近似描述匹配现存 App、无合理候选失败、非 macOS 拒绝、缺少 App 名称和打开失败。
- [x] 1.3 为 HTTP Request Tool 增加单元测试，覆盖 JSON 响应、文本响应、SSE 事件解析、SSE 事件或时间限制、不支持协议和网络异常。
- [x] 1.4 为 Shell Tool 安全确认策略增加单元测试，覆盖安全只读命令自动执行、风险命令仍需确认、用户拒绝和超时。

## 2. 工具实现

- [x] 2.1 实现 OS Config Tool，返回基础操作系统配置摘要，并确保不读取当前工作目录、默认 Shell 或环境变量相关信息。
- [x] 2.2 实现 App Open Tool，仅在 macOS 上先尝试直接打开 App，失败后枚举现存 App 并按用户描述选择达到阈值的最接近候选。
- [x] 2.3 实现 HTTP Request Tool，支持 HTTP/HTTPS 请求、timeout、headers/body、JSON 解析、文本摘要截断和 SSE 有限事件解析。
- [x] 2.4 实现 Shell Tool 安全命令分类器，让明确只读命令绕过确认，未知或风险命令继续请求确认。

## 3. 注册与集成

- [x] 3.1 在 CLI 内置工具列表中注册 OS Config Tool、App Open Tool 和 HTTP Request Tool。
- [x] 3.2 更新必要的导入、包导出或测试辅助代码，确保新工具能通过 `ToolRegistry` 暴露给 Runtime。

## 4. 验证

- [x] 4.1 运行工具层单元测试，确认新工具和 Shell 安全策略符合规格。
- [x] 4.2 运行 Runtime 或 CLI 相关测试，确认新增工具注册不破坏现有 Agent Loop。
- [x] 4.3 运行 OpenSpec 验证，确认本次 change 的规格、设计和任务状态有效。

## 5. App 打开缺陷修复

- [x] 5.1 为 App Open Tool 增加回归测试，覆盖通过本地化显示名把“网易云音乐”匹配到 `NeteaseMusic.app`。
- [x] 5.2 为 Runtime 增加回归测试，覆盖 `app_open` 成功后最终回复只做简短确认。
- [x] 5.3 调整 App Open Tool，优先扫描 macOS 应用目录并读取本地化显示名后再执行打开。
- [x] 5.4 调整 Runtime，让成功的 `app_open` 结果不再触发多余排查建议。
- [x] 5.5 调整 App Open Tool，使无法解码的 `InfoPlist.strings` 不会中断应用目录扫描。
- [x] 5.6 为 Runtime 增加回归测试，覆盖未实际调用 `app_open` 时不得声明 App 打开成功。
- [x] 5.7 调整 Runtime 和系统提示，要求打开本机 App 必须调用 `app_open`，并拦截无工具证据的成功声明。

## 6. HTTP 内容可信度缺陷修复

- [x] 6.1 为 HTTP Request Tool 增加回归测试，覆盖 `urlopen` 的 timeout 必须作为关键字参数传入。
- [x] 6.2 为 HTTP Request Tool 增加回归测试，覆盖 gzip HTML 解压和网页标题提取。
- [x] 6.3 为 Runtime 增加回归测试，覆盖用户询问网页标题时必须使用 HTTP Tool 的标题 metadata。
- [x] 6.4 修复 HTTP Request Tool 的真实 `urlopen` 调用参数、gzip 解压、charset 解码和 HTML 标题解析。
- [x] 6.5 调整 Runtime，让标题类问题优先返回 HTTP Tool 解析出的可信标题。
- [x] 6.6 替换默认 `web_search` 占位工具，CLI 内置工具列表只暴露真实可用的 `http_request` 网页请求能力。
- [x] 6.7 为 HTTP Request Tool 增加回归测试，覆盖默认浏览器风格请求头和用户请求头覆盖默认值。
- [x] 6.8 修复 HTTP Request Tool 的默认请求头，降低真实网页返回 412 等拒绝状态的概率。
