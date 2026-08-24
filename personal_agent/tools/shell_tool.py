from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any

from personal_agent.tools.base import ToolResult


ConfirmCallback = Callable[[str], bool]


class ShellTool:
    """本地命令执行工具。

    Shell Tool 很强，也很危险，所以这里有三个保护：
    1. 执行前必须调用 confirm 回调，让用户二次确认
    2. 设置 timeout，避免命令卡死
    3. 不抛异常，所有结果都结构化返回给 Agent
    """

    name = "shell_exec"
    description = "执行本地 shell 命令，执行前必须由用户确认。"

    def __init__(self, timeout_seconds: int = 10, confirm: ConfirmCallback | None = None) -> None:
        self.timeout_seconds = timeout_seconds

        # 默认 confirm 返回 False，也就是“没有 UI 确认机制时绝不执行命令”。
        # CLI 层会注入真正的 Rich Confirm 回调。
        self.confirm = confirm or (lambda command: False)

    def to_openai_tool(self) -> dict[str, Any]:
        """声明 shell 工具的输入 schema。"""

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "要执行的 shell 命令"}
                    },
                    "required": ["command"],
                },
            },
        }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        command = str(arguments.get("command") or "").strip()
        if not command:
            return ToolResult(ok=False, error="缺少 shell 命令。")

        # 关键安全点：模型“想执行”不等于程序“允许执行”。
        # 只有用户明确确认后，才会进入 subprocess.run。
        if not self.confirm(command):
            return ToolResult(
                ok=False,
                error="用户取消执行",
                metadata={"command": command, "exit_code": None, "stderr": ""},
            )

        try:
            # `shell=True` 允许执行完整 shell 命令字符串，例如 `ls -la | head`。
            # 这也意味着更需要二次确认。V1 选择本地用户确认模型。
            completed = subprocess.run(
                command,
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return ToolResult(
                ok=False,
                error=f"命令执行超时：超过 {self.timeout_seconds} 秒。",
                metadata={
                    "command": command,
                    "exit_code": None,
                    "stdout": exc.stdout or "",
                    "stderr": exc.stderr or "",
                    "timeout_seconds": self.timeout_seconds,
                },
            )

        return ToolResult(
            # 命令成功与否按 exit code 判断。非 0 不抛异常，而是 ok=False。
            ok=completed.returncode == 0,
            content=completed.stdout,
            error=None if completed.returncode == 0 else "命令执行失败。",
            metadata={
                "command": command,
                "exit_code": completed.returncode,
                "stderr": completed.stderr,
            },
        )
