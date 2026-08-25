"""State schema for the Day 08 LangGraph lab.

Students should extend the schema only when needed. Keep state lean and serializable.
"""

from __future__ import annotations

from enum import StrEnum
from operator import add
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, Field, field_validator


class Route(StrEnum):
    SIMPLE = "simple"
    TOOL = "tool"
    MISSING_INFO = "missing_info"
    RISKY = "risky"
    ERROR = "error"
    DEAD_LETTER = "dead_letter"
    DONE = "done"


class LabEvent(BaseModel):
    """Append-only audit event for grading and debugging."""

    node: str
    event_type: str
    message: str
    latency_ms: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    approved: bool = False
    reviewer: str = "mock-reviewer"
    comment: str = ""


class AgentState(TypedDict, total=False):
    """LangGraph state.

    Overwrite fields: scalars that change per step (route, attempt, evaluation_result, …)
    Append-only fields: audit lists accumulate across nodes (messages, tool_results, errors, events)
    """

    # ── Conversation ──────────────────────────────────────────────
    thread_id: str
    scenario_id: str
    query: str

    # ── Classification ───────────────────────────────────────────
    route: str
    risk_level: str

    # ── Retry ────────────────────────────────────────────────────
    attempt: int
    max_attempts: int

    # ── Response ─────────────────────────────────────────────────
    final_answer: str | None
    evaluation_result: str
    pending_question: str | None
    proposed_action: str | None
    approval: dict[str, Any] | ApprovalDecision | None

    # ── Error Model (P1-P2) ───────────────────────────────────────
    # tool_error: last exception message (raw, from tool_node try/except)
    tool_error: str | None
    # error_type: normalized category — 'timeout', 'rate_limit', 'unauthorized', 'not_found', …
    error_type: str | None
    # retryable: True = transient (retry); False = permanent (dead_letter immediately)
    retryable: bool | None
    # internal_error: raw repr for audit only — NEVER shown to user
    internal_error: str | None
    # safe_error: user-facing message — no stack trace / credentials
    safe_error: str | None

    # ── HITL Safety (P4-P5) ──────────────────────────────────────
    # action_id: UUID per risky action — key for idempotency
    action_id: str | None
    # idempotency_key: '{thread_id}:{action_id}' — prevents double execution on retry
    idempotency_key: str | None

    # ── Append-only audit lists ───────────────────────────────────
    messages: Annotated[list[str], add]
    tool_results: Annotated[list[str], add]
    errors: Annotated[list[str], add]
    events: Annotated[list[dict[str, Any]], add]


class Scenario(BaseModel):
    id: str
    query: str
    expected_route: Route
    requires_approval: bool = False
    should_retry: bool = False
    max_attempts: int = 3
    tags: list[str] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value


def initial_state(scenario: Scenario) -> AgentState:
    """Create a serializable initial state for one scenario."""
    return {
        "thread_id": f"thread-{scenario.id}",
        "scenario_id": scenario.id,
        "query": scenario.query,
        "route": "",
        "risk_level": "unknown",
        "attempt": 0,
        "max_attempts": scenario.max_attempts,
        "final_answer": None,
        "evaluation_result": "",
        "pending_question": None,
        "proposed_action": None,
        "approval": None,
        # Error model
        "tool_error": None,
        "error_type": None,
        "retryable": None,
        "internal_error": None,
        "safe_error": None,
        # HITL safety
        "action_id": None,
        "idempotency_key": None,
        # Audit lists
        "messages": [],
        "tool_results": [],
        "errors": [],
        "events": [],
    }


def make_event(node: str, event_type: str, message: str, **metadata: object) -> dict[str, Any]:
    """Create a normalized event payload."""
    return LabEvent(
        node=node, event_type=event_type, message=message, metadata=dict(metadata)
    ).model_dump()


