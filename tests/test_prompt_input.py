import unittest

from personal_agent.cli.prompt_input import create_prompt_reader


class FakePromptSession:
    def __init__(self) -> None:
        self.prompts = []

    def prompt(self, prompt_text: str) -> str:
        self.prompts.append(prompt_text)
        return "用户输入"


class PromptInputTests(unittest.TestCase):
    def test_prompt_reader_uses_prompt_session_prompt_as_non_editable_prefix(self) -> None:
        """防止把 `> ` 当成普通输入文本，导致退格键可以删掉提示符。"""

        fake_session = FakePromptSession()
        read_input = create_prompt_reader(prompt_session=fake_session)

        value = read_input("> ")

        self.assertEqual(value, "用户输入")
        self.assertEqual(fake_session.prompts, ["> "])


if __name__ == "__main__":
    unittest.main()
