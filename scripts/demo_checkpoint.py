"""
Demo checkpointing: run scenarios, save to SQLite, read back state history.
"""

import os
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.state import Scenario, Route, initial_state

DB_PATH = "checkpoints/demo.db"
Path("checkpoints").mkdir(exist_ok=True)

# ── 1. Build graph with SQLite checkpointer ──────────────────────────────────
print("=" * 60)
print("[1] Init SQLite checkpointer...")
checkpointer = build_checkpointer("sqlite", DB_PATH)
graph = build_graph(checkpointer=checkpointer)
print(f"    OK: {DB_PATH}")
print()

# ── 2. Run scenarios ─────────────────────────────────────────────────────────
scenarios = [
    Scenario(id="demo_simple",  query="How do I reset my password?", expected_route=Route.SIMPLE),
    Scenario(id="demo_missing", query="Can you fix it?",             expected_route=Route.MISSING_INFO),
]

print("[2] Running scenarios...")
for scenario in scenarios:
    state = initial_state(scenario)
    run_config = {"configurable": {"thread_id": state["thread_id"]}}
    print(f"    -> [{scenario.id}] thread_id={state['thread_id']}")
    final = graph.invoke(state, config=run_config)
    print(f"       route        = {final.get('route')}")
    print(f"       events count = {len(final.get('events', []))}")
    answer = str(final.get('final_answer', '') or final.get('pending_question', ''))
    print(f"       answer       = {answer[:80]}...")
    print()

# ── 3. Read checkpoint history via LangGraph API ─────────────────────────────
print("[3] Reading checkpoint history (LangGraph API)...")
print()
for scenario in scenarios:
    thread_id = f"thread-{scenario.id}"
    run_config = {"configurable": {"thread_id": thread_id}}
    history = list(graph.get_state_history(run_config))
    print(f"    Thread [{thread_id}] -> {len(history)} checkpoints")
    if history:
        s = history[0].values
        print(f"      route          = {s.get('route')}")
        print(f"      attempt        = {s.get('attempt')}")
        print(f"      events_count   = {len(s.get('events', []))}")
        print(f"      evaluation     = {s.get('evaluation_result')}")
        answer_val = str(s.get('final_answer', '') or s.get('pending_question', ''))
        print(f"      answer         = {answer_val[:70]}...")
    print()

# ── 4. Raw SQLite tables ─────────────────────────────────────────────────────
print("[4] Raw SQLite database tables:")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"    Tables found: {tables}")
print()

for table in tables:
    cur.execute(f"SELECT COUNT(*) FROM [{table}]")
    count = cur.fetchone()[0]
    print(f"    [{table}] -> {count} rows")
    if count > 0 and table == "checkpoints":
        cur.execute(f"SELECT thread_id, checkpoint_ns, checkpoint_id FROM [{table}] LIMIT 5")
        rows = cur.fetchall()
        for row in rows:
            print(f"      thread_id={row[0]}, ns={row[1]}, id={row[2][:16]}...")

conn.close()

print()
print("=" * 60)
print("DONE - data saved to SQLite!")
print(f"File: {Path(DB_PATH).absolute()}")
print()
print("NOTE: To use Postgres (Supabase) when network allows:")
print("  Set CHECKPOINTER=postgres in .env")
print("  Logic is identical, only storage backend differs.")
