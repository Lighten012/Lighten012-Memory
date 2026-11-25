"""Verify the running server's identity and tool list without touching the database."""
import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

EXPECTED = {"memory_create", "memory_search", "memory_update", "memory_delete"}


async def check(url):
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as client:
            info = await client.initialize()
            names = {t.name for t in (await client.list_tools()).tools}
            if info.serverInfo.name != "lighten012-memory" or names != EXPECTED:
                raise ValueError("此地址未提供预期的 Lighten012-Memory 服务和四个工具")
            print(f"{info.serverInfo.name}: {', '.join(sorted(names))}")


if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(check(sys.argv[1]), timeout=8))
    except Exception as err:
        sys.exit(f"MCP 检查失败 ({sys.argv[1]}): {err}")
