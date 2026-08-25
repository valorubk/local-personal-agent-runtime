## Context

参见 `proposal.md` 的动机说明。当前 `AgentRuntime` 已经把 `AGENTS.md` 加载和拼接委托给 `personal_agent.prompt_profile`，但 post-turn 自动更新仍集中在 Runtime 内部：Runtime 直接持有候选判断 prompt、强制抽取 prompt、冲突整理 prompt、JSON 解析、目标路径解析和最终写入调用。

现有 LangGraph 主循环是 `prepare -> llm -> (tools -> llm)* -> finalize`。`AGENTS.md` 自动更新发生在 `run_turn()` 结束阶段，不属于 LangGraph 节点；本次设计保持这一点不变。

## Goals / Non-Goals

**Goals:**

- 让 `AgentRuntime` 只负责任务执行编排：清洗输入、显式 Memory 保存、运行 LangGraph、生成 stream、保存 Task History、更新短期历史、调用 post-turn maintenance。
- 新增 `AgentsMdMaintenanceService`，集中管理 `AGENTS.md` 自动更新细节，并提供清晰的输入上下文和输出结果。
- 保持现有自动写入行为：不新增用户确认；无候选规则时不写入；有候选规则时按目标层级写入 managed section。
- 当前版本保持同步 post-turn maintenance，避免引入后台队列、并发写入和 CLI 退出等待语义。
- 保持现有安全边界：多层 `AGENTS.md` 拼接不做 LLM 合并；LLM 只整理单个目标文件的 managed section；写入函数只替换 managed section。
- 让测试能清楚区分 Runtime 编排责任与 maintenance 服务责任。

**Non-Goals:**

- 不实现独立 Agent、Multi-Agent、后台 Scheduler、异步队列或后台 worker 生命周期管理。
- 不改变 `AGENTS.md` 的发现顺序、拼接格式、managed section 标记格式或默认写入目标。
- 不改变 Shell Tool 二次确认逻辑；本次维护服务不复用 Shell Tool 的确认机制。
- 不改变 SQLite Memory 的存储位置、表结构或 Task History 写入时机。
- 不改变 CLI 的用户交互形态，不增加 `AGENTS.md` 写入确认提示。

## Decisions

### 1. 新增同步维护服务，而不是把逻辑放进 LangGraph 节点

`AgentsMdMaintenanceService` 暴露一个同步入口，例如 `run(context: PostTurnMaintenanceContext) -> AgentsMdMaintenanceResult | None`。Runtime 在 Task History 保存和短期历史更新之后调用它。

选择同步服务的原因是：当前行为已经是 post-turn 附加流程，失败时不应影响主回答；把它放进 LangGraph 节点会模糊主 Agent Loop 与维护流程边界，也会让维护 LLM 调用被误解为任务推理的一部分。

备选方案是新增 LangGraph maintenance 节点，但该方案会把 prompt 维护纳入主循环图，不符合“主 Agent Loop 只负责理解请求、调用工具、生成最终回答”的边界。

### 2. 用上下文对象固定 Runtime 与维护服务的接口

新增 `PostTurnMaintenanceContext`，包含本轮维护所需的最小输入：

- `user_input`：清洗后的用户输入。
- `final_response`：清洗后的最终回答。
- `agents_home`、`current_dir`、`workspace_root`：用于读取已加载 `AGENTS.md` 上下文和解析写入目标。

服务内部继续调用 `build_agents_prompt()` 读取当前已加载的 `AGENTS.md`，避免 Runtime 传入由维护流程专用的 prompt 字符串。这样 Runtime 不需要理解候选判断所需的上下文细节，只传一轮任务事实和路径边界。

备选方案是让 Runtime 传入完整 `loaded_agents_prompt`。该方案能减少一次文件读取，但会让 Runtime 知道维护 LLM 的输入结构，边界不够干净。

### 3. 维护服务拥有 LLM prompt、JSON 解析和候选重试策略

`AGENTS_UPDATE_JUDGE_PROMPT`、`AGENTS_UPDATE_FORCED_EXTRACTION_PROMPT`、`AGENTS_CONFLICT_RESOLUTION_PROMPT`、`_load_json_object()` 和 `_looks_like_explicit_agents_preference()` 从 Runtime 移入维护模块。服务负责：

1. 判断本轮是否产生长期候选规则。
2. 对明确长期偏好表达进行保守兜底重试。
3. 解析 LLM JSON，非 JSON 或空偏好时静默跳过。
4. 读取单个目标 `AGENTS.md`。
5. 让 LLM 生成整理后的 managed section 规则列表。
6. 调用 `replace_managed_preferences()` 写入。

Runtime 只持有一个可选的 `agents_md_maintenance` 依赖和 `enable_agents_update` 开关，不再暴露 `_judge_agents_update_candidate()`、`_resolve_agents_update_conflicts()`、`_resolve_agents_update_path()` 这类维护细节方法。

### 4. 写入仍自动发生，但输出结果可审计

维护服务返回结果对象，例如 `AgentsMdMaintenanceResult`，用于测试和未来审计扩展。结果中可包含目标路径、候选规则、整理后的规则列表和冲突整理说明。

V1 不把该结果展示给用户，也不要求用户确认。`AgentRuntime.run_turn()` 可以忽略返回值，保持 CLI 用户体验不变。

### 5. `prompt_profile.py` 继续承担确定性文件操作

`personal_agent.prompt_profile` 继续负责：

- 发现分层 `AGENTS.md`。
- 拼接原文 prompt。
- 创建或替换 managed section。
- 保留 managed section 外用户手写内容。

维护服务只编排这些确定性工具和 LLM 判断，不复制 managed section 字符串处理逻辑。这样安全边界集中在一个低层模块中，service 层只决定“写哪些规则到哪个目标文件”。

### 6. 当前保持同步执行，但接口预留异步演进空间

`AgentsMdMaintenanceService` 的逻辑天然可以后台化，因为它发生在主回答生成之后，不参与本轮用户请求的理解、工具调用和最终回答生成。但 V1 不直接异步执行，原因是异步化会额外引入三类复杂度：

1. 连续多轮对话时，上一轮维护任务可能尚未写入，下一轮已经读取 system prompt，导致用户以为偏好已经沉淀但下一轮尚未生效。
2. 多个后台维护任务可能同时读写同一个 `AGENTS.md`，需要文件锁、串行队列或版本检查，否则可能出现后写覆盖先写。
3. CLI 退出时需要定义是否等待后台任务完成、失败如何记录、是否影响退出体验，这些都超出当前 V1 边界。

因此当前实现采用同步 `run(context)`：Runtime 在 Task History 和短期历史都完成后调用它，维护流程完成后本轮 `run_turn()` 才返回。接口保持在 context/result 边界上，未来可以把服务内部替换为串行队列或 Steward Agent，而不把异步细节泄漏回 Runtime。

## Risks / Trade-offs

- Runtime 测试如果继续断言写入细节，会掩盖边界调整是否成功 → 拆分测试：Runtime 只验证 post-turn 调用时机和禁用开关；维护服务测试验证候选、冲突整理、目标解析和写入。
- 服务抽离后依赖注入对象增多，初始化路径可能变复杂 → 默认构造 `AgentsMdMaintenanceService(llm=self.llm, ...)`，测试可显式注入 fake service。
- post-turn maintenance 失败可能影响用户主流程 → 保持现有容错原则：LLM 非 JSON 时跳过；如果写入路径或文件操作异常，本次任务主回答、Task History 和短期历史已经完成。实现阶段需要决定是否吞掉所有维护异常或仅保持现状；倾向于让维护流程自身尽量容错，不扩大主流程失败面。
- 同步维护会让一轮 `run_turn()` 在主回答生成后多等待维护 LLM 调用 → 这是当前 V1 为换取确定写入顺序、简单测试和清晰退出语义接受的成本；后续如体验上明显变慢，再通过同一 service 接口演进为串行异步队列。
- 未来升级为独立 Steward Agent 时，当前同步接口可能需要演进 → 先用清晰 context/result 边界隔离 Runtime，后续可把 service 内部实现替换为 Agent，而不改变 Runtime 调用位置。

## Migration Plan

1. 新增维护模块和数据结构，把 Runtime 中 `AGENTS.md` 自动更新相关 prompt、数据类、解析函数和流程方法迁移进去。
2. 修改 `AgentRuntime.__init__()`，支持注入维护服务；未注入且启用自动更新时创建默认服务。
3. 修改 `run_turn()`，在 Task History 保存和短期历史更新后调用维护服务，并保持返回值不变。
4. 调整测试：新增维护服务单元测试覆盖原有自动写入场景；Runtime 测试改为验证调用边界。
5. 运行相关单元测试，确认 `AGENTS.md` 加载、自动更新和 Runtime 主循环行为保持兼容。

回滚策略：如果抽离后出现问题，可以把 `AgentRuntime` 的维护服务依赖临时关闭，主 Agent Loop、Task History 和短期记忆仍能保持可用。
