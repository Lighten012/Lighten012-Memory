import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import memory


class MemoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "test.sqlite3"
        vector = patch.object(memory, "embed", return_value=(1.0, 0.0))
        self.embed = vector.start()
        self.addCleanup(vector.stop)

    def test_update_delete_and_retry(self):
        with closing(memory.connect(self.path)) as db:
            other = memory.save(db, "想保留的记录")["id"]
            target = memory.save(db, "红色赛车", {"state": "draft"})["id"]
            memory.save(db, "蓝色赛车", row_id=target)
            found = memory.search(db, "蓝色")["results"][0]
            self.assertEqual((found["id"], found["meta"]), (target, {"state": "draft"}))
            self.assertTrue(memory.delete(db, target)["deleted"])
            self.assertEqual(db.execute("SELECT count(*) FROM memory_vectors WHERE memory_id=?",
                                        (target,)).fetchone()[0], 0)
            new = memory.save(db, "下一条记录")["id"]
            self.assertGreater(new, target)
            self.assertFalse(memory.delete(db, target)["deleted"])
            self.assertEqual({r["id"] for r in memory.search(db, "赛车")["results"]}, {new, other})

    def test_model_unavailable(self):
        with closing(memory.connect(self.path)) as db:
            row = memory.save(db, "旧正文")
            self.embed.side_effect = OSError("模型离线")
            updated = memory.save(db, "新的正文", row_id=row["id"])
            self.assertTrue(updated["saved"])
            self.assertFalse(updated["indexed"])
            self.assertEqual(db.execute("SELECT count(*) FROM memory_vectors").fetchone()[0], 0)
            result = memory.search(db, "新的")
            self.assertTrue(result["embedding_warning"])
            self.assertTrue(result["results"][0]["exact_match"])
            self.assertEqual(memory.search(db, "旧正文")["results"], [])
            self.assertTrue(memory.delete(db, row["id"])["deleted"])

    def test_late_embedding_cannot_resurrect_record(self):
        with closing(memory.connect(self.path)) as db:
            target = memory.save(db, "初稿")["id"]
            def delete_while_embedding(_body):
                with closing(memory.connect(self.path)) as second:
                    memory.delete(second, target)
                return (1.0, 0.0)
            self.embed.side_effect = delete_while_embedding
            result = memory.save(db, "改稿", row_id=target)
            self.assertFalse(result["indexed"])
            self.assertEqual(db.execute("SELECT count(*) FROM memory_vectors").fetchone()[0], 0)

    def test_migrate_preview(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript("""
                CREATE TABLE memories (id INTEGER PRIMARY KEY, body TEXT NOT NULL,
                    visibility TEXT NOT NULL, meta TEXT NOT NULL, revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                INSERT INTO memories VALUES(7,'旧笔记','private','{"keep":1}',3,'then','now');
            """)
            db.execute(memory.VECTORS)
            db.execute("INSERT INTO memory_vectors VALUES(7,?,2,3,?)",
                       (memory.DEFAULT_MODEL, memory.struct.pack("<2f", 1, 0)))
            db.commit()
        with closing(memory.connect(self.path)) as db:
            row = db.execute("SELECT * FROM memories").fetchone()
            self.assertEqual((row["id"], row["revision"], row["created_at"], row["updated_at"]),
                             (7, 3, "then", "now"))
            self.assertNotIn("visibility", row.keys())
            self.assertEqual(json.loads(row["meta"]), {"keep": 1})
            self.assertEqual(memory.search(db, "旧笔记")["results"][0]["id"], 7)
            self.assertEqual(db.execute("SELECT count(*) FROM memory_vectors").fetchone()[0], 1)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertTrue(memory.delete(db, 7)["deleted"])
        with closing(memory.connect(self.path)) as db:
            self.assertGreater(memory.save(db, "新记录")["id"], 7)


if __name__ == "__main__":
    unittest.main()
