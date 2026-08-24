from __future__ import annotations

from collections.abc import Callable
from typing import Any


def create_prompt_reader(prompt_session: Any | None = None) -> Callable[[str], str]:
    """创建 CLI 的用户输入读取函数。

    这里优先使用 `prompt_toolkit.PromptSession`，原因是它把 prompt 和用户输入
    分成两个区域处理：
    - `> ` 是不可编辑的提示符
    - 用户只能编辑提示符后面的输入内容

    这样用户在输入行开头继续按退格键时，不会把 `> ` 删除掉。
    同时 prompt_toolkit 天然支持左右移动、Delete、中间插入和历史浏览。

    参数 `prompt_session` 主要给测试使用。测试传入假的 session，就可以验证
    我们确实把 `> ` 当成 prompt 交给输入库，而不是拼进用户文本。
    """

    session = prompt_session or _create_real_prompt_session()
    if session is None:
        return input

    def read_input(prompt_text: str) -> str:
        return str(session.prompt(prompt_text))

    return read_input


def _create_real_prompt_session() -> Any | None:
    """创建真实 PromptSession。

    `prompt_toolkit` 是更专业的终端输入库。它不是 Python 标准库，
    所以这里延迟导入，并在缺失时返回 None，让调用方回退到普通 input。
    """

    try:
        from prompt_toolkit import PromptSession
    except ImportError:
        return None

    return PromptSession()
