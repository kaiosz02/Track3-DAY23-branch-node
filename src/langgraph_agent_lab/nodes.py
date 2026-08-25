"""Node functions for the LangGraph workflow.

Each function receives AgentState and returns a partial state update dict.
Do NOT mutate input state — return new values only.

LLM REQUIREMENT:
- classify_node MUST use a real LLM call (structured output for intent classification)
- answer_node MUST use a real LLM call (grounded response generation)
- evaluate_node SHOULD use LLM-as-judge (bonus points; heuristic acceptable for base score)
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Literal, cast

from pydantic import BaseModel, Field

from .llm import get_llm
from .state import AgentState, make_event

# ── Deterministic safety net ──────────────────────────────────────────────────
# Queries containing these keywords MUST route risky regardless of LLM output.
# Prevents LLM from accidentally bypassing HITL approval.
RISKY_KEYWORDS: frozenset[str] = frozenset({
    "refund",
    "delete",
    "remove",
    "cancel",
    "send email",
    "send confirmation",
    "account deletion",
    "wipe",
    "erase",
})

# ── Retry/Error Policy ────────────────────────────────────────────────────────
# Errors in RETRYABLE_ERRORS are transient — worth retrying with backoff.
# All other errors are permanent — route straight to dead_letter.
RETRYABLE_ERRORS: frozenset[str] = frozenset({
    "timeout",
    "rate_limit",
    "bad_gateway",
    "service_unavailable",
    "connection_reset",
    "temporary_failure",
})

TOOL_TIMEOUT_SECONDS: float = float(os.getenv("TOOL_TIMEOUT_SECONDS", "8"))


def _normalize_error(exc: Exception) -> tuple[str, str, bool]:
    """Normalize an exception into (error_type, safe_error, retryable).

    Returns:
        error_type: machine-readable category string
        safe_error: user-facing message (no stack trace)
        retryable: True if the caller should retry
    """
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg:
        return "timeout", "The service timed out. Please try again.", True
    if "rate limit" in msg or "429" in msg or "rate_limit" in msg:
        return "rate_limit", "Request rate limit reached. Retrying shortly.", True
    if "502" in msg or "bad gateway" in msg:
        return "bad_gateway", "Gateway error. Retrying.", True
    if "503" in msg or "service unavailable" in msg or "unavailable" in msg:
        return "service_unavailable", "Service temporarily unavailable. Retrying.", True
    if "connection" in msg or "reset" in msg or "network" in msg:
        return "connection_reset", "Network issue. Retrying.", True
    if "401" in msg or "unauthorized" in msg:
        return "unauthorized", "Authentication failed. Please contact support.", False
    if "403" in msg or "forbidden" in msg:
        return "forbidden", "Access denied. Please contact support.", False
    if "404" in msg or "not found" in msg:
        return "not_found", "The requested resource was not found.", False
    if "400" in msg or "bad request" in msg or "invalid" in msg:
        return "validation_error", "Invalid request. Please check your input.", False
    return "unknown", "An unexpected error occurred. Please try again.", False


# ─── EXAMPLE: working node (provided for reference) ──────────────────────────
def intake_node(state: AgentState) -> dict:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


# ─── Pydantic models ──────────────────────────────────────────────────────────

class ClassificationResult(BaseModel):
    route: Literal["simple", "tool", "missing_info", "risky", "error"] = Field(
        description=(
            "The classified route. Follow priority: risky > tool > missing_info > error > simple. "
            "- 'risky': Actions with side effects like refunds, account deletions, sending emails. "
            "- 'tool': Information lookups such as order status, tracking, account search. "
            "- 'missing_info': Vague queries lacking details (e.g. 'Can you fix it?'). "
            "- 'error': System failures, timeouts, crashes, unrecoverable errors. "
            "- 'simple': General questions and self-service FAQ (e.g. 'How do I reset password?')."
        )
    )
    risk_level: Literal["high", "low"] = Field(
        default="low",
        description="'high' for risky actions with side effects, 'low' otherwise.",
    )
    reasoning: str = Field(
        default="",
        description="Brief reasoning for the chosen classification.",
    )


class EvaluationResult(BaseModel):
    is_satisfactory: bool = Field(
        description="True if tool execution succeeded; False if error/timeout needing retry."
    )
    feedback: str = Field(
        default="",
        description="Brief feedback on the tool result quality.",
    )


# ─── Node implementations ─────────────────────────────────────────────────────

def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using an LLM.

    *** MUST use a real LLM call — keyword-only heuristics will lose points. ***
    """
    query = state.get("query", "").strip()
    llm = get_llm()
    structured_llm = llm.with_structured_output(ClassificationResult)

    system_prompt = (
        "You are an expert intent classifier for a customer support-ticket workflow.\n"
        "Analyze the user's query and classify it into exactly one of the 5 routes.\n"
        "You MUST strictly follow this priority order: "
        "risky > tool > missing_info > error > simple.\n\n"
        "Route definitions:\n"
        "1. 'risky': Side effects or financial consequences (refunds, cancellations, deletions).\n"
        "2. 'tool': Read-only queries requiring lookups (order status, tracking, account search).\n"
        "3. 'missing_info': Queries too vague or incomplete to act upon (e.g. 'Can you fix it?').\n"
        "4. 'error': Reports of system failures, timeouts, crash logs.\n"
        "5. 'simple': General informational FAQ questions (e.g. 'How do I reset my password?').\n\n"
        "For 'risky' route, risk_level must be 'high'. For all others, risk_level must be 'low'."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Customer Ticket Query: {query}"},
    ]

    result = cast(ClassificationResult, structured_llm.invoke(messages))
    route = result.route
    risk_level = "high" if route == "risky" or result.risk_level == "high" else "low"

    # ── Safety net: deterministic override to prevent LLM bypassing HITL ──────
    query_lower = query.lower()
    if any(kw in query_lower for kw in RISKY_KEYWORDS):
        route = "risky"
        risk_level = "high"

    return {
        "route": route,
        "risk_level": risk_level,
        "events": [
            make_event(
                "classify",
                "completed",
                f"classified as {route}",
                route=route,
                risk_level=risk_level,
                reasoning=result.reasoning,
            )
        ],
    }


def tool_node(state: AgentState) -> dict:
    """Execute a mock tool call.

    Optimizations (P3, P4, P5):
    - Uses pending_action args when coming from a risky/approved flow (frozen args).
    - Normalizes errors into error_type + retryable + safe_error + internal_error.
    - Idempotency key prevents double-executing side effects on retry.
    - All exceptions caught — graph never crashes before finalize_node.
    """
    attempt = state.get("attempt", 0)
    route = state.get("route", "")
    query = state.get("query", "")
    thread_id = state.get("thread_id", "unknown")
    idempotency_key = state.get("idempotency_key") or f"{thread_id}:attempt-{attempt}"

    try:
        # ── Simulate tool behaviour ────────────────────────────────────────
        if route == "error" and attempt < 2:
            # Simulate transient timeout for error-route scenarios
            raise TimeoutError(
                f"timeout: Service timeout for request '{query}' (attempt {attempt + 1})"
            )

        # Use frozen approved action args if available (risky flow)
        pending_action = state.get("proposed_action")
        if pending_action and isinstance(pending_action, str):
            result_string = (
                f"SUCCESS: Executed approved action for '{query}'. "
                f"Action: {pending_action[:80]}. "
                f"[idempotency_key={idempotency_key}]"
            )
        else:
            result_string = (
                f"SUCCESS: Tool executed successfully for '{query}'. "
                f"Retrieved order/account status: active and verified. "
                f"[idempotency_key={idempotency_key}]"
            )

        return {
            "tool_results": [result_string],
            "tool_error": None,
            "error_type": None,
            "retryable": None,
            "internal_error": None,
            "safe_error": None,
            "events": [
                make_event(
                    "tool", "completed", "tool executed",
                    result=result_string[:120], attempt=attempt,
                    idempotency_key=idempotency_key,
                )
            ],
        }

    except Exception as exc:  # noqa: BLE001
        error_type, safe_error, retryable = _normalize_error(exc)
        internal_error = repr(exc)  # raw — audit only, never shown to user
        tool_error = f"[{error_type}] {safe_error}"

        return {
            "tool_results": [],
            "tool_error": tool_error,
            "error_type": error_type,
            "retryable": retryable,
            "internal_error": internal_error,
            "safe_error": safe_error,
            "errors": [tool_error],
            "events": [
                make_event(
                    "tool", "error", tool_error,
                    attempt=attempt, error_type=error_type, retryable=retryable,
                )
            ],
        }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — the retry-loop gate.

    Optimizations (P2, P8):
    - 3 outcomes: 'success' / 'needs_retry' / 'failed_permanently'
    - Checks retryable field first (deterministic, from tool_node error model)
    - Falls back to heuristic string check, then LLM-as-judge
    - Non-retryable errors (401, 404, validation) → 'failed_permanently' → dead_letter immediately
    """
    tool_results = state.get("tool_results", [])
    latest_result = tool_results[-1] if tool_results else ""
    tool_error = state.get("tool_error")
    retryable = state.get("retryable")

    # ── Step 1: Deterministic evaluation (fast path) ───────────────────────
    if tool_error:
        # Use retryable flag set by _normalize_error in tool_node
        if retryable is False:
            eval_result = "failed_permanently"
        else:
            eval_result = "needs_retry"
    elif not latest_result or "ERROR" in latest_result.upper():
        eval_result = "needs_retry"
    else:
        # ── Step 2: Semantic LLM-as-judge (only when result is non-empty) ─
        try:
            llm = get_llm()
            judge = llm.with_structured_output(EvaluationResult)
            prompt = (
                "You are an automated quality evaluation judge for tool execution results.\n"
                f"Query: {state.get('query', '')}\n"
                f"Tool Output: {latest_result}\n\n"
                "Evaluate whether this tool execution succeeded or requires retry."
            )
            verdict = cast(EvaluationResult, judge.invoke(prompt))
            eval_result = "success" if verdict.is_satisfactory else "needs_retry"
        except Exception:  # noqa: BLE001
            eval_result = "success"  # assume success if LLM judge fails

    return {
        "evaluation_result": eval_result,
        "events": [
            make_event(
                "evaluate",
                "completed",
                f"evaluated result as {eval_result}",
                evaluation=eval_result,
                error_type=state.get("error_type"),
                retryable=retryable,
            )
        ],
    }


def answer_node(state: AgentState) -> dict:
    """Generate a final response using an LLM.

    *** MUST use a real LLM call — hardcoded strings will lose points. ***

    Optimization (P6, P11):
    - Wrapped in try/except with safe fallback so graph never crashes before finalize.
    """
    query = state.get("query", "")
    tool_results = state.get("tool_results", [])
    approval = state.get("approval")
    safe_error = state.get("safe_error")

    context_lines = [f"Customer Query: {query}"]
    if tool_results:
        context_lines.append(f"Tool Execution Results: {'; '.join(tool_results)}")
    if approval:
        context_lines.append(f"Approval Decision: {approval}")
    if safe_error:
        context_lines.append(f"Note: {safe_error}")

    try:
        llm = get_llm()
        prompt = (
            "You are a helpful and professional customer support agent.\n"
            "Generate a clear, friendly, and complete response grounded in the context:\n\n"
            + "\n".join(context_lines)
            + "\n\nProvide the final response directly to the customer."
        )
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        if isinstance(content, list):
            content = "".join(
                str(b.get("text", b)) if isinstance(b, dict) else str(b) for b in content
            )
        final_answer = content.strip()
    except Exception:  # noqa: BLE001
        # Safe fallback — graph must not crash before finalize
        final_answer = (
            "We have processed your request. "
            "If you need further assistance, please contact our support team."
        )

    return {
        "final_answer": final_answer,
        "events": [make_event("answer", "completed", "final answer generated")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating."""
    query = state.get("query", "")
    question = (
        f"We need a bit more information to help you with: '{query}'. "
        "Could you please provide specific details such as your account ID or order number?"
    )
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [
            make_event("clarify", "completed", "clarification requested", question=question)
        ],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for human approval.

    Optimization (P4, P5):
    - Creates a unique action_id (UUID) per risky action.
    - Stores frozen proposed_action dict with action_id — args cannot change after this point.
    - approval_node will create idempotency_key from thread_id + action_id.
    """
    query = state.get("query", "")
    action_id = str(uuid.uuid4())[:8]  # short UUID for readability

    proposed = (
        f"High-impact action proposed for request: '{query}'. "
        "Requires explicit human authorization."
    )

    return {
        "action_id": action_id,
        "proposed_action": proposed,
        "events": [
            make_event(
                "risky_action", "completed", "proposed risky action",
                action=proposed, action_id=action_id,
            )
        ],
    }


def approval_node(state: AgentState) -> dict:
    """Human-in-the-loop approval step.

    Optimization (P4, P5):
    - After approval, creates idempotency_key = '{thread_id}:{action_id}'.
    - This key is passed to tool_node to prevent double-execution on retry.

    Default: mock approval (approved=True) for tests/CI.
    Extension: set LANGGRAPH_INTERRUPT=true for real HITL via interrupt().
    """
    thread_id = state.get("thread_id", "unknown")
    action_id = state.get("action_id", "unknown")

    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        proposed_action = state.get("proposed_action", "")
        decision = interrupt({
            "action": "approval_required",
            "proposed_action": proposed_action,
            "action_id": action_id,
            "query": state.get("query", ""),
        })
        if isinstance(decision, dict):
            approved = bool(decision.get("approved", True))
            reviewer = str(decision.get("reviewer", "human-reviewer"))
            comment = str(decision.get("comment", ""))
        else:
            approved = bool(decision)
            reviewer = "human-reviewer"
            comment = ""
        approval_data = {"approved": approved, "reviewer": reviewer, "comment": comment}
    else:
        approval_data = {
            "approved": True,
            "reviewer": "mock-reviewer",
            "comment": "Auto-approved by policy for automated workflow",
        }

    # Create idempotency_key after approval so tool_node can use it
    idempotency_key = f"{thread_id}:{action_id}" if approval_data["approved"] else None
    status_str = "action approved" if approval_data["approved"] else "action rejected"

    return {
        "approval": approval_data,
        "idempotency_key": idempotency_key,
        "events": [
            make_event(
                "approval", "completed", status_str,
                approved=approval_data["approved"],
                action_id=action_id,
                idempotency_key=idempotency_key,
            )
        ],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt with exponential backoff.

    Optimization (P10):
    - Applies exponential backoff: delay = 0.25 * (2 ** attempt) seconds.
    - Logs error_type in audit event for traceability.
    """
    attempt = state.get("attempt", 0)
    new_attempt = attempt + 1
    error_type = state.get("error_type", "unknown")

    # Exponential backoff: 0.5s → 1s → 2s → …
    backoff_delay = 0.25 * (2 ** attempt)
    if backoff_delay > 0 and os.getenv("DISABLE_BACKOFF", "").lower() != "true":
        time.sleep(backoff_delay)

    err_msg = (
        f"Attempt {new_attempt} failed [{error_type}]: "
        f"transient error, retrying in {backoff_delay:.1f}s"
    )

    return {
        "attempt": new_attempt,
        "errors": [err_msg],
        "events": [
            make_event(
                "retry", "completed", f"retry attempt {new_attempt}",
                attempt=new_attempt, error_type=error_type, backoff_s=backoff_delay,
            )
        ],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failures — permanent errors or max retries exhausted.

    Optimization (P12):
    - Uses safe_error for user message (no raw stack trace).
    - Logs internal_error for audit only.
    """
    attempt = state.get("attempt", 0)
    query = state.get("query", "")
    safe_error = state.get("safe_error")
    internal_error = state.get("internal_error")
    error_type = state.get("error_type", "unknown")

    if safe_error:
        user_msg = (
            f"We were unable to complete your request after {attempt} attempt(s). "
            f"{safe_error} "
            "Your ticket has been escalated to Tier-2 technical support."
        )
    else:
        user_msg = (
            f"We were unable to complete your request: '{query}' after {attempt} attempts. "
            "Your ticket has been escalated to Tier-2 technical support."
        )

    return {
        "final_answer": user_msg,
        "events": [
            make_event(
                "dead_letter", "completed",
                f"escalated to dead letter after {attempt} attempts",
                error_type=error_type,
                # internal_error logged for audit but not surfaced to user
                internal_error_recorded=bool(internal_error),
            )
        ],
    }


def finalize_node(state: AgentState) -> dict:
    """Emit a final audit event. All routes must pass through here before END."""
    return {
        "events": [
            make_event(
                "finalize", "completed", "workflow finished",
                route=state.get("route", "unknown"),
                attempt=state.get("attempt", 0),
                has_answer=bool(state.get("final_answer")),
                has_approval=state.get("approval") is not None,
            )
        ],
    }
