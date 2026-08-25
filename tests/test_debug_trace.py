import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path

from personal_agent.debug_trace import (
    DebugTraceEvent,
    DebugTraceRecorder,
    DebugTraceStore,
    NullDebugTraceRecorder,
    build_debug_trace_path,
    format_debug_time,
)


class DebugTraceTests(unittest.TestCase):
    def test_format_debug_time_uses_local_readable_timestamp(self) -> None:
        """防止调试记录时间被保存成 ISO/UTC 格式，影响按示例阅读。"""

        now = datetime(2026, 8, 25, 19, 6, 1)

        self.assertEqual(format_debug_time(now), "2026-08-25 19:06:01")

    def test_build_debug_trace_path_uses_date_partitioned_file_name(self) -> None:
        """防止调试 SQLite 文件落到错误目录或带上不符合需求的扩展名。"""

        with tempfile.TemporaryDirectory() as tmp:
            path = build_debug_trace_path(Path(tmp), now=datetime(2026, 8, 25, 19, 6, 1))

        self.assertEqual(path, Path(tmp) / ".babyface" / "debug" / "debug_trace_20260825")

    def test_store_writes_event_to_date_partitioned_sqlite_file(self) -> None:
        """防止调试事件只停留在内存中，没有真正落到 SQLite。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = DebugTraceStore(root)
            event = DebugTraceEvent(
                event_type="llm",
                stage="llm_after",
                name="chat",
                input="[]",
                output="模型输出",
                metadata={"model": "test-model"},
                session_id="session-1",
                trace_id="trace-1",
                created_at="2026-08-25 19:06:01",
            )

            store.save(event, now=datetime(2026, 8, 25, 19, 6, 1))

            db_path = root / ".babyface" / "debug" / "debug_trace_20260825"
            with closing(sqlite3.connect(db_path)) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT * FROM debug_trace_events").fetchone()

        self.assertEqual(row["event_type"], "llm")
        self.assertEqual(row["stage"], "llm_after")
        self.assertEqual(row["session_id"], "session-1")
        self.assertEqual(row["trace_id"], "trace-1")
        self.assertEqual(row["input"], "[]")
        self.assertEqual(row["output"], "模型输出")
        self.assertIn('"model": "test-model"', row["metadata"])
        self.assertNotIn("sessionId", row.keys())
        self.assertNotIn("traceId", row.keys())

    def test_store_switches_sqlite_file_when_date_changes(self) -> None:
        """防止跨日期调试记录被追加进前一天的 SQLite 文件。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = DebugTraceStore(root)
            event = DebugTraceEvent(
                event_type="user",
                stage="user_input_received",
                name="user_input",
                input="你好",
                output="",
                metadata={},
                session_id="session-1",
                trace_id="trace-1",
                created_at="2026-08-25 23:59:59",
            )

            store.save(event, now=datetime(2026, 8, 25, 23, 59, 59))
            store.save(
                DebugTraceEvent(
                    **{
                        **event.__dict__,
                        "trace_id": "trace-2",
                        "created_at": "2026-08-26 00:00:01",
                    }
                ),
                now=datetime(2026, 8, 26, 0, 0, 1),
            )

            first = root / ".babyface" / "debug" / "debug_trace_20260825"
            second = root / ".babyface" / "debug" / "debug_trace_20260826"

            self.assertTrue(first.exists())
            self.assertTrue(second.exists())

    def test_recorder_failure_reports_safe_error_without_sensitive_payload(self) -> None:
        """防止 SQLite 写入失败时把用户输入或模型输出泄露到命令行错误提示中。"""

        class BrokenStore:
            def save(self, event, now=None):
                raise OSError("disk full")

        messages = []
        recorder = DebugTraceRecorder(
            session_id="session-1",
            store=BrokenStore(),
            error_sink=messages.append,
            now=lambda: datetime(2026, 8, 25, 19, 6, 1),
        )

        recorder.record(
            event_type="user",
            stage="user_input_received",
            name="user_input",
            input_data="用户隐私输入",
            output_data="模型敏感输出",
            metadata={},
            trace_id="trace-1",
        )

        self.assertEqual(len(messages), 1)
        self.assertIn("调试记录写入失败", messages[0])
        self.assertNotIn("用户隐私输入", messages[0])
        self.assertNotIn("模型敏感输出", messages[0])

    def test_null_recorder_does_not_create_debug_file(self) -> None:
        """防止普通模式误创建调试 SQLite 文件。"""

        with tempfile.TemporaryDirectory() as tmp:
            recorder = NullDebugTraceRecorder()
            recorder.record(
                event_type="user",
                stage="user_input_received",
                name="user_input",
                input_data="你好",
                output_data="",
                metadata={},
                trace_id="trace-1",
            )

            self.assertFalse((Path(tmp) / ".babyface" / "debug").exists())


if __name__ == "__main__":
    unittest.main()
