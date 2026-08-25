from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Protocol, TypeVar


T = TypeVar("T")


def format_debug_time(now: datetime | None = None) -> str:
    """把系统时间格式化为调试记录要求的可读字符串。

    输入是一个 `datetime`，测试可以传固定时间；生产路径不传时使用本地当前时间。
    输出固定为 `YYYY-MM-DD HH:MM:SS`，便于直接查看 SQLite 内容。
    """

    current = now or datetime.now()
    return current.strftime("%Y-%m-%d %H:%M:%S")


def build_debug_trace_path(root: str | Path, now: datetime | None = None) -> Path:
    """根据日期生成当天调试 SQLite 文件路径。

    Babyface 的调试文件默认放在项目本地 `.babyface/debug/` 下。
    文件名严格使用 `debug_trace_YYYYMMDD`，不额外追加 `.sqlite3` 后缀。
    """

    current = now or datetime.now()
    return Path(root) / ".babyface" / "debug" / f"debug_trace_{current:%Y%m%d}"


@dataclass(frozen=True)
class DebugTraceEvent:
    """一条调试链路事件。

    该对象是 Runtime、LLM、Tool、Skill 与 SQLite 存储之间的统一数据边界。
    所有结构化 ID 字段都使用蛇形命名：`session_id` 和 `trace_id`。
    """

    event_type: str
    stage: str
    name: str
    input: str
    output: str
    metadata: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    trace_id: str = ""
    created_at: str = ""


class DebugTraceStore:
    """按日期分文件保存调试链路事件的 SQLite Store。

    它只负责 SQLite 表结构和写入，不知道 CLI、Runtime 或 LangGraph 的细节。
    """

    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root)

    def save(self, event: DebugTraceEvent, now: datetime | None = None) -> None:
        """把一条调试事件写入当天 SQLite 文件。"""

        db_path = build_debug_trace_path(self.root, now=now)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO debug_trace_events (
                    event_type,
                    stage,
                    name,
                    session_id,
                    trace_id,
                    input,
                    output,
                    metadata,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_type,
                    event.stage,
                    event.name,
                    event.session_id,
                    event.trace_id,
                    event.input,
                    event.output,
                    json.dumps(event.metadata, ensure_ascii=False),
                    event.created_at,
                ),
            )

    @contextmanager
    def _connect(self, db_path: Path) -> Iterator[sqlite3.Connection]:
        """创建调试 SQLite 连接并确保表结构存在。"""

        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS debug_trace_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    name TEXT,
                    session_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    input TEXT NOT NULL,
                    output TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            yield conn
            conn.commit()
        finally:
            conn.close()


class DebugRecorder(Protocol):
    """Runtime 使用的调试记录端口。

    这个协议让普通模式可以传入空实现，调试模式传入真实实现。
    """

    session_id: str

    def record(
        self,
        *,
        event_type: str,
        stage: str,
        name: str,
        input_data: Any,
        output_data: Any,
        metadata: dict[str, Any] | None,
        trace_id: str,
    ) -> None:
        """记录一条调试事件。"""
        ...


class NullDebugTraceRecorder:
    """普通模式使用的空调试记录器。

    它保持 Runtime 调用形状一致，但不会创建文件、写 SQLite 或输出调试链路。
    """

    session_id = ""

    def record(
        self,
        *,
        event_type: str,
        stage: str,
        name: str,
        input_data: Any,
        output_data: Any,
        metadata: dict[str, Any] | None,
        trace_id: str,
    ) -> None:
        """普通模式不做任何调试记录。"""

    def around_llm_call(
        self,
        *,
        trace_id: str,
        name: str,
        input_data: Any,
        metadata: dict[str, Any] | None,
        call: Callable[[], T],
        output_builder: Callable[[T], Any],
    ) -> T:
        """普通模式直接执行 LLM 调用。"""

        return call()

    def around_tool_call(
        self,
        *,
        trace_id: str,
        name: str,
        input_data: Any,
        metadata: dict[str, Any] | None,
        call: Callable[[], T],
        output_builder: Callable[[T], Any],
    ) -> T:
        """普通模式直接执行 Tool 调用。"""

        return call()

    def around_skill_call(
        self,
        *,
        trace_id: str,
        name: str,
        input_data: Any,
        metadata: dict[str, Any] | None,
        call: Callable[[], T],
        output_builder: Callable[[T], Any],
    ) -> T:
        """普通模式直接执行 Skill 调用。"""

        return call()


class DebugTraceRecorder:
    """调试模式使用的切面式记录器。

    Runtime 只调用 record/around_* 方法；命令行输出、SQL 细节和时间格式化都不
    泄露到业务流程中，从而保持 Agent Loop 代码干净。
    """

    def __init__(
        self,
        session_id: str,
        store: DebugTraceStore,
        *,
        error_sink: Callable[[str], None] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_id = session_id
        self.store = store
        self.error_sink = error_sink
        self.now = now or datetime.now

    def record(
        self,
        *,
        event_type: str,
        stage: str,
        name: str,
        input_data: Any,
        output_data: Any,
        metadata: dict[str, Any] | None,
        trace_id: str,
    ) -> None:
        """记录一条调试事件到 SQLite。

        写入失败会被吞掉并转成安全错误提示，避免调试系统拖垮主会话。
        """

        current = self.now()
        event = DebugTraceEvent(
            event_type=event_type,
            stage=stage,
            name=name,
            input=_to_debug_text(input_data),
            output=_to_debug_text(output_data),
            metadata=metadata or {},
            session_id=self.session_id,
            trace_id=trace_id,
            created_at=format_debug_time(current),
        )
        try:
            self.store.save(event, now=current)
        except Exception:
            if self.error_sink is not None:
                self.error_sink("调试记录写入失败，当前 Session 将继续运行。")

    def around_llm_call(
        self,
        *,
        trace_id: str,
        name: str,
        input_data: Any,
        metadata: dict[str, Any] | None,
        call: Callable[[], T],
        output_builder: Callable[[T], Any],
    ) -> T:
        """记录 LLM 调用前后的调试事件。"""

        return self._around(
            event_type="llm",
            before_stage="llm_before",
            after_stage="llm_after",
            trace_id=trace_id,
            name=name,
            input_data=input_data,
            metadata=metadata,
            call=call,
            output_builder=output_builder,
        )

    def around_tool_call(
        self,
        *,
        trace_id: str,
        name: str,
        input_data: Any,
        metadata: dict[str, Any] | None,
        call: Callable[[], T],
        output_builder: Callable[[T], Any],
    ) -> T:
        """记录 Tool 调用前后的调试事件。"""

        return self._around(
            event_type="tool",
            before_stage="tool_before",
            after_stage="tool_after",
            trace_id=trace_id,
            name=name,
            input_data=input_data,
            metadata=metadata,
            call=call,
            output_builder=output_builder,
        )

    def around_skill_call(
        self,
        *,
        trace_id: str,
        name: str,
        input_data: Any,
        metadata: dict[str, Any] | None,
        call: Callable[[], T],
        output_builder: Callable[[T], Any],
    ) -> T:
        """记录 Skill 调用前后的调试事件。"""

        return self._around(
            event_type="skill",
            before_stage="skill_before",
            after_stage="skill_after",
            trace_id=trace_id,
            name=name,
            input_data=input_data,
            metadata=metadata,
            call=call,
            output_builder=output_builder,
        )

    def _around(
        self,
        *,
        event_type: str,
        before_stage: str,
        after_stage: str,
        trace_id: str,
        name: str,
        input_data: Any,
        metadata: dict[str, Any] | None,
        call: Callable[[], T],
        output_builder: Callable[[T], Any],
    ) -> T:
        """通用前后置记录逻辑。"""

        self.record(
            event_type=event_type,
            stage=before_stage,
            name=name,
            input_data=input_data,
            output_data="",
            metadata=metadata,
            trace_id=trace_id,
        )
        try:
            result = call()
        except Exception as exc:
            self.record(
                event_type=event_type,
                stage=after_stage,
                name=name,
                input_data="",
                output_data={"error": str(exc)},
                metadata={**(metadata or {}), "ok": False},
                trace_id=trace_id,
            )
            raise
        self.record(
            event_type=event_type,
            stage=after_stage,
            name=name,
            input_data="",
            output_data=output_builder(result),
            metadata={**(metadata or {}), "ok": True},
            trace_id=trace_id,
        )
        return result


def _to_debug_text(value: Any) -> str:
    """把任意调试输入输出转为可保存文本。"""

    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)
