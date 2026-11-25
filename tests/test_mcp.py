from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from mcp.server.fastmcp.exceptions import ToolError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import memory
from server import mcp


class ToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_registered_tools_return_structured_results_and_delete_one_integer_id(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.sqlite3"
            db_connect = memory.connect
            with patch.object(memory, "connect", lambda: db_connect(path)), \
                 patch.object(memory, "embed", return_value=(1.0, 0.0)):
                names = {tool.name for tool in await mcp.list_tools()}
                self.assertEqual(names, {"memory_create", "memory_search", "memory_update", "memory_delete"})
                _, created = await mcp.call_tool("memory_create", {"body": "测试"})
                row_id = created["id"]
                for invalid in (True, -1, [row_id], "全部"):
                    with self.subTest(invalid=invalid), self.assertRaises(ToolError):
                        await mcp.call_tool("memory_delete", {"id": invalid})
                _, hits = await mcp.call_tool("memory_search", {"query": "测试"})
                self.assertEqual(hits["results"][0]["id"], row_id)
                _, result = await mcp.call_tool("memory_delete", {"id": row_id})
                self.assertEqual(result, {"id": row_id, "deleted": True})
                _, hits = await mcp.call_tool("memory_search", {"query": "测试"})
                self.assertEqual(hits["results"], [])
