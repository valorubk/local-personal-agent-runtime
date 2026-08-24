import unittest

from personal_agent.cli.banner import build_startup_banner


class BannerTests(unittest.TestCase):
    def test_startup_banner_contains_babyface_without_exit_hint(self) -> None:
        """防止启动 Banner 退回普通中文提示，或把退出说明又塞回 Banner。"""

        banner = build_startup_banner()
        plain_text = banner.renderable.plain

        self.assertIn("BABYFACE", plain_text)
        self.assertNotIn("exit", plain_text)
        self.assertNotIn("quit", plain_text)
        self.assertNotIn("/exit", plain_text)


if __name__ == "__main__":
    unittest.main()
