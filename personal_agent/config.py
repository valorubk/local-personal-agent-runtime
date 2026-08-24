from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class ConfigError(RuntimeError):
    """配置错误。

    这里专门定义一个业务异常，而不是直接抛 `ValueError`，
    是为了让 CLI 层可以只捕获配置类错误，并把错误信息友好地展示给用户。
    """


@dataclass(frozen=True)
class Settings:
    """运行时配置对象。

    `@dataclass(frozen=True)` 会帮我们自动生成 `__init__` 等方法，并让对象创建后不可变。
    对配置来说，“不可变”是个好习惯：程序启动后配置不应该在各处被随手改掉。
    """

    openai_api_key: str
    openai_base_url: str | None
    openai_model: str
    memory_db_path: Path
    shell_timeout_seconds: int


def load_settings(
    env: Mapping[str, str] | None = None,
    config_path: str | Path | None = None,
) -> Settings:
    """读取 Babyface 的配置。

    这个函数是配置层的唯一入口。它同时支持：
    1. 环境变量，例如 `OPENAI_API_KEY`
    2. TOML 配置文件，例如 `babyface.local.toml` 或 `~/.babyface/config.toml`

    参数里允许传入 `env`，主要是为了测试。测试时不应该真的修改系统环境变量，
    所以我们可以传一个普通 dict 进来模拟环境。
    """

    # 没有显式传 env 时，默认使用真实系统环境变量。
    source_env = env if env is not None else os.environ

    # 先读取配置文件，再用环境变量覆盖。这样本地可以写文件，CI/部署可以用 env。
    config = _load_config_file(source_env, config_path)

    # API key 是 LLM 调用的必要条件。这里故意在启动阶段失败，
    # 避免用户进入对话后才在第一次模型调用时看到底层 SDK 报错。
    api_key = _get_value(source_env, config, "OPENAI_API_KEY", "openai_api_key")
    if not api_key:
        raise ConfigError("请配置 OPENAI_API_KEY 后再启动 babyface。")

    # OpenAI-compatible 服务一般只需要换 base_url 和 model。
    # 例如阿里云百炼、DeepSeek、OpenRouter 等都常用这种兼容格式。
    base_url = _get_value(source_env, config, "OPENAI_BASE_URL", "openai_base_url", "BASE_URL") or None
    model = _get_value(source_env, config, "OPENAI_MODEL", "openai_model", "MODEL") or "gpt-4o-mini"

    # Memory 默认放在项目目录内，方便初版开发时观察 SQLite 文件。
    # 后续如果要做成真正长期个人助手，可以改成用户目录，例如 `~/.babyface/`。
    memory_path = (
        _get_value(source_env, config, "BABYFACE_MEMORY_DB_PATH", "memory_db_path")
        or ".babyface/memory.sqlite3"
    )

    # Shell Tool 一定要有超时，避免 Agent 执行一个永不结束的命令导致 CLI 卡死。
    timeout_raw = (
        _get_value(
            source_env,
            config,
            "BABYFACE_SHELL_TIMEOUT_SECONDS",
            "shell_timeout_seconds",
        )
        or "10"
    )

    try:
        timeout = int(timeout_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError("BABYFACE_SHELL_TIMEOUT_SECONDS 必须是整数。") from exc
    if timeout <= 0:
        raise ConfigError("BABYFACE_SHELL_TIMEOUT_SECONDS 必须大于 0。")

    return Settings(
        openai_api_key=str(api_key),
        openai_base_url=base_url,
        openai_model=str(model),
        memory_db_path=Path(str(memory_path)),
        shell_timeout_seconds=timeout,
    )


def _load_config_file(
    env: Mapping[str, str],
    config_path: str | Path | None,
) -> dict[str, object]:
    """读取 TOML 配置文件。

    Python 3.11+ 标准库内置 `tomllib`，可以直接读取 TOML。
    我们这里不引入额外配置库，是为了让 V1 尽量轻。
    """

    # 配置文件路径优先级：
    # 1. CLI 通过 `--config` 传入的路径
    # 2. 环境变量 `BABYFACE_CONFIG_PATH`
    # 3. 当前目录下默认 `babyface.toml`
    # 4. 用户目录下默认 `~/.babyface/config.toml`
    #
    # 第 4 条是为了让用户可以在任意目录直接运行 `babyface`，
    # 不必每次都带 `--config /path/to/config.toml`。
    resolved = config_path or env.get("BABYFACE_CONFIG_PATH")
    if resolved is None:
        for candidate in _default_config_candidates(env):
            if candidate.exists():
                resolved = candidate
                break
        if resolved is None:
            return {}

    path = Path(resolved)
    if not path.exists():
        return {}

    with path.open("rb") as file:
        return tomllib.load(file)


def _default_config_candidates(env: Mapping[str, str]) -> list[Path]:
    """返回没有显式指定配置文件时要尝试读取的默认路径。

    `babyface.toml` 适合项目内开发；`~/.babyface/config.toml` 适合日常命令行使用。
    测试传入 `env={}` 时不会误读真实用户目录，避免本机私密配置影响单元测试。
    """

    candidates = [Path("babyface.toml")]
    home = env.get("HOME")
    if home:
        candidates.append(Path(home) / ".babyface" / "config.toml")
    return candidates


def _get_value(
    env: Mapping[str, str],
    config: Mapping[str, object],
    env_name: str,
    *config_names: str,
) -> object | None:
    """按优先级读取一个配置值。

    规则是：环境变量优先，其次配置文件。
    `*config_names` 是 Python 的可变参数语法，允许一个配置项有多个文件字段别名。
    例如 base URL 可以写成 `openai_base_url`，也可以写成用户给出的 `BASE_URL`。
    """

    value = env.get(env_name)
    if value not in (None, ""):
        return value
    for config_name in (env_name, *config_names):
        value = config.get(config_name)
        if value not in (None, ""):
            return value
    return None
