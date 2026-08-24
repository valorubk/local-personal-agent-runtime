import tempfile
import unittest
from pathlib import Path

from personal_agent.config import ConfigError, load_settings


class ConfigTests(unittest.TestCase):
    def test_missing_api_key_returns_chinese_error(self) -> None:
        with self.assertRaises(ConfigError) as ctx:
            load_settings(env={})

        self.assertIn("OPENAI_API_KEY", str(ctx.exception))
        self.assertIn("请配置", str(ctx.exception))

    def test_env_overrides_default_sqlite_path_and_timeout(self) -> None:
        settings = load_settings(
            env={
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "test-model",
                "BABYFACE_MEMORY_DB_PATH": "/tmp/custom.sqlite3",
                "BABYFACE_SHELL_TIMEOUT_SECONDS": "7",
            }
        )

        self.assertEqual(settings.openai_api_key, "test-key")
        self.assertEqual(settings.openai_model, "test-model")
        self.assertEqual(settings.memory_db_path, Path("/tmp/custom.sqlite3"))
        self.assertEqual(settings.shell_timeout_seconds, 7)

    def test_project_config_file_is_read_when_env_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "babyface.toml"
            config_path.write_text(
                "\n".join(
                    [
                        'openai_api_key = "file-key"',
                        'openai_model = "file-model"',
                        'memory_db_path = "data/memory.sqlite3"',
                        "shell_timeout_seconds = 3",
                    ]
                ),
                encoding="utf-8",
            )

            settings = load_settings(env={}, config_path=config_path)

        self.assertEqual(settings.openai_api_key, "file-key")
        self.assertEqual(settings.openai_model, "file-model")
        self.assertEqual(settings.memory_db_path, Path("data/memory.sqlite3"))
        self.assertEqual(settings.shell_timeout_seconds, 3)

    def test_config_file_accepts_uppercase_llm_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "babyface.local.toml"
            config_path.write_text(
                "\n".join(
                    [
                        'OPENAI_API_KEY = "alias-key"',
                        'BASE_URL = "https://example.test/v1"',
                        'MODEL = "alias-model"',
                    ]
                ),
                encoding="utf-8",
            )

            settings = load_settings(env={}, config_path=config_path)

        self.assertEqual(settings.openai_api_key, "alias-key")
        self.assertEqual(settings.openai_base_url, "https://example.test/v1")
        self.assertEqual(settings.openai_model, "alias-model")


if __name__ == "__main__":
    unittest.main()
