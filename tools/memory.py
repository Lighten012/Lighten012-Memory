#!/usr/bin/env python3
"""Lighten012-Memory CLI and shared SQLite operations."""
import argparse
import json
import math
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import struct
from urllib.parse import urlsplit
import urllib.request

DEFAULT_MODEL = "qwen3-embedding:8b-q8_0"
DEFAULT_BASE = "http://127.0.0.1:11434"
PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama")
if PROVIDER not in ("ollama", "openai"):
    raise ValueError("EMBEDDING_PROVIDER 必须是 ollama 或 openai")
BASE = os.getenv("EMBEDDING_BASE_URL", DEFAULT_BASE if PROVIDER == "ollama" else "").rstrip("/")
MODEL = os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL if PROVIDER == "ollama" else "")
if not MODEL or urlsplit(BASE).scheme not in ("http", "https") or not urlsplit(BASE).hostname:
    raise ValueError("请填写 EMBEDDING_BASE_URL 和 EMBEDDING_MODEL")
MODEL_KEY = json.dumps([PROVIDER, BASE, MODEL])
DATA_HOME = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local/share"))
DB_PATH = Path(os.getenv("LIGHTEN012_DB", DATA_HOME / "lighten012-memory/memory.sqlite3")).expanduser()
EMBED_ERRORS = (OSError, ValueError, KeyError, IndexError, TypeError, OverflowError)

MEMORIES = """CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}', revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)"""
VECTORS = """CREATE TABLE memory_vectors (
    memory_id INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    model TEXT NOT NULL, dimensions INTEGER NOT NULL,
    revision INTEGER NOT NULL, embedding BLOB NOT NULL,
    PRIMARY KEY(memory_id, model, dimensions)
)"""


def connect(path=DB_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        if db.execute("PRAGMA user_version").fetchone()[0] == 0:
            # Keep child rows while replacing the legacy parent table. Foreign keys
            # must be disabled outside the transaction, on this connection only.
            db.execute("PRAGMA foreign_keys=OFF")
            with db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("PRAGMA user_version").fetchone()[0] == 0:
                    columns = {r["name"] for r in db.execute("PRAGMA table_info(memories)")}
                    if not columns:
                        db.execute(MEMORIES)
                        db.execute(VECTORS)
                    elif "visibility" in columns:
                        db.execute(MEMORIES.replace("TABLE memories", "TABLE new_memories"))
                        fields = "id, body, meta, revision, created_at, updated_at"
                        db.execute(f"INSERT INTO new_memories ({fields}) SELECT {fields} FROM memories")
                        db.execute("DROP TABLE memories")
                        db.execute("ALTER TABLE new_memories RENAME TO memories")
                        db.execute("UPDATE memory_vectors SET model=? WHERE model=?",
                                   (json.dumps(["ollama", DEFAULT_BASE, DEFAULT_MODEL]), DEFAULT_MODEL))
                    else:
                        raise ValueError("无法识别数据库格式，请核对 LIGHTEN012_DB")
                    if db.execute("PRAGMA foreign_key_check").fetchone():
                        raise ValueError("向量记录与正文不一致，数据库迁移已回滚")
                    db.execute("PRAGMA user_version=1")
        if db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValueError("数据库版本不受当前程序支持")
        db.execute("PRAGMA foreign_keys=ON")
        return db
    except Exception:
        db.close()
        raise


def nonempty(value):
    if not value.strip():
        raise ValueError("内容不能为空")
    return value.strip()


def embed(text):
    payload = {"model": MODEL, "input": text}
    if PROVIDER == "ollama":
        endpoint = BASE + "/api/embed"
        payload["truncate"] = False
        if MODEL == DEFAULT_MODEL:
            payload["dimensions"] = 768
    else:
        endpoint = BASE + "/embeddings"
        payload["encoding_format"] = "float"
    headers = {"Content-Type": "application/json"}
    key = os.getenv("EMBEDDING_API_KEY")
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(endpoint, json.dumps(payload).encode(), headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if (
        urlsplit(BASE).hostname in ("localhost", "127.0.0.1", "::1")
    ) else urllib.request.build_opener()
    with opener.open(req, timeout=45) as response:
        data = json.load(response)
    vector = data["embeddings"][0] if PROVIDER == "ollama" else data["data"][0]["embedding"]
    if not isinstance(vector, list) or not vector or not all(math.isfinite(x) for x in vector):
        raise ValueError("Embedding 返回的向量无效")
    norm = math.hypot(*vector)
    if not norm or not math.isfinite(norm):
        raise ValueError("Embedding 返回的向量无法归一化")
    return tuple(x / norm for x in vector)


def index_row(db, row_id, revision, body):
    try:
        vector = embed(body)
        dims = len(vector)
        blob = struct.pack(f"<{dims}f", *vector)
    except EMBED_ERRORS as err:
        return str(err)
    with db:
        written = db.execute("""
            INSERT OR REPLACE INTO memory_vectors
            SELECT id, ?, ?, revision, ? FROM memories WHERE id=? AND revision=?
        """, (MODEL_KEY, dims, blob, row_id, revision)).rowcount
    return None if written else "记录已被更新或删除，本次向量已丢弃"


def search(db, query, limit=5):
    query = nonempty(query)
    if not 1 <= limit <= 50:
        raise ValueError("limit 必须在 1 到 50 之间")
    try:
        prompt = ("Instruct: Retrieve relevant personal memories for this query.\nQuery: " + query
                  if MODEL.lower().startswith("qwen3-embedding") else query)
        qvec, warning = embed(prompt), None
    except EMBED_ERRORS as err:
        qvec, warning = (), str(err)
    rows = db.execute("""
        SELECT m.*, v.embedding FROM memories m
        LEFT JOIN memory_vectors v ON v.memory_id=m.id AND v.revision=m.revision
            AND v.model=? AND v.dimensions=?
    """, (MODEL_KEY, len(qvec)))
    found = []
    for row in rows:
        exact = query.casefold() in row["body"].casefold()
        blob = row["embedding"]
        similarity = (sum(a*b for a, b in zip(qvec, struct.unpack(f"<{len(qvec)}f", blob)))
                      if blob is not None else None)
        if exact or similarity is not None:
            found.append(dict(id=row["id"], body=row["body"], meta=json.loads(row["meta"]),
                              exact_match=exact,
                              similarity=None if similarity is None else round(similarity, 5)))
    found.sort(key=lambda r: (r["exact_match"],
                             r["similarity"] if r["similarity"] is not None else -2,
                             r["id"]), reverse=True)
    return dict(results=found[:limit], embedding_warning=warning)


def save(db, body, meta=None, row_id=None):
    body = nonempty(body)
    if meta is not None and not isinstance(meta, dict):
        raise ValueError("meta 必须是 JSON 对象")
    encoded = None if meta is None else json.dumps(meta, ensure_ascii=False, allow_nan=False)
    with db:
        if row_id is None:
            row_id = db.execute("INSERT INTO memories(body,meta) VALUES(?,?)",
                                (body, encoded or "{}")).lastrowid
            revision = 1
        else:
            updated = db.execute("""
                UPDATE memories SET body=?, meta=COALESCE(?,meta),
                    revision=revision+1, updated_at=CURRENT_TIMESTAMP
                WHERE id=? RETURNING revision
            """, (body, encoded, row_id)).fetchone()
            if not updated:
                raise ValueError("未找到该记录")
            revision = updated[0]
            db.execute("DELETE FROM memory_vectors WHERE memory_id=?", (row_id,))
    warning = index_row(db, row_id, revision, body)
    return dict(id=row_id, revision=revision, saved=True, indexed=warning is None,
                embedding_warning=warning)


def delete(db, row_id):
    with db:
        deleted = db.execute("DELETE FROM memories WHERE id=?", (row_id,)).rowcount
    return dict(id=row_id, deleted=bool(deleted))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    sub = parser.add_subparsers(dest="cmd", required=True)
    create = sub.add_parser("create")
    create.add_argument("body")
    create.add_argument("--meta", type=json.loads)
    update = sub.add_parser("update")
    update.add_argument("id", type=int)
    update.add_argument("body")
    update.add_argument("--meta", type=json.loads)
    find = sub.add_parser("search")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=5)
    sub.add_parser("delete").add_argument("id", type=int)
    a = parser.parse_args()
    try:
        with closing(connect(a.db)) as db:
            if a.cmd == "search":
                out = search(db, a.query, a.limit)
            elif a.cmd == "delete":
                out = delete(db, a.id)
            else:
                out = save(db, a.body, a.meta, getattr(a, "id", None))
    except (ValueError, sqlite3.Error) as err:
        parser.exit(1, f"{err}\n")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
