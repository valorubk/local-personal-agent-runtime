## Context

本项目的 V1 已经具备 `babyface` 交互式 CLI、OpenAI-compatible LLM 配置读取和 Rich 终端渲染能力。此次变更只调整启动前后的用户体验和配置发现路径，不引入新的外部依赖，也不改变 Agent Loop、Memory 或 Tool Calling 的核心架构。

## Goals / Non-Goals

**Goals:**

- 让全局安装后的 `babyface` 在用户不进入项目目录时也能读取默认配置。
- 保持项目目录配置优先级，方便开发或特定项目覆盖用户级配置。
- 让启动 Banner 更像一个稳定的产品入口：大号 `BABYFACE` 为主视觉，副标题居中展示，退出命令交给 `--help`。
- 用单元测试覆盖配置路径优先级和 Banner 渲染结构。

**Non-Goals:**

- 不引入新的配置格式或配置迁移工具。
- 不把真实 API Key 写入仓库。
- 不新增 HTTP API、Web Dashboard 或远程配置同步。
- 不改变 LangGraph workflow、Shell 二次确认、流式输出或 SQLite Memory 的既有行为。

## Decisions

### Decision: 配置加载采用固定优先级链

配置加载顺序保持简单可解释：显式 `--config` 优先，其次是 `BABYFACE_CONFIG_PATH`，然后是当前目录 `babyface.toml`，最后是 `~/.babyface/config.toml`。

选择这个顺序的原因是：显式输入代表用户本次运行的最高意图；环境变量适合脚本化或临时切换；项目目录配置适合开发验证；用户目录配置适合作为全局默认值。备选方案是只读取用户目录配置，但会降低项目开发时切换配置的便利性。

### Decision: 默认用户配置只读取，不自动生成

Runtime 在启动时尝试读取 `~/.babyface/config.toml`，但不会在代码中自动写入带敏感信息的配置文件。配置复制可以通过用户本地操作完成，并且真实配置文件不进入版本控制。

这样可以避免误提交密钥，也让配置文件的生命周期由用户掌控。备选方案是在首次启动时生成模板文件，但 V1 当前更关注最小可运行和安全边界。

### Decision: Banner 继续使用 Rich 渲染

Banner 继续由 Rich 的 `Panel`、`Text` 和 `Align` 组合渲染。大号 ASCII `BABYFACE` 使用彩虹渐变样式，副标题 `- Your Local Personal Agent -` 使用较简洁的强调色，并通过居中对齐让视觉重心稳定。

继续使用 Rich 的原因是项目已经依赖它来展示 CLI UI，改动小且可测试。备选方案是引入专门的 ASCII art 或终端 UI 库，但会增加依赖和维护成本。

### Decision: 退出命令说明放到 `--help`

启动 Banner 不再展示中文退出提示，退出方式集中放到 `babyface --help`。这样启动界面更干净，也符合命令行工具把操作说明放到帮助信息里的常见习惯。

## Risks / Trade-offs

- 用户目录配置缺失时仍可能启动失败 → 继续保留中文错误提示，说明缺少必要 LLM 配置。
- 当前目录配置优先于用户目录配置可能导致用户误以为读取了全局配置 → 在 README 中说明配置优先级，并用测试锁定行为。
- Rich 在不同终端宽度下的视觉效果可能略有差异 → 测试验证结构和关键文本，人工验证实际终端展示。
- 用户目录中的真实配置不在仓库中管理 → 保持 `.gitignore` 规则和 README 提醒，避免泄露密钥。

## Migration Plan

1. 保留已有 `babyface.toml` 项目级配置能力。
2. 将本地可用配置复制到 `~/.babyface/config.toml`，并设置合理文件权限。
3. 安装或重装 CLI 后，从任意目录运行 `babyface` 验证默认配置可用。
4. 如果需要回滚，只需删除用户目录配置或显式传入其他配置文件。
