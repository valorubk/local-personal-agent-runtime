from __future__ import annotations

from collections.abc import Callable

from personal_agent.agent.runtime import AgentRuntime, RuntimeResult
from personal_agent.cli.errors import format_runtime_error
from personal_agent.debug_trace import DebugRecorder, NullDebugTraceRecorder


EXIT_COMMANDS = {"exit", "quit", "/exit"}


class CLISession:
    """一个可测试的简化 CLI Session。

    `personal_agent.main` 里是真实 Rich/Typer CLI。
    这个类更像“核心交互循环”的抽象版本：read_input 和 write 都可以注入，
    所以测试里不用真的打开终端，也能验证多轮输入和退出逻辑。
    """

    def __init__(
        self,
        runtime: AgentRuntime,
        *,
        read_input: Callable[[str], str] = input,
        write: Callable[[str], None] = print,
        debug_recorder: DebugRecorder | None = None,
    ) -> None:
        self.runtime = runtime
        self.debug_recorder = debug_recorder or NullDebugTraceRecorder()

        # 依赖注入：默认用 input/print，测试时可以传 lambda/list.append。
        self.read_input = read_input
        self.write = write

    def run(self) -> None:
        """进入持续对话循环。"""

        self.write("BABYFACE")
        while True:
            user_input = self.read_input("> ").strip()
            if not user_input:
                continue
            if user_input in EXIT_COMMANDS:
                self.write("再见。")
                return

            try:
                result = self.runtime.run_turn(user_input)
            except Exception as exc:
                # 交互式 CLI 最重要的体验之一是“不要因为一轮失败就退出”。
                # 这里兜住 Runtime 内部异常，输出友好的中文提示，然后继续下一轮输入。
                self.write(format_runtime_error(exc))
                continue
            self._render_result(result)

    def _render_result(self, result: RuntimeResult) -> None:
        """渲染一轮 Agent 结果。

        真实 CLI 使用 Rich Markdown；这个简化版本只输出纯文本，
        目的是让 Session 行为容易单元测试。
        """

        for executed in result.tool_results:
            status = "成功" if executed.result.ok else "失败"
            self.write(f"[Tool] {executed.name} {status}")
        self.write("")
        self.write("Babyface:")
        self.write(result.final_response)
        self.write("")
