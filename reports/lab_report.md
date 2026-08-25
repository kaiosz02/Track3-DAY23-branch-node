# Day 08 Lab Report — LangGraph Support-Ticket Agent

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
| Total scenarios | 7 |
| Successful | 7 |
| Failed | 0 |
| Success rate | 100.0% |
| Avg nodes visited | 14.9 |
| Total retries | 11 |
| Total interrupts | 4 |
| Crash-resume | MemorySaver used (no cross-process resume) |

**Per-scenario:**

| Scenario | Expected | Actual | Success | Retries | Interrupts | Approval | Nodes |
|---|---|---|---|---:|---:|:---:|---:|
| S01_simple | simple | simple | ✅ | 0 | 0 | - | 12 |
| S02_tool | tool | tool | ✅ | 0 | 0 | - | 13 |
| S03_missing | missing_info | missing_info | ✅ | 0 | 0 | - | 8 |
| S04_risky | risky | risky | ✅ | 3 | 2 | ✓ | 23 |
| S05_error | error | error | ✅ | 6 | 0 | - | 22 |
| S06_delete | risky | risky | ✅ | 0 | 2 | ✓ | 16 |
| S07_dead_letter | error | error | ✅ | 2 | 0 | - | 10 |

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
- **Thread ID**: Each scenario run uses `thread-{scenario_id}` as `thread_id`.
- **State history**: `graph.get_state_history(config)` returns all checkpoints per thread.
- **Crash resume**: Switch to `checkpointer: sqlite` in `configs/lab.yaml`, then:
  ```python
  graph.invoke(Command(resume=approval_decision), config={"configurable": {"thread_id": tid}})
  ```
- **SQLite WAL mode**: Enables concurrent reads during long-running HITL pauses.

---

## 7. Extension work

- **LLM-as-judge** in `evaluate_node`: LLM evaluates tool result quality beyond heuristics.
- **Real HITL**: `approval_node` uses `interrupt()` when `LANGGRAPH_INTERRUPT=true`.
- **Idempotency key** in `tool_node`: `{thread_id}:attempt-{n}` prevents duplicate side-effects.
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
