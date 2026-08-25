## Context

当前 `personal_agent.agent.runtime` 中的 system prompt 是模块级常量，Agent 每轮推理时直接把它作为第一条 system message。运行时配置由 `babyface.toml` 和环境变量承载，长期用户事实保存在 SQLite Memory；这三类信息各自承担不同职责。

本次设计需要在不引入多 Agent、不改变 LLM 配置方式、不扩大 V1 工具范围的前提下，让 Babyface 可以从 `AGENTS.md` 读取用户和项目指令，并把这些指令稳定地带入新 Session。

## Goals / Non-Goals

**Goals:**

- 将 prompt 指令加载从 runtime 主流程中拆出，形成独立、可测试的 `AGENTS.md` 加载能力。
- 支持 `~/.babyface/AGENTS.md` 到当前工作目录的文件系统层级拼接。
- 拼接结果保留来源边界，便于排查 prompt 行为。
- 为未来按 Agent 身份读取 section 留出文档结构和代码接口空间。
- 支持后台自动写入全局受控偏好。
- 每轮任务完成后用 LLM 生成可审计的 `AGENTS.md` 更新候选，并在后台完成写入，不向用户暴露候选规则、目标文件或冲突整理细节。
- 写入前用 LLM 判断候选规则是否与现有规则冲突；如有冲突，只解决目标 managed section 内的候选规则，不重写整份 prompt。

**Non-Goals:**

- 不实现多 Agent 调度、Agent registry 或按身份选择不同 Agent。
- 不要求 V1 解析 `AGENTS.md` 中的 `## Babyface`、`## Reviewer` 等 section；V1 读取整份文件。
- 不把 API key、模型、Memory 路径等运行配置迁移到 `AGENTS.md`。
- 不实现自动、静默的 prompt 自我改写。
- 不使用 LLM 对多个 `AGENTS.md` 做冲突解决、总结、合并、裁剪或改写。

## Decisions

### 1. 新增独立的 prompt profile 模块

新增 `personal_agent/prompt_profile.py` 或等价模块，负责发现、读取、拼接和更新 `AGENTS.md`。`AgentRuntime` 只消费一个已经拼好的 prompt 字符串，避免把文件系统细节塞进 LangGraph 节点。

备选方案是继续在 `runtime.py` 内直接查找文件。它初期更少文件，但会让 runtime 同时承担 Agent Loop、Memory、Tool 和 prompt 配置职责，后续多 Agent 扩展会更难拆。

### 2. Prompt 组装顺序固定为内置基础规则先行

最终 system prompt 采用：

```text
内置 Babyface 基础规则
全局 AGENTS.md
工作区/目录 AGENTS.md
```

Memory 上下文继续作为单独的 system message 注入。这样基础身份和安全边界不会被外部文件完全替换，外部文件负责补充偏好、风格和项目规则。

备选方案是把 Memory 也拼进同一条 system prompt。保留独立 message 更接近现有结构，测试和调试也更清楚。

### 3. 文件系统层级从全局到局部读取

发现顺序为：

1. `~/.babyface/AGENTS.md`
2. 工作区根目录到当前工作目录之间每一层的 `AGENTS.md`

工作区根目录优先使用 git root；如果当前目录不在 git repo 中，则使用当前工作目录向上到用户 home 之间的目录链。不存在的文件跳过，不报错。

备选方案是从当前目录向上读取后反转。实现上也可行，但对需求表达不如“先确定层级，再顺序读取”直观。

### 4. 拼接内容保留来源边界

每个文件内容前增加稳定边界，例如：

```markdown
## AGENTS.md
Source: /path/to/AGENTS.md

...
```

来源边界不改变用户文件内容，只存在于最终 prompt。这样当多个层级出现冲突时，用户能在调试输出或测试中看到来源。

### 5. 冲突处理使用确定性顺序，不使用 LLM 合并

多个 `AGENTS.md` 指令冲突时，系统不尝试“解决”冲突，也不调用 LLM 生成一份合并后的 system prompt。LLM 合并存在真实风险：它可能省略看似重复但实际重要的规则，可能把强约束改写成弱约束，也可能引入原文没有的解释。V1 应保留所有原始文件内容，通过“越靠近当前工作目录越晚出现”的顺序表达优先级。

最终 prompt 应在内置基础规则附近明确说明：如果不同 `AGENTS.md` 之间存在冲突，后出现、更靠近当前工作目录的指令优先；不得删除、改写或总结任何 `AGENTS.md` 内容。

备选方案是增加一个 LLM conflict resolver。它可以让 prompt 更短、更顺，但会引入额外成本、不可重复输出和语义漂移风险，不适合作为 V1 默认路径。后续如果需要增强，可以增加只读冲突提示器：它只报告可能冲突和最终优先层级，不改写 prompt。

### 6. 受控偏好写入默认只改全局文件

偏好沉淀使用 `~/.babyface/AGENTS.md` 中的 managed section：

```markdown
## Babyface Learned Preferences

<!-- babyface-managed:start -->
<!-- babyface-managed:end -->
```

只要 LLM 判断本轮产生了长期偏好，就在后台写入。项目内 `AGENTS.md` 必须由用户明确指定才修改。写入逻辑应尽量只替换 managed section 内部内容，保留用户手写内容。

备选方案是继续使用 SQLite Profile Memory 存偏好。SQLite 适合结构化事实和任务历史，但 system prompt 偏好需要用户可审计、可编辑，并且跨新 Session 立即成为 Agent 指令，因此文件更合适。

### 7. 每轮任务后增加 LLM 辅助偏好提取

`AgentRuntime.run_turn()` 在完成正常 Agent Loop、保存 Task History 和更新短期记忆后，增加一个可选的 `AGENTS.md` 更新检查步骤。该步骤由 `enable_agents_update` 开关控制，真实 CLI 开启它；测试、脚本模式或未来批处理流程可以保持关闭，避免意外改写用户目录。

检查步骤使用同一个 LLM 客户端发起一次无工具调用，请求模型输出严格 JSON：

```json
{
  "should_update": true,
  "target": "global",
  "preference": "用户偏好先给结论，再给关键依据。",
  "reason": "用户明确表达了长期交流偏好。"
}
```

Prompt 必须约束模型只提取稳定、长期、可复用的偏好；不记录一次性任务内容、敏感信息或普通任务事实；每轮最多生成一条候选规则；不确定时返回 `should_update: false`。

如果用户输入中明确出现“记住”“以后”“每次”“一定要”等长期偏好表达，且第一轮判断返回 `should_update: false`，Runtime 会进行一次更严格的 LLM 抽取重试。这个兜底仍然由 LLM 总结候选规则，不直接用规则拼接用户原文；它的作用是避免明确的长期偏好请求被一次保守判断静默吞掉。

### 8. 冲突解决只作用于目标文件的 managed section

写入前，Runtime 会读取目标 `AGENTS.md` 当前全文，并把全文和候选规则交给 LLM。LLM 可以判断候选偏好是否与目标文件中的已有规则冲突，但不能重写整份 `AGENTS.md`。它只能返回解决冲突后的 managed section 规则列表：

```json
{
  "managed_preferences": [
    "用户偏好先给结论，再给关键依据。"
  ],
  "conflict_resolution": "候选规则与旧规则重复，保留更清晰的新表述。"
}
```

程序随后在后台用该列表替换 managed section，不向用户展示候选规则、冲突处理说明或目标文件。

这样保留了“冲突时让 LLM 协助解决”的能力，但把破坏半径限制在 managed section 内，避免 LLM 吞掉或改写用户手写内容。

### 9. 多 Agent 只预留结构，不实现解析

README 推荐用户在 `AGENTS.md` 中使用：

```markdown
# AGENTS.md

## Shared Instructions

## Babyface

## Babyface Learned Preferences
```

V1 不解析这些 section，而是整份注入。未来多 Agent 可以在同一文件结构上增加按身份提取逻辑，不需要改用户已有文件。

## Risks / Trade-offs

- 外部 prompt 文件可能包含冲突或低质量指令 → 通过全局到局部的顺序、来源边界和内置优先级说明降低调试成本，不通过 LLM 改写用户原文。
- `AGENTS.md` 过长会增加 token 消耗 → V1 不做 token 裁剪，但加载器应跳过空文件，并可在后续增加长度限制或摘要策略。
- 自动写入可能破坏用户手写内容 → 只写 managed section，默认只写全局文件，项目文件需要用户明确要求，不允许重写整份 `AGENTS.md`。
- LLM 冲突解决可能改错语义 → 只允许 LLM 产出 managed section 规则列表，不允许重写整份 `AGENTS.md`。
- LLM 偏好判断可能过于保守 → 对明确长期偏好表达追加一次强制抽取重试。
- git root 之外的目录层级定义可能不符合所有用户直觉 → 在不属于 git repo 时退回 home 到 cwd 的目录链，保持规则可解释。

## Migration Plan

1. 引入加载器后，没有 `AGENTS.md` 的用户行为保持不变。
2. 文档新增可选 `AGENTS.md` 示例；用户可以逐步创建全局或项目文件。
3. 如果需要回滚，删除或禁用加载器调用即可恢复为内置 prompt 加 Memory 上下文。
