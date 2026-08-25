from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from personal_agent.config import ConfigError


TransportName = Literal["stdio", "streamable_http"]


@dataclass(frozen=True)
class McpServerConfig:
    """单个 MCP Server 的内部配置模型。

    这个模型屏蔽 JSON/YAML 字段差异：
    - 生态常见 JSON 可以写 `mcpServers` 和 `disabled`
    - Babyface 手写 YAML 可以写 `mcp_servers` 和 `enabled`

    解析后 Runtime 和 MCP 管理器只读取这里的统一字段。
    """

    name: str
    transport: TransportName
    enabled: bool = True
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 10


def load_mcp_servers(config_path: str | Path | None) -> list[McpServerConfig]:
    """从 JSON 或 YAML 文件读取 MCP Server 配置。

    返回空列表表示用户未配置外部 MCP Server。解析错误统一抛出
    `ConfigError`，让 CLI 层可以展示中文友好错误。
    """

    if config_path is None:
        return []

    path = Path(config_path)
    if not path.exists():
        return []

    raw = _load_raw_config(path)
    servers = raw.get("mcpServers", raw.get("mcp_servers"))
    if servers is None:
        return []
    if not isinstance(servers, dict):
        raise ConfigError("MCP 配置里的 mcpServers 必须是对象。")

    return [_parse_server(name, value) for name, value in servers.items()]


def _load_raw_config(path: Path) -> dict[str, Any]:
    """按扩展名读取 JSON 或 YAML 配置文件。"""

    try:
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        else:
            raise ConfigError("MCP 配置文件只支持 .json、.yaml 或 .yml。")
    except json.JSONDecodeError as exc:
        raise ConfigError(f"MCP JSON 配置无法解析：{exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"MCP YAML 配置无法解析：{exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError("MCP 配置文件顶层必须是对象。")
    return data


def _parse_server(name: object, value: object) -> McpServerConfig:
    """把单个 server 声明转换成内部配置。"""

    if not isinstance(name, str) or not name.strip():
        raise ConfigError("MCP Server 名称不能为空。")
    if not isinstance(value, dict):
        raise ConfigError(f"MCP Server {name} 的配置必须是对象。")

    enabled = _parse_enabled(value)
    transport = str(value.get("transport") or _guess_transport(value))
    if transport not in {"stdio", "streamable_http"}:
        raise ConfigError(f"MCP Server {name} 的 transport 不支持：{transport}")

    timeout_seconds = _parse_timeout(name, value.get("timeout_seconds", 10))
    config = McpServerConfig(
        name=name,
        transport=transport,  # type: ignore[arg-type]
        enabled=enabled,
        command=_optional_string(value.get("command")),
        args=_string_list(name, "args", value.get("args", [])),
        url=_optional_string(value.get("url")),
        headers=_string_dict(name, "headers", value.get("headers", {})),
        env=_string_dict(name, "env", value.get("env", {})),
        timeout_seconds=timeout_seconds,
    )
    _validate_server(config)
    return config


def _parse_enabled(value: dict[str, Any]) -> bool:
    """兼容 `enabled` 与 MCP 生态常见的 `disabled` 字段。"""

    if "enabled" in value:
        return bool(value["enabled"])
    if "disabled" in value:
        return not bool(value["disabled"])
    return True


def _guess_transport(value: dict[str, Any]) -> str:
    """根据字段推断 transport，兼容生态里省略 transport 的 stdio 配置。"""

    if value.get("url"):
        return "streamable_http"
    return "stdio"


def _parse_timeout(name: str, value: object) -> int:
    """校验 timeout_seconds 是正整数。"""

    try:
        timeout = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"MCP Server {name} 的 timeout_seconds 必须是整数。") from exc
    if timeout <= 0:
        raise ConfigError(f"MCP Server {name} 的 timeout_seconds 必须大于 0。")
    return timeout


def _validate_server(config: McpServerConfig) -> None:
    """按 transport 校验必要字段。"""

    if config.transport == "stdio" and not config.command:
        raise ConfigError(f"MCP Server {config.name} 使用 stdio 时必须配置 command。")
    if config.transport == "streamable_http" and not config.url:
        raise ConfigError(f"MCP Server {config.name} 使用 streamable_http 时必须配置 url。")


def _optional_string(value: object) -> str | None:
    """把可选字段转换成字符串或 None。"""

    if value in (None, ""):
        return None
    return str(value)


def _string_list(name: str, field_name: str, value: object) -> list[str]:
    """校验列表字段，并把元素统一转换为字符串。"""

    if not isinstance(value, list):
        raise ConfigError(f"MCP Server {name} 的 {field_name} 必须是列表。")
    return [str(item) for item in value]


def _string_dict(name: str, field_name: str, value: object) -> dict[str, str]:
    """校验字典字段，并把 key/value 统一转换为字符串。"""

    if not isinstance(value, dict):
        raise ConfigError(f"MCP Server {name} 的 {field_name} 必须是对象。")
    return {str(key): str(item) for key, item in value.items()}
