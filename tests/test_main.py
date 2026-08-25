import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from personal_agent.agent.runtime import RuntimeResult
from personal_agent.config import Settings
from personal_agent.main import app
from personal_agent.tools.base import ToolResult


class MainCLITests(unittest.TestCase):
    def test_help_shows_session_exit_commands(self) -> None:
        """防止把退出命令只放在启动提示里，导致用户只能进 Session 后才看到。"""

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Session 内退出命令", result.stdout)
        self.assertIn("exit", result.stdout)
        self.assertIn("quit", result.stdout)
        self.assertIn("/exit", result.stdout)

    def test_help_shows_debug_option(self) -> None:
        """防止新增调试模式后，用户无法从 help 发现 `--debug` 参数。"""

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--debug", result.stdout)
        self.assertIn("调试", result.stdout)

    def test_debug_option_does_not_print_trace_fields_to_cli(self) -> None:
        """防止调试模式把调用链路字段直接刷到命令行。"""

        class FakeRuntime:
            debug_recorder = None

            def __init__(self, **kwargs):
                FakeRuntime.debug_recorder = kwargs["debug_recorder"]

            def run_turn(self, user_input):
                return RuntimeResult(final_response=f"收到：{user_input}", stream=[f"收到：{user_input}"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(
                openai_api_key="test-key",
                openai_base_url=None,
                openai_model="test-model",
                memory_db_path=root / "memory.sqlite3",
                shell_timeout_seconds=3,
            )
            inputs = iter(["你好", "/exit"])
            runner = CliRunner()
            with (
                patch("personal_agent.main.load_settings", return_value=settings),
                patch("personal_agent.main.AgentRuntime", FakeRuntime),
                patch("personal_agent.main.create_prompt_reader", return_value=lambda prompt: next(inputs)),
            ):
                result = runner.invoke(app, ["--debug"])

        self.assertEqual(result.exit_code, 0)
        self.assertIsNotNone(FakeRuntime.debug_recorder)
        self.assertNotIn("llm_before", result.stdout)
        self.assertNotIn("tool_before", result.stdout)
        self.assertNotIn("session_id=", result.stdout)
        self.assertNotIn("trace_id=", result.stdout)

    def test_mcp_config_is_loaded_and_external_tools_are_registered(self) -> None:
        """防止 CLI 启动时只注册内置 Tool，忽略 MCP 配置文件。"""

        class FakeTool:
            name = "weather__forecast"
            description = "查询天气"

            def to_openai_tool(self):
                return {"type": "function", "function": {"name": self.name}}

            def run(self, arguments):
                return ToolResult(ok=True, content="晴")

        class FakeManager:
            startup_errors = ["MCP Server broken 启动失败：boom"]
            closed = False

            def __init__(self, configs):
                self.configs = configs

            def start(self):
                return None

            def tools(self):
                return [FakeTool()]

            def close(self):
                FakeManager.closed = True

        class FakeRuntime:
            tool_names = []

            def __init__(self, **kwargs):
                FakeRuntime.tool_names = kwargs["tools"].names()

            def run_turn(self, user_input):
                return RuntimeResult(final_response=f"收到：{user_input}", stream=[f"收到：{user_input}"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(
                openai_api_key="test-key",
                openai_base_url=None,
                openai_model="test-model",
                memory_db_path=root / "memory.sqlite3",
                shell_timeout_seconds=3,
                mcp_config_path=root / "mcp.json",
            )
            inputs = iter(["/exit"])
            runner = CliRunner()
            with (
                patch("personal_agent.main.load_settings", return_value=settings),
                patch("personal_agent.main.load_mcp_servers", return_value=[object()], create=True),
                patch("personal_agent.main.McpServerManager", FakeManager, create=True),
                patch("personal_agent.main.AgentRuntime", FakeRuntime),
                patch("personal_agent.main.create_prompt_reader", return_value=lambda prompt: next(inputs)),
            ):
                result = runner.invoke(app, [])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("weather__forecast", FakeRuntime.tool_names)
        self.assertIn("MCP Server broken 启动失败：boom", result.stdout)
        self.assertTrue(FakeManager.closed)


if __name__ == "__main__":
    unittest.main()
