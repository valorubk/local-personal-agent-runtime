from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from personal_agent.mcp.config import McpServerConfig
from personal_agent.tools.base import ToolResult


@dataclass(frozen=True)
class McpToolDefinition:
    """外部 MCP Server 暴露的 Tool 定义。

    MCP SDK 返回的对象字段会随版本略有差异。Babyface 先把它归一化成
    这个小模型，后续 Tool 适配层只依赖 `name/description/input_schema`。
    """

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class McpCallResult:
    """一次 MCP Tool 调用的归一化结果。"""

    ok: bool
    content: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class McpServerClient(Protocol):
    """MCP Server Client 协议。

    生产环境实现会包住 MCP SDK；测试环境可以传入 fake client。
    这样 MCP 管理器的行为可以在不启动真实外部进程的情况下被测试。
    """

    def connect(self) -> None:
        """建立 MCP 连接或启动 stdio 子进程。"""
        ...

    def list_tools(self) -> list[McpToolDefinition]:
        """列出当前 MCP Server 暴露的工具。"""
        ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> McpCallResult:
        """调用指定 MCP Tool。"""
        ...

    def close(self) -> None:
        """关闭 MCP 连接或本地子进程。"""
        ...


class McpToolAdapter:
    """把 MCP Tool 适配成 Babyface 现有 Tool 协议。

    Agent Runtime 已经只认识 `Tool` 协议。适配器负责把 MCP 的 tool name、
    input schema 和调用结果转换成 Runtime/CLI/Memory 都能理解的统一形状。
    """

    def __init__(
        self,
        *,
        server_name: str,
        definition: McpToolDefinition,
        client: McpServerClient,
    ) -> None:
        self.server_name = server_name
        self.mcp_tool_name = definition.name
        self.name = _namespace_tool_name(server_name, definition.name)
        self.description = f"{definition.description}（来自 MCP Server：{server_name}）"
        self.input_schema = _normalize_input_schema(server_name, definition)
        self._client = client

    def to_openai_tool(self) -> dict[str, Any]:
        """返回 OpenAI tool calling 需要的 JSON schema。"""

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        """调用 MCP Tool，并转换为 Babyface 的统一 ToolResult。"""

        result = self._client.call_tool(self.mcp_tool_name, arguments)
        metadata = {
            "source": "mcp",
            "server": self.server_name,
            "tool": self.mcp_tool_name,
            **result.metadata,
        }
        return ToolResult(
            ok=result.ok,
            content=result.content,
            error=result.error,
            metadata=metadata,
        )


class McpServerManager:
    """管理多个 MCP Server 的启动、Tool 发现和关闭。

    CLI Session 在创建 AgentRuntime 前调用 `start()`，拿到 `tools()` 后注入
    ToolRegistry；Session 退出时调用 `close()`，避免外部连接残留。
    """

    def __init__(
        self,
        configs: list[McpServerConfig],
        *,
        client_factory: Callable[[McpServerConfig], McpServerClient] | None = None,
    ) -> None:
        self.configs = configs
        self.client_factory = client_factory or create_mcp_client
        self.startup_errors: list[str] = []
        self._clients: list[McpServerClient] = []
        self._tools: list[McpToolAdapter] = []

    def start(self) -> None:
        """启动所有已启用的 MCP Server，并注册它们的 Tool。"""

        self.startup_errors.clear()
        self._tools.clear()
        for config in self.configs:
            if not config.enabled:
                continue
            client = self.client_factory(config)
            try:
                client.connect()
                definitions = client.list_tools()
                adapters = [
                    McpToolAdapter(server_name=config.name, definition=definition, client=client)
                    for definition in definitions
                ]
            except Exception as exc:  # noqa: BLE001 - 外部 Server 异常需要降级
                self.startup_errors.append(f"MCP Server {config.name} 启动失败：{exc}")
                try:
                    client.close()
                except Exception:
                    pass
                continue
            self._clients.append(client)
            self._tools.extend(adapters)

    def tools(self) -> list[McpToolAdapter]:
        """返回已成功注册的 MCP Tool。"""

        return list(self._tools)

    def close(self) -> None:
        """关闭所有已启动的 MCP Client。"""

        for client in reversed(self._clients):
            client.close()
        self._clients.clear()


def create_mcp_client(config: McpServerConfig) -> McpServerClient:
    """根据配置创建真实 MCP Client。"""

    return SdkMcpServerClient(config)


class SdkMcpServerClient:
    """基于官方 MCP SDK 的同步包装。

    Babyface 现有 Tool 协议是同步的，所以这里用独立 event loop 包住 MCP SDK
    的异步 API。未来如果 Runtime 改为 async，可以把这一层删除。
    """

    def __init__(self, config: McpServerConfig) -> None:
        self.config = config
        self._loop = asyncio.new_event_loop()
        self._stack = AsyncExitStack()
        self._session: Any | None = None

    def connect(self) -> None:
        self._loop.run_until_complete(self._connect())

    async def _connect(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        if self.config.transport == "stdio":
            params = StdioServerParameters(
                command=self.config.command or "",
                args=self.config.args,
                env=self.config.env or None,
            )
            read_stream, write_stream = await self._stack.enter_async_context(stdio_client(params))
        else:
            import httpx
            from mcp.client.streamable_http import streamable_http_client

            http_client = await self._stack.enter_async_context(
                httpx.AsyncClient(
                    headers=self.config.headers or None,
                    timeout=self.config.timeout_seconds,
                )
            )
            read_stream, write_stream, _ = await self._stack.enter_async_context(
                streamable_http_client(self.config.url or "", http_client=http_client)
            )

        self._session = await self._stack.enter_async_context(ClientSession(read_stream, write_stream))
        await self._session.initialize()

    def list_tools(self) -> list[McpToolDefinition]:
        result = self._loop.run_until_complete(self._session.list_tools())  # type: ignore[union-attr]
        return [_definition_from_sdk_tool(tool) for tool in result.tools]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> McpCallResult:
        try:
            result = self._loop.run_until_complete(self._session.call_tool(name, arguments))  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 - 外部 Tool 错误要回传给 Agent
            return McpCallResult(ok=False, error=f"MCP Tool 调用失败：{exc}")
        return McpCallResult(ok=not getattr(result, "isError", False), content=_content_to_text(result))

    def close(self) -> None:
        self._loop.run_until_complete(self._stack.aclose())
        self._loop.close()


def _definition_from_sdk_tool(tool: Any) -> McpToolDefinition:
    """把 MCP SDK Tool 对象转换为内部 Tool 定义。"""

    return McpToolDefinition(
        name=str(getattr(tool, "name")),
        description=str(getattr(tool, "description", "") or ""),
        input_schema=dict(
            getattr(tool, "inputSchema", None)
            or getattr(tool, "input_schema", None)
            or {"type": "object", "properties": {}}
        ),
    )


def _content_to_text(result: Any) -> str:
    """把 MCP SDK 返回内容转换成可喂给 LLM 的文本。"""

    parts: list[str] = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(str(text))
        else:
            parts.append(str(item))
    return "\n".join(parts)


def _normalize_input_schema(server_name: str, definition: McpToolDefinition) -> dict[str, Any]:
    """校验并归一化 MCP Tool input schema。

    OpenAI function parameters 需要对象型 JSON schema。遇到数组、字符串等
    顶层 schema 时，先拒绝注册，避免 LLM 看到不可调用的工具。
    """

    schema = definition.input_schema or {"type": "object", "properties": {}}
    if not isinstance(schema, dict) or schema.get("type", "object") != "object":
        raise ValueError(f"MCP Server {server_name} 的 Tool {definition.name} input schema 不可转换。")
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    return schema


def _namespace_tool_name(server_name: str, tool_name: str) -> str:
    """生成兼容 OpenAI tool name 约束的命名空间名称。"""

    return f"{_sanitize_name(server_name)}__{_sanitize_name(tool_name)}"


def _sanitize_name(name: str) -> str:
    """只保留 OpenAI function name 允许的字符。"""

    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in name)
