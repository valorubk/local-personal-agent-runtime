from __future__ import annotations

from pathlib import Path
from typing import Any

from personal_agent.tools.base import ToolResult


class FileTool:
    """只读文件工具。

    这是最小 Personal Agent 很重要的能力：用户经常会让 Agent 总结本地笔记、
    配置文件或学习资料。V1 只读文本，不做写文件，降低误操作风险。
    """

    name = "file_read"
    description = "读取本地文本文件。"

    def to_openai_tool(self) -> dict[str, Any]:
        """声明给 LLM 的工具 schema。

        `parameters` 是 JSON Schema。模型看到这个 schema 后，会知道调用该工具时
        需要提供一个 `path` 字段。
        """

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "要读取的本地文件路径"}
                    },
                    "required": ["path"],
                },
            },
        }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        """执行文件读取。

        注意：模型传来的 `arguments` 不是可信输入，因此每一步都要校验：
        是否有 path、路径是否存在、是否是文件、是否能按 UTF-8 解码。
        """

        raw_path = arguments.get("path")
        if not raw_path:
            return ToolResult(ok=False, error="缺少文件路径。")

        # `expanduser()` 支持用户写 `~/notes.md` 这种路径。
        path = Path(str(raw_path)).expanduser()
        if not path.exists():
            return ToolResult(ok=False, error=f"文件不存在：{path}")
        if not path.is_file():
            return ToolResult(ok=False, error=f"路径不是文件：{path}")

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResult(ok=False, error=f"文件不是 UTF-8 文本：{path}")
        except OSError as exc:
            return ToolResult(ok=False, error=f"读取文件失败：{exc}")

        return ToolResult(ok=True, content=content, metadata={"path": str(path)})
