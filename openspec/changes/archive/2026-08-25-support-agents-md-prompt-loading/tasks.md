## 1. AGENTS.md 加载器

- [x] 1.1 新增独立 prompt profile 模块，定义 `AGENTS.md` 的发现、读取和拼接入口
- [x] 1.2 实现 `~/.babyface/AGENTS.md` 全局层读取，缺失文件时返回空外部指令
- [x] 1.3 实现工作区根目录到当前工作目录之间的 `AGENTS.md` 查找顺序
- [x] 1.4 为每个被读取的 `AGENTS.md` 在拼接结果中加入稳定来源边界
- [x] 1.5 为加载器补充单元测试，覆盖无文件、全局文件、多层文件、空文件、局部优先顺序和冲突原文保留

## 2. Runtime Prompt 接入

- [x] 2.1 将 Babyface 内置基础指令保留为代码内默认 prompt
- [x] 2.2 在 Agent Runtime 准备 LLM messages 时注入“内置基础规则 + 分层 AGENTS.md”组合 prompt
- [x] 2.3 保持 Memory 上下文作为独立 system message，不并入 `AGENTS.md` prompt
- [x] 2.4 在内置 prompt 中加入冲突处理说明，明确后出现的局部指令优先且不得总结改写 `AGENTS.md`
- [x] 2.5 为 runtime 补充回归测试，验证缺少 `AGENTS.md` 时行为保持兼容
- [x] 2.6 为 runtime 补充测试，验证外部 `AGENTS.md` 原文进入第一条 system message

## 3. 受控偏好写入

- [x] 3.1 定义 `~/.babyface/AGENTS.md` 中 Babyface managed section 的标记格式
- [x] 3.2 实现全局 managed section 写入工具函数
- [x] 3.3 确保写入时保留 managed section 外的用户手写内容
- [x] 3.4 确保项目级 `AGENTS.md` 不会在没有用户明确要求时被自动修改
- [x] 3.5 为 managed section 创建、追加、去重和保留手写内容补充单元测试

## 4. 文档与规格同步

- [x] 4.1 更新 README，说明 `AGENTS.md` 的全局和项目层级读取规则
- [x] 4.2 更新 README，给出推荐的 `AGENTS.md` section 结构和 Babyface managed section 示例
- [x] 4.3 更新主规格 `openspec/specs/personal-agent-runtime/spec.md`，同步本 change 的用户可见行为
- [x] 4.4 扫描说明性内容，确保只使用 `Babyface` 或 `BABYFACE`，不使用其他 camel-case 变体

## 5. 验证

- [x] 5.1 运行 OpenSpec 校验，确认 change delta 格式有效
- [x] 5.2 运行 Python 单元测试，确认现有行为和新增行为都通过
- [x] 5.3 手动检查最终 prompt 拼接样例，确认来源边界和层级顺序易读

## 6. LLM 辅助偏好更新

- [x] 6.1 定义每轮任务后的 `AGENTS.md` 更新候选数据结构
- [x] 6.2 实现 LLM 判断 prompt，要求返回严格 JSON 并限制每轮最多一条候选规则
- [x] 6.3 在 Runtime 主流程完成任务后触发可选更新检查
- [x] 6.4 后台写入候选规则和冲突解决结果，不向用户展示更新细节
- [x] 6.5 冲突时只替换 managed section 中 LLM 指定的旧规则，不改写用户手写内容
- [x] 6.6 在真实 CLI 中开启后台 AGENTS.md 自动更新流程
- [x] 6.7 补充单元测试覆盖无更新、后台自动写入和冲突替换
- [x] 6.8 对明确长期偏好请求增加 LLM 抽取重试，避免首次判断 false 时静默跳过
