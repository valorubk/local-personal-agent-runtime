## Why

Babyface 当前在代码中使用固定的 system prompt，用户无法通过稳定文件自定义 Agent 行为，也无法让偏好在新 Session 中自动生效。引入分层 `AGENTS.md` 可以让全局偏好、项目规则和局部目录规则以可审计的文本文件沉淀下来，并为未来多 Agent 的身份定义预留结构。

## What Changes

- Babyface 启动后在每轮 Agent 推理前加载文件系统层级中的 `AGENTS.md`，并将内容拼接到最终 system prompt。
- 分层顺序采用“全局层到局部层”：越靠近当前工作目录的 `AGENTS.md` 越晚拼接，语义优先级越高。
- 多个 `AGENTS.md` 出现冲突时，系统使用确定性层级顺序表达优先级，不调用 LLM 总结、改写、合并或裁剪原始指令。
- 全局文件固定为 `~/.babyface/AGENTS.md`；项目和目录文件使用从工作区根目录到当前工作目录之间发现的 `AGENTS.md`。
- system prompt 继续保留代码内置的 Babyface 基础身份与边界；`AGENTS.md` 作为用户可编辑的外部补充。
- 为未来多 Agent 预留 `AGENTS.md` section 结构，但本次只要求 Babyface 读取整份文件，不实现按 Agent 身份解析或多 Agent 调度。
- Babyface 学习到用户偏好时，默认只允许更新 `~/.babyface/AGENTS.md` 中受控的 managed section；项目内 `AGENTS.md` 只有在用户明确要求时才可更新。
- 每轮任务完成后，Babyface 可以调用 LLM 判断本轮是否产生长期偏好；如果需要写入，LLM 生成候选规则并由系统后台自动写入。
- 写入前需要判断候选规则是否与目标 `AGENTS.md` managed section 冲突；如有冲突，由 LLM 产出整理后的 managed section 规则列表，系统只替换 managed section。
- 统一命名写法：面向品牌或 Agent 名称时仅使用 `Babyface`，全大写品牌或文件语境使用 `BABYFACE`；不使用其他 camel-case 变体。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `personal-agent-runtime`: 增加基于分层 `AGENTS.md` 的 system prompt 加载、拼接、LLM 辅助偏好提取和后台受控偏好更新行为。

## Impact

- 影响 Agent Runtime 的 system prompt 组装逻辑，现有硬编码 prompt 需要演进为“内置基础规则 + 外部 `AGENTS.md` 层级 + Memory 上下文”。
- 需要新增独立的 prompt profile/指令加载模块，避免和 `babyface.toml` 的 LLM、Memory、Shell 配置混在一起。
- 需要补充单元测试覆盖 `AGENTS.md` 查找顺序、缺失文件行为、拼接边界、冲突优先级、命名约束和受控 section 更新策略。
- README 与 OpenSpec 主规格需要补充 `AGENTS.md` 的用户可见行为说明。
