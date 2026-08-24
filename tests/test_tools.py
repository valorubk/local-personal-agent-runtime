import tempfile
import unittest
from pathlib import Path

from personal_agent.tools.file_tool import FileTool
from personal_agent.tools.shell_tool import ShellTool
from personal_agent.tools.web_tool import WebTool


class ToolTests(unittest.TestCase):
    def test_file_tool_reads_existing_text_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.txt"
            path.write_text("你好，Babyface", encoding="utf-8")

            result = FileTool().run({"path": str(path)})

        self.assertTrue(result.ok)
        self.assertEqual(result.content, "你好，Babyface")

    def test_file_tool_reports_missing_file(self) -> None:
        result = FileTool().run({"path": "/no/such/file.txt"})

        self.assertFalse(result.ok)
        self.assertIn("文件不存在", result.error or "")

    def test_shell_tool_returns_stdout_stderr_and_exit_code_after_confirmation(self) -> None:
        tool = ShellTool(timeout_seconds=3, confirm=lambda command: True)

        result = tool.run({"command": "printf hello"})

        self.assertTrue(result.ok)
        self.assertEqual(result.content, "hello")
        self.assertEqual(result.metadata["exit_code"], 0)
        self.assertEqual(result.metadata["stderr"], "")

    def test_shell_tool_does_not_execute_when_user_rejects(self) -> None:
        tool = ShellTool(timeout_seconds=3, confirm=lambda command: False)

        result = tool.run({"command": "printf should-not-run"})

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "用户取消执行")
        self.assertEqual(result.metadata["exit_code"], None)

    def test_web_tool_returns_not_implemented_result(self) -> None:
        result = WebTool().run({"query": "今天新闻"})

        self.assertFalse(result.ok)
        self.assertIn("尚未实现", result.error or "")


if __name__ == "__main__":
    unittest.main()
