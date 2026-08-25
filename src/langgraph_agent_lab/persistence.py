"""Checkpointer adapter."""

from __future__ import annotations

from typing import Any


def build_checkpointer(kind: str = "memory", database_url: str | None = None) -> Any | None:
    """Return a LangGraph checkpointer.

    Supports:
    - "none"   → No persistence (stateless)
    - "memory" → In-memory (MemorySaver, default, good for tests/CI)
    - "sqlite" → SQLite with WAL mode for crash-resume evidence
    - "postgres" → Postgres (optional extension)

    SQLite usage:
        build_checkpointer("sqlite", "checkpoints/lab.db")

    The thread_id per run (set in cli.py via run_config) enables:
        - State history:  graph.get_state_history(config)
        - Crash resume:   graph.invoke(Command(resume=...), config)
        - Time travel:    graph.update_state(config, values, as_node=...)
    """
    if kind == "none":
        return None

    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()

    if kind == "sqlite":
        # pip install langgraph-checkpoint-sqlite
        try:
            import sqlite3
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as exc:
            raise RuntimeError(
                "Install SQLite checkpointer: pip install langgraph-checkpoint-sqlite"
            ) from exc

        db_path = database_url or "checkpoints/lab.db"
        conn = sqlite3.connect(db_path, check_same_thread=False)
        # WAL mode: allows concurrent reads without blocking writes
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.commit()
        checkpointer = SqliteSaver(conn=conn)
        return checkpointer

    if kind == "postgres":
        # pip install langgraph-checkpoint-postgres psycopg2-binary
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
        except ImportError as exc:
            raise RuntimeError(
                "Install Postgres checkpointer: pip install langgraph-checkpoint-postgres"
            ) from exc
        if not database_url:
            raise ValueError("database_url is required for postgres checkpointer")
        return PostgresSaver.from_conn_string(database_url)

    raise ValueError(f"Unknown checkpointer kind: {kind!r}. Choose: none, memory, sqlite, postgres")
