from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Iterator
from typing import Any

from personal_agent.memory.models import TaskHistory


class MemoryStore:
    """SQLite Memory 存储。

    V1 使用标准库 `sqlite3`，不引入 ORM。原因是：
    - SQLite 本身已经足够支撑本地个人助手的初版记忆
    - 直接 SQL 更容易看清楚数据表结构
    - 初学者可以更直观理解“记忆”到底落在哪里
    """

    def __init__(self, db_path: str | Path) -> None:
        # db_path 可以是字符串，也可以是 Path。统一转成 Path 后更方便处理目录。
        self.db_path = Path(db_path)

        # SQLite 文件所在目录可能不存在，例如 `.babyface/`，这里先创建目录。
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 初始化表结构。`CREATE TABLE IF NOT EXISTS` 让重复启动不会报错。
        self._initialize()

    def save_profile(self, key: str, value: str) -> None:
        """保存长期用户信息。

        Profile Memory 是“长期事实”，例如用户偏好、学习目标、面试状态。
        这里用 key-value 结构，足够简单，也方便后续迁移到更复杂的 schema。
        """

        now = _now_iso()
        with self._connect() as conn:
            # UPSERT：如果 key 已存在就更新，否则插入。
            conn.execute(
                """
                INSERT INTO profile_memory (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, now),
            )

    def get_profile(self, key: str) -> str | None:
        """读取单条 Profile Memory。"""

        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM profile_memory WHERE key = ?",
                (key,),
            ).fetchone()
        return None if row is None else str(row["value"])

    def list_profile(self) -> dict[str, str]:
        """读取全部 Profile Memory。

        当前 V1 会把这些信息注入 LLM 的 system message。
        数据量大以后不能这么做，未来需要检索、摘要或 RAG。
        """

        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM profile_memory ORDER BY key").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

    def save_task_history(
        self,
        user_input: str,
        final_response: str,
        tool_calls: list[dict[str, Any]] | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
    ) -> int:
        """保存一轮任务历史。

        Task History 是“发生过什么”的记录：
        用户问了什么、Agent 最终答了什么、期间调用了哪些工具。

        `session_id` 和 `trace_id` 来自 Debug 模式的调用链路：
        - session_id：一次 Babyface CLI 启动对应一个会话
        - trace_id：用户每输入一轮对话生成一个唯一链路
        普通模式下这两个字段可以为空，避免把 Debug 机制强绑到 Memory。
        """

        created_at = _now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO task_history (
                    user_input,
                    final_response,
                    created_at,
                    session_id,
                    trace_id
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_input, final_response, created_at, session_id, trace_id),
            )
            task_id = int(cursor.lastrowid)
            for call in tool_calls or []:
                # Debug 关联 ID 同时写入结构化列和 metadata JSON。
                # 结构化列方便 SQL 查询，metadata 保持 list_task_history() 现有返回形态可直接使用。
                call_with_trace_ids = {
                    **call,
                    "session_id": session_id,
                    "trace_id": trace_id,
                }

                # tool_calls 表只保留少量可查询字段，同时把完整结构放进 metadata JSON。
                conn.execute(
                    """
                    INSERT INTO tool_calls (
                        task_id,
                        name,
                        ok,
                        content,
                        error,
                        metadata,
                        session_id,
                        trace_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        call_with_trace_ids.get("name", ""),
                        bool(call_with_trace_ids.get("ok", False)),
                        call_with_trace_ids.get("content", ""),
                        call_with_trace_ids.get("error"),
                        json.dumps(call_with_trace_ids, ensure_ascii=False),
                        session_id,
                        trace_id,
                    ),
                )
        return task_id

    def list_task_history(self, limit: int = 20) -> list[TaskHistory]:
        """按时间倒序读取最近任务历史。"""

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, user_input, final_response, created_at, session_id, trace_id
                FROM task_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            histories: list[TaskHistory] = []
            for row in rows:
                calls = conn.execute(
                    """
                    SELECT metadata FROM tool_calls
                    WHERE task_id = ?
                    ORDER BY id
                    """,
                    (row["id"],),
                ).fetchall()
                histories.append(
                    TaskHistory(
                        id=int(row["id"]),
                        user_input=str(row["user_input"]),
                        final_response=str(row["final_response"]),
                        created_at=datetime.fromisoformat(str(row["created_at"])),
                        session_id=_optional_str(row["session_id"]),
                        trace_id=_optional_str(row["trace_id"]),
                        tool_calls=[json.loads(str(call["metadata"])) for call in calls],
                    )
                )
        return histories

    def retrieve_knowledge(self, query: str) -> list[dict[str, Any]]:
        """未来 RAG 的接口占位。

        RAG 的核心是“根据 query 找到相关知识片段再喂给 LLM”。
        V1 暂时不做 embeddings/vector search，但先保留这个接口，
        Runtime 就不需要等到 V2 再改调用形状。
        """

        return []

    def _initialize(self) -> None:
        """创建 SQLite 表结构。"""

        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS profile_memory (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_input TEXT NOT NULL,
                    final_response TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    session_id TEXT,
                    trace_id TEXT
                );

                CREATE TABLE IF NOT EXISTS tool_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    error TEXT,
                    metadata TEXT NOT NULL,
                    session_id TEXT,
                    trace_id TEXT,
                    FOREIGN KEY(task_id) REFERENCES task_history(id)
                );
                """
            )
            self._ensure_column(conn, "task_history", "session_id", "TEXT")
            self._ensure_column(conn, "task_history", "trace_id", "TEXT")
            self._ensure_column(conn, "tool_calls", "session_id", "TEXT")
            self._ensure_column(conn, "tool_calls", "trace_id", "TEXT")

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_type: str,
    ) -> None:
        """给旧 SQLite 表补充缺失字段。

        `CREATE TABLE IF NOT EXISTS` 不会修改已经存在的表结构。
        所以本地用户升级 Babyface 后，需要用 `PRAGMA table_info` 检查旧表，
        再用 `ALTER TABLE` 追加可空列，旧数据保持 NULL。
        """

        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}
        if column_name in columns:
            return
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """创建一个自动 commit/close 的连接上下文。

        `@contextmanager` 让我们可以写：

        `with self._connect() as conn:`

        进入 with 时打开连接，离开 with 时提交并关闭。
        这能避免忘记 close 导致 ResourceWarning。
        """

        conn = sqlite3.connect(self.db_path)

        # row_factory 让查询结果可以用 row["column"] 访问，比 tuple 下标更清楚。
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _optional_str(value: Any) -> str | None:
    """把 SQLite 可空字段转换成 Python 的可空字符串。"""

    return None if value is None else str(value)
