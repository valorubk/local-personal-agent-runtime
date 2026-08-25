from __future__ import annotations

import subprocess
from collections.abc import Callable
import shlex
from typing import Any

from personal_agent.tools.base import ToolResult


ConfirmCallback = Callable[[str], bool]


class ShellTool:
    """本地命令执行工具。

    Shell Tool 很强，也很危险，所以这里有三个保护：
    1. 风险命令执行前必须调用 confirm 回调，让用户二次确认
    2. 设置 timeout，避免命令卡死
    3. 不抛异常，所有结果都结构化返回给 Agent

    明确只读的命令会自动执行，避免用户在 `pwd`、`ls`、`git status`
    这类查询操作上频繁点确认。未知命令默认按风险命令处理。
    """

    name = "shell_exec"
    description = "执行本地 shell 命令；安全只读命令自动执行，风险命令需要用户确认。"

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

        confirmation_required = not is_safe_readonly_command(command)

        # 关键安全点：模型“想执行”不等于程序“允许执行”。
        # 只有安全只读命令，或用户明确确认的风险命令，才会进入 subprocess.run。
        if confirmation_required and not self.confirm(command):
            return ToolResult(
                ok=False,
                error="用户取消执行",
                metadata={
                    "command": command,
                    "exit_code": None,
                    "stderr": "",
                    "confirmation_required": confirmation_required,
                },
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
                    "confirmation_required": confirmation_required,
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
                "confirmation_required": confirmation_required,
            },
        )


def is_safe_readonly_command(command: str) -> bool:
    """判断 shell 命令是否属于明确安全的只读操作。

    这个函数采用 allowlist：只有能确定不会编辑、删除、写入、安装、
    提权或提交网络变更的命令才自动放行。任何未知命令都返回 False，
    交给 Shell Tool 的用户确认流程处理。
    """

    if _contains_write_or_control_operator(command):
        return False

    segments = [segment.strip() for segment in command.split("|")]
    if not segments:
        return False
    return all(_is_safe_readonly_segment(segment) for segment in segments)


def _contains_write_or_control_operator(command: str) -> bool:
    """识别容易产生写入、组合执行或命令替换风险的 shell 语法。"""

    risky_tokens = [">", "<", ";", "&&", "||", "`", "$("]
    return any(token in command for token in risky_tokens)


def _is_safe_readonly_segment(segment: str) -> bool:
    """判断管道中的单个命令片段是否为只读命令。"""

    try:
        parts = shlex.split(segment)
    except ValueError:
        return False
    if not parts:
        return False

    command_name = parts[0]
    args = parts[1:]
    if command_name in {"pwd", "ls", "cat", "head", "tail", "wc", "rg", "grep", "find"}:
        return _args_do_not_request_mutation(args)
    if command_name == "sed":
        return bool(args) and args[0] == "-n" and _args_do_not_request_mutation(args)
    if command_name == "git":
        return _is_safe_git_command(args)
    if command_name in {"python", "python3", "uv"}:
        return _is_safe_python_or_uv_command(command_name, args)
    return False


def _args_do_not_request_mutation(args: list[str]) -> bool:
    """检查参数中是否包含常见的写入或删除意图。"""

    risky_args = {
        "-delete",
        "--delete",
        "-exec",
        "-execdir",
        "-i",
        "--in-place",
        "--replace",
    }
    return not any(arg in risky_args for arg in args)


def _is_safe_git_command(args: list[str]) -> bool:
    """只放行常见只读 git 子命令。"""

    if not args:
        return False
    subcommand = args[0]
    readonly_without_mutation_flags = {"status", "diff", "log", "show", "rev-parse", "show-ref"}
    if subcommand in readonly_without_mutation_flags:
        return _args_do_not_request_mutation(args)
    if subcommand == "branch":
        return _git_args_only_use_options(args[1:], {"--all", "-a", "--list", "-l", "--show-current", "-v", "-vv"})
    if subcommand == "remote":
        return _git_args_only_use_options(args[1:], {"-v", "--verbose", "show"})
    if subcommand == "tag":
        return _git_args_only_use_options(args[1:], {"--list", "-l", "-n"})
    return False


def _git_args_only_use_options(args: list[str], allowed_options: set[str]) -> bool:
    """检查 git 子命令只使用明确只读的参数。

    `git branch -D`、`git tag -d`、`git remote remove` 都是修改仓库状态
    的操作，因此不能只因为子命令名称常见就自动放行。
    """

    return all(arg in allowed_options for arg in args)


def _is_safe_python_or_uv_command(command_name: str, args: list[str]) -> bool:
    """允许项目测试命令自动运行，但不允许任意 Python 脚本。"""

    if command_name in {"python", "python3"}:
        return len(args) >= 2 and args[:2] == ["-m", "unittest"]
    if command_name == "uv":
        return len(args) >= 3 and args[:3] == ["run", "python", "-m"] and args[3:4] == ["unittest"]
    return False
