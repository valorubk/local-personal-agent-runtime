## Why

当前 `AGENTS.md` 自动更新逻辑虽然运行在主 Agent Loop 之后，但候选判断、冲突整理、JSON 解析、目标路径解析和 managed section 写入编排都放在 `AgentRuntime` 内部。这让 Runtime 同时承担任务执行和 prompt/记忆维护职责，边界不够清晰，也不利于未来把该能力升级为独立的 Memory/Prompt Steward Agent。

本次变更需要在不改变现有用户可见行为的前提下，把 post-turn prompt maintenance 从 Runtime 中抽离为独立服务，使 Runtime 只负责编排调用。

## What Changes

- 新增独立的 `AGENTS.md` post-turn maintenance 服务，用于承载自动更新 `AGENTS.md` 的候选判断、目标文件读取、冲突整理、写入提案构造和 managed section 写入流程。
- `AgentRuntime` 在每轮主 Agent Loop 完成、Task History 保存、短期对话历史更新之后调用 maintenance 服务，不再直接包含 prompt 更新判断、冲突整理、JSON 解析和 managed section 写入细节。
- 保持现有自动写入行为不变：有长期偏好候选时，系统仍在 post-turn 自动写入对应目标 `AGENTS.md` 的 managed section，不新增用户确认步骤。
- 保持现有安全边界不变：多层 `AGENTS.md` 拼接仍不使用 LLM 合并；LLM 只允许在写入单个目标 `AGENTS.md` 前整理该文件的 managed section；不得改写 managed section 外的用户手写内容。
- 为 Runtime 与 maintenance 服务补充职责边界测试，确保 Runtime 只编排调用，维护细节集中在新服务中。

## Capabilities

### New Capabilities

无。该变更不引入新的用户可见能力。

### Modified Capabilities

无。该变更保持 `personal-agent-runtime` 中 `AGENTS.md` 自动更新的现有行为不变，仅调整内部架构边界。

## Impact

- 影响 `personal_agent.agent.runtime` 中 post-turn `AGENTS.md` 自动更新相关代码。
- 可能新增 `personal_agent.agent.maintenance`、`personal_agent.prompt_maintenance` 或等价模块，用于封装维护服务和数据结构。
- 继续复用 `personal_agent.prompt_profile` 中确定性的 `AGENTS.md` 发现、拼接和 managed section 写入工具。
- 影响现有 `tests/test_runtime.py` 中直接验证 Runtime 写入细节的测试，需要拆分为 service 测试和 Runtime 编排测试。
- 不新增外部依赖，不改变 CLI 命令入口，不改变 LangGraph 主循环节点。
