from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from personal_agent.config import Settings


@dataclass(frozen=True)
class ToolCall:
    """LLM 请求调用工具时的标准表示。

    OpenAI SDK 返回的 tool call 对象比较深：
    `call.function.name`、`call.function.arguments` 等。
    Runtime 不应该到处依赖 SDK 的内部对象结构，所以我们把它转换成自己的
    `ToolCall` dataclass。
    """

    # OpenAI 每个 tool call 都会有一个 id，后续 tool message 需要带回这个 id。
    id: str

    # 工具名称，例如 `file_read`、`shell_exec`。
    name: str

    # 模型生成的工具参数。OpenAI 原始返回通常是 JSON 字符串，这里解析成 dict。
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    """一次 LLM 调用的结果。

    一个模型回复可能有两种形态：
    1. 普通文本回答：content 有内容，tool_calls 为空
    2. 工具调用请求：content 可能为空，tool_calls 里有一个或多个 ToolCall
    """

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(Protocol):
    """LLM 客户端协议。

    Runtime 只依赖这个协议，而不直接依赖 OpenAI SDK。
    这样测试时可以传 FakeLLMClient，不需要真的访问网络，也不会消耗 token。
    这就是常见的“依赖倒置”：高层业务逻辑依赖抽象，不依赖具体服务。
    """

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        ...

    def stream_text(self, text: str) -> Iterable[str]:
        ...


class OpenAILLMClient:
    """基于 OpenAI SDK 的 LLM 客户端。

    这里使用的是 OpenAI SDK，但通过 `base_url` 支持 OpenAI-compatible endpoint。
    换句话说，只要服务兼容 OpenAI Chat Completions API，就可以复用这层代码。
    """

    def __init__(self, settings: Settings) -> None:
        # 延迟 import OpenAI：这样单元测试里如果不用真实客户端，也不必提前加载 SDK。
        from openai import OpenAI

        self.settings = settings
        kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}

        # 如果配置了 base_url，SDK 会把请求发到兼容服务，而不是默认 OpenAI 地址。
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        self.client = OpenAI(**kwargs)

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        """执行一次非流式 Chat Completions 调用。

        当前 V1 的设计是：
        - Tool Loop 用非流式调用，便于拿到完整 tool_calls
        - 最终回答再交给 CLI 按字符流式展示

        真正生产级 Agent 后续可以升级为端到端 streaming。
        """

        kwargs: dict[str, Any] = {
            "model": self.settings.openai_model,
            "messages": messages,
        }

        # 只有注册了工具时才传 tools。没有工具时传空列表反而可能让某些兼容服务报错。
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        tool_calls = []

        # SDK 返回的 function.arguments 是 JSON 字符串，
        # Tool Registry 更适合接收 Python dict，所以这里统一转换。
        for call in message.tool_calls or []:
            arguments = json.loads(call.function.arguments or "{}")
            tool_calls.append(
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=arguments,
                )
            )
        return LLMResponse(content=message.content or "", tool_calls=tool_calls)

    def stream_text(self, text: str) -> Iterable[str]:
        # V1 的 Tool Loop 先完成推理，再把最终回答流式交给 CLI 展示。
        # 这里的“流式”是 CLI 展示层面的最小实现：把完整文本拆成小片段输出。
        # 这让 CLI 和 Runtime 的接口先具备 stream 形状，未来替换成 SDK 原生 streaming 更容易。
        yield from text
