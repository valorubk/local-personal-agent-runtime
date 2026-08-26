from __future__ import annotations

import json
import gzip
import html
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from personal_agent.tools.base import ToolResult


class HttpRequestTool:
    """发送 HTTP 请求并解析响应的本地工具。

    这个工具用于 Agent 访问用户指定的 HTTP/HTTPS 资源。它支持普通
    JSON/文本响应，也支持对 SSE 响应做有限事件采样，避免长连接让一轮
    Agent 对话无限等待。
    """

    name = "http_request"
    description = "发送 HTTP/HTTPS 请求，解析 JSON、文本或有限 SSE 响应。"

    def __init__(
        self,
        *,
        opener: Callable[[urllib.request.Request, float], Any] = urllib.request.urlopen,
        max_body_chars: int = 8000,
        default_timeout_seconds: float = 10.0,
        default_max_sse_events: int = 5,
        default_max_sse_seconds: float = 10.0,
    ) -> None:
        self.opener = opener
        self.max_body_chars = max_body_chars
        self.default_timeout_seconds = default_timeout_seconds
        self.default_max_sse_events = default_max_sse_events
        self.default_max_sse_seconds = default_max_sse_seconds

    def to_openai_tool(self) -> dict[str, Any]:
        """声明 HTTP 请求工具的输入 schema。"""

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "HTTP 或 HTTPS URL"},
                        "method": {"type": "string", "description": "HTTP 方法，默认 GET"},
                        "headers": {"type": "object", "description": "请求头键值对"},
                        "body": {"type": "string", "description": "请求体文本"},
                        "timeout_seconds": {"type": "number", "description": "请求超时时间"},
                        "max_sse_events": {"type": "integer", "description": "SSE 最大读取事件数"},
                        "max_sse_seconds": {"type": "number", "description": "SSE 最大读取秒数"},
                    },
                    "required": ["url"],
                },
            },
        }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        """发送 HTTP 请求，并根据响应类型返回解析后的结果。"""

        url = str(arguments.get("url") or "").strip()
        if not url:
            return ToolResult(ok=False, error="缺少 URL。")

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return ToolResult(ok=False, error="仅支持 HTTP 和 HTTPS URL。", metadata={"url": url})

        method = str(arguments.get("method") or "GET").strip().upper()
        headers = self._coerce_headers(arguments.get("headers"))
        body = self._coerce_body(arguments.get("body"))
        timeout_seconds = self._coerce_positive_float(
            arguments.get("timeout_seconds"),
            default=self.default_timeout_seconds,
        )
        request = urllib.request.Request(url=url, data=body, headers=headers, method=method)

        try:
            with self.opener(request, timeout=timeout_seconds) as response:
                content_type = self._header_value(response, "Content-Type")
                if "text/event-stream" in content_type.casefold():
                    return self._read_sse_response(response, arguments)
                return self._read_normal_response(response, content_type)
        except urllib.error.HTTPError as exc:
            return ToolResult(
                ok=False,
                error=f"HTTP 请求失败：状态码 {exc.code}",
                metadata={"url": url, "status_code": exc.code},
            )
        except Exception as exc:  # noqa: BLE001 - 网络错误需要结构化返回
            return ToolResult(ok=False, error=f"HTTP 请求失败：{exc}", metadata={"url": url})

    def _read_normal_response(self, response: Any, content_type: str) -> ToolResult:
        """读取普通 HTTP 响应，并按 JSON 或文本返回。"""

        raw_body = self._decode_response_body(response)
        text = self._decode_body(raw_body, content_type)
        status_code = int(getattr(response, "status", 200))
        headers = self._headers_summary(response)
        try:
            parsed_json = json.loads(text)
        except json.JSONDecodeError:
            if "text/html" in content_type.casefold():
                return self._read_html_response(text, response, content_type)
            truncated_text, truncated = self._truncate(text)
            return ToolResult(
                ok=True,
                content=truncated_text,
                metadata={
                    "status_code": status_code,
                    "headers": headers,
                    "content_type": content_type,
                    "response_type": "text",
                    "truncated": truncated,
                },
            )

        formatted = json.dumps(parsed_json, ensure_ascii=False, indent=2)
        truncated_json, truncated = self._truncate(formatted)
        return ToolResult(
            ok=True,
            content=truncated_json,
            metadata={
                "status_code": status_code,
                "headers": headers,
                "content_type": content_type,
                "response_type": "json",
                "truncated": truncated,
            },
        )

    def _read_html_response(self, text: str, response: Any, content_type: str) -> ToolResult:
        """解析 HTML 响应，优先提取网页标题。

        对网页类请求，用户经常询问“标题是什么”。如果只把整段 HTML
        塞给 LLM，模型可能从脚本、推荐内容或空信息里误猜。这里把
        `<title>` 或 OpenGraph 标题提成明确字段，降低误读概率。
        """

        title = self._extract_html_title(text)
        truncated_text, truncated = self._truncate(text)
        title_line = f"网页标题: {title}\n\n" if title else "网页标题: 未在 HTML 中解析到标题\n\n"
        return ToolResult(
            ok=True,
            content=(
                f"{title_line}"
                "以下是 HTTP Tool 从响应体解码得到的 HTML 文本片段；"
                "回答时只能依据这里实际出现的内容，不得补全未出现的信息。\n"
                f"{truncated_text}"
            ),
            metadata={
                "status_code": int(getattr(response, "status", 200)),
                "headers": self._headers_summary(response),
                "content_type": content_type,
                "response_type": "html",
                "title": title,
                "truncated": truncated,
                "compressed": False,
            },
        )

    def _read_sse_response(self, response: Any, arguments: dict[str, Any]) -> ToolResult:
        """有限读取 SSE 响应，并把事件整理为摘要。"""

        max_events = self._coerce_positive_int(
            arguments.get("max_sse_events"),
            default=self.default_max_sse_events,
        )
        max_seconds = self._coerce_positive_float(
            arguments.get("max_sse_seconds"),
            default=self.default_max_sse_seconds,
        )
        started_at = time.monotonic()
        events: list[dict[str, str]] = []
        current: dict[str, list[str] | str] = {"data": []}
        stop_reason = "connection_closed"

        while len(events) < max_events:
            if time.monotonic() - started_at >= max_seconds:
                stop_reason = "time_limit"
                break

            raw_line = response.readline()
            if raw_line == b"":
                self._append_sse_event(events, current)
                stop_reason = "connection_closed"
                break

            line = self._decode_body(raw_line).rstrip("\r\n")
            if line == "":
                self._append_sse_event(events, current)
                current = {"data": []}
                continue
            if line.startswith(":"):
                continue
            field, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field == "data":
                data_lines = current.setdefault("data", [])
                if isinstance(data_lines, list):
                    data_lines.append(value)
            elif field in {"event", "id", "retry"}:
                current[field] = value

        if len(events) >= max_events:
            stop_reason = "event_limit"

        content = json.dumps(events, ensure_ascii=False, indent=2)
        truncated_content, truncated = self._truncate(content)
        return ToolResult(
            ok=True,
            content=truncated_content,
            metadata={
                "status_code": int(getattr(response, "status", 200)),
                "headers": self._headers_summary(response),
                "content_type": self._header_value(response, "Content-Type"),
                "response_type": "sse",
                "event_count": len(events),
                "stop_reason": stop_reason,
                "truncated": truncated,
            },
        )

    def _append_sse_event(self, events: list[dict[str, str]], current: dict[str, list[str] | str]) -> None:
        """把正在读取的 SSE 字段合并成一个事件。"""

        data_lines = current.get("data", [])
        has_data = isinstance(data_lines, list) and bool(data_lines)
        scalar_fields = {
            key: value
            for key, value in current.items()
            if key != "data" and isinstance(value, str)
        }
        if not has_data and not scalar_fields:
            return
        event = dict(scalar_fields)
        if isinstance(data_lines, list):
            event["data"] = "\n".join(data_lines)
        events.append(event)

    def _coerce_headers(self, raw_headers: object) -> dict[str, str]:
        """把模型传入的 headers 归一化为字符串字典。"""

        if not isinstance(raw_headers, dict):
            return {}
        return {str(key): str(value) for key, value in raw_headers.items()}

    def _coerce_body(self, raw_body: object) -> bytes | None:
        """把请求体转换为 bytes；缺省时表示没有请求体。"""

        if raw_body is None:
            return None
        if isinstance(raw_body, bytes):
            return raw_body
        return str(raw_body).encode("utf-8")

    def _coerce_positive_float(self, value: object, *, default: float) -> float:
        """读取正数配置，非法值回退到默认值。"""

        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return number if number > 0 else default

    def _coerce_positive_int(self, value: object, *, default: int) -> int:
        """读取正整数配置，非法值回退到默认值。"""

        try:
            number = int(value)
        except (TypeError, ValueError):
            return default
        return number if number > 0 else default

    def _decode_response_body(self, response: Any) -> bytes:
        """读取并按响应头解压响应体。"""

        body = response.read()
        encoding = self._header_value(response, "Content-Encoding").casefold()
        if encoding == "gzip":
            try:
                return gzip.decompress(body)
            except OSError:
                return body
        return body

    def _decode_body(self, body: bytes, content_type: str = "") -> str:
        """把响应 bytes 解码成文本，遇到坏字符时保留可读内容。"""

        charset = self._extract_charset(content_type) or "utf-8"
        return body.decode(charset, errors="replace")

    def _extract_charset(self, content_type: str) -> str | None:
        """从 Content-Type 中提取 charset。"""

        match = re.search(r"charset=([^;\s]+)", content_type, flags=re.IGNORECASE)
        return match.group(1).strip('"') if match else None

    def _extract_html_title(self, text: str) -> str | None:
        """从 HTML 中提取可信标题字段。"""

        patterns = [
            r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"'](?P<title>[^\"']+)[\"'][^>]*>",
            r"<meta[^>]+content=[\"'](?P<title>[^\"']+)[\"'][^>]+property=[\"']og:title[\"'][^>]*>",
            r"<title[^>]*>(?P<title>.*?)</title>",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            if match:
                title = re.sub(r"\s+", " ", html.unescape(match.group("title"))).strip()
                if title:
                    return title
        return None

    def _header_value(self, response: Any, name: str) -> str:
        """按大小写不敏感方式读取响应头。"""

        headers = getattr(response, "headers", {})
        if hasattr(headers, "get"):
            return str(headers.get(name, ""))
        return ""

    def _headers_summary(self, response: Any) -> dict[str, str]:
        """返回响应头摘要，确保可以 JSON 序列化。"""

        headers = getattr(response, "headers", {})
        if hasattr(headers, "items"):
            return {str(key): str(value) for key, value in headers.items()}
        return {}

    def _truncate(self, text: str) -> tuple[str, bool]:
        """限制返回给 LLM 的响应体长度。"""

        if len(text) <= self.max_body_chars:
            return text, False
        return text[: self.max_body_chars], True
