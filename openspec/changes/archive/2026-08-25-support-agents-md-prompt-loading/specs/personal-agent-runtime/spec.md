## ADDED Requirements

### Requirement: 支持分层 AGENTS.md 指令
系统 SHALL 允许用户通过文件系统层级中的 `AGENTS.md` 自定义 Babyface 的长期行为指令，并在 Agent 推理时将这些指令纳入 system prompt。

#### Scenario: 没有 AGENTS.md 时仍可运行
- **WHEN** 用户启动 Babyface 且所有默认位置都不存在 `AGENTS.md`
- **THEN** 系统仍使用内置 Babyface 基础指令运行，不因为缺少 `AGENTS.md` 报错

#### Scenario: 读取用户全局 AGENTS.md
- **WHEN** 用户目录存在 `~/.babyface/AGENTS.md`
- **THEN** 系统将该文件内容纳入 Babyface 的 system prompt

#### Scenario: 按文件系统层级拼接 AGENTS.md
- **WHEN** 用户目录、工作区根目录、当前工作目录的父目录或当前工作目录中存在多个 `AGENTS.md`
- **THEN** 系统按全局层到局部层的顺序拼接这些文件内容，越靠近当前工作目录的内容越晚出现

#### Scenario: 局部目录指令优先级更高
- **WHEN** 上级目录和当前工作目录的 `AGENTS.md` 包含互相冲突的行为指令
- **THEN** 最终 system prompt 中当前工作目录的指令出现在上级目录指令之后，使其具有更高语义优先级

#### Scenario: 冲突指令不经 LLM 改写
- **WHEN** 多个层级的 `AGENTS.md` 包含互相冲突或重复的行为指令
- **THEN** 系统不得调用 LLM 总结、合并、裁剪或改写这些文件内容，而是保留原文并通过拼接顺序表达优先级

#### Scenario: 保留指令来源边界
- **WHEN** 系统拼接一个或多个 `AGENTS.md`
- **THEN** 最终 system prompt 为每个文件内容标明来源边界，便于用户理解和调试指令来自哪里

#### Scenario: AGENTS.md 与 babyface.toml 职责分离
- **WHEN** 用户配置 LLM、Memory 或 Shell timeout
- **THEN** 系统仍通过环境变量或 `babyface.toml` 读取运行时配置，而不要求这些配置写入 `AGENTS.md`

### Requirement: 支持受控偏好写入
系统 SHALL 允许 Babyface 在任务完成后自动把长期偏好写入全局 `AGENTS.md` 的受控区域，并避免静默修改项目级指令。

#### Scenario: 每轮任务后判断是否需要写入 AGENTS.md
- **WHEN** Babyface 完成一轮用户请求
- **THEN** 系统可以调用 LLM 判断本轮输入、执行结果和最终回答是否产生应沉淀到 `AGENTS.md` 的长期偏好

#### Scenario: 无长期偏好时不请求写入
- **WHEN** LLM 判断本轮没有稳定、长期、可复用的用户偏好
- **THEN** 系统不修改任何 `AGENTS.md`

#### Scenario: 有长期偏好时后台自动写入
- **WHEN** LLM 生成一条应写入 `AGENTS.md` 的候选偏好
- **THEN** 系统在后台写入整理后的 managed section，且不向用户展示候选内容、目标文件或冲突处理细节

#### Scenario: 写入前检测目标文件规则冲突
- **WHEN** LLM 生成一条候选偏好
- **THEN** 系统要求 LLM 判断该候选偏好是否与目标 `AGENTS.md` 中已有规则冲突

#### Scenario: 冲突时由 LLM 整理 managed section
- **WHEN** 候选偏好与目标 `AGENTS.md` 中已有规则冲突
- **THEN** 系统要求 LLM 产出解决冲突后的 managed section 规则列表，且不得改写 managed section 外的用户手写内容

#### Scenario: 自动写入全局受控区域
- **WHEN** Babyface 发现可沉淀为长期指令的用户偏好
- **THEN** 系统将该偏好写入 `~/.babyface/AGENTS.md` 的 Babyface 受控区域

#### Scenario: 不静默修改项目级 AGENTS.md
- **WHEN** Babyface 发现可沉淀为长期指令的用户偏好但用户没有明确要求写入项目文件
- **THEN** 系统不得自动修改工作区或项目目录中的 `AGENTS.md`

#### Scenario: 用户明确要求写入项目指令
- **WHEN** 用户明确要求把某条规则写入当前项目或当前目录的 `AGENTS.md`
- **THEN** 系统可以将该规则写入用户指定层级的 `AGENTS.md`

#### Scenario: 受控区域不存在时可创建
- **WHEN** `~/.babyface/AGENTS.md` 不存在或缺少 Babyface 受控区域，且系统需要写入长期偏好
- **THEN** 系统创建必要文件或区域，并保留用户可编辑的 Markdown 结构

### Requirement: 保持 Babyface 命名规范
系统 SHALL 在面向用户的说明性内容中统一使用 `Babyface` 或 `BABYFACE`，不得使用其他 camel-case 变体。

#### Scenario: 展示 Agent 名称
- **WHEN** CLI、README、OpenSpec 或错误提示展示 Agent 品牌名称
- **THEN** 系统使用 `Babyface` 或 `BABYFACE`，不展示其他 camel-case 变体
