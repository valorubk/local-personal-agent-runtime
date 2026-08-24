from __future__ import annotations

from typing import Optional

try:
    # Typer 负责 CLI 参数解析；Rich 负责更舒服的终端显示。
    # 这两个依赖在测试环境里不一定需要，所以这里用 try/except 延迟处理。
    import typer
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.prompt import Confirm
except ImportError:  # pragma: no cover - 安装依赖后由 CLI 路径覆盖
    typer = None
    Console = None
    Markdown = None
    Confirm = None

from personal_agent.agent.runtime import AgentRuntime
from personal_agent.cli.banner import build_startup_banner
from personal_agent.cli.errors import format_runtime_error
from personal_agent.cli.input_editing import enable_terminal_input_editing
from personal_agent.cli.prompt_input import create_prompt_reader
from personal_agent.config import ConfigError, load_settings
from personal_agent.memory.store import MemoryStore
from personal_agent.tools.file_tool import FileTool
from personal_agent.tools.registry import ToolRegistry
from personal_agent.tools.shell_tool import ShellTool
from personal_agent.tools.web_tool import WebTool


if typer is not None:
    # Typer 的 app 对象就是 CLI 应用。pyproject.toml 里把 `babyface` 指向这里。
    app = typer.Typer(
        help=(
            "启动 Babyface 本地个人 Agent。\n\n"
            "Session 内退出命令：\n"
            "- exit：退出当前对话 Session。\n"
            "- quit：退出当前对话 Session。\n"
            "- /exit：退出当前对话 Session。"
        )
    )
else:
    app = None


def _run(config: Optional[str] = None) -> None:
    """启动真实交互式 CLI。

    这个函数是“组装层”：
    - 读取配置
    - 创建 MemoryStore
    - 创建 ToolRegistry
    - 创建 AgentRuntime
    - 进入 while True 对话循环
    """

    if Console is None or Markdown is None or Confirm is None:
        raise RuntimeError("缺少 CLI 依赖，请先安装项目依赖。")

    # 启用终端行编辑能力。这样方向键不会以 `^[[A` 形式进入输入框，
    # 左右键可以移动光标，Delete 可以删除光标后的字符。
    enable_terminal_input_editing()

    console = Console()
    try:
        # `--config babyface.local.toml` 会从这里传入。
        settings = load_settings(config_path=config)
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    def confirm_shell(command: str) -> bool:
        """Shell Tool 的二次确认回调。

        Tool 本身不直接依赖 Rich，这样它可以被单元测试复用。
        CLI 层负责把“询问用户”这件事注入给 ShellTool。
        """

        console.print(f"[yellow]Shell Tool 请求执行：[/yellow]{command}")
        return bool(Confirm.ask("是否允许执行该命令？", default=False))

    # MemoryStore 启动时会自动创建 SQLite 文件和表。
    memory = MemoryStore(settings.memory_db_path)

    # 注册 V1 支持的三个工具。未来新增工具只需要加到这个列表里。
    tools = ToolRegistry(
        [
            FileTool(),
            ShellTool(timeout_seconds=settings.shell_timeout_seconds, confirm=confirm_shell),
            WebTool(),
        ]
    )

    # Runtime 是 Agent 的核心；CLI 只负责输入输出，不关心 LangGraph 细节。
    runtime = AgentRuntime(settings=settings, memory=memory, tools=tools)

    console.print(build_startup_banner())
    read_user_input = create_prompt_reader()
    while True:
        # Prompt reader 会把 `> ` 作为不可编辑提示符传给输入库，
        # 用户无法通过退格键删掉提示符，只能编辑提示符后面的内容。
        user_input = read_user_input("> ").strip()
        if not user_input:
            continue
        if user_input in {"exit", "quit", "/exit"}:
            console.print("再见。")
            return

        try:
            result = runtime.run_turn(user_input)
        except Exception as exc:
            # 不把 Python traceback 直接展示给用户。
            # 如果能识别错误类型，`format_runtime_error` 会给出更具体说明；
            # 否则统一显示“系统异常”，并让 Session 继续可用。
            console.print(f"[red]{format_runtime_error(exc)}[/red]")
            continue
        for executed in result.tool_results:
            # Tool 调用过程必须可见，这是 Claude Code 风格 CLI 的关键体验之一。
            status = "成功" if executed.result.ok else "失败"
            console.print(f"[cyan]Tool[/cyan] {executed.name} {status}")
            if executed.result.error:
                console.print(f"[red]{executed.result.error}[/red]")
        console.print()
        console.print("[bold]Babyface:[/bold]")

        # Runtime 返回 stream 片段。这里先拼成 Markdown 渲染；
        # 如果后续要做真正逐 token 展示，可以在这里改成 Live/Console.print 分片输出。
        console.print(Markdown("".join(result.stream)))
        console.print()


if typer is not None:

    @app.callback(invoke_without_command=True)
    def main(
        config: Optional[str] = typer.Option(
            None,
            "--config",
            "-c",
            help="本地配置文件路径。",
        )
    ) -> None:
        _run(config)


def cli() -> None:
    _run()
