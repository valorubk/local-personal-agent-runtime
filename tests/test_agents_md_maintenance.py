import json
import tempfile
import unittest
from pathlib import Path

from personal_agent.agent.llm import LLMResponse
from personal_agent.agent.maintenance import AgentsMdMaintenanceService, PostTurnMaintenanceContext


class FakeLLMClient:
    """测试用 LLM 替身，用固定响应替代真实网络请求。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.messages_seen = []

    def complete(self, messages, tools):
        self.messages_seen.append(messages)
        return self.responses.pop(0)

    def stream_text(self, text):
        yield from text


class FailingLLMClient:
    """如果维护服务错误调用 LLM，测试应立即失败。"""

    def complete(self, messages, tools):
        raise AssertionError("未明示长期记忆意图时不应调用 AGENTS.md 更新判断 LLM")

    def stream_text(self, text):
        yield from text


class AgentsMdMaintenanceServiceTests(unittest.TestCase):
    """验证 `AGENTS.md` 维护服务独立承担 post-turn prompt 维护职责。"""

    def make_context(self, root: Path, user_input: str, final_response: str) -> PostTurnMaintenanceContext:
        """构造一轮任务结束后的维护上下文。

        测试用临时目录隔离 `AGENTS.md` 写入，避免污染真实用户目录。
        """

        return PostTurnMaintenanceContext(
            user_input=user_input,
            final_response=final_response,
            agents_home=root / "home",
            current_dir=root / "repo",
            workspace_root=root / "repo",
        )

    def test_skips_agents_update_when_llm_says_no_update(self) -> None:
        """防止没有长期偏好时仍创建或写入 `AGENTS.md`。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            llm = FakeLLMClient([LLMResponse(content='{"should_update": false}')])
            service = AgentsMdMaintenanceService(llm=llm)

            result = service.run(self.make_context(root, "帮我计算 1+1", "2"))

        self.assertIsNone(result)
        self.assertFalse((root / "home" / ".babyface" / "AGENTS.md").exists())

    def test_skips_llm_judgement_when_user_does_not_explicitly_ask_to_remember(self) -> None:
        """防止普通情绪或一次性请求被 LLM 自主沉淀到 `AGENTS.md`。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = AgentsMdMaintenanceService(llm=FailingLLMClient())

            result = service.run(self.make_context(root, "天在下雨，我好怕怕", "别怕，下雨天也可以很安心。"))

        self.assertIsNone(result)
        self.assertFalse((root / "home" / ".babyface" / "AGENTS.md").exists())

    def test_writes_agents_update_to_global_agents_md(self) -> None:
        """防止长期偏好候选没有被自动写入全局 managed section。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            llm = FakeLLMClient(
                [
                    LLMResponse(
                        content=json.dumps(
                            {
                                "should_update": True,
                                "target": "global",
                                "preference": "用户偏好先给结论，再补充关键细节。",
                                "reason": "用户表达了长期交流偏好。",
                            },
                            ensure_ascii=False,
                        )
                    ),
                    LLMResponse(
                        content=json.dumps(
                            {
                                "managed_preferences": [
                                    "用户偏好先给结论，再补充关键细节。",
                                ]
                            },
                            ensure_ascii=False,
                        )
                    ),
                ]
            )
            service = AgentsMdMaintenanceService(llm=llm)

            result = service.run(self.make_context(root, "以后回答请先给结论", "以后我会先给结论。"))

            agents_path = root / "home" / ".babyface" / "AGENTS.md"
            content = agents_path.read_text(encoding="utf-8")

        self.assertIsNotNone(result)
        self.assertEqual(result.target_path, agents_path)
        self.assertIn("- 用户偏好先给结论，再补充关键细节。", content)

    def test_uses_llm_resolved_managed_preferences_before_writing_conflict(self) -> None:
        """防止冲突时机械追加新规则，留下互相矛盾的 managed section。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agents_path = root / "home" / ".babyface" / "AGENTS.md"
            agents_path.parent.mkdir(parents=True)
            agents_path.write_text(
                "\n".join(
                    [
                        "# AGENTS.md",
                        "",
                        "## Babyface Learned Preferences",
                        "",
                        "<!-- babyface-managed:start -->",
                        "- 用户偏好回答必须简短。",
                        "<!-- babyface-managed:end -->",
                    ]
                ),
                encoding="utf-8",
            )
            llm = FakeLLMClient(
                [
                    LLMResponse(
                        content=json.dumps(
                            {
                                "should_update": True,
                                "target": "global",
                                "preference": "用户偏好回答必须详细解释。",
                                "reason": "用户表达了新的长期交流偏好。",
                            },
                            ensure_ascii=False,
                        )
                    ),
                    LLMResponse(
                        content=json.dumps(
                            {
                                "managed_preferences": [
                                    "用户偏好回答必须详细解释。",
                                ],
                                "conflict_resolution": "新规则替换旧的简短回答偏好。",
                            },
                            ensure_ascii=False,
                        )
                    ),
                ]
            )
            service = AgentsMdMaintenanceService(llm=llm)

            result = service.run(self.make_context(root, "以后回答要详细解释", "以后我会详细解释。"))

            content = agents_path.read_text(encoding="utf-8")

        self.assertIsNotNone(result)
        self.assertEqual(result.conflict_resolution, "新规则替换旧的简短回答偏好。")
        self.assertNotIn("用户偏好回答必须简短。", content)
        self.assertIn("- 用户偏好回答必须详细解释。", content)

    def test_retries_extraction_for_explicit_preference_request(self) -> None:
        """防止用户明确要求长期回复规则时，被第一轮保守判断静默吞掉。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agents_path = root / "home" / ".babyface" / "AGENTS.md"
            agents_path.parent.mkdir(parents=True)
            agents_path.write_text(
                "\n".join(
                    [
                        "# AGENTS.md",
                        "",
                        "## Babyface Learned Preferences",
                        "",
                        "<!-- babyface-managed:start -->",
                        "- 回复用户时需以“Ciallo～”开头，作为固定开场问候语",
                        "<!-- babyface-managed:end -->",
                    ]
                ),
                encoding="utf-8",
            )
            llm = FakeLLMClient(
                [
                    LLMResponse(content='{"should_update": false}'),
                    LLMResponse(
                        content=json.dumps(
                            {
                                "should_update": True,
                                "target": "global",
                                "preference": "回复用户时需以“okeydoky～”开头，作为固定开场问候语",
                                "reason": "用户明确要求替换固定回复开场白。",
                            },
                            ensure_ascii=False,
                        )
                    ),
                    LLMResponse(
                        content=json.dumps(
                            {
                                "managed_preferences": [
                                    "回复用户时需以“okeydoky～”开头，作为固定开场问候语",
                                ],
                                "conflict_resolution": "新开场白替换旧的 Ciallo 开场白。",
                            },
                            ensure_ascii=False,
                        )
                    ),
                ]
            )
            service = AgentsMdMaintenanceService(llm=llm)

            result = service.run(
                self.make_context(root, "记住在跟我回复的时候一定要先说这么一句话“OkeyDoky～”", "我会记住。")
            )

            content = agents_path.read_text(encoding="utf-8")
            extraction_messages = llm.messages_seen[1]

        self.assertIsNotNone(result)
        self.assertIn("当前已加载的 AGENTS.md", extraction_messages[1]["content"])
        self.assertNotIn("Ciallo", content)
        self.assertIn("okeydoky", content.lower())


if __name__ == "__main__":
    unittest.main()
