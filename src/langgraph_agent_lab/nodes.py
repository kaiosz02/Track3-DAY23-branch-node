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
from typing import Literal

from pydantic import BaseModel, Field

from .llm import get_llm
from .state import AgentState, make_event


# ─── EXAMPLE: working node (provided for reference) ──────────────────
def intake_node(state: AgentState) -> dict:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


# ─── Student implemented nodes ──────────────────────────────────────


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

    result: ClassificationResult = structured_llm.invoke(messages)
    route = result.route
    risk_level = "high" if route == "risky" or result.risk_level == "high" else "low"

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
            )
        ],
    }


def tool_node(state: AgentState) -> dict:
    """Execute a mock tool call.

    Simulate transient failures for error-route scenarios to test retry loops.
    """
    attempt = state.get("attempt", 0)
    route = state.get("route", "")
    query = state.get("query", "")

    # If route is "error" and attempt < 2, simulate a transient failure with "ERROR"
    if route == "error" and attempt < 2:
        result_string = (
            f"ERROR: Service timeout while processing request '{query}' (attempt {attempt + 1})"
        )
    else:
        result_string = (
            f"SUCCESS: Tool executed successfully for '{query}'. "
            "Retrieved order/account status: active and verified."
        )

    return {
        "tool_results": [result_string],
        "events": [
            make_event("tool", "completed", "tool executed", result=result_string, attempt=attempt)
        ],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — the retry-loop gate.

    Check whether the latest tool result is satisfactory or needs retry.
    Uses LLM-as-judge with fallback to heuristic check.
    """
    tool_results = state.get("tool_results", [])
    latest_result = tool_results[-1] if tool_results else ""

    # Check for failure in tool output
    if "ERROR" in latest_result.upper():
        eval_result = "needs_retry"
    else:
        # LLM-as-judge evaluation for bonus points
        try:
            llm = get_llm()
            judge = llm.with_structured_output(EvaluationResult)
            prompt = (
                "You are an automated quality evaluation judge for tool execution results.\n"
                f"Query: {state.get('query', '')}\n"
                f"Tool Output: {latest_result}\n\n"
                "Evaluate whether this tool execution succeeded or requires retry."
            )
            verdict: EvaluationResult = judge.invoke(prompt)
            eval_result = "success" if verdict.is_satisfactory else "needs_retry"
        except Exception:
            eval_result = "needs_retry" if "ERROR" in latest_result.upper() else "success"

    return {
        "evaluation_result": eval_result,
        "events": [
            make_event(
                "evaluate",
                "completed",
                f"evaluated result as {eval_result}",
                evaluation=eval_result,
            )
        ],
    }


def answer_node(state: AgentState) -> dict:
    """Generate a final response using an LLM.

    *** MUST use a real LLM call — hardcoded strings will lose points. ***
    """
    query = state.get("query", "")
    tool_results = state.get("tool_results", [])
    approval = state.get("approval")

    context_lines = [f"Customer Query: {query}"]
    if tool_results:
        context_lines.append(f"Tool Execution Results: {'; '.join(tool_results)}")
    if approval:
        context_lines.append(f"Approval Decision: {approval}")

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
        content = "".join(str(b.get("text", b)) if isinstance(b, dict) else str(b) for b in content)

    final_answer = content.strip()
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
    """Prepare a risky action for human approval."""
    query = state.get("query", "")
    proposed = (
        f"High-impact action proposed for request: '{query}'. "
        "Requires explicit human authorization."
    )
    return {
        "proposed_action": proposed,
        "events": [
            make_event("risky_action", "completed", "proposed risky action", action=proposed)
        ],
    }


def approval_node(state: AgentState) -> dict:
    """Human-in-the-loop approval step.

    Default behavior: mock approval (approved=True) so tests and CI run offline.
    Extension: if env LANGGRAPH_INTERRUPT=true, use langgraph.types.interrupt() for real HITL.
    """
    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        proposed_action = state.get("proposed_action", "")
        decision = interrupt({
            "action": "approval_required",
            "proposed_action": proposed_action,
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

    status_str = "action approved" if approval_data["approved"] else "action rejected"
    return {
        "approval": approval_data,
        "events": [
            make_event(
                "approval",
                "completed",
                status_str,
                approved=approval_data["approved"],
            )
        ],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt.

    Increment the attempt counter and log the transient failure.
    """
    attempt = state.get("attempt", 0)
    new_attempt = attempt + 1
    err_msg = f"Attempt {new_attempt} failed: transient error occurred, retrying..."

    return {
        "attempt": new_attempt,
        "errors": [err_msg],
        "events": [
            make_event("retry", "completed", f"retry attempt {new_attempt}", attempt=new_attempt)
        ],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failures after max retries exceeded."""
    attempt = state.get("attempt", 0)
    query = state.get("query", "")
    msg = (
        f"We were unable to complete your request: '{query}' after {attempt} attempts. "
        "Your ticket has been escalated to Tier-2 technical support."
    )
    return {
        "final_answer": msg,
        "events": [
            make_event(
                "dead_letter",
                "completed",
                f"max retries ({attempt}) exceeded, escalated to dead letter",
            )
        ],
    }


def finalize_node(state: AgentState) -> dict:
    """Emit a final audit event. All routes must pass through here before END."""
    return {
        "events": [make_event("finalize", "completed", "workflow finished")],
    }

