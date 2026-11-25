"""Run the Lighten012-Memory Streamable HTTP MCP service on loopback."""
import asyncio
import os
from contextlib import closing
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

import memory

MemoryID = Annotated[int, Field(strict=True, gt=0, le=2**63-1)]
mcp = FastMCP("lighten012-memory", host="127.0.0.1",
              port=int(os.getenv("LIGHTEN012_PORT", "8765")),
              stateless_http=True, json_response=True)


async def run_db(operation, *args):
    def run():
        with closing(memory.connect()) as db:
            return operation(db, *args)
    return await asyncio.to_thread(run)


@mcp.tool()
async def memory_create(body: str, meta: dict | None = None) -> dict[str, Any]:
    """明确要求记住时，保存一条记忆。返回 ID、是否已保存和向量索引状态。"""
    return await run_db(memory.save, body, meta)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def memory_search(query: str, limit: int = 5) -> dict[str, Any]:
    """按文字及语义查找相关记忆。limit 为 1 到 50；相似结果需要核对正文。"""
    return await run_db(memory.search, query, limit)


@mcp.tool()
async def memory_update(id: MemoryID, body: str, meta: dict | None = None) -> dict[str, Any]:
    """更正指定 ID 的正文。省略 meta 时保留原属性。"""
    return await run_db(memory.save, body, meta, id)


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True))
async def memory_delete(id: MemoryID) -> dict[str, Any]:
    """用户明确要求忘掉且已确认目标时，永久删除单个 ID 的正文和向量。"""
    return await run_db(memory.delete, id)


if __name__ == "__main__":
    with closing(memory.connect()):
        pass
    mcp.run(transport="streamable-http")
