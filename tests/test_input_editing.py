import unittest

from personal_agent.cli.input_editing import enable_terminal_input_editing


class FakeReadline:
    def __init__(self) -> None:
        self.bindings = []

    def parse_and_bind(self, binding: str) -> None:
        self.bindings.append(binding)


class TerminalInputEditingTests(unittest.TestCase):
    def test_enable_terminal_input_editing_configures_readline_bindings(self) -> None:
        """防止真实 CLI 忘记启用 readline，导致方向键变成 ^[[A 这类字符。"""

        fake_readline = FakeReadline()

        enabled = enable_terminal_input_editing(readline_module=fake_readline)

        self.assertTrue(enabled)
        self.assertIn("set editing-mode emacs", fake_readline.bindings)
        self.assertIn('"\\e[3~": delete-char', fake_readline.bindings)
        self.assertIn("bind ^[[3~ ed-delete-next-char", fake_readline.bindings)


if __name__ == "__main__":
    unittest.main()
