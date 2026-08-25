"""Unit tests for individual nodes in nodes.py."""

from unittest.mock import MagicMock, patch

from langgraph_agent_lab.nodes import (
    ClassificationResult,
    answer_node,
    approval_node,
    ask_clarification_node,
    classify_node,
    dead_letter_node,
    evaluate_node,
    finalize_node,
    intake_node,
    retry_or_fallback_node,
    risky_action_node,
    tool_node,
)
from langgraph_agent_lab.state import AgentState, Route, Scenario, initial_state


def test_intake_node() -> None:
    scenario = Scenario(id="test1", query="  How do I reset password?  ", expected_route=Route.SIMPLE)
    state = initial_state(scenario)
    result = intake_node(state)
    assert result["query"] == "How do I reset password?"
    assert len(result["events"]) == 1
    assert result["events"][0]["node"] == "intake"


def test_tool_node_error_simulation() -> None:
    state: AgentState = {
        "scenario_id": "test_err",
        "query": "Timeout error",
        "route": "error",
        "attempt": 0,
        "max_attempts": 3,
        "messages": [],
        "tool_results": [],
        "errors": [],
        "events": [],
    }
    result = tool_node(state)
    assert "ERROR" in result["tool_results"][0]
    assert len(result["events"]) == 1
    assert result["events"][0]["node"] == "tool"


def test_tool_node_success_after_retries() -> None:
    state: AgentState = {
        "scenario_id": "test_err",
        "query": "Timeout error",
        "route": "error",
        "attempt": 2,
        "max_attempts": 3,
        "messages": [],
        "tool_results": [],
        "errors": [],
        "events": [],
    }
    result = tool_node(state)
    assert "SUCCESS" in result["tool_results"][0]


def test_evaluate_node_needs_retry() -> None:
    state: AgentState = {
        "query": "Timeout error",
        "tool_results": ["ERROR: Service timeout occurred"],
        "events": [],
    }
    result = evaluate_node(state)
    assert result["evaluation_result"] == "needs_retry"
    assert result["events"][0]["node"] == "evaluate"


def test_evaluate_node_success() -> None:
    state: AgentState = {
        "query": "Order 123",
        "tool_results": ["SUCCESS: Order 123 is delivered"],
        "events": [],
    }
    result = evaluate_node(state)
    assert result["evaluation_result"] == "success"


def test_ask_clarification_node() -> None:
    state: AgentState = {
        "query": "Can you fix it?",
        "events": [],
    }
    result = ask_clarification_node(state)
    assert "pending_question" in result
    assert "Can you fix it?" in result["pending_question"]
    assert result["events"][0]["node"] == "clarify"


def test_risky_action_node() -> None:
    state: AgentState = {
        "query": "Refund customer 100$",
        "events": [],
    }
    result = risky_action_node(state)
    assert "proposed_action" in result
    assert "Refund customer 100$" in result["proposed_action"]
    assert result["events"][0]["node"] == "risky_action"


def test_approval_node_default() -> None:
    state: AgentState = {
        "query": "Delete account",
        "proposed_action": "Delete account",
        "events": [],
    }
    result = approval_node(state)
    assert result["approval"]["approved"] is True
    assert result["events"][0]["node"] == "approval"


def test_retry_or_fallback_node() -> None:
    state: AgentState = {
        "attempt": 1,
        "errors": [],
        "events": [],
    }
    result = retry_or_fallback_node(state)
    assert result["attempt"] == 2
    assert len(result["errors"]) == 1
    assert result["events"][0]["node"] == "retry"


def test_dead_letter_node() -> None:
    state: AgentState = {
        "query": "System crash",
        "attempt": 3,
        "events": [],
    }
    result = dead_letter_node(state)
    assert "final_answer" in result
    assert "escalated" in result["final_answer"].lower()
    assert result["events"][0]["node"] == "dead_letter"


def test_finalize_node() -> None:
    state: AgentState = {
        "events": [],
    }
    result = finalize_node(state)
    assert len(result["events"]) == 1
    assert result["events"][0]["node"] == "finalize"


def test_classify_node_with_mock_llm() -> None:
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.invoke.return_value = ClassificationResult(
        route="simple", risk_level="low", reasoning="password reset is simple"
    )
    mock_llm.with_structured_output.return_value = mock_structured

    with patch("langgraph_agent_lab.nodes.get_llm", return_value=mock_llm):
        state: AgentState = {"query": "How do I reset my password?", "events": []}
        result = classify_node(state)
        assert result["route"] == "simple"
        assert result["risk_level"] == "low"
        assert result["events"][0]["node"] == "classify"


def test_answer_node_with_mock_llm() -> None:
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "Here are the instructions to reset your password."
    mock_llm.invoke.return_value = mock_response

    with patch("langgraph_agent_lab.nodes.get_llm", return_value=mock_llm):
        state: AgentState = {
            "query": "How do I reset my password?",
            "tool_results": [],
            "approval": None,
            "events": [],
        }
        result = answer_node(state)
        assert "instructions" in result["final_answer"]
        assert result["events"][0]["node"] == "answer"


