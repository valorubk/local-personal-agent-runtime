## 1. 测试准备

- [ ] 1.1 为 OS Config Tool 增加单元测试，覆盖基础字段、敏感环境变量脱敏和缺省项容错。
- [ ] 1.2 为 App Open Tool 增加单元测试，覆盖 macOS 成功调用、非 macOS 拒绝、缺少 App 名称和打开失败。
- [ ] 1.3 为 HTTP Request Tool 增加单元测试，覆盖 JSON 响应、文本响应、不支持协议和网络异常。
- [ ] 1.4 为 Shell Tool 安全确认策略增加单元测试，覆盖安全只读命令自动执行、风险命令仍需确认、用户拒绝和超时。

## 2. 工具实现

- [ ] 2.1 实现 OS Config Tool，返回非敏感操作系统配置摘要并避免泄露敏感环境变量值。
- [ ] 2.2 实现 App Open Tool，仅在 macOS 上按 App 名称请求系统打开应用，并结构化返回成功或失败。
- [ ] 2.3 实现 HTTP Request Tool，支持 HTTP/HTTPS 请求、timeout、headers/body、JSON 解析和文本摘要截断。
- [ ] 2.4 实现 Shell Tool 安全命令分类器，让明确只读命令绕过确认，未知或风险命令继续请求确认。

## 3. 注册与集成

- [ ] 3.1 在 CLI 内置工具列表中注册 OS Config Tool、App Open Tool 和 HTTP Request Tool。
- [ ] 3.2 更新必要的导入、包导出或测试辅助代码，确保新工具能通过 `ToolRegistry` 暴露给 Runtime。

## 4. 验证

- [ ] 4.1 运行工具层单元测试，确认新工具和 Shell 安全策略符合规格。
- [ ] 4.2 运行 Runtime 或 CLI 相关测试，确认新增工具注册不破坏现有 Agent Loop。
- [ ] 4.3 运行 OpenSpec 验证，确认本次 change 的规格、设计和任务状态有效。
