"""CLI for the lab."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml

from .graph import build_graph
from .metrics import MetricsReport, metric_from_state, summarize_metrics, write_metrics
from .persistence import build_checkpointer
from .report import write_report
from .scenarios import load_scenarios
from .state import initial_state

app = typer.Typer(no_args_is_help=True)


@app.command("run-scenarios")
def run_scenarios(
    config: Annotated[Path, typer.Option("--config")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Run all grading scenarios and write metrics JSON."""
    import os
    from dotenv import load_dotenv
    load_dotenv()  # ensure .env is loaded before reading DATABASE_URL

    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    scenarios = load_scenarios(cfg["scenarios_path"])

    # database_url: yaml takes precedence, fallback to OS env var (set in .env)
    db_url = cfg.get("database_url") or os.getenv("DATABASE_URL")
    checkpointer_kind = cfg.get("checkpointer", os.getenv("CHECKPOINTER", "memory"))
    checkpointer = build_checkpointer(checkpointer_kind, db_url)
    graph = build_graph(checkpointer=checkpointer)
    metrics = []
    for scenario in scenarios:
        state = initial_state(scenario)
        run_config = {"configurable": {"thread_id": state["thread_id"]}}
        final_state = graph.invoke(state, config=run_config)
        m = metric_from_state(
            final_state, scenario.expected_route.value, scenario.requires_approval
        )
        metrics.append(m)
    report = summarize_metrics(metrics)
    write_metrics(report, output)
    if cfg.get("report_path"):
        write_report(report, cfg["report_path"])
    typer.echo(f"Wrote metrics to {output}")


@app.command("validate-metrics")
def validate_metrics(metrics: Annotated[Path, typer.Option("--metrics")]) -> None:
    """Validate metrics JSON schema for grading."""
    payload = json.loads(metrics.read_text(encoding="utf-8"))
    report = MetricsReport.model_validate(payload)
    if report.total_scenarios < 6:
        raise typer.BadParameter("Expected at least 6 scenarios")
    typer.echo(f"Metrics valid. success_rate={report.success_rate:.2%}")


@app.command("serve")
def serve(
    host: Annotated[str, typer.Option("--host", help="Host IP to bind")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="Port to listen on")] = 8000,
    reload: Annotated[bool, typer.Option("--reload", help="Enable hot reload")] = False,
) -> None:
    """Start the interactive demo web server."""
    import uvicorn
    typer.echo(f"Starting LangGraph Agent Lab Interactive Demo at http://{host}:{port}/")
    uvicorn.run("langgraph_agent_lab.server:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()

