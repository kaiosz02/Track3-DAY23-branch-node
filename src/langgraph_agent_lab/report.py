"""Report generation helper.

Renders a complete Markdown lab report from MetricsReport data,
following the structure in reports/lab_report_template.md.
"""

from __future__ import annotations

from pathlib import Path

from .metrics import MetricsReport


def render_report(metrics: MetricsReport) -> str:
    """Render a complete lab report from metrics data.

    Generates a report that includes:
    1. Metrics summary table (total scenarios, success rate, retries, interrupts)
    2. Per-scenario results table
    3. Architecture explanation
    4. Failure analysis (two failure modes)
    5. Improvement plan
    """
    total = metrics.total_scenarios
    success_count = round(metrics.success_rate * total)
    failed_count = total - success_count

    # ── Per-scenario rows ──────────────────────────────────────────────
    scenario_rows = []
    for s in metrics.scenario_metrics:
        status = "✅" if s.success else "❌"
        approval_flag = "✓" if s.approval_observed else "-"
        scenario_rows.append(
            f"| {s.scenario_id} "
            f"| {s.expected_route} "
            f"| {s.actual_route or 'N/A'} "
            f"| {status} "
            f"| {s.retry_count} "
            f"| {s.interrupt_count} "
            f"| {approval_flag} "
            f"| {s.nodes_visited} |"
        )
    scenario_table = "\n".join(scenario_rows)

    resume_evidence = (
        "✅ Crash-resume verified"
        if metrics.resume_success
        else "MemorySaver used (no cross-process resume)"
    )

    report = f"""# Day 08 Lab Report — LangGraph Support-Ticket Agent

## 1. Team / student

- Name: (fill in)
- Repo/commit: (fill in)
- Date: (fill in)

---

## 2. Architecture

The graph is a **StateGraph** with 11 nodes and 4 conditional routing functions.

```
START → intake → classify → [route_after_classify]
  simple       → answer → finalize → END
  tool         → tool → evaluate → [route_after_evaluate]
                           success    → answer → finalize → END
                           needs_retry → retry → [route_after_retry]
                                          attempt < max → tool (loop)
                                          exhausted     → dead_letter → finalize → END
  missing_info → clarify → finalize → END
  risky        → risky_action → approval → [route_after_approval]
                                 approved → tool → evaluate → ...
                                 rejected → clarify → finalize → END
  error        → retry → [route_after_retry] → ...
```

**Key design decisions:**

- `intake_node` normalizes raw input before any LLM call.
- `classify_node` uses `llm.with_structured_output(ClassificationResult)`.
- A deterministic `RISKY_KEYWORDS` safety net overrides LLM to protect HITL.
- `tool_node` wraps execution in try/except and stores exceptions in `tool_error`.
  Graph never crashes before `finalize_node`.
- `evaluate_node` checks `tool_error` first, then heuristic, then LLM-as-judge.
- Bounded retry: `route_after_retry` checks `attempt < max_attempts` before looping.
- `approval_node` supports real HITL via `interrupt()` when `LANGGRAPH_INTERRUPT=true`.
- All execution paths terminate at `finalize → END`.

---

## 3. State schema

| Field | Reducer | Why |
|---|---|---|
| `thread_id` | overwrite | unique per scenario run |
| `query` | overwrite | normalized input |
| `route` | overwrite | current classification |
| `risk_level` | overwrite | high/low for risky route |
| `attempt` | overwrite | retry counter |
| `max_attempts` | overwrite | retry upper bound |
| `evaluation_result` | overwrite | success / needs_retry |
| `final_answer` | overwrite | response to user |
| `pending_question` | overwrite | clarification text |
| `proposed_action` | overwrite | risky action description |
| `approval` | overwrite | HITL decision dict |
| `tool_error` | overwrite | last tool exception (None = ok) |
| `messages` | append (`add`) | conversation audit |
| `tool_results` | append (`add`) | all tool outputs |
| `errors` | append (`add`) | all error messages |
| `events` | append (`add`) | full audit trail |

---

## 4. Scenario results

**Summary:**

| Metric | Value |
|---|---|
| Total scenarios | {total} |
| Successful | {success_count} |
| Failed | {failed_count} |
| Success rate | {metrics.success_rate:.1%} |
| Avg nodes visited | {metrics.avg_nodes_visited:.1f} |
| Total retries | {metrics.total_retries} |
| Total interrupts | {metrics.total_interrupts} |
| Crash-resume | {resume_evidence} |

**Per-scenario:**

| Scenario | Expected | Actual | Success | Retries | Interrupts | Approval | Nodes |
|---|---|---|---|---:|---:|:---:|---:|
{scenario_table}

---

## 5. Failure analysis

### Failure mode 1 — Tool exception crashes graph before finalize

**Problem:** If `tool_node` raises an unhandled exception the graph exits immediately,
skipping `finalize_node` and losing the audit trail. The scenario metric has no `final_answer`.

**Solution implemented:** All tool calls are wrapped in `try/except`. Exceptions are stored
in `tool_error` and returned as state update. `evaluate_node` reads `tool_error` first
and routes to `retry`. Dead letter fires after `max_attempts`, ensuring `finalize` is reached.

### Failure mode 2 — Risky action bypasses HITL approval

**Problem:** LLM classifier may return `route = "tool"` for a query like
"Refund this customer" that is actually risky, silently skipping the approval gate.

**Solution implemented:** A deterministic `RISKY_KEYWORDS` set in `nodes.py` overrides the
LLM result after classification. Any query containing `refund`, `delete`, `cancel`, etc.
is forced to `route = "risky"` regardless of LLM output. This is a defense-in-depth layer;
the LLM prompt also enforces the priority `risky > tool > missing_info > error > simple`.

---

## 6. Persistence / recovery evidence

- **Checkpointer**: `MemorySaver` by default (configured in `configs/lab.yaml`).
- **Thread ID**: Each scenario run uses `thread-{{scenario_id}}` as `thread_id`.
- **State history**: `graph.get_state_history(config)` returns all checkpoints per thread.
- **Crash resume**: Switch to `checkpointer: sqlite` in `configs/lab.yaml`, then:
  ```python
  graph.invoke(Command(resume=approval_decision), config={{"configurable": {{"thread_id": tid}}}})
  ```
- **SQLite WAL mode**: Enables concurrent reads during long-running HITL pauses.

---

## 7. Extension work

- **LLM-as-judge** in `evaluate_node`: LLM evaluates tool result quality beyond heuristics.
- **Real HITL**: `approval_node` uses `interrupt()` when `LANGGRAPH_INTERRUPT=true`.
- **Idempotency key** in `tool_node`: `{{thread_id}}:attempt-{{n}}` prevents duplicate side-effects.
- **SQLite persistence**: `build_checkpointer("sqlite")` in `persistence.py` with WAL mode.
- **Graph diagram**: Run `graph.get_graph().draw_mermaid()` to get Mermaid topology.

---

## 8. Improvement plan

If given one more day, priority productionization steps:

1. **Idempotent tool backend**: Persist `idempotency_key` in a real DB so retried refunds/emails
   never duplicate even across process restarts.
2. **Structured tool dispatch**: `classify_node` should also extract `tool_name` + `tool_args`
   so `error → retry → tool` has concrete arguments rather than re-guessing from query.
3. **Streaming metrics**: Push events to a time-series store (e.g. Langfuse) in `finalize_node`
   for live dashboards instead of batch JSON.
4. **Multi-turn clarification**: After `clarify → END`, resume on the same `thread_id` with
   the user's follow-up, preserving full conversation history via checkpointer.
5. **Parallel fan-out**: Use LangGraph `Send()` to run multiple tools concurrently when a
   single query requires cross-system lookups (order + account + shipping).
"""
    return report


def write_report(metrics: MetricsReport, output_path: str | Path) -> None:
    """Write the rendered report to a file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(metrics), encoding="utf-8")
