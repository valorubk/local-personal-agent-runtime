# local-personal-agent-runtime

一个运行在个人电脑上的本地优先个人 Agent Runtime。

V1 的目标是先跑通一个类似 Claude Code 交互体验的本地个人助手，但核心用途不是代码开发，而是作为长期个人助手，帮助用户管理信息、执行任务、辅助学习和提升效率。

## 当前 V1 能力

- 使用 `babyface` 启动持续交互式 CLI Session。
- 通过 OpenAI-compatible LLM 完成 Agent 推理。
- 使用 LangGraph 串联基础 Agent Workflow。
- 支持 Tool Calling：
  - File Tool：读取本地文本文件。
  - Shell Tool：执行本地命令，执行前必须二次确认。
  - Web Tool：V1 占位，返回“尚未实现”。
- 使用 SQLite 保存本地 Memory：
  - Profile Memory
  - Task History
  - Tool 调用摘要
- SQLite 默认位置为 `.babyface/memory.sqlite3`，支持配置覆盖。
- CLI 输出使用中文提示，最终回答支持流式展示路径。

## 安装

建议使用 Python 3.12 或更高版本。

```bash
python -m pip install -e .
```

安装后会暴露命令：

```bash
babyface
```

## 配置

复制配置示例：

```bash
cp .env.example .env
```

根据实际模型服务配置环境变量：

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://your-openai-compatible-endpoint/v1"
export OPENAI_MODEL="your-model"
```

可选配置：

```bash
export BABYFACE_MEMORY_DB_PATH=".babyface/memory.sqlite3"
export BABYFACE_SHELL_TIMEOUT_SECONDS="10"
```

也可以创建项目内配置文件 `babyface.toml`：

```toml
openai_api_key = "your-api-key"
openai_base_url = "https://your-openai-compatible-endpoint/v1"
openai_model = "your-model"
memory_db_path = ".babyface/memory.sqlite3"
shell_timeout_seconds = 10
```

日常命令行使用时，也可以把配置放在用户目录：

```text
~/.babyface/config.toml
```

没有显式传入 `--config`、也没有设置 `BABYFACE_CONFIG_PATH` 时，Babyface 会先尝试读取当前目录的 `babyface.toml`，再尝试读取用户目录的 `~/.babyface/config.toml`。

本地验证时也可以使用不会提交到 Git 的私密配置文件：

```bash
babyface --config babyface.local.toml
```

`babyface.local.toml` 已在 `.gitignore` 中忽略，可以放置真实 API key。
配置文件中的 LLM 字段支持两种写法：

```toml
openai_api_key = "your-api-key"
openai_base_url = "https://your-openai-compatible-endpoint/v1"
openai_model = "your-model"
```

也支持大写别名：

```toml
OPENAI_API_KEY = "your-api-key"
BASE_URL = "https://your-openai-compatible-endpoint/v1"
MODEL = "your-model"
```

## 运行

```bash
babyface
```

启动后会先展示一个带边框的彩虹色 `BABYFACE` Banner，并在大字下方显示 `- Your Local Personal Agent -`。

进入 Session 后可以连续对话：

```text
> 帮我总结最近的 Agent 学习内容
Babyface:
...

> 帮我分析我的面试准备情况
Babyface:
...
```

退出命令：

```text
exit
quit
/exit
```

也可以通过 `babyface --help` 查看这些退出命令的说明。

交互式输入行会启用终端行编辑能力。正常终端中，上下键可浏览输入历史，左右键可在当前输入中移动光标，Delete 可删除光标后的字符，也可以在光标所在位置继续插入字符。输入行最开始的 `> ` 是不可编辑提示符，不能通过退格键删除。

每轮回复会在 `Babyface:` 标签前后保留空行，让回复内容和下一轮输入提示保持间距。

## Shell Tool 二次确认

当 Agent 请求执行 shell 命令时，CLI 会先展示命令并询问是否允许执行。

用户拒绝时，命令不会执行，Tool 会返回“用户取消执行”的结构化结果，Session 不会崩溃。

## 异常提示

如果某一轮对话内部出现异常，CLI 会用中文提示问题，并继续保持 Session 可用，不会直接展示 Python traceback。

当输入中包含当前系统无法直接编码的特殊字符时，Runtime 会先把异常字符替换为安全占位字符，再继续处理本轮对话。

## Memory

默认数据库位置：

```text
.babyface/memory.sqlite3
```

Memory 分成两层：

- 短期记忆：当前 `babyface` Session 内的对话历史。只要不退出 CLI，后续轮次会带上前面几轮的用户输入和 Agent 回答。
- 长期记忆：保存到 SQLite 的 Profile Memory 和 Task History。重启 CLI 后仍然可以读取。

当用户输入类似以下内容时，Runtime 会保存为 Profile Memory：

```text
记住：我正在准备 AI Agent 方向的面试
记住，我不爱吃梅菜扣肉
我不爱吃梅菜扣肉，记住它
```

每轮完成后，Runtime 会保存 Task History，包括用户输入、最终回答、时间戳和可选 Tool 调用摘要。

## 测试

```bash
python -m unittest discover -s tests
```

## OpenSpec

本项目使用 OpenSpec 管理 V1 规格与实现任务。

主规格：

```text
openspec/specs/personal-agent-runtime/spec.md
```

V1 change 已归档：

```text
openspec/changes/archive/2026-08-25-implement-personal-agent-runtime-v1/
```

原始中文需求文档保留在：

```text
docs/requirements/personal-agent-runtime-v1.md
```
