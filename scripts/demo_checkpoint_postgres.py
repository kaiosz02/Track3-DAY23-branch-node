"""
Run LangGraph scenarios and persist state checkpoints to Supabase PostgreSQL.
Usage:
    python scripts/demo_checkpoint_postgres.py
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.state import Scenario, Route, initial_state

# ── Mock LLM in case Gemini free tier rate limit is active ───────────────────
class MockClassify:
    route = "simple"
    risk_level = "low"
    reasoning = "Informational ticket inquiry"

class MockEval:
    is_satisfactory = True
    feedback = "Tool execution was successful"

class MockLLM:
    def with_structured_output(self, schema):
        return self
    def invoke(self, messages):
        msg_str = str(messages)
        if "evaluate" in msg_str.lower() or "tool output" in msg_str.lower():
            return MockEval()
        return MockClassify()

def get_configured_llm():
    # If API key is available, attempt real LLM, fallback to mock if rate-limited
    try:
        from langgraph_agent_lab.llm import get_llm
        llm = get_llm()
        return llm
    except Exception:
        return MockLLM()

def run_demo():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set in .env")
        return

    print("=" * 70)
    print(" SUPABASE POSTGRESQL CHECKPOINT PERSISTENCE DEMO")
    print("=" * 70)
    print(f"PostgreSQL URL: {db_url.split('@')[1] if '@' in db_url else db_url}")
    print()

    # 1. Build checkpointer
    print("[1] Initializing PostgresSaver connection pool...")
    checkpointer = build_checkpointer("postgres", db_url)
    graph = build_graph(checkpointer=checkpointer)
    print("    PostgresSaver initialized & tables verified in Supabase.")
    print()

    # 2. Run scenarios
    scenarios = [
        Scenario(id="pg_s01_simple", query="How do I reset my password?", expected_route=Route.SIMPLE),
        Scenario(id="pg_s02_tool", query="Lookup order status for order 998877", expected_route=Route.TOOL),
        Scenario(id="pg_s03_risky", query="Refund this customer ORD-5544", expected_route=Route.RISKY, requires_approval=True),
    ]

    print("[2] Running scenarios through LangGraph workflow with PostgreSQL checkpointer...")
    print()

    for sc in scenarios:
        state = initial_state(sc)
        run_config = {"configurable": {"thread_id": state["thread_id"]}}
        print(f"    -> Running scenario [{sc.id}] (Thread: {state['thread_id']})...")

        try:
            final = graph.invoke(state, config=run_config)
        except Exception as e:
            err_str = str(e)
            if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str or "quota" in err_str.lower():
                print("       (Gemini Free-tier quota active -> continuing with mock LLM for persistence demonstration)")
                # Generate mock response
                with patch("langgraph_agent_lab.nodes.get_llm", return_value=MockLLM()):
                    # Rebuild graph to ensure patched node execution
                    g_mock = build_graph(checkpointer=checkpointer)
                    final = g_mock.invoke(state, config=run_config)
            else:
                raise e

        route = final.get("route", "")
        events = final.get("events", [])
        answer = final.get("final_answer") or final.get("pending_question") or ""
        print(f"       Status: Route={route} | Events recorded={len(events)}")
        print(f"       Result: {str(answer)[:75]}...")
        print()

    # 3. Read back state history directly from PostgreSQL checkpointer
    print("[3] Querying state history directly from Supabase PostgreSQL Checkpointer:")
    print()
    for sc in scenarios:
        thread_id = f"thread-{sc.id}"
        run_config = {"configurable": {"thread_id": thread_id}}
        history = list(graph.get_state_history(run_config))
        print(f"    Thread [{thread_id}] has {len(history)} checkpoint snapshots saved in Supabase:")
        for idx, snapshot in enumerate(history[:3]):
            vals = snapshot.values
            step_name = snapshot.metadata.get("source", "step")
            print(f"      Step {idx + 1}: route={vals.get('route', 'N/A')} | attempt={vals.get('attempt', 0)} | events={len(vals.get('events', []))}")
        print()

    print("=" * 70)
    print(" SUCCESS: All checkpoints persisted to Supabase PostgreSQL!")
    print(" You can run: python scripts/inspect_db.py to inspect the raw database tables.")
    print("=" * 70)

if __name__ == "__main__":
    run_demo()
