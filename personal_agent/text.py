from __future__ import annotations


def sanitize_text_for_runtime(value: str) -> str:
    """把进入 Agent Runtime 的文本清洗成稳定可编码的字符串。

    终端、剪贴板或某些外部来源偶尔会产生 Unicode surrogate 字符。
    这类字符在 Python 字符串里可以存在，但不能直接编码成标准 UTF-8。
    OpenAI SDK 在发送请求前会把 messages 转成 JSON 再编码成 UTF-8，
    如果里面混入 surrogate，就会抛出 `UnicodeEncodeError`。

    V1 的策略很朴素：保留所有正常字符，把 surrogate 替换成 `�`。
    这样用户的大部分输入仍然能传给模型，异常字符也不会击穿整个 CLI。
    """

    return "".join("\ufffd" if _is_surrogate(character) else character for character in value)


def _is_surrogate(character: str) -> bool:
    """判断单个字符是否属于 Unicode surrogate 区间。"""

    code_point = ord(character)
    return 0xD800 <= code_point <= 0xDFFF
