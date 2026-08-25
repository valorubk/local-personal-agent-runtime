import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path

from personal_agent.memory.store import MemoryStore


class MemoryStoreTests(unittest.TestCase):
    def test_memory_store_creates_database_and_saves_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "memory.sqlite3"
            store = MemoryStore(db_path)
            store.save_profile("learning_goal", "学习 Agent Runtime")

            self.assertTrue(db_path.exists())
            self.assertEqual(store.get_profile("learning_goal"), "学习 Agent Runtime")

    def test_memory_store_saves_task_history_and_tool_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.sqlite3")
            task_id = store.save_task_history(
                user_input="总结文件",
                final_response="已总结",
                tool_calls=[{"name": "file_read", "ok": True}],
                session_id="session-1",
                trace_id="trace-1",
            )

            history = store.list_task_history()

        self.assertEqual(task_id, 1)
        self.assertEqual(history[0].user_input, "总结文件")
        self.assertEqual(history[0].final_response, "已总结")
        self.assertEqual(history[0].session_id, "session-1")
        self.assertEqual(history[0].trace_id, "trace-1")
        self.assertEqual(history[0].tool_calls[0]["name"], "file_read")
        self.assertEqual(history[0].tool_calls[0]["session_id"], "session-1")
        self.assertEqual(history[0].tool_calls[0]["trace_id"], "trace-1")

    def test_memory_store_migrates_existing_history_tables_for_trace_ids(self) -> None:
        """防止已有 memory.sqlite3 升级后缺少 session_id/trace_id 字段。"""

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "memory.sqlite3"
            with closing(sqlite3.connect(db_path)) as conn:
                conn.executescript(
                    """
                    CREATE TABLE task_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_input TEXT NOT NULL,
                        final_response TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE tool_calls (
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

            MemoryStore(db_path)

            with closing(sqlite3.connect(db_path)) as conn:
                task_columns = {row[1] for row in conn.execute("PRAGMA table_info(task_history)")}
                tool_columns = {row[1] for row in conn.execute("PRAGMA table_info(tool_calls)")}

        self.assertIn("session_id", task_columns)
        self.assertIn("trace_id", task_columns)
        self.assertIn("session_id", tool_columns)
        self.assertIn("trace_id", tool_columns)

    def test_memory_store_moves_legacy_default_database_into_memory_directory(self) -> None:
        """防止默认路径调整后看不到旧 `.babyface/memory.sqlite3` 里的数据。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            babyface_dir = root / ".babyface"
            legacy_path = babyface_dir / "memory.sqlite3"
            new_path = babyface_dir / "memory" / "memory.sqlite3"
            babyface_dir.mkdir(parents=True)
            legacy_store = MemoryStore(legacy_path)
            legacy_store.save_profile("favorite_food", "梅菜扣肉")

            migrated_store = MemoryStore(new_path)

            self.assertEqual(migrated_store.get_profile("favorite_food"), "梅菜扣肉")
            self.assertTrue(new_path.exists())
            self.assertFalse(legacy_path.exists())

    def test_retrieve_knowledge_returns_compatible_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.sqlite3")

            self.assertEqual(store.retrieve_knowledge("Agent"), [])


if __name__ == "__main__":
    unittest.main()
