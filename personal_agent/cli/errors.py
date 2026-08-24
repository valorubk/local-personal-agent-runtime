from __future__ import annotations


def format_runtime_error(error: Exception) -> str:
    """把内部异常转换成面向用户的中文提示。

    CLI 里不应该直接展示 Python traceback。traceback 对开发者有用，
    但对正在对话的用户来说很吓人，也会打断 Session 体验。

    这里先识别我们已经遇到的 Unicode 编码问题；其他未知异常统一归为
    “系统异常”。后续如果发现更多可诊断错误，可以继续在这里添加分支。
    """

    if isinstance(error, UnicodeError):
        return "输入内容包含当前系统无法直接处理的特殊字符，已跳过这一轮。请删除异常符号后重试。"
    return "系统异常：本轮对话没有完成，但 Session 仍然可继续。请稍后重试或换一种说法。"
