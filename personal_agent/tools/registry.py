from __future__ import annotations

from typing import Iterable

from personal_agent.config import ConfigError
from personal_agent.tools.base import Tool, ToolResult


class ToolRegistry:
    """Tool 注册表。

    Agent Runtime 不直接依赖某个具体 Tool，而是依赖 Registry。
    这样未来增加 Web Search、日历、邮件、RAG 等工具时，只需要注册进去，
    Runtime 的主循环不用大改。
    """

    def __init__(self, tools: Iterable[Tool]) -> None:
        # 用 name 建索引，方便 LLM 请求 `shell_exec` 时快速找到对应工具。
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ConfigError(f"重复 Tool 名称：{tool.name}")
            self._tools[tool.name] = tool

    def list_openai_tools(self) -> list[dict]:
        """把所有工具转换成 OpenAI SDK 需要的 tools 参数。"""

        return [tool.to_openai_tool() for tool in self._tools.values()]

    def run(self, name: str, arguments: dict) -> ToolResult:
        """按名称执行工具，并把异常隔离成结构化 ToolResult。

        这里不让异常冒泡到 CLI，是因为 Agent Session 应该持续运行。
        工具失败只是一轮推理里的信息，不应该让整个程序崩掉。
        """

        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, error=f"未知 Tool：{name}")
        try:
            return tool.run(arguments)
        except Exception as exc:  # noqa: BLE001 - Tool 错误需要隔离到结构化结果
            return ToolResult(ok=False, error=f"Tool 执行失败：{exc}")

    def names(self) -> list[str]:
        return sorted(self._tools)
