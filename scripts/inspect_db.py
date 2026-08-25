"""
Script to inspect LangGraph checkpoints stored in Postgres (Supabase) or SQLite.
Usage:
    python scripts/inspect_db.py
"""

import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

def inspect_postgres():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL is not set in .env")
        return

    if "sslmode" not in db_url:
        db_url += "?sslmode=require"

    print("=" * 70)
    print(" SUPABASE POSTGRESQL CHECKPOINTS INSPECTION")
    print("=" * 70)
    host_display = db_url.split("@")[1] if "@" in db_url else db_url
    print(f"Connecting to: {host_display}\n")

    try:
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                # 1. Summary of tables
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    ORDER BY table_name;
                """)
                tables = [r[0] for r in cur.fetchall()]
                print("[1] Tables in Database:")
                for tbl in tables:
                    cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                    cnt = cur.fetchone()[0]
                    print(f"    - {tbl:<25}: {cnt:>4} rows")
                print()

                # 2. Checkpoints details
                if "checkpoints" in tables:
                    cur.execute("""
                        SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id
                        FROM checkpoints
                        ORDER BY thread_id, checkpoint_id;
                    """)
                    rows = cur.fetchall()
                    print(f"[2] Stored Checkpoints ({len(rows)} total):")
                    if not rows:
                        print("    (No checkpoints recorded yet. Run a scenario to create checkpoints!)")
                    else:
                        for row in rows:
                            thread_id, ns, cp_id, parent_id = row
                            parent_str = parent_id[:16] + "..." if parent_id else "None (root)"
                            print(f"    - Thread: {thread_id:<20} | ID: {cp_id[:20]}... | Parent: {parent_str}")
                    print()

                # 3. Checkpoint writes
                if "checkpoint_writes" in tables:
                    cur.execute("""
                        SELECT thread_id, task_id, idx, channel
                        FROM checkpoint_writes
                        ORDER BY thread_id, task_id;
                    """)
                    writes = cur.fetchall()
                    print(f"[3] Checkpoint Writes / Channel Updates ({len(writes)} total):")
                    if not writes:
                        print("    (No channel writes recorded yet)")
                    else:
                        for w in writes:
                            thread_id, task_id, idx, channel = w
                            print(f"    - Thread: {thread_id:<20} | Task: {task_id[:15]}... | Channel: {channel}")
                    print()

    except Exception as e:
        print(f"Error querying Postgres: {e}")

if __name__ == "__main__":
    inspect_postgres()
