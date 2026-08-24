from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolResult:
    """所有 Tool 的统一返回结构。

    Agent 调 Tool 时最怕“每个工具返回格式都不一样”。统一成 `ToolResult` 后：
    - CLI 可以统一展示成功/失败
    - Agent Runtime 可以统一把结果喂回 LLM
    - Memory 可以统一保存工具调用摘要
    """

    # `ok` 表示工具是否成功完成。注意：命令 exit code 非 0 也是 ok=False。
    ok: bool

    # 成功结果放在 content 中。为了简单，V1 先用字符串。
    content: str = ""

    # 失败原因放在 error 中，并保持中文，便于直接展示给用户。
    error: str | None = None

    # metadata 存结构化补充信息，例如 exit_code、stderr、path 等。
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_message_content(self) -> str:
        """把工具结果转成可以发送给 LLM 的文本。

        OpenAI 的 tool message 需要一个 content 字段。这里把成功内容或失败原因
        转成普通文本，让模型可以基于这个结果继续推理。
        """

        if self.ok:
            return self.content
        return self.error or "Tool 执行失败。"


class Tool(Protocol):
    """Tool 协议。

    `Protocol` 是 Python 的“结构化类型”能力：一个对象只要拥有这里声明的属性和方法，
    就可以被当成 Tool 使用，不要求显式继承某个基类。
    这对插件式架构很适合：未来新增工具时，只要实现这几个成员即可。
    """

    name: str
    description: str

    def to_openai_tool(self) -> dict[str, Any]:
        """返回 OpenAI tool calling 需要的 JSON schema。"""
        ...

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        """执行工具。

        `arguments` 是 LLM 生成的参数字典。工具内部必须做校验，
        因为模型输出不一定总是完整或正确。
        """
        ...
