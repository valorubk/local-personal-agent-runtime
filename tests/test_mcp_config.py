import json
import tempfile
import unittest
from pathlib import Path

from personal_agent.config import ConfigError
from personal_agent.mcp.config import load_mcp_servers


class McpConfigTests(unittest.TestCase):
    def test_loads_mcpservers_json_weather_server_from_config_file(self) -> None:
        """防止用户从 MCP 生态页面复制的 JSON 注册片段无法直接使用。"""

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "mcp.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "weather": {
                                "command": "python",
                                "args": ["-m", "mcp_weather_server"],
                                "disabled": False,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            servers = load_mcp_servers(config_path)

        self.assertEqual(len(servers), 1)
        self.assertEqual(servers[0].name, "weather")
        self.assertEqual(servers[0].transport, "stdio")
        self.assertTrue(servers[0].enabled)
        self.assertEqual(servers[0].command, "python")
        self.assertEqual(servers[0].args, ["-m", "mcp_weather_server"])

    def test_loads_streamable_http_server_from_json(self) -> None:
        """防止 MCP over HTTP 配置被误当成通用 HTTP Tool。"""

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "mcp.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "docs": {
                                "transport": "streamable_http",
                                "url": "https://example.test/mcp",
                                "headers": {"Authorization": "Bearer ${DOCS_TOKEN}"},
                                "timeout_seconds": 30,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            servers = load_mcp_servers(config_path)

        self.assertEqual(servers[0].name, "docs")
        self.assertEqual(servers[0].transport, "streamable_http")
        self.assertEqual(servers[0].url, "https://example.test/mcp")
        self.assertEqual(servers[0].headers["Authorization"], "Bearer ${DOCS_TOKEN}")
        self.assertEqual(servers[0].timeout_seconds, 30)

    def test_loads_yaml_when_json_is_not_used(self) -> None:
        """防止只接受 JSON 后破坏用户手写 YAML 配置的兼容性。"""

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "mcp.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "mcp_servers:",
                        "  weather:",
                        "    transport: stdio",
                        "    command: python",
                        "    args:",
                        "      - -m",
                        "      - mcp_weather_server",
                        "    enabled: true",
                    ]
                ),
                encoding="utf-8",
            )

            servers = load_mcp_servers(config_path)

        self.assertEqual(servers[0].name, "weather")
        self.assertEqual(servers[0].args, ["-m", "mcp_weather_server"])

    def test_rejects_malformed_mcp_config_with_chinese_error(self) -> None:
        """防止配置缺少 stdio command 时进入后续启动阶段才失败。"""

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "mcp.json"
            config_path.write_text(
                json.dumps({"mcpServers": {"broken": {"transport": "stdio"}}}),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigError) as ctx:
                load_mcp_servers(config_path)

        self.assertIn("broken", str(ctx.exception))
        self.assertIn("command", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
