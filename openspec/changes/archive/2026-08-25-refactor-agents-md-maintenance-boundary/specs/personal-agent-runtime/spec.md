## MODIFIED Requirements

### Requirement: 支持受控偏好写入
系统 SHALL 允许 Babyface 在用户明示要求记住或长期采用某条偏好后，把长期偏好写入全局 `AGENTS.md` 的受控区域，并避免静默修改项目级指令。

#### Scenario: 每轮任务后判断是否需要写入 AGENTS.md
- **WHEN** Babyface 完成一轮用户请求，且用户输入明示要求记住、以后遵循、每次采用或固定使用某条长期偏好
- **THEN** 系统可以调用 LLM 判断本轮输入、执行结果和最终回答是否产生应沉淀到 `AGENTS.md` 的长期偏好

#### Scenario: 用户未明示长期偏好时不请求写入判断
- **WHEN** Babyface 完成一轮用户请求，但用户没有明示要求记住或长期采用某条偏好
- **THEN** 系统不得调用 `AGENTS.md` 更新判断 LLM
- **AND** 系统不得修改任何 `AGENTS.md`

#### Scenario: 无长期偏好时不请求写入
- **WHEN** 用户明示要求记住或长期采用某条偏好，但 LLM 判断本轮没有稳定、长期、可复用的用户偏好
- **THEN** 系统不修改任何 `AGENTS.md`

#### Scenario: 有长期偏好时后台自动写入
- **WHEN** 用户明示要求记住或长期采用某条偏好，且 LLM 生成一条应写入 `AGENTS.md` 的候选偏好
- **THEN** 系统在后台写入整理后的 managed section，且不向用户展示候选内容、目标文件或冲突处理细节

#### Scenario: 写入前检测目标文件规则冲突
- **WHEN** LLM 生成一条候选偏好
- **THEN** 系统要求 LLM 判断该候选偏好是否与目标 `AGENTS.md` 中已有规则冲突

#### Scenario: 冲突时由 LLM 整理 managed section
- **WHEN** 候选偏好与目标 `AGENTS.md` 中已有规则冲突
- **THEN** 系统要求 LLM 产出解决冲突后的 managed section 规则列表，且不得改写 managed section 外的用户手写内容

#### Scenario: 自动写入全局受控区域
- **WHEN** Babyface 在用户明示长期偏好后发现可沉淀为长期指令的用户偏好
- **THEN** 系统将该偏好写入 `~/.babyface/AGENTS.md` 的 Babyface 受控区域

#### Scenario: 不静默修改项目级 AGENTS.md
- **WHEN** Babyface 在用户明示长期偏好后发现可沉淀为长期指令的用户偏好但用户没有明确要求写入项目文件
- **THEN** 系统不得自动修改工作区或项目目录中的 `AGENTS.md`

#### Scenario: 用户明确要求写入项目指令
- **WHEN** 用户明确要求把某条规则写入当前项目或当前目录的 `AGENTS.md`
- **THEN** 系统可以将该规则写入用户指定层级的 `AGENTS.md`

#### Scenario: 受控区域不存在时可创建
- **WHEN** `~/.babyface/AGENTS.md` 不存在或缺少 Babyface 受控区域，且系统需要写入长期偏好
- **THEN** 系统创建必要文件或区域，并保留用户可编辑的 Markdown 结构
