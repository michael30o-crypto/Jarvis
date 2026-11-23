from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jarvis


class JarvisTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["JARVIS_SKIP_GPU_HANDOFF"] = "1"
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db = jarvis.DB_PATH
        jarvis.DB_PATH = Path(self.temp_dir.name) / "test.sqlite3"
        jarvis.init_db()

    def tearDown(self) -> None:
        jarvis.DB_PATH = self.original_db
        self.temp_dir.cleanup()

    def test_tasks_are_persisted(self) -> None:
        result = jarvis.run_tool("add_task", {"text": "Open the project"})
        self.assertIn("Added task #1", result)
        self.assertEqual(json.loads(jarvis.run_tool("list_tasks", {})), [{"id": 1, "text": "Open the project"}])

    def test_non_http_url_is_refused(self) -> None:
        result = jarvis.run_tool("open_url", {"url": "file:///C:/Windows"})
        self.assertIn("Refused", result)

    @patch("jarvis.ollama_chat")
    def test_plain_chat_is_saved(self, model_chat) -> None:
        model_chat.return_value = {"message": {"role": "assistant", "content": "Ready."}}
        self.assertEqual(jarvis.chat("Hello"), "Ready.")
        with jarvis.db() as connection:
            roles = [row["role"] for row in connection.execute("SELECT role FROM messages ORDER BY id")]
        self.assertEqual(roles, ["user", "assistant"])


if __name__ == "__main__":
    unittest.main()
