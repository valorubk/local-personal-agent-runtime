import json
import tempfile
import unittest
from pathlib import Path

from personal_agent.agent.llm import LLMResponse, ToolCall
from personal_agent.agent.runtime import AgentRuntime
from personal_agent.config import Settings
from personal_agent.memory.store import MemoryStore
from personal_agent.tools.base import ToolResult
from personal_agent.tools.registry import ToolRegistry


class FakeLLMClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.messages_seen = []

    def complete(self, messages, tools):
        self.messages_seen.append(messages)
        return self.responses.pop(0)

    def stream_text(self, text):
        for char in text:
            yield char


class Utf8EncodingCheckingLLMClient:
    """模拟 OpenAI SDK 在发送请求前会做的 JSON + UTF-8 编码检查。"""

    def __init__(self):
        self.messages_seen = []

    def complete(self, messages, tools):
        json.dumps(messages, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.messages_seen.append(messages)
        return LLMResponse(content="输入已经可以被模型处理。")

    def stream_text(self, text):
        yield from text


class EchoTool:
    name = "echo"
    description = "返回输入内容"

    def to_openai_tool(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
        }

    def run(self, arguments):
        return ToolResult(ok=True, content=arguments["text"], metadata={"source": "fake"})


class AgentRuntimeTests(unittest.TestCase):
    def make_settings(self, db_path: Path) -> Settings:
        return Settings(
            openai_api_key="test-key",
            openai_base_url=None,
            openai_model="test-model",
            memory_db_path=db_path,
            shell_timeout_seconds=3,
        )

    def test_runtime_answers_without_tool_and_saves_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.sqlite3")
            llm = FakeLLMClient([LLMResponse(content="你好，我在。")])
            runtime = AgentRuntime(
                settings=self.make_settings(Path(tmp) / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([]),
                llm=llm,
            )

            result = runtime.run_turn("你好")

            self.assertEqual(result.final_response, "你好，我在。")
            self.assertEqual("".join(result.stream), "你好，我在。")
            self.assertEqual(store.list_task_history()[0].user_input, "你好")

    def test_runtime_executes_tool_and_uses_result_in_final_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.sqlite3")
            llm = FakeLLMClient(
                [
                    LLMResponse(
                        content="",
                        tool_calls=[
                            ToolCall(
                                id="call-1",
                                name="echo",
                                arguments={"text": "工具结果"},
                            )
                        ],
                    ),
                    LLMResponse(content="最终：工具结果"),
                ]
            )
            runtime = AgentRuntime(
                settings=self.make_settings(Path(tmp) / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([EchoTool()]),
                llm=llm,
            )

            result = runtime.run_turn("调用工具")

            self.assertEqual(result.final_response, "最终：工具结果")
            self.assertEqual(result.tool_results[0].name, "echo")
            self.assertTrue(result.tool_results[0].result.ok)
            self.assertIn("工具结果", str(llm.messages_seen[-1]))

    def test_runtime_includes_previous_turns_in_next_llm_call(self) -> None:
        """防止短期记忆断掉。

        这个测试要捕获的生产问题是：如果 Runtime 每轮都只把当前 user input
        发给 LLM，那么用户在同一个 Session 里追问“我不爱吃什么”时，模型看不到
        上一轮“记住，我不爱吃梅菜扣肉”的上下文。
        """

        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.sqlite3")
            llm = FakeLLMClient(
                [
                    LLMResponse(content="已记录：你不爱吃梅菜扣肉。"),
                    LLMResponse(content="你不爱吃梅菜扣肉。"),
                ]
            )
            runtime = AgentRuntime(
                settings=self.make_settings(Path(tmp) / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([]),
                llm=llm,
            )

            runtime.run_turn("记住，我不爱吃梅菜扣肉")
            runtime.run_turn("我不爱吃什么")

            second_turn_messages = llm.messages_seen[1]
            self.assertIn({"role": "user", "content": "记住，我不爱吃梅菜扣肉"}, second_turn_messages)
            self.assertIn({"role": "assistant", "content": "已记录：你不爱吃梅菜扣肉。"}, second_turn_messages)
            self.assertEqual(second_turn_messages[-1], {"role": "user", "content": "我不爱吃什么"})

    def test_runtime_saves_profile_memory_from_natural_remember_phrases(self) -> None:
        """防止长期记忆只支持“记住：xxx”这一种机械句式。"""

        cases = [
            ("记住，我不爱吃梅菜扣肉", "我不爱吃梅菜扣肉"),
            ("我不爱吃梅菜扣肉，记住它", "我不爱吃梅菜扣肉"),
            ("请记住我不爱吃梅菜扣肉", "我不爱吃梅菜扣肉"),
        ]
        for user_input, expected_memory in cases:
            with self.subTest(user_input=user_input):
                with tempfile.TemporaryDirectory() as tmp:
                    store = MemoryStore(Path(tmp) / "memory.sqlite3")
                    llm = FakeLLMClient([LLMResponse(content="好的，我已记住。")])
                    runtime = AgentRuntime(
                        settings=self.make_settings(Path(tmp) / "memory.sqlite3"),
                        memory=store,
                        tools=ToolRegistry([]),
                        llm=llm,
                    )

                    runtime.run_turn(user_input)

                    self.assertIn(expected_memory, store.list_profile().values())

    def test_runtime_replaces_invalid_unicode_before_calling_llm(self) -> None:
        """防止终端输入里的 surrogate 字符击穿 OpenAI SDK 的 UTF-8 编码。"""

        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.sqlite3")
            llm = Utf8EncodingCheckingLLMClient()
            runtime = AgentRuntime(
                settings=self.make_settings(Path(tmp) / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([]),
                llm=llm,
            )

            result = runtime.run_turn("这个输入里有坏字符：\udce5")

            self.assertEqual(result.final_response, "输入已经可以被模型处理。")
            self.assertEqual(llm.messages_seen[0][-1]["content"], "这个输入里有坏字符：�")
            self.assertEqual(store.list_task_history()[0].user_input, "这个输入里有坏字符：�")


if __name__ == "__main__":
    unittest.main()
