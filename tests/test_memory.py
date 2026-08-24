import tempfile
import unittest
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
            )

            history = store.list_task_history()

        self.assertEqual(task_id, 1)
        self.assertEqual(history[0].user_input, "总结文件")
        self.assertEqual(history[0].final_response, "已总结")
        self.assertEqual(history[0].tool_calls[0]["name"], "file_read")

    def test_retrieve_knowledge_returns_compatible_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.sqlite3")

            self.assertEqual(store.retrieve_knowledge("Agent"), [])


if __name__ == "__main__":
    unittest.main()
