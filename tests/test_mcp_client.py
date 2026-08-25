import unittest

from personal_agent.config import ConfigError
from personal_agent.mcp.client import McpCallResult, McpServerManager, McpToolDefinition
from personal_agent.mcp.config import McpServerConfig
from personal_agent.tools.registry import ToolRegistry


class FakeMcpClient:
    """测试用 MCP Client，模拟外部 MCP Server 的最小行为。"""

    def __init__(self, tools=None, fail_start: Exception | None = None, fail_call: Exception | None = None) -> None:
        self._tools = tools or []
        self.fail_start = fail_start
        self.fail_call = fail_call
        self.closed = False
        self.calls: list[tuple[str, dict]] = []

    def connect(self) -> None:
        if self.fail_start:
            raise self.fail_start

    def list_tools(self) -> list[McpToolDefinition]:
        return self._tools

    def call_tool(self, name: str, arguments: dict) -> McpCallResult:
        if self.fail_call:
            raise self.fail_call
        self.calls.append((name, arguments))
        return McpCallResult(ok=True, content=f"{name}:{arguments['city']}")

    def close(self) -> None:
        self.closed = True


class McpClientTests(unittest.TestCase):
    def test_manager_registers_enabled_stdio_server_tools(self) -> None:
        """防止已启用 MCP Server 的工具没有暴露给 Agent。"""

        fake_client = FakeMcpClient(
            tools=[
                McpToolDefinition(
                    name="forecast",
                    description="查询天气",
                    input_schema={
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                )
            ]
        )
        manager = McpServerManager(
            [
                McpServerConfig(
                    name="weather",
                    transport="stdio",
                    command="python",
                    args=["-m", "mcp_weather_server"],
                )
            ],
            client_factory=lambda config: fake_client,
        )

        manager.start()
        tools = manager.tools()
        result = tools[0].run({"city": "Shanghai"})

        self.assertEqual(tools[0].name, "weather__forecast")
        self.assertEqual(tools[0].to_openai_tool()["function"]["name"], "weather__forecast")
        self.assertTrue(result.ok)
        self.assertEqual(result.content, "forecast:Shanghai")
        self.assertEqual(result.metadata["source"], "mcp")
        self.assertEqual(result.metadata["server"], "weather")
        self.assertEqual(fake_client.calls, [("forecast", {"city": "Shanghai"})])

    def test_manager_skips_disabled_servers_and_records_failed_servers(self) -> None:
        """防止单个 MCP Server 失败导致整个 Session 不可用。"""

        good_client = FakeMcpClient(
            tools=[McpToolDefinition(name="ok", description="ok", input_schema={"type": "object"})]
        )
        failed_client = FakeMcpClient(fail_start=RuntimeError("boom"))
        clients = {
            "disabled": FakeMcpClient(
                tools=[McpToolDefinition(name="hidden", description="hidden", input_schema={"type": "object"})]
            ),
            "broken": failed_client,
            "good": good_client,
        }
        manager = McpServerManager(
            [
                McpServerConfig(name="disabled", transport="stdio", enabled=False, command="python"),
                McpServerConfig(name="broken", transport="stdio", command="python"),
                McpServerConfig(name="good", transport="streamable_http", url="https://example.test/mcp"),
            ],
            client_factory=lambda config: clients[config.name],
        )

        manager.start()

        self.assertEqual([tool.name for tool in manager.tools()], ["good__ok"])
        self.assertEqual(len(manager.startup_errors), 1)
        self.assertIn("broken", manager.startup_errors[0])
        self.assertIn("boom", manager.startup_errors[0])

    def test_manager_closes_started_clients(self) -> None:
        """防止 CLI Session 退出后 MCP 连接或子进程残留。"""

        fake_client = FakeMcpClient()
        manager = McpServerManager(
            [McpServerConfig(name="weather", transport="stdio", command="python")],
            client_factory=lambda config: fake_client,
        )

        manager.start()
        manager.close()

        self.assertTrue(fake_client.closed)

    def test_tool_registry_rejects_duplicate_tool_names(self) -> None:
        """防止同名 Tool 静默覆盖，导致 LLM 调用到错误工具。"""

        tool = McpServerManager(
            [McpServerConfig(name="weather", transport="stdio", command="python")],
            client_factory=lambda config: FakeMcpClient(
                tools=[McpToolDefinition(name="forecast", description="a", input_schema={"type": "object"})]
            ),
        )
        tool.start()

        with self.assertRaises(ConfigError) as ctx:
            ToolRegistry([tool.tools()[0], tool.tools()[0]])

        self.assertIn("重复 Tool", str(ctx.exception))
        self.assertIn("weather__forecast", str(ctx.exception))

    def test_registry_turns_mcp_timeout_into_structured_tool_error(self) -> None:
        """防止外部 MCP Tool 超时异常让 Agent Session 崩溃。"""

        manager = McpServerManager(
            [McpServerConfig(name="weather", transport="stdio", command="python")],
            client_factory=lambda config: FakeMcpClient(
                tools=[
                    McpToolDefinition(
                        name="forecast",
                        description="查询天气",
                        input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
                    )
                ],
                fail_call=TimeoutError("timeout"),
            ),
        )
        manager.start()
        registry = ToolRegistry(manager.tools())

        result = registry.run("weather__forecast", {"city": "Shanghai"})

        self.assertFalse(result.ok)
        self.assertIn("Tool 执行失败", result.error or "")
        self.assertIn("timeout", result.error or "")

    def test_manager_rejects_unconvertible_mcp_tool_schema(self) -> None:
        """防止不可转换的 MCP schema 暴露给 LLM 后调用失败。"""

        manager = McpServerManager(
            [McpServerConfig(name="weather", transport="stdio", command="python")],
            client_factory=lambda config: FakeMcpClient(
                tools=[
                    McpToolDefinition(
                        name="forecast",
                        description="查询天气",
                        input_schema={"type": "array"},
                    )
                ]
            ),
        )

        manager.start()

        self.assertEqual(manager.tools(), [])
        self.assertEqual(len(manager.startup_errors), 1)
        self.assertIn("weather", manager.startup_errors[0])
        self.assertIn("input schema", manager.startup_errors[0])


if __name__ == "__main__":
    unittest.main()
