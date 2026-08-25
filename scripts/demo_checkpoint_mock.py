"""
Demo checkpointing WITHOUT LLM calls (mock nodes).
Shows SQLite state persistence and checkpoint history.
Run: python scripts/demo_checkpoint_mock.py
"""

import sys
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.state import Scenario, Route, initial_state

DB_PATH = "checkpoints/demo_mock.db"
Path("checkpoints").mkdir(exist_ok=True)

# ── Mock LLM responses ────────────────────────────────────────────────────────
class MockClassify:
    route = "simple"
    risk_level = "low"
    reasoning = "FAQ question about password reset"

class MockEval:
    is_satisfactory = True
    feedback = "Result is satisfactory"

class MockAnswer:
    content = "To reset your password, go to the login page and click 'Forgot Password'."

class MockLLM:
    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        # Return appropriate mock based on schema context
        if hasattr(messages, '__class__') and 'classify' in str(messages).lower():
            return MockClassify()
        msg_str = str(messages)
        if 'evaluate' in msg_str or 'tool execution' in msg_str.lower():
            return MockEval()
        if 'Classify' in msg_str or 'route' in msg_str.lower():
            return MockClassify()
        return MockClassify()  # default

def make_mock_llm():
    return MockLLM()

# ── Scenarios ─────────────────────────────────────────────────────────────────
SCENARIOS = [
    Scenario(id="s01_simple",  query="How do I reset my password?", expected_route=Route.SIMPLE),
    Scenario(id="s02_missing", query="Can you fix it?",             expected_route=Route.MISSING_INFO),
    Scenario(id="s03_tool",    query="Lookup order status for order 12345", expected_route=Route.TOOL),
]

print("=" * 65)
print(" CHECKPOINT DEMO (Mock LLM - no API calls needed)")
print("=" * 65)
print()

# ── 1. Build graph with SQLite checkpointer ───────────────────────────────────
print("[1] Init SQLite checkpointer...")
checkpointer = build_checkpointer("sqlite", DB_PATH)

with patch("langgraph_agent_lab.nodes.get_llm", make_mock_llm):
    graph = build_graph(checkpointer=checkpointer)
    print(f"    OK -> {DB_PATH}")
    print()

    # ── 2. Run scenarios ──────────────────────────────────────────────────────
    print("[2] Running 3 scenarios through graph...")
    print()
    results = {}
    for scenario in SCENARIOS:
        state = initial_state(scenario)
        run_config = {"configurable": {"thread_id": state["thread_id"]}}

        print(f"    -> [{scenario.id}]")
        print(f"       query     = {scenario.query[:50]}")

        final = graph.invoke(state, config=run_config)
        results[scenario.id] = final

        route = final.get("route", "?")
        events = final.get("events", [])
        answer = str(
            final.get("final_answer") or
            final.get("pending_question") or ""
        )
        print(f"       route     = {route}")
        print(f"       events    = {len(events)} events")
        print(f"       answer    = {answer[:70]}...")
        print()

    # ── 3. Read back state history from DB ───────────────────────────────────
    print("[3] Reading checkpoint history (LangGraph API)...")
    print()
    for scenario in SCENARIOS:
        thread_id = f"thread-{scenario.id}"
        run_config = {"configurable": {"thread_id": thread_id}}
        history = list(graph.get_state_history(run_config))

        print(f"    Thread [{thread_id}]")
        print(f"      -> {len(history)} checkpoints saved in DB")
        if history:
            latest = history[0].values   # most recent snapshot
            print(f"         route       = {latest.get('route')}")
            print(f"         attempt     = {latest.get('attempt')}")
            print(f"         events      = {len(latest.get('events', []))} events")
            evts = [e.get("node") for e in latest.get("events", [])]
            print(f"         node path   = {' -> '.join(evts)}")
        print()

# ── 4. Raw SQLite ─────────────────────────────────────────────────────────────
print("[4] Raw SQLite database content:")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"    Tables: {tables}")
print()

for table in tables:
    cur.execute(f"SELECT COUNT(*) FROM [{table}]")
    count = cur.fetchone()[0]
    print(f"    [{table}] -> {count} rows")

print()
print("    Sample checkpoint rows:")
try:
    cur.execute("SELECT thread_id, checkpoint_ns, checkpoint_id FROM checkpoints LIMIT 6")
    for row in cur.fetchall():
        print(f"      thread_id={row[0]:<25} | id={row[2][:20]}...")
except Exception as e:
    print(f"    (Could not query checkpoints: {e})")

conn.close()

print()
print("=" * 65)
print(" DONE - SQLite checkpoint demo complete!")
print(f" DB file: {Path(DB_PATH).absolute()}")
print()
print(" To use with real LLM (when quota resets tomorrow):")
print("   python scripts/demo_checkpoint.py")
print()
print(" To use Postgres (Supabase) instead of SQLite:")
print("   set CHECKPOINTER=postgres in .env")
print("   (same API, only storage backend differs)")
print("=" * 65)
