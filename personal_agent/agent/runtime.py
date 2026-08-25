from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from personal_agent.agent.llm import LLMClient, LLMResponse, OpenAILLMClient
from personal_agent.agent.maintenance import AgentsMdMaintenanceService, PostTurnMaintenanceContext
from personal_agent.config import Settings
from personal_agent.debug_trace import DebugRecorder, NullDebugTraceRecorder
from personal_agent.memory.store import MemoryStore
from personal_agent.prompt_profile import build_agents_prompt
from personal_agent.text import sanitize_text_for_runtime
from personal_agent.tools.base import ToolResult
from personal_agent.tools.registry import ToolRegistry


SYSTEM_PROMPT = """你是 Babyface，一个本地优先的个人 Agent Runtime。
你通过中文与用户交流。需要本地信息时可以调用工具；工具失败时要解释原因并继续帮助用户。
当用户明确要求你记住长期个人信息时，在回答中说明你会保存该信息。
如果不同 AGENTS.md 之间存在冲突，后出现的、更靠近当前工作目录的指令优先。
不得删除、改写或总结任何 AGENTS.md 内容。"""


@dataclass(frozen=True)
class ExecutedTool:
    """一次已经执行过的 Tool 调用。

    Runtime 需要保存三类信息：
    - LLM 请求了哪个工具
    - 传了什么参数
    - 工具实际返回什么

    这些信息既要展示给 CLI，也要保存到 Task History。
    """

    id: str
    name: str
    arguments: dict[str, Any]
    result: ToolResult

    def as_history_item(self) -> dict[str, Any]:
        """转换成可以 JSON 序列化并保存到 SQLite 的结构。"""

        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
            "ok": self.result.ok,
            "content": self.result.content,
            "error": self.result.error,
            "metadata": self.result.metadata,
        }


@dataclass(frozen=True)
class RuntimeResult:
    """一轮用户输入的最终结果。

    CLI 不需要知道 LangGraph 内部状态，只关心：
    - final_response：最终完整回答
    - stream：用于流式展示的片段
    - tool_results：这一轮发生过的工具调用
    """

    final_response: str
    stream: list[str]
    tool_results: list[ExecutedTool] = field(default_factory=list)


class RuntimeState(TypedDict, total=False):
    """LangGraph 中流动的状态对象。

    LangGraph 的核心思想是：每个节点接收 state，返回更新后的 state。
    这里用 `TypedDict` 给 state 标注可能有哪些字段，便于读代码和类型检查。

    `total=False` 表示这些 key 不是一开始都必须存在。
    例如 `response` 只有执行过 LLM 节点之后才会出现。
    """

    user_input: str
    messages: list[dict[str, Any]]
    response: LLMResponse
    tool_results: list[ExecutedTool]
    iterations: int
    final_response: str
    trace_id: str


class AgentsMdMaintenanceRunner(Protocol):
    """Runtime 依赖的 post-turn 维护端口。

    Runtime 只知道维护服务可以接收一轮上下文并同步执行，不关心它内部如何
    判断候选规则、整理冲突或写入 `AGENTS.md`。测试可用轻量 fake 实现该端口。
    """

    def run(self, context: PostTurnMaintenanceContext) -> object | None:
        """执行一轮 post-turn 维护，返回值由具体服务自行定义。"""


class AgentRuntime:
    """Agent Runtime 的门面对象。

    CLI 只需要调用 `run_turn(user_input)`。
    Runtime 内部负责：
    1. 读取 Memory
    2. 调用 LLM
    3. 判断是否需要 Tool
    4. 执行 Tool
    5. 把 Tool 结果交回 LLM
    6. 保存任务历史
    """

    def __init__(
        self,
        settings: Settings,
        memory: MemoryStore,
        tools: ToolRegistry,
        llm: LLMClient | None = None,
        max_tool_iterations: int = 4,
        agents_home: Path | None = None,
        current_dir: Path | None = None,
        workspace_root: Path | None = None,
        enable_agents_update: bool = False,
        agents_md_maintenance: AgentsMdMaintenanceRunner | None = None,
        debug_recorder: DebugRecorder | None = None,
    ) -> None:
        # settings 是启动时确定的配置，贯穿整个 Runtime 生命周期。
        self.settings = settings

        # memory 和 tools 从外部注入，方便测试替换，也方便未来扩展。
        self.memory = memory
        self.tools = tools

        # 如果没有传 llm，就创建真实 OpenAI-compatible 客户端。
        # 测试里会传 FakeLLMClient，避免访问真实网络。
        self.llm = llm or OpenAILLMClient(settings)

        # 防止模型无限循环调用工具。真实 Agent 系统里通常都要有这种保护。
        self.max_tool_iterations = max_tool_iterations

        self.agents_home = agents_home
        self.current_dir = current_dir
        self.workspace_root = workspace_root
        self.enable_agents_update = enable_agents_update
        self.agents_md_maintenance = agents_md_maintenance
        if self.agents_md_maintenance is None and self.enable_agents_update:
            self.agents_md_maintenance = AgentsMdMaintenanceService(llm=self.llm)
        self.debug_recorder: DebugRecorder = debug_recorder or NullDebugTraceRecorder()

        # 短期记忆：只存在于当前 AgentRuntime 实例，也就是当前 CLI Session。
        #
        # 它和 SQLite Profile Memory 的区别：
        # - conversation_history：保存“刚刚聊过什么”，重启 CLI 后会消失
        # - profile_memory：保存“长期用户事实”，重启 CLI 后还能从 SQLite 读回来
        #
        # V1 先保留整个 Session 历史，满足“连续几轮对话传递所有历史内容”的需求。
        # 未来上下文变长后，可以在这里加入摘要、裁剪或基于 token 的窗口管理。
        self.conversation_history: list[dict[str, str]] = []

        # LangGraph 编译后的 workflow 可以被重复 invoke。
        self.workflow = self._build_workflow()

    def run_turn(self, user_input: str) -> RuntimeResult:
        """执行一轮对话。

        这里是一轮用户输入的最高层流程。注意它没有直接写复杂逻辑，
        复杂逻辑被放进 LangGraph 节点里，这样流程结构更清楚。
        """

        # 先清洗输入，确保后续写 SQLite、拼 messages、调用 LLM 时都是合法文本。
        # 这一步会把无法 UTF-8 编码的 surrogate 字符替换为 `�`。
        safe_user_input = sanitize_text_for_runtime(user_input)
        trace_id = str(uuid4())
        self.debug_recorder.record(
            event_type="user",
            stage="user_input_received",
            name="user_input",
            input_data=safe_user_input,
            output_data="",
            metadata={},
            trace_id=trace_id,
        )

        # V1 用非常简单的规则支持显式长期记忆：用户输入“记住：...”就保存。
        # 更完整的 Memory 抽取可以后续交给模型判断。
        self._save_explicit_profile_memory(safe_user_input)

        # LangGraph 的初始 state。后续每个节点都会往这个 dict 里补字段。
        initial_state: RuntimeState = {
            "user_input": safe_user_input,
            "tool_results": [],
            "iterations": 0,
            "trace_id": trace_id,
        }
        state = self.workflow.invoke(initial_state)
        final_response = sanitize_text_for_runtime(str(state.get("final_response", "")))
        tool_results = list(state.get("tool_results", []))

        # V1 的 stream 是展示层 stream：把最终回答拆成片段给 CLI。
        stream = list(self.llm.stream_text(final_response))

        # 一轮结束后保存 Task History。这样后续用户可以问“我最近做过什么”。
        self.memory.save_task_history(
            user_input=safe_user_input,
            final_response=final_response,
            tool_calls=[tool.as_history_item() for tool in tool_results],
            session_id=self.debug_recorder.session_id or None,
            trace_id=trace_id,
        )

        # 一轮完成后，把“用户问题 + Agent 最终回答”加入短期记忆。
        # 下一次 run_turn() 的 `_prepare()` 会把这些历史消息放到当前 user input 前面。
        self.conversation_history.extend(
            [
                {"role": "user", "content": safe_user_input},
                {"role": "assistant", "content": final_response},
            ]
        )
        self._run_post_turn_maintenance(safe_user_input, final_response, trace_id)
        return RuntimeResult(final_response=final_response, stream=stream, tool_results=tool_results)

    def _run_post_turn_maintenance(self, user_input: str, final_response: str, trace_id: str) -> None:
        """在一轮任务完成后调用可选的 `AGENTS.md` 维护服务。

        Runtime 只负责确定调用时机：主 Agent Loop、Task History 保存和短期历史
        更新都完成之后，才把本轮上下文交给维护服务。候选判断、冲突整理和文件
        写入都属于维护服务自己的职责。
        """

        if not self.enable_agents_update or self.agents_md_maintenance is None:
            return

        context = PostTurnMaintenanceContext(
            user_input=user_input,
            final_response=final_response,
            agents_home=self.agents_home,
            current_dir=self.current_dir,
            workspace_root=self.workspace_root,
        )
        self.debug_recorder.around_skill_call(
            trace_id=trace_id,
            name="agents_md_maintenance",
            input_data={
                "user_input": user_input,
                "final_response": final_response,
                "agents_home": self.agents_home,
                "current_dir": self.current_dir,
                "workspace_root": self.workspace_root,
            },
            metadata={"skill": "agents_md_maintenance"},
            call=lambda: self.agents_md_maintenance.run(context),  # type: ignore[union-attr]
            output_builder=lambda result: {"result": result},
        )

    def _build_workflow(self):
        """创建 LangGraph 工作流。

        LangGraph 里最重要的三个概念：
        - State：节点之间传递的数据，这里是 `RuntimeState`
        - Node：处理 state 的函数，例如 `_prepare`、`_call_llm`
        - Edge：节点之间的连接，例如 prepare -> llm

        当前图形结构：

        prepare -> llm -> (tools -> llm)* -> finalize -> END

        `llm` 后面的括号表示：如果模型请求工具，就执行 tools 后再回到 llm；
        如果没有工具请求，就进入 finalize。
        """

        graph = StateGraph(RuntimeState)

        # add_node 把普通 Python 方法注册成 LangGraph 节点。
        graph.add_node("prepare", self._prepare)
        graph.add_node("llm", self._call_llm)
        graph.add_node("tools", self._run_tools)
        graph.add_node("finalize", self._finalize)

        # set_entry_point 指定工作流从哪个节点开始。
        graph.set_entry_point("prepare")
        graph.add_edge("prepare", "llm")

        # conditional_edges 是 Agent Loop 的关键：
        # LLM 返回后，根据 `_route_after_llm` 的结果决定下一步去 tools 还是 finalize。
        graph.add_conditional_edges(
            "llm",
            self._route_after_llm,
            {
                "tools": "tools",
                "finalize": "finalize",
            },
        )
        graph.add_edge("tools", "llm")
        graph.add_edge("finalize", END)
        return graph.compile()

    def _prepare(self, state: RuntimeState) -> RuntimeState:
        """准备发给 LLM 的 messages。

        LLM API 通常接收一个 messages 列表：
        - system：告诉模型它是谁、有哪些规则
        - user：用户真实输入
        - assistant/tool：后续多轮中补充模型回复和工具结果
        """

        profile = self.memory.list_profile()
        knowledge = self.memory.retrieve_knowledge(state["user_input"])
        memory_context = {
            "profile": profile,
            "knowledge": knowledge,
        }
        system_prompt = self._build_system_prompt()
        messages = [
            # 第一个 system prompt 设定 Agent 的身份和行为边界。
            {"role": "system", "content": system_prompt},

            # 第二个 system message 注入 Memory。V1 简单注入全部 profile；
            # 后续 RAG 可以把 retrieve_knowledge 的结果换成向量检索结果。
            {"role": "system", "content": f"当前 Memory 上下文：{memory_context}"},
        ]

        # 把当前 Session 中之前轮次的 user/assistant 消息传给 LLM。
        # 这就是“短期记忆”的核心：模型不是只看当前这一句话，而是能看到连续对话。
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": state["user_input"]})

        return {
            **state,
            "messages": messages,
        }

    def _build_system_prompt(self) -> str:
        agents_prompt = build_agents_prompt(
            home=self.agents_home,
            current_dir=self.current_dir,
            workspace_root=self.workspace_root,
        )
        if not agents_prompt:
            return SYSTEM_PROMPT
        return f"{SYSTEM_PROMPT}\n\n{agents_prompt}"

    def _call_llm(self, state: RuntimeState) -> RuntimeState:
        """调用 LLM，并把 assistant message 写回 state。

        如果模型决定调用工具，response.tool_calls 会有内容；
        如果模型直接回答，response.content 就是最终候选回答。
        """

        openai_tools = self.tools.list_openai_tools()
        response = self.debug_recorder.around_llm_call(
            trace_id=state["trace_id"],
            name="complete",
            input_data={
                "messages": state["messages"],
                "tools": openai_tools,
            },
            metadata={"model": self.settings.openai_model},
            call=lambda: self.llm.complete(state["messages"], openai_tools),
            output_builder=lambda result: {
                "content": result.content,
                "tool_calls": [
                    {"id": call.id, "name": call.name, "arguments": call.arguments}
                    for call in result.tool_calls
                ],
            },
        )
        messages = list(state["messages"])
        assistant_message: dict[str, Any] = {"role": "assistant", "content": response.content}
        if response.tool_calls:
            # OpenAI 的对话协议要求：
            # assistant message 里带 tool_calls，后面必须追加对应的 role=tool message。
            assistant_message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in response.tool_calls
            ]
        messages.append(assistant_message)
        return {**state, "messages": messages, "response": response}

    def _route_after_llm(self, state: RuntimeState) -> str:
        """决定 LLM 之后的下一站。

        这是 LangGraph 条件边的路由函数。
        返回值必须匹配 `_build_workflow()` 中 conditional_edges 的 key：
        - "tools"：去执行工具
        - "finalize"：进入最终回答
        """

        response = state["response"]
        iterations = int(state.get("iterations", 0))
        if response.tool_calls and iterations < self.max_tool_iterations:
            return "tools"
        return "finalize"

    def _run_tools(self, state: RuntimeState) -> RuntimeState:
        """执行 LLM 请求的所有工具，并把结果作为 tool message 追加回 messages。

        Tool Calling 的闭环是：
        1. LLM 生成 tool_calls
        2. 程序执行本地工具
        3. 程序把工具结果以 role=tool 的 message 发回 LLM
        4. LLM 根据工具结果继续回答
        """

        response = state["response"]
        messages = list(state["messages"])
        tool_results = list(state.get("tool_results", []))
        for call in response.tool_calls:
            result = self.debug_recorder.around_tool_call(
                trace_id=state["trace_id"],
                name=call.name,
                input_data=call.arguments,
                metadata={"tool_call_id": call.id},
                call=lambda call=call: self.tools.run(call.name, call.arguments),
                output_builder=lambda tool_result: {
                    "ok": tool_result.ok,
                    "content": tool_result.content,
                    "error": tool_result.error,
                    "metadata": tool_result.metadata,
                },
            )
            executed = ExecutedTool(
                id=call.id,
                name=call.name,
                arguments=call.arguments,
                result=result,
            )
            tool_results.append(executed)
            messages.append(
                {
                    # role=tool 是 OpenAI tool calling 协议的一部分。
                    "role": "tool",

                    # tool_call_id 必须对应前一个 assistant message 里的 tool call id。
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": result.as_message_content(),
                }
            )
        return {
            **state,
            "messages": messages,
            "tool_results": tool_results,
            "iterations": int(state.get("iterations", 0)) + 1,
        }

    def _finalize(self, state: RuntimeState) -> RuntimeState:
        """生成最终输出字段。

        正常情况下，最后一次 LLM 调用不再请求工具，content 就是最终回答。
        如果达到工具调用上限还在请求工具，就返回一个保护性提示。
        """

        response = state["response"]
        content = response.content
        if response.tool_calls:
            content = "Tool 调用达到上限，已停止继续执行。"
        return {**state, "final_response": content}

    def _save_explicit_profile_memory(self, user_input: str) -> None:
        """保存用户明确要求记住的长期信息。

        这是一个非常朴素的 Memory 写入策略，适合 V1：
        用户输入“记住：xxx”时直接保存。

        更高级的 Personal Agent 可以让 LLM 判断哪些事实值得长期保存，
        但那会引入更多误记、隐私和可解释性问题，先不放进 V1。
        """

        value = self._extract_profile_memory_value(user_input)
        if value:
            self.memory.save_profile(f"user_note_{len(self.memory.list_profile()) + 1}", value)

    def _extract_profile_memory_value(self, user_input: str) -> str | None:
        """从用户输入中抽取“希望长期记住”的事实。

        这里仍然是 V1 的轻量规则，不做复杂 NLP。
        目标是覆盖中文里最常见的几种表达：
        - “记住：我不爱吃梅菜扣肉”
        - “记住，我不爱吃梅菜扣肉”
        - “请记住我不爱吃梅菜扣肉”
        - “我不爱吃梅菜扣肉，记住它”

        为什么不直接把整句话都保存？
        因为“记住它”“请记住”是指令，不是用户事实。
        Profile Memory 里最好保存干净事实，例如“我不爱吃梅菜扣肉”。
        """

        stripped = user_input.strip()

        # 先处理“记住...”开头的句子：去掉开头的指令词和中文/英文标点。
        leading_match = re.match(r"^(?:请)?记住[：:，,、\s]*(?P<value>.+)$", stripped)
        if leading_match:
            return _clean_memory_value(leading_match.group("value"))

        # 再处理“...，记住它”结尾的句子：去掉末尾的提醒指令。
        trailing_match = re.match(
            r"^(?P<value>.+?)[，,。\s]*(?:请)?记住(?:它|这个|这件事|一下)?[。！!？?]*$",
            stripped,
        )
        if trailing_match:
            return _clean_memory_value(trailing_match.group("value"))

        return None


def _clean_memory_value(value: str) -> str | None:
    """清洗规则抽取出的长期记忆内容。

    返回 `None` 表示没有有效内容；调用方据此决定不写入 SQLite。
    """

    cleaned = value.strip(" ：:，,。！!？?\t\n")
    return cleaned or None
