import unittest

from typer.testing import CliRunner

from personal_agent.main import app


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


if __name__ == "__main__":
    unittest.main()
