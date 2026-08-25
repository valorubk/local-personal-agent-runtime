import unittest

from rich.align import Align

from personal_agent.cli.banner import build_startup_banner


class BannerTests(unittest.TestCase):
    def test_startup_banner_contains_babyface_without_exit_hint(self) -> None:
        """防止启动 Banner 退回普通中文提示，或把退出说明又塞回 Banner。"""

        banner = build_startup_banner()
        plain_text = banner.renderable.renderable.plain
        lines = [line for line in plain_text.splitlines() if line.strip()]

        self.assertIsInstance(banner.renderable, Align)
        self.assertEqual(banner.renderable.align, "center")
        self.assertEqual(banner.renderable.vertical, "middle")
        self.assertNotEqual(lines[0], "BABYFACE")
        self.assertIn("- Your Local Personal Agent -", plain_text)
        self.assertNotIn("exit", plain_text)
        self.assertNotIn("quit", plain_text)
        self.assertNotIn("/exit", plain_text)
        self.assertNotIn("Debug mode", plain_text)

    def test_debug_startup_banner_marks_debug_mode(self) -> None:
        """防止用户以调试模式启动后，Banner 没有明确提示当前运行模式。"""

        banner = build_startup_banner(debug=True)
        plain_text = banner.renderable.renderable.plain

        self.assertIn("- Your Local Personal Agent -", plain_text)
        self.assertIn("Debug mode", plain_text)


if __name__ == "__main__":
    unittest.main()
