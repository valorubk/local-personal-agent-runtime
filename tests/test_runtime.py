import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path

from personal_agent.agent.llm import LLMResponse, ToolCall
from personal_agent.agent.runtime import AgentRuntime
from personal_agent.config import Settings
from personal_agent.debug_trace import DebugTraceRecorder, DebugTraceStore
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


class SuccessfulAppTool:
    """模拟成功打开 App 的工具。

    这个替身用于验证 Runtime 对 app_open 成功结果的最终回答约束，
    不需要真的启动 macOS 应用。
    """

    name = "app_open"
    description = "打开 App"

    def to_openai_tool(self):
        return {"type": "function", "function": {"name": self.name}}

    def run(self, arguments):
        return ToolResult(
            ok=True,
            content="已成功打开 App：网易云音乐",
            metadata={"matched_app": "网易云音乐", "match_method": "fuzzy"},
        )


class SuccessfulHttpTitleTool:
    """模拟 HTTP Tool 从 HTML 中解析出网页标题。"""

    name = "http_request"
    description = "发送 HTTP 请求"

    def to_openai_tool(self):
        return {"type": "function", "function": {"name": self.name}}

    def run(self, arguments):
        return ToolResult(
            ok=True,
            content="网页标题: 真实网页标题",
            metadata={"response_type": "html", "title": "真实网页标题"},
        )


class RecordingAgentsMdMaintenance:
    """记录 Runtime 是否在一轮结束后调用维护服务。"""

    def __init__(self, memory: MemoryStore, runtime_getter):
        self.memory = memory
        self.runtime_getter = runtime_getter
        self.contexts = []
        self.history_counts_at_call = []
        self.conversation_lengths_at_call = []

    def run(self, context):
        self.contexts.append(context)
        self.history_counts_at_call.append(len(self.memory.list_task_history()))
        self.conversation_lengths_at_call.append(len(self.runtime_getter().conversation_history))
        return None


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

    def test_runtime_returns_short_confirmation_after_successful_app_open(self) -> None:
        """防止 App 已成功打开后，最终回答继续输出无谓的排查建议。"""

        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.sqlite3")
            llm = FakeLLMClient(
                [
                    LLMResponse(
                        content="",
                        tool_calls=[
                            ToolCall(
                                id="call-app",
                                name="app_open",
                                arguments={"app_name": "网易云音乐"},
                            )
                        ],
                    ),
                    LLMResponse(content="已打开。如果仍然无法打开，请确认路径和权限。"),
                ]
            )
            runtime = AgentRuntime(
                settings=self.make_settings(Path(tmp) / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([SuccessfulAppTool()]),
                llm=llm,
            )

            result = runtime.run_turn("打开网易云音乐")

        self.assertEqual(result.final_response, "已成功打开网易云音乐。")

    def test_runtime_rejects_app_open_success_claim_without_tool_call(self) -> None:
        """防止模型没有调用 app_open 工具，却声称本机 App 已成功打开。"""

        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.sqlite3")
            llm = FakeLLMClient([LLMResponse(content="已成功打开IINA。")])
            runtime = AgentRuntime(
                settings=self.make_settings(Path(tmp) / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([SuccessfulAppTool()]),
                llm=llm,
            )

            result = runtime.run_turn("打开IINA APP")

        self.assertEqual(result.tool_results, [])
        self.assertIn("没有实际调用 app_open 工具", result.final_response)
        self.assertNotIn("已成功打开IINA", result.final_response)

    def test_system_prompt_requires_app_open_tool_for_opening_apps(self) -> None:
        """防止模型把打开本机 App 这种副作用任务当成普通文本回复。"""

        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.sqlite3")
            llm = FakeLLMClient([LLMResponse(content="需要调用工具。")])
            runtime = AgentRuntime(
                settings=self.make_settings(Path(tmp) / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([SuccessfulAppTool()]),
                llm=llm,
            )

            runtime.run_turn("打开IINA APP")

        system_prompt = llm.messages_seen[0][0]["content"]
        self.assertIn("打开本机 App", system_prompt)
        self.assertIn("必须调用 app_open", system_prompt)
        self.assertIn("不得声称已经打开", system_prompt)

    def test_runtime_uses_http_title_metadata_when_user_asks_for_page_title(self) -> None:
        """防止 HTTP Tool 已解析标题后，最终回答仍被 LLM 编造成其他标题。"""

        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.sqlite3")
            llm = FakeLLMClient(
                [
                    LLMResponse(
                        content="",
                        tool_calls=[
                            ToolCall(
                                id="call-http",
                                name="http_request",
                                arguments={"url": "https://example.test/video"},
                            )
                        ],
                    ),
                    LLMResponse(content="这个网页标题是：虚假的网页标题"),
                ]
            )
            runtime = AgentRuntime(
                settings=self.make_settings(Path(tmp) / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([SuccessfulHttpTitleTool()]),
                llm=llm,
            )

            result = runtime.run_turn("告诉我这个网页下的视频的标题是什么 https://example.test/video")

        self.assertEqual(result.final_response, "网页标题：真实网页标题")

    def test_system_prompt_tells_model_to_use_tools_or_ask_for_missing_arguments(self) -> None:
        """防止模型在天气等实时信息场景中不调用工具也不追问必要参数。"""

        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.sqlite3")
            llm = FakeLLMClient([LLMResponse(content="你想查哪个城市？")])
            runtime = AgentRuntime(
                settings=self.make_settings(Path(tmp) / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([EchoTool()]),
                llm=llm,
            )

            runtime.run_turn("今天天气怎么样")

        system_prompt = llm.messages_seen[0][0]["content"]
        self.assertIn("实时信息", system_prompt)
        self.assertIn("优先调用工具", system_prompt)
        self.assertIn("必要参数", system_prompt)
        self.assertIn("追问", system_prompt)

    def test_debug_trace_records_session_and_distinct_trace_ids_across_turns(self) -> None:
        """防止调试链路无法按同一 Session 下的不同对话轮次回溯。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = MemoryStore(root / "memory.sqlite3")
            llm = FakeLLMClient(
                [
                    LLMResponse(content="第一轮"),
                    LLMResponse(content="第二轮"),
                ]
            )
            runtime = AgentRuntime(
                settings=self.make_settings(root / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([]),
                llm=llm,
                debug_recorder=DebugTraceRecorder(
                    session_id="session-fixed",
                    store=DebugTraceStore(root),
                    now=lambda: datetime(2026, 8, 25, 19, 6, 1),
                ),
            )

            runtime.run_turn("你好")
            runtime.run_turn("继续")

            db_path = root / ".babyface" / "debug" / "debug_trace_20260825"
            with closing(sqlite3.connect(db_path)) as conn:
                rows = conn.execute(
                    "SELECT session_id, trace_id FROM debug_trace_events ORDER BY id"
                ).fetchall()

        session_ids = {row[0] for row in rows}
        trace_ids = {row[1] for row in rows}
        self.assertEqual(session_ids, {"session-fixed"})
        self.assertEqual(len(trace_ids), 2)

    def test_debug_trace_records_llm_tool_and_skill_stages_to_sqlite(self) -> None:
        """防止切面记录漏掉 LLM、Tool 或 Skill 的前后置阶段。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = MemoryStore(root / "memory.sqlite3")
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
            runtime_ref = {}
            maintenance = RecordingAgentsMdMaintenance(store, lambda: runtime_ref["runtime"])
            runtime = AgentRuntime(
                settings=self.make_settings(root / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([EchoTool()]),
                llm=llm,
                enable_agents_update=True,
                agents_md_maintenance=maintenance,
                debug_recorder=DebugTraceRecorder(
                    session_id="session-fixed",
                    store=DebugTraceStore(root),
                    now=lambda: datetime(2026, 8, 25, 19, 6, 1),
                ),
            )
            runtime_ref["runtime"] = runtime

            runtime.run_turn("调用工具")

            db_path = root / ".babyface" / "debug" / "debug_trace_20260825"
            with closing(sqlite3.connect(db_path)) as conn:
                stages = [
                    row[0]
                    for row in conn.execute(
                        "SELECT stage FROM debug_trace_events ORDER BY id"
                    ).fetchall()
                ]

        for stage in [
            "user_input_received",
            "llm_before",
            "llm_after",
            "tool_before",
            "tool_after",
            "skill_before",
            "skill_after",
        ]:
            self.assertIn(stage, stages)

    def test_task_history_and_tool_calls_share_debug_trace_ids(self) -> None:
        """防止 Memory 历史无法和 debug trace 按 session_id/trace_id 关联。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = MemoryStore(root / "memory.sqlite3")
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
                settings=self.make_settings(root / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([EchoTool()]),
                llm=llm,
                debug_recorder=DebugTraceRecorder(
                    session_id="session-fixed",
                    store=DebugTraceStore(root),
                    now=lambda: datetime(2026, 8, 25, 19, 6, 1),
                ),
            )

            runtime.run_turn("调用工具")

            history = store.list_task_history()[0]
            debug_db_path = root / ".babyface" / "debug" / "debug_trace_20260825"
            with closing(sqlite3.connect(debug_db_path)) as conn:
                debug_ids = conn.execute(
                    "SELECT DISTINCT session_id, trace_id FROM debug_trace_events"
                ).fetchall()

        self.assertEqual(history.session_id, "session-fixed")
        self.assertEqual(history.tool_calls[0]["session_id"], history.session_id)
        self.assertEqual(history.tool_calls[0]["trace_id"], history.trace_id)
        self.assertEqual(debug_ids, [(history.session_id, history.trace_id)])

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

    def test_runtime_uses_builtin_prompt_when_agents_md_is_missing(self) -> None:
        """防止新增 AGENTS.md 支持后，没有配置文件的默认启动路径被破坏。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = MemoryStore(root / "memory.sqlite3")
            llm = FakeLLMClient([LLMResponse(content="你好，我在。")])
            runtime = AgentRuntime(
                settings=self.make_settings(root / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([]),
                llm=llm,
                agents_home=root / "home",
                current_dir=root / "repo",
                workspace_root=root / "repo",
            )

            runtime.run_turn("你好")

            first_message = llm.messages_seen[0][0]
            self.assertEqual(first_message["role"], "system")
            self.assertIn("你是 Babyface", first_message["content"])
            self.assertNotIn("Source:", first_message["content"])

    def test_runtime_includes_agents_md_original_text_in_first_system_message(self) -> None:
        """防止 Runtime 把 AGENTS.md 总结、吞掉或放到错误的 message 里。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            repo = root / "repo"
            current = repo / "app"
            (home / ".babyface").mkdir(parents=True)
            current.mkdir(parents=True)
            (home / ".babyface" / "AGENTS.md").write_text("回答必须简短。", encoding="utf-8")
            (current / "AGENTS.md").write_text("回答必须详细解释。", encoding="utf-8")
            store = MemoryStore(root / "memory.sqlite3")
            llm = FakeLLMClient([LLMResponse(content="收到。")])
            runtime = AgentRuntime(
                settings=self.make_settings(root / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([]),
                llm=llm,
                agents_home=home,
                current_dir=current,
                workspace_root=repo,
            )

            runtime.run_turn("你好")

            first_prompt = llm.messages_seen[0][0]["content"]
            memory_prompt = llm.messages_seen[0][1]["content"]
            self.assertIn("你是 Babyface", first_prompt)
            self.assertIn("后出现", first_prompt)
            self.assertIn("不得删除、改写或总结任何 AGENTS.md 内容", first_prompt)
            self.assertIn("回答必须简短。", first_prompt)
            self.assertIn("回答必须详细解释。", first_prompt)
            self.assertLess(first_prompt.index("回答必须简短。"), first_prompt.index("回答必须详细解释。"))
            self.assertIn("Source:", first_prompt)
            self.assertIn("当前 Memory 上下文", memory_prompt)
            self.assertNotIn("回答必须简短。", memory_prompt)

    def test_runtime_skips_agents_update_when_llm_says_no_update(self) -> None:
        """防止每轮任务都无脑写入 AGENTS.md，污染长期 system prompt。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            llm = FakeLLMClient(
                [
                    LLMResponse(content="收到。"),
                    LLMResponse(content='{"should_update": false}'),
                ]
            )
            runtime = AgentRuntime(
                settings=self.make_settings(root / "memory.sqlite3"),
                memory=MemoryStore(root / "memory.sqlite3"),
                tools=ToolRegistry([]),
                llm=llm,
                agents_home=root / "home",
                current_dir=root / "repo",
                workspace_root=root / "repo",
                enable_agents_update=True,
            )

            runtime.run_turn("帮我计算 1+1")

            self.assertFalse((root / "home" / ".babyface" / "AGENTS.md").exists())

    def test_runtime_does_not_call_agents_maintenance_when_update_is_disabled(self) -> None:
        """防止默认测试或嵌入式调用路径意外触发 post-turn 维护流程。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = MemoryStore(root / "memory.sqlite3")
            llm = FakeLLMClient([LLMResponse(content="收到。")])
            runtime_ref = {}
            maintenance = RecordingAgentsMdMaintenance(store, lambda: runtime_ref["runtime"])
            runtime = AgentRuntime(
                settings=self.make_settings(root / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([]),
                llm=llm,
                agents_home=root / "home",
                current_dir=root / "repo",
                workspace_root=root / "repo",
                enable_agents_update=False,
                agents_md_maintenance=maintenance,
            )
            runtime_ref["runtime"] = runtime

            runtime.run_turn("你好")

        self.assertEqual(maintenance.contexts, [])

    def test_runtime_calls_agents_maintenance_after_history_is_updated(self) -> None:
        """防止 Runtime 在 Task History 或短期历史更新前就执行 prompt 维护。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = MemoryStore(root / "memory.sqlite3")
            llm = FakeLLMClient([LLMResponse(content="收到。")])
            runtime_ref = {}
            maintenance = RecordingAgentsMdMaintenance(store, lambda: runtime_ref["runtime"])
            runtime = AgentRuntime(
                settings=self.make_settings(root / "memory.sqlite3"),
                memory=store,
                tools=ToolRegistry([]),
                llm=llm,
                agents_home=root / "home",
                current_dir=root / "repo",
                workspace_root=root / "repo",
                enable_agents_update=True,
                agents_md_maintenance=maintenance,
            )
            runtime_ref["runtime"] = runtime

            runtime.run_turn("你好")

        self.assertEqual(len(maintenance.contexts), 1)
        self.assertEqual(maintenance.contexts[0].user_input, "你好")
        self.assertEqual(maintenance.contexts[0].final_response, "收到。")
        self.assertEqual(maintenance.history_counts_at_call, [1])
        self.assertEqual(maintenance.conversation_lengths_at_call, [2])

    def test_runtime_writes_agents_update_to_global_agents_md_without_user_confirmation(self) -> None:
        """防止长期偏好写入流程暴露额外确认细节给用户。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            llm = FakeLLMClient(
                [
                    LLMResponse(content="以后我会先给结论。"),
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
            runtime = AgentRuntime(
                settings=self.make_settings(root / "memory.sqlite3"),
                memory=MemoryStore(root / "memory.sqlite3"),
                tools=ToolRegistry([]),
                llm=llm,
                agents_home=root / "home",
                current_dir=root / "repo",
                workspace_root=root / "repo",
                enable_agents_update=True,
            )

            runtime.run_turn("以后回答请先给结论")

            agents_path = root / "home" / ".babyface" / "AGENTS.md"
            content = agents_path.read_text(encoding="utf-8")
        self.assertIn("- 用户偏好先给结论，再补充关键细节。", content)

    def test_runtime_uses_llm_resolved_managed_preferences_before_writing_conflict(self) -> None:
        """防止冲突时只机械追加新规则，导致 managed section 中留下互相矛盾的规则。"""

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
                    LLMResponse(content="以后我会详细解释。"),
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
            runtime = AgentRuntime(
                settings=self.make_settings(root / "memory.sqlite3"),
                memory=MemoryStore(root / "memory.sqlite3"),
                tools=ToolRegistry([]),
                llm=llm,
                agents_home=root / "home",
                current_dir=root / "repo",
                workspace_root=root / "repo",
                enable_agents_update=True,
            )

            runtime.run_turn("以后回答要详细解释")

            content = agents_path.read_text(encoding="utf-8")
        self.assertNotIn("用户偏好回答必须简短。", content)
        self.assertIn("- 用户偏好回答必须详细解释。", content)

    def test_runtime_retries_agents_update_extraction_for_explicit_preference_request(self) -> None:
        """防止用户明确要求更新长期回复规则时，被第一轮保守判断静默吞掉。"""

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
                    LLMResponse(content="Ciallo～ 我已经记住了，以后每次回复你都会先说“okeydoky～”。"),
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
            runtime = AgentRuntime(
                settings=self.make_settings(root / "memory.sqlite3"),
                memory=MemoryStore(root / "memory.sqlite3"),
                tools=ToolRegistry([]),
                llm=llm,
                agents_home=root / "home",
                current_dir=root / "repo",
                workspace_root=root / "repo",
                enable_agents_update=True,
            )

            runtime.run_turn("记住在跟我回复的时候一定要先说这么一句话“OkeyDoky～”")

            content = agents_path.read_text(encoding="utf-8")
            extraction_messages = llm.messages_seen[2]
        self.assertIn("当前已加载的 AGENTS.md", extraction_messages[1]["content"])
        self.assertNotIn("Ciallo", content)
        self.assertIn("okeydoky", content.lower())


if __name__ == "__main__":
    unittest.main()
