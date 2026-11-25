#!/usr/bin/env python3
"""Local preview: SQLite text rows + precomputed Ollama embeddings."""
import argparse
import json
import math
from pathlib import Path
import sqlite3
import struct
import urllib.request

MODEL = "qwen3-embedding:8b-q8_0"
DIMS = 768
ROOT = Path(__file__).resolve().parent.parent
ENDPOINT = "http://127.0.0.1:11434/api/embed"


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS memories (
          id INTEGER PRIMARY KEY, body TEXT NOT NULL,
          visibility TEXT NOT NULL CHECK(visibility IN ('private','ai')),
          meta TEXT NOT NULL DEFAULT '{}', revision INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS memory_vectors (
          memory_id INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
          model TEXT NOT NULL, dimensions INTEGER NOT NULL,
          revision INTEGER NOT NULL, embedding BLOB NOT NULL,
          PRIMARY KEY(memory_id, model, dimensions)
        );
    """)
    return db


def embed(text):
    data = json.dumps(dict(model=MODEL, input=text, dimensions=DIMS, truncate=False)).encode()
    req = urllib.request.Request(ENDPOINT, data, {"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=20) as response:
        vector = json.load(response)["embeddings"][0]
    if len(vector) != DIMS or not all(math.isfinite(x) for x in vector):
        raise ValueError("Embedding 返回的维度或数值不符合预期")
    norm = math.sqrt(sum(x*x for x in vector))
    if not norm:
        raise ValueError("Embedding 为零向量")
    return tuple(x/norm for x in vector)


def index_row(db, row_id, revision, body):
    try:
        blob = struct.pack(f"<{DIMS}f", *embed(body))
    except (OSError, ValueError, KeyError, IndexError) as err:
        return str(err)
    with db:
        db.execute("""
            INSERT OR REPLACE INTO memory_vectors
            SELECT id, ?, ?, revision, ? FROM memories WHERE id=? AND revision=?
        """, (MODEL, DIMS, blob, row_id, revision))
    return None


def search(db, query, as_ai=False, limit=5):
    try:
        qvec = embed("Instruct: Retrieve relevant personal memories for this query.\nQuery: " + query)
        warning = None
    except (OSError, ValueError, KeyError, IndexError) as err:
        qvec, warning = None, str(err)
    rows = db.execute("""
        SELECT m.*, v.embedding FROM memories m
        LEFT JOIN memory_vectors v ON v.memory_id=m.id AND v.revision=m.revision
            AND v.model=? AND v.dimensions=?
        WHERE (?=0 OR m.visibility='ai')
    """, (MODEL, DIMS, int(as_ai)))
    found = []
    for row in rows:
        exact = query.casefold() in row["body"].casefold()
        blob = row["embedding"]
        similarity = (sum(a*b for a,b in zip(qvec, struct.unpack(f"<{DIMS}f", blob)))
                      if qvec is not None and blob is not None else None)
        if exact or similarity is not None:
            found.append(dict(id=row["id"], body=row["body"], meta=json.loads(row["meta"]),
                              visibility=row["visibility"], exact_match=exact,
                              similarity=None if similarity is None else round(similarity, 5)))
    found.sort(key=lambda r:(r["exact_match"],
                            r["similarity"] if r["similarity"] is not None else -2,
                            r["id"]), reverse=True)
    return dict(results=found[:limit], embedding_warning=warning)


def metadata(s):
    try:
        value = json.loads(s)
    except ValueError as err:
        raise argparse.ArgumentTypeError(str(err)) from err
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("meta 必须是 JSON 对象")
    return json.dumps(value, ensure_ascii=False)


def nonempty(s):
    if not s.strip():
        raise argparse.ArgumentTypeError("内容不能为空")
    return s.strip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=ROOT/"preview.sqlite3")
    sub = p.add_subparsers(dest="cmd", required=True)
    create = sub.add_parser("create")
    create.add_argument("body", type=nonempty)
    create.add_argument("--share", action="store_true")
    create.add_argument("--meta", type=metadata, default="{}")
    update = sub.add_parser("update")
    update.add_argument("id", type=int)
    update.add_argument("body", type=nonempty)
    update.add_argument("--as-ai", action="store_true")
    update.add_argument("--meta", type=metadata)
    find = sub.add_parser("search")
    find.add_argument("query", type=nonempty)
    find.add_argument("--as-ai", action="store_true")
    find.add_argument("--limit", type=int, choices=range(1, 51), default=5)
    a = p.parse_args()
    db = connect(a.db)
    if a.cmd == "search":
        out = search(db, a.query, a.as_ai, a.limit)
    else:
        with db:
            if a.cmd == "create":
                row_id = db.execute("INSERT INTO memories(body,visibility,meta) VALUES(?,?,?)",
                                    (a.body,"ai" if a.share else "private",a.meta)).lastrowid
                revision = 1
            else:
                updated = db.execute("""
                    UPDATE memories SET body=?, meta=COALESCE(?,meta),
                      revision=revision+1, updated_at=CURRENT_TIMESTAMP
                    WHERE id=? AND (?=0 OR visibility='ai') RETURNING revision
                    """, (a.body,a.meta,a.id,int(a.as_ai))).fetchone()
                if not updated:
                    p.exit(1, "未找到可以更新的记录。\n")
                row_id, revision = a.id, updated[0]
                db.execute("DELETE FROM memory_vectors WHERE memory_id=?", (row_id,))
        error = index_row(db, row_id, revision, a.body)
        out = dict(id=row_id, revision=revision, saved=True, indexed=error is None,
                   embedding_warning=error)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
