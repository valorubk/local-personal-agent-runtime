from __future__ import annotations

from typing import Any


def enable_terminal_input_editing(readline_module: Any | None = None) -> bool:
    """启用终端输入行编辑能力。

    你看到 `^[[A`、`^[[B`、`^[[D`、`^[[C` 的根因通常是：
    终端把方向键发送成 ANSI escape sequence，但当前输入函数没有把这些序列
    解释成“上一个历史命令 / 下一个历史命令 / 光标左移 / 光标右移”。

    Python 标准库的 `readline` 会接管 `input()` 的行编辑能力。
    启用后，终端通常会自然支持：
    - 上下键浏览输入历史
    - 左右键在当前输入行内移动光标
    - Delete 删除光标后的字符
    - 在光标所在位置插入新字符

    返回值表示是否成功启用。失败时不抛异常，因为这不应该阻止 Agent 启动；
    最坏情况只是退回普通输入体验。
    """

    try:
        readline = readline_module or _import_readline()
    except ImportError:
        return False

    bindings = [
        # 使用 emacs 风格行编辑，这是 readline 的常见默认模式。
        "set editing-mode emacs",

        # Delete 键在大多数现代终端里会发送 ESC [ 3 ~。
        # GNU readline 使用下面这种写法。
        '"\\e[3~": delete-char',

        # macOS 自带 Python 常常链接的是 libedit，它使用另一套绑定语法。
        # 两条都尝试配置，哪条当前后端能理解就会生效。
        "bind ^[[3~ ed-delete-next-char",
    ]
    for binding in bindings:
        try:
            readline.parse_and_bind(binding)
        except Exception:
            # 某些 readline/libedit 后端不认识其中一种语法。
            # 忽略单条绑定失败，继续尝试其他兼容写法。
            continue
    return True


def _import_readline() -> Any:
    """延迟导入 readline，避免在不支持的平台上导入 CLI 模块就失败。"""

    import readline

    return readline
