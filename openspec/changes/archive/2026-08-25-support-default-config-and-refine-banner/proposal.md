## Why

`babyface` 需要能从任意目录稳定启动，而不是依赖用户每次都进入项目目录或显式传入配置文件。同时，启动界面是用户进入长期交互 Session 的第一眼体验，需要更简洁、更有识别度，并把退出说明从 Banner 中移到 `--help`。

## What Changes

- 配置加载顺序增加用户目录默认配置：未显式传入 `--config`、未设置 `BABYFACE_CONFIG_PATH`、当前目录不存在 `babyface.toml` 时，自动尝试读取 `~/.babyface/config.toml`。
- 保留项目内配置能力，当前目录 `babyface.toml` 仍优先于用户目录默认配置，方便项目级覆盖。
- 启动 Banner 去掉顶部简单 `BABYFACE` 文案。
- 在大号 `BABYFACE` 字样下方增加 `- Your Local Personal Agent -`。
- Banner 内容在面板中水平和垂直居中展示。
- README、主规格和测试补充对应行为说明与验证。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `personal-agent-runtime`: 调整交互式 CLI 启动 Banner 的展示要求，并补充 OpenAI-compatible LLM 配置读取的用户目录默认配置行为。

## Impact

- 影响配置加载模块：`personal_agent/config.py`。
- 影响 CLI Banner 渲染模块：`personal_agent/cli/banner.py`。
- 影响面向用户的启动与配置说明：`README.md`。
- 影响 OpenSpec 主规格：`openspec/specs/personal-agent-runtime/spec.md`。
- 增加或调整配置与 Banner 的单元测试，确保默认配置优先级和 Banner 布局可回归验证。
