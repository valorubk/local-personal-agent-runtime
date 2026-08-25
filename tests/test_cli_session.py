import unittest

from personal_agent.agent.runtime import ExecutedTool, RuntimeResult
from personal_agent.cli.session import CLISession
from personal_agent.tools.base import ToolResult


class FakeRuntime:
    def __init__(self) -> None:
        self.inputs = []

    def run_turn(self, user_input: str) -> RuntimeResult:
        self.inputs.append(user_input)
        return RuntimeResult(final_response=f"收到：{user_input}", stream=[f"收到：{user_input}"])


class BrokenRuntime:
    def __init__(self) -> None:
        self.inputs = []

    def run_turn(self, user_input: str) -> RuntimeResult:
        self.inputs.append(user_input)
        raise RuntimeError("底层异常细节")


class CLISessionTests(unittest.TestCase):
    def test_session_keeps_running_until_exit_command(self) -> None:
        runtime = FakeRuntime()
        inputs = iter(["第一轮", "/exit"])
        outputs = []
        session = CLISession(
            runtime=runtime,  # type: ignore[arg-type]
            read_input=lambda prompt: next(inputs),
            write=outputs.append,
        )

        session.run()

        self.assertEqual(runtime.inputs, ["第一轮"])
        self.assertIn("再见。", outputs)
        self.assertIn("", outputs)
        self.assertIn("Babyface:", outputs)
        self.assertNotIn("Agent:", outputs)
        self.assertEqual(outputs[1:5], ["", "Babyface:", "收到：第一轮", ""])

    def test_session_catches_runtime_errors_and_keeps_running(self) -> None:
        runtime = BrokenRuntime()
        inputs = iter(["特殊字符输入", "/exit"])
        outputs = []
        session = CLISession(
            runtime=runtime,  # type: ignore[arg-type]
            read_input=lambda prompt: next(inputs),
            write=outputs.append,
        )

        session.run()

        rendered = "\n".join(outputs)
        self.assertEqual(runtime.inputs, ["特殊字符输入"])
        self.assertIn("系统异常", rendered)
        self.assertNotIn("Traceback", rendered)
        self.assertIn("再见。", outputs)

    def test_session_renders_mcp_tool_source(self) -> None:
        """防止外部 MCP Tool 调用时看不到来源 Server，难以排查配置。"""

        class McpRuntime:
            def run_turn(self, user_input: str) -> RuntimeResult:
                return RuntimeResult(
                    final_response="天气晴朗",
                    stream=["天气晴朗"],
                    tool_results=[
                        ExecutedTool(
                            id="call-1",
                            name="weather__forecast",
                            arguments={"city": "Shanghai"},
                            result=ToolResult(
                                ok=True,
                                content="晴",
                                metadata={"source": "mcp", "server": "weather"},
                            ),
                        )
                    ],
                )

        inputs = iter(["查天气", "/exit"])
        outputs = []
        session = CLISession(
            runtime=McpRuntime(),  # type: ignore[arg-type]
            read_input=lambda prompt: next(inputs),
            write=outputs.append,
        )

        session.run()

        self.assertIn("[Tool] weather__forecast 成功 (MCP: weather)", outputs)


if __name__ == "__main__":
    unittest.main()
