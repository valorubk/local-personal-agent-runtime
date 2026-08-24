from __future__ import annotations

from typing import Any

from personal_agent.tools.base import ToolResult


class WebTool:
    """Web Tool 占位。

    很多 Agent 都需要 Web Search，但 V1 的目标是先跑通本地 Runtime。
    这里先保留工具形状，让 Agent Runtime、Tool Registry、测试都能按统一接口工作。
    未来真正接入搜索 API 时，只需要替换 `run()` 的实现。
    """

    name = "web_search"
    description = "Web 能力占位，V1 尚未实现真实 Web Search。"

    def to_openai_tool(self) -> dict[str, Any]:
        """提前固定未来 Web Tool 的参数形状。"""

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索查询"}
                    },
                    "required": ["query"],
                },
            },
        }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        """V1 明确返回未实现，而不是静默失败。"""

        query = str(arguments.get("query") or "")
        return ToolResult(
            ok=False,
            error="Web Tool 尚未实现，V1 仅保留接口占位。",
            metadata={"query": query},
        )
