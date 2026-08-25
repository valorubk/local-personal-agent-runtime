## Why

当前 `AGENTS.md` 自动更新逻辑虽然运行在主 Agent Loop 之后，但候选判断、冲突整理、JSON 解析、目标路径解析和 managed section 写入编排都放在 `AgentRuntime` 内部。这让 Runtime 同时承担任务执行和 prompt/记忆维护职责，边界不够清晰，也不利于未来把该能力升级为独立的 Memory/Prompt Steward Agent。

本次变更需要把 post-turn prompt maintenance 从 Runtime 中抽离为独立服务，使 Runtime 只负责编排调用。同时收紧 `AGENTS.md` 自动写入触发条件：只有用户明示要求 Babyface 记住或长期采用某条偏好时，系统才允许进入 `AGENTS.md` 更新判断。

## What Changes

- 新增独立的 `AGENTS.md` post-turn maintenance 服务，用于承载自动更新 `AGENTS.md` 的候选判断、目标文件读取、冲突整理、写入提案构造和 managed section 写入流程。
- `AgentRuntime` 在每轮主 Agent Loop 完成、Task History 保存、短期对话历史更新之后调用 maintenance 服务，不再直接包含 prompt 更新判断、冲突整理、JSON 解析和 managed section 写入细节。
- 收紧自动写入入口：用户没有明示“记住”“以后”“每次”“固定”等长期记忆意图时，系统不得调用 `AGENTS.md` 更新判断 LLM，也不得写入 `AGENTS.md`。
- 保持确认行为不变：用户明示长期偏好且 LLM 生成候选规则时，系统仍在 post-turn 自动写入对应目标 `AGENTS.md` 的 managed section，不新增用户确认步骤。
- 当前实现保持同步 post-turn 调用，不引入后台异步队列；服务接口需要保持清晰，未来可以在不改变 Runtime 编排边界的前提下替换为异步队列或独立 Memory/Prompt Steward Agent。
- 保持现有安全边界不变：多层 `AGENTS.md` 拼接仍不使用 LLM 合并；LLM 只允许在写入单个目标 `AGENTS.md` 前整理该文件的 managed section；不得改写 managed section 外的用户手写内容。
- 为 Runtime 与 maintenance 服务补充职责边界测试，确保 Runtime 只编排调用，维护细节集中在新服务中。

## Capabilities

### New Capabilities

无。该变更不引入新的用户可见能力。

### Modified Capabilities

- `personal-agent-runtime`: `AGENTS.md` 自动写入从“每轮任务后由 LLM 判断是否沉淀”调整为“只有用户明示要求记住或长期采用偏好后，才进入 LLM 判断与写入流程”。

## Impact

- 影响 `personal_agent.agent.runtime` 中 post-turn `AGENTS.md` 自动更新相关代码。
- 可能新增 `personal_agent.agent.maintenance`、`personal_agent.prompt_maintenance` 或等价模块，用于封装维护服务和数据结构。
- 继续复用 `personal_agent.prompt_profile` 中确定性的 `AGENTS.md` 发现、拼接和 managed section 写入工具。
- 影响现有 `tests/test_runtime.py` 中直接验证 Runtime 写入细节的测试，需要拆分为 service 测试和 Runtime 编排测试。
- 不新增外部依赖，不改变 CLI 命令入口，不改变 LangGraph 主循环节点，不引入异步 worker 或后台任务生命周期管理。
