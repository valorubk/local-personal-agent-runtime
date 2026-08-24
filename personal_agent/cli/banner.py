from __future__ import annotations

from rich.align import Align
from rich.panel import Panel
from rich.text import Text


BABYFACE_ASCII = """
██████╗  █████╗ ██████╗ ██╗   ██╗███████╗ █████╗  ██████╗███████╗
██╔══██╗██╔══██╗██╔══██╗╚██╗ ██╔╝██╔════╝██╔══██╗██╔════╝██╔════╝
██████╔╝███████║██████╔╝ ╚████╔╝ █████╗  ███████║██║     █████╗
██╔══██╗██╔══██║██╔══██╗  ╚██╔╝  ██╔══╝  ██╔══██║██║     ██╔══╝
██████╔╝██║  ██║██████╔╝   ██║   ██║     ██║  ██║╚██████╗███████╗
╚═════╝ ╚═╝  ╚═╝╚═════╝    ╚═╝   ╚═╝     ╚═╝  ╚═╝ ╚═════╝╚══════╝
""".strip("\n")

RAINBOW_STYLES = [
    "bold red",
    "bold orange1",
    "bold yellow1",
    "bold green1",
    "bold cyan",
    "bold blue",
    "bold magenta",
]


def build_startup_banner() -> Panel:
    """构建 Babyface 启动 Banner。

    Rich 的 `Text` 可以给同一段文本里的不同字符设置不同颜色。
    这里按字符循环应用彩虹色，让整块 `BABYFACE` ASCII 字体呈现彩虹效果。

    注意：Banner 只负责品牌展示，不放退出命令说明。
    退出命令属于帮助信息，放在 `babyface --help` 里更容易被用户主动查看。
    """

    text = Text()

    # 大号 ASCII 字体是启动时的主视觉。
    # 这里逐字符上色，让整块 Banner 呈现彩虹效果。
    color_index = 0
    for character in BABYFACE_ASCII:
        if character == "\n":
            text.append(character)
            continue
        if character == " ":
            text.append(character)
            continue
        text.append(character, style=RAINBOW_STYLES[color_index % len(RAINBOW_STYLES)])
        color_index += 1
    text.append("\n\n")

    # 底部 tagline 使用和原先小标题一致的彩虹色，让视觉有一个轻巧收尾。
    _append_rainbow_text(text, "- Your Local Personal Agent -")

    return Panel(
        Align.center(text, vertical="middle"),
        border_style="bright_magenta",
        padding=(1, 2),
    )


def _append_rainbow_text(text: Text, value: str) -> None:
    """把一段文本按彩虹色追加到 Rich Text 中。"""

    color_index = 0
    for character in value:
        text.append(character, style=RAINBOW_STYLES[color_index % len(RAINBOW_STYLES)])
        color_index += 1
