from __future__ import annotations

import locale
import platform
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any

from personal_agent.tools.base import ToolResult


class OSConfigTool:
    """读取操作系统基础配置的本地工具。

    这个工具用于让 Agent 了解“当前设备是什么系统”这类低敏信息。
    它刻意不读取当前工作目录、默认 Shell 和环境变量，避免把会话路径、
    终端偏好或潜在凭证线索交给 LLM。
    """

    name = "os_config_read"
    description = "读取本机操作系统基础配置，不包含当前目录、Shell 或环境变量。"

    def __init__(
        self,
        *,
        system_provider: Callable[[], str] = platform.system,
        version_provider: Callable[[], str] = platform.version,
        machine_provider: Callable[[], str] = platform.machine,
        home_provider: Callable[[], Path] = Path.home,
        hostname_provider: Callable[[], str] = socket.gethostname,
        locale_provider: Callable[[], tuple[str | None, str | None]] = locale.getlocale,
    ) -> None:
        self.system_provider = system_provider
        self.version_provider = version_provider
        self.machine_provider = machine_provider
        self.home_provider = home_provider
        self.hostname_provider = hostname_provider
        self.locale_provider = locale_provider

    def to_openai_tool(self) -> dict[str, Any]:
        """声明 OS 配置读取工具的输入 schema。

        该工具不需要参数，因为它只读取固定的低敏系统摘要。
        """

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        """读取并返回基础操作系统配置。

        单个字段读取失败时不会让整个工具失败，而是把该字段标记为“不可用”。
        这样 Agent 仍能使用其余系统信息继续回答用户。
        """

        system_name = self._read_value("操作系统", self.system_provider)
        values = {
            "操作系统": system_name,
            "系统版本": self._read_value("系统版本", self.version_provider),
            "CPU 架构": self._read_value("CPU 架构", self.machine_provider),
            "用户目录": self._read_value("用户目录", lambda: str(self.home_provider())),
            "主机名": self._read_value("主机名", self.hostname_provider),
            "语言区域": self._read_locale(),
            "是否 macOS": "是" if system_name == "Darwin" else "否",
        }
        content = "\n".join(f"{key}: {value}" for key, value in values.items())
        return ToolResult(ok=True, content=content, metadata=values)

    def _read_value(self, label: str, reader: Callable[[], object]) -> str:
        """读取单个字段，并把异常隔离成中文占位值。"""

        try:
            value = reader()
        except Exception as exc:  # noqa: BLE001 - 工具需隔离系统读取异常
            return f"不可用（{label}读取失败：{exc}）"
        if value is None or value == "":
            return "不可用"
        return str(value)

    def _read_locale(self) -> str:
        """读取系统语言区域，并兼容 locale 返回空值的情况。"""

        try:
            language, encoding = self.locale_provider()
        except Exception as exc:  # noqa: BLE001 - 工具需隔离系统读取异常
            return f"不可用（语言区域读取失败：{exc}）"
        parts = [part for part in (language, encoding) if part]
        return ".".join(parts) if parts else "不可用"
