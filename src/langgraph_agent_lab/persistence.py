"""Checkpointer adapter."""

from __future__ import annotations

from typing import Any


def build_checkpointer(kind: str = "memory", database_url: str | None = None) -> Any | None:
    """Return a LangGraph checkpointer.

    Supports:
    - "none"     → No persistence (stateless)
    - "memory"   → In-memory (MemorySaver, default, good for tests/CI)
    - "sqlite"   → SQLite with WAL mode for crash-resume evidence
    - "postgres" → PostgreSQL via psycopg3 connection pool (Supabase-compatible)

    Postgres usage (.env):
        CHECKPOINTER=postgres
        DATABASE_URL=postgresql://user:pass@host:5432/dbname

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
        return SqliteSaver(conn=conn)

    if kind == "postgres":
        # pip install langgraph-checkpoint-postgres psycopg[binary] psycopg-pool
        if not database_url:
            raise ValueError(
                "DATABASE_URL is required for postgres checkpointer.\n"
                "Example: postgresql://user:pass@host:5432/dbname"
            )
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise RuntimeError(
                "Install Postgres checkpointer:\n"
                "  pip install langgraph-checkpoint-postgres psycopg[binary] psycopg-pool"
            ) from exc

        # Connection pool — works with Supabase (requires ?sslmode=require for Supabase)
        # Add sslmode if not already present
        conn_string = database_url
        if "supabase" in conn_string and "sslmode" not in conn_string:
            conn_string += "?sslmode=require"

        pool = ConnectionPool(
            conninfo=conn_string,
            max_size=10,
            open=False,           # don't open immediately — call open() to catch errors
            kwargs={"autocommit": True, "connect_timeout": 10, "prepare_threshold": None},
        )
        pool.open(wait=True, timeout=15)   # fail fast if Supabase unreachable
        checkpointer = PostgresSaver(pool)  # type: ignore[arg-type]
        # Creates checkpoint tables if they don't exist yet (idempotent)
        checkpointer.setup()
        return checkpointer

    raise ValueError(f"Unknown checkpointer kind: {kind!r}. Choose: none, memory, sqlite, postgres")

