"""FastAPI Server for LangGraph Support-Ticket Agent Interactive Demo.

Provides real-time SSE streaming for graph execution, HITL approval/rejection handling,
scenario listing, and batch evaluation.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pydantic import BaseModel

from .graph import build_graph
from .metrics import metric_from_state, summarize_metrics
from .scenarios import load_scenarios
from .state import AgentState, Route, Scenario, initial_state

# Load environment variables
load_dotenv()
os.environ["LANGGRAPH_INTERRUPT"] = "true"

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEMO_HTML_PATH = BASE_DIR / "demo.html"
SCENARIOS_PATH = BASE_DIR / "data" / "sample" / "scenarios.jsonl"

app = FastAPI(
    title="LangGraph Agent Lab Demo API",
    description="Interactive backend API for LangGraph Support-Ticket Agent",
    version="1.0.0",
)

# CORS middleware for local frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global in-memory checkpointer & graph
checkpointer = MemorySaver()
graph = build_graph(checkpointer=checkpointer)


class RunRequest(BaseModel):
    query: str
    scenario_id: str | None = None
    max_attempts: int = 3
    thread_id: str | None = None
    expected_route: str | None = None
    requires_approval: bool = False
    should_retry: bool = False


class ApprovalRequest(BaseModel):
    thread_id: str
    approved: bool = True
    reviewer: str = "human-admin@support.corp"
    comment: str = ""


@app.get("/", response_class=HTMLResponse)
async def serve_demo() -> FileResponse:
    """Serve the interactive demo dashboard."""
    if not DEMO_HTML_PATH.exists():
        raise HTTPException(status_code=404, detail="demo.html not found")
    return FileResponse(DEMO_HTML_PATH, media_type="text/html")


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    """Health status and configuration."""
    if os.getenv("GEMINI_API_KEY"):
        provider = "gemini"
    elif os.getenv("OPENAI_API_KEY"):
        provider = "openai"
    elif os.getenv("ANTHROPIC_API_KEY"):
        provider = "anthropic"
    else:
        provider = "unknown"

    model = os.getenv("LLM_MODEL", "gemini-2.5-flash" if provider == "gemini" else "gpt-4o-mini")
    return {
        "status": "healthy",
        "llm_provider": provider,
        "llm_model": model,
        "total_nodes": 11,
        "nodes": [
            "intake", "classify", "risky_action", "approval",
            "tool", "evaluate", "retry", "dead_letter",
            "clarify", "answer", "finalize"
        ],
        "checkpointer": "MemorySaver",
        "hitl_enabled": True,
        "version": "0.1.0",
    }


@app.get("/api/scenarios")
async def get_scenarios() -> list[dict[str, Any]]:
    """Return all preset scenarios."""
    scenarios = load_scenarios(SCENARIOS_PATH)
    return [s.model_dump() for s in scenarios]


def _clean_state_for_json(state: dict[str, Any]) -> dict[str, Any]:
    """Ensure state dictionary is JSON serializable."""
    clean: dict[str, Any] = {}
    for k, v in state.items():
        if hasattr(v, "model_dump"):
            clean[k] = v.model_dump()
        elif isinstance(v, (list, tuple)):
            cleaned_list = []
            for item in v:
                if hasattr(item, "model_dump"):
                    cleaned_list.append(item.model_dump())
                else:
                    cleaned_list.append(item)
            clean[k] = cleaned_list
        else:
            clean[k] = v
    return clean


async def stream_graph_execution(
    init_state: AgentState,
    thread_id: str,
) -> AsyncGenerator[str, None]:
    """Execute LangGraph workflow and yield SSE events."""
    config = {"configurable": {"thread_id": thread_id}}

    # 1. Start event
    init_payload = json.dumps({"thread_id": thread_id, "state": _clean_state_for_json(init_state)})
    yield f"event: start\ndata: {init_payload}\n\n"

    last_step_time = time.perf_counter()

    try:
        # Run graph in streaming mode
        for chunk in graph.stream(init_state, config=config, stream_mode="updates"):
            curr_time = time.perf_counter()
            latency_ms = int((curr_time - last_step_time) * 1000)
            last_step_time = curr_time

            # chunk has format {'node_name': {state_updates}}
            for node_name, update_dict in chunk.items():
                if node_name == "__interrupt__":
                    continue

                state_snapshot = graph.get_state(config)
                current_values = _clean_state_for_json(state_snapshot.values)

                clean_update = _clean_state_for_json(
                    update_dict if isinstance(update_dict, dict) else {}
                )
                payload = {
                    "node": node_name,
                    "update": clean_update,
                    "state": current_values,
                    "latency_ms": latency_ms,
                    "thread_id": thread_id,
                }
                yield f"event: step\ndata: {json.dumps(payload)}\n\n"

        # Check if paused at HITL interrupt
        state_after = graph.get_state(config)
        is_paused = bool(state_after.next and "approval" in state_after.next)

        if is_paused:
            values = _clean_state_for_json(state_after.values)
            hitl_payload = {
                "thread_id": thread_id,
                "node": "approval",
                "proposed_action": values.get("proposed_action"),
                "action_id": values.get("action_id"),
                "query": values.get("query"),
                "state": values,
            }
            yield f"event: hitl_paused\ndata: {json.dumps(hitl_payload)}\n\n"
        else:
            final_values = _clean_state_for_json(state_after.values)
            completed_payload = {
                "thread_id": thread_id,
                "final_answer": final_values.get("final_answer"),
                "state": final_values,
            }
            yield f"event: completed\ndata: {json.dumps(completed_payload)}\n\n"

    except Exception as exc:
        err_payload = {"thread_id": thread_id, "error": str(exc)}
        yield f"event: error\ndata: {json.dumps(err_payload)}\n\n"


async def stream_approval_resume(
    req: ApprovalRequest,
) -> AsyncGenerator[str, None]:
    """Resume an interrupted graph from HITL decision and stream remaining steps."""
    config = {"configurable": {"thread_id": req.thread_id}}

    default_comment = "Approved by admin" if req.approved else "Rejected by admin"
    resume_payload = {
        "approved": req.approved,
        "reviewer": req.reviewer,
        "comment": req.comment or default_comment,
    }
    command = Command(resume=resume_payload)
    last_step_time = time.perf_counter()

    try:
        for chunk in graph.stream(command, config=config, stream_mode="updates"):
            curr_time = time.perf_counter()
            latency_ms = int((curr_time - last_step_time) * 1000)
            last_step_time = curr_time

            for node_name, update_dict in chunk.items():
                if node_name == "__interrupt__":
                    continue

                state_snapshot = graph.get_state(config)
                current_values = _clean_state_for_json(state_snapshot.values)

                clean_update = _clean_state_for_json(
                    update_dict if isinstance(update_dict, dict) else {}
                )
                payload = {
                    "node": node_name,
                    "update": clean_update,
                    "state": current_values,
                    "latency_ms": latency_ms,
                    "thread_id": req.thread_id,
                }
                yield f"event: step\ndata: {json.dumps(payload)}\n\n"

        state_after = graph.get_state(config)
        final_values = _clean_state_for_json(state_after.values)
        completed_payload = {
            "thread_id": req.thread_id,
            "final_answer": final_values.get("final_answer"),
            "state": final_values,
        }
        yield f"event: completed\ndata: {json.dumps(completed_payload)}\n\n"

    except Exception as exc:
        err_payload = {"thread_id": req.thread_id, "error": str(exc)}
        yield f"event: error\ndata: {json.dumps(err_payload)}\n\n"


@app.post("/api/run-stream")
async def run_stream(req: RunRequest) -> StreamingResponse:
    """Run a query or scenario with real-time SSE streaming."""
    thread_id = req.thread_id or f"thread-{req.scenario_id or uuid.uuid4().hex[:8]}"

    # Map expected_route string to Route enum safely
    route_enum = Route.SIMPLE
    if req.expected_route:
        try:
            route_enum = Route(req.expected_route)
        except ValueError:
            route_enum = Route.SIMPLE

    scenario = Scenario(
        id=req.scenario_id or f"custom_{uuid.uuid4().hex[:6]}",
        query=req.query,
        expected_route=route_enum,
        requires_approval=req.requires_approval,
        should_retry=req.should_retry,
        max_attempts=req.max_attempts,
    )
    state = initial_state(scenario)
    state["thread_id"] = thread_id

    return StreamingResponse(
        stream_graph_execution(state, thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/approve")
async def approve_stream(req: ApprovalRequest) -> StreamingResponse:
    """Submit HITL approval decision and stream subsequent execution."""
    return StreamingResponse(
        stream_approval_resume(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/run-batch")
async def run_batch() -> dict[str, Any]:
    """Execute all 7 grading scenarios on real LangGraph backend and return summary."""
    scenarios = load_scenarios(SCENARIOS_PATH)
    # Temporary non-interrupting graph for automated batch grading
    saved_env = os.environ.get("LANGGRAPH_INTERRUPT")
    os.environ["LANGGRAPH_INTERRUPT"] = "false"
    batch_checkpointer = MemorySaver()
    batch_graph = build_graph(checkpointer=batch_checkpointer)

    metrics = []
    scenario_results = []

    try:
        for sc in scenarios:
            state = initial_state(sc)
            run_config = {"configurable": {"thread_id": state["thread_id"]}}
            final_state = batch_graph.invoke(state, config=run_config)
            m = metric_from_state(final_state, sc.expected_route.value, sc.requires_approval)
            metrics.append(m)
            scenario_results.append({
                "id": sc.id,
                "query": sc.query,
                "expected_route": sc.expected_route.value,
                "actual_route": final_state.get("route"),
                "passed": m.success,
                "attempt": final_state.get("attempt", 0),
                "has_answer": bool(final_state.get("final_answer")),
                "events_count": len(final_state.get("events", [])),
                "final_answer": (final_state.get("final_answer") or "")[:120] + "...",
            })

        report = summarize_metrics(metrics)
        report_dict = report.model_dump()
        report_dict["scenarios_detail"] = scenario_results
        report_dict["passed_scenarios"] = sum(1 for m in metrics if m.success)
        report_dict["routing_accuracy"] = sum(
            1 for m in metrics if m.actual_route == m.expected_route
        ) / len(metrics)
        report_dict["bounded_retry_verified"] = any(m.retry_count > 0 for m in metrics)
        report_dict["hitl_verified"] = any(m.approval_required for m in metrics)

        # Write to outputs/metrics.json
        out_path = BASE_DIR / "outputs" / "metrics.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report_dict, indent=2, ensure_ascii=False), encoding="utf-8")

        return report_dict
    finally:
        if saved_env is not None:
            os.environ["LANGGRAPH_INTERRUPT"] = saved_env
        else:
            os.environ["LANGGRAPH_INTERRUPT"] = "true"


def start(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start uvicorn server programmatically."""
    import uvicorn
    uvicorn.run("langgraph_agent_lab.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    start()
