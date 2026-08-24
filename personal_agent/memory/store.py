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
    ) -> int:
        """保存一轮任务历史。

        Task History 是“发生过什么”的记录：
        用户问了什么、Agent 最终答了什么、期间调用了哪些工具。
        """

        created_at = _now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO task_history (user_input, final_response, created_at)
                VALUES (?, ?, ?)
                """,
                (user_input, final_response, created_at),
            )
            task_id = int(cursor.lastrowid)
            for call in tool_calls or []:
                # tool_calls 表只保留少量可查询字段，同时把完整结构放进 metadata JSON。
                conn.execute(
                    """
                    INSERT INTO tool_calls (task_id, name, ok, content, error, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        call.get("name", ""),
                        bool(call.get("ok", False)),
                        call.get("content", ""),
                        call.get("error"),
                        json.dumps(call, ensure_ascii=False),
                    ),
                )
        return task_id

    def list_task_history(self, limit: int = 20) -> list[TaskHistory]:
        """按时间倒序读取最近任务历史。"""

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, user_input, final_response, created_at
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
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tool_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    error TEXT,
                    metadata TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES task_history(id)
                );
                """
            )

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
