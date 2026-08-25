import tempfile
import unittest
from pathlib import Path

from personal_agent.prompt_profile import (
    AGENTS_MANAGED_END,
    AGENTS_MANAGED_START,
    build_agents_prompt,
    discover_agents_files,
    upsert_agents_preference,
    replace_managed_preferences,
    upsert_global_preference,
)


class PromptProfileTests(unittest.TestCase):
    def test_missing_agents_files_returns_empty_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            prompt = build_agents_prompt(
                home=root / "home",
                current_dir=root / "repo",
                workspace_root=root / "repo",
            )

        self.assertEqual(prompt, "")

    def test_reads_global_agents_md_before_workspace_agents_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            repo = root / "repo"
            current = repo / "feature"
            (home / ".babyface").mkdir(parents=True)
            current.mkdir(parents=True)
            (home / ".babyface" / "AGENTS.md").write_text("全局指令", encoding="utf-8")
            (repo / "AGENTS.md").write_text("项目指令", encoding="utf-8")
            (current / "AGENTS.md").write_text("局部指令", encoding="utf-8")

            files = discover_agents_files(home=home, current_dir=current, workspace_root=repo)
            prompt = build_agents_prompt(home=home, current_dir=current, workspace_root=repo)

        self.assertEqual(
            files,
            [
                (home / ".babyface" / "AGENTS.md").resolve(),
                (repo / "AGENTS.md").resolve(),
                (current / "AGENTS.md").resolve(),
            ],
        )
        self.assertLess(prompt.index("全局指令"), prompt.index("项目指令"))
        self.assertLess(prompt.index("项目指令"), prompt.index("局部指令"))

    def test_prompt_keeps_source_boundaries_and_conflicting_original_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            repo = root / "repo"
            current = repo / "app"
            (home / ".babyface").mkdir(parents=True)
            current.mkdir(parents=True)
            global_file = home / ".babyface" / "AGENTS.md"
            local_file = current / "AGENTS.md"
            global_file.write_text("回答必须简短。", encoding="utf-8")
            local_file.write_text("回答必须详细解释。", encoding="utf-8")

            prompt = build_agents_prompt(home=home, current_dir=current, workspace_root=repo)

        self.assertIn(f"Source: {global_file.resolve()}", prompt)
        self.assertIn(f"Source: {local_file.resolve()}", prompt)
        self.assertIn("回答必须简短。", prompt)
        self.assertIn("回答必须详细解释。", prompt)
        self.assertLess(prompt.index("回答必须简短。"), prompt.index("回答必须详细解释。"))

    def test_empty_agents_md_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            repo = root / "repo"
            repo.mkdir(parents=True)
            (home / ".babyface").mkdir(parents=True)
            (home / ".babyface" / "AGENTS.md").write_text("   \n", encoding="utf-8")
            (repo / "AGENTS.md").write_text("项目指令", encoding="utf-8")

            prompt = build_agents_prompt(home=home, current_dir=repo, workspace_root=repo)

        self.assertNotIn(str(home / ".babyface" / "AGENTS.md"), prompt)
        self.assertIn("项目指令", prompt)

    def test_upsert_global_preference_creates_managed_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)

            path = upsert_global_preference(home, "用户偏好先给结论。")

            content = path.read_text(encoding="utf-8")
        self.assertEqual(path, home / ".babyface" / "AGENTS.md")
        self.assertIn("## Babyface Learned Preferences", content)
        self.assertIn(AGENTS_MANAGED_START, content)
        self.assertIn("- 用户偏好先给结论。", content)
        self.assertIn(AGENTS_MANAGED_END, content)

    def test_upsert_global_preference_preserves_user_content_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / ".babyface" / "AGENTS.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                "\n".join(
                    [
                        "# AGENTS.md",
                        "",
                        "## Shared Instructions",
                        "用户手写内容",
                        "",
                        "## Babyface Learned Preferences",
                        "",
                        AGENTS_MANAGED_START,
                        "- 用户偏好先给结论。",
                        AGENTS_MANAGED_END,
                    ]
                ),
                encoding="utf-8",
            )

            upsert_global_preference(home, "用户偏好先给结论。")
            upsert_global_preference(home, "用户偏好使用中文。")

            content = path.read_text(encoding="utf-8")
        self.assertIn("用户手写内容", content)
        self.assertEqual(content.count("- 用户偏好先给结论。"), 1)
        self.assertIn("- 用户偏好使用中文。", content)

    def test_upsert_agents_preference_can_target_project_agents_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_agents = Path(tmp) / "project" / "AGENTS.md"

            path = upsert_agents_preference(project_agents, "当前项目回答要引用文件路径。")

            content = path.read_text(encoding="utf-8")
        self.assertEqual(path, project_agents)
        self.assertIn("- 当前项目回答要引用文件路径。", content)

    def test_replace_managed_preferences_replaces_only_managed_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "AGENTS.md"
            path.write_text(
                "\n".join(
                    [
                        "# AGENTS.md",
                        "",
                        "## Shared Instructions",
                        "用户手写内容",
                        "",
                        "## Babyface Learned Preferences",
                        "",
                        AGENTS_MANAGED_START,
                        "- 旧规则",
                        AGENTS_MANAGED_END,
                    ]
                ),
                encoding="utf-8",
            )

            replace_managed_preferences(path, ["新规则"])

            content = path.read_text(encoding="utf-8")
        self.assertIn("用户手写内容", content)
        self.assertNotIn("- 旧规则", content)
        self.assertIn("- 新规则", content)


if __name__ == "__main__":
    unittest.main()
