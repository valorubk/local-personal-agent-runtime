## 1. 测试边界调整

- [x] 1.1 新增维护服务单元测试，覆盖无长期偏好时不写入 `AGENTS.md`
- [x] 1.2 新增维护服务单元测试，覆盖有长期偏好时自动写入全局 managed section
- [x] 1.3 新增维护服务单元测试，覆盖冲突整理时使用 LLM 返回的 managed section 规则列表
- [x] 1.4 新增维护服务单元测试，覆盖明确长期偏好表达触发兜底重试
- [x] 1.5 调整 Runtime 测试，验证 `enable_agents_update=False` 时不调用 maintenance 服务
- [x] 1.6 调整 Runtime 测试，验证 `enable_agents_update=True` 时在 Task History 保存和短期历史更新后调用 maintenance 服务

## 2. 维护服务抽离

- [x] 2.1 新增 `AgentsMdMaintenanceService` 所在模块和中文注释，定义 post-turn maintenance 的职责边界
- [x] 2.2 新增 `PostTurnMaintenanceContext`，封装清洗后的用户输入、最终回答和 `AGENTS.md` 路径上下文
- [x] 2.3 将 `AgentsUpdateCandidate`、`AgentsUpdateProposal` 或等价数据结构迁移到维护模块
- [x] 2.4 将候选判断 prompt、强制抽取 prompt、冲突整理 prompt 迁移到维护模块
- [x] 2.5 将 JSON 解析、明确偏好启发式判断、目标路径解析迁移到维护模块
- [x] 2.6 在维护服务中复用 `build_agents_prompt()` 和 `replace_managed_preferences()`，避免复制确定性文件处理逻辑
- [x] 2.7 保持维护服务当前为同步 `run(context)` 接口，不引入异步 worker，同时避免 Runtime 依赖服务内部实现细节

## 3. Runtime 编排改造

- [x] 3.1 修改 `AgentRuntime.__init__()`，支持注入维护服务并在启用自动更新时创建默认服务
- [x] 3.2 修改 `run_turn()`，在主 Agent Loop、Task History 保存和短期历史更新完成后调用维护服务
- [x] 3.3 删除 Runtime 中的 `AGENTS.md` 候选判断、冲突整理、JSON 解析和 managed section 写入细节方法
- [x] 3.4 保持 LangGraph 节点结构不变，确认 maintenance 不进入主 Agent Loop
- [x] 3.5 保持 CLI 入口行为不变，继续通过 `enable_agents_update=True` 开启自动写入流程
- [x] 3.6 确认 Runtime 不引入后台任务、退出等待或并发写入管理逻辑，为未来异步化保留在 service 内部演进的空间

## 4. 验证与收尾

- [x] 4.1 运行维护服务相关单元测试，确认自动写入行为与原先一致
- [x] 4.2 运行 Runtime 相关单元测试，确认主循环、Task History、短期历史和 post-turn 调用顺序正确
- [x] 4.3 运行 `AGENTS.md` prompt profile 相关测试，确认分层拼接和 managed section 写入安全边界未变化
- [x] 4.4 检查代码中不再从 Runtime 直接暴露维护细节，确保职责边界符合 design
- [x] 4.5 按项目规范提交本次实现相关改动
