"""Run a small, offline scorecard against the existing learning workflows."""

from pathlib import Path

from langchain_core.messages import HumanMessage

from sensorassist.agent import build_agent
from sensorassist.graph import build_graph
from sensorassist.simulation import ScriptedModel


def run_scorecard(data_dir: Path) -> int:
    baseline = build_graph(data_dir)
    rows = []
    for after_id, case in (("R-105", "Threshold change"), ("R-999", "Missing run")):
        fixed = baseline.invoke({"before_run_id": "R-104", "after_run_id": after_id})
        loop = build_agent(data_dir, ScriptedModel(after_run_id=after_id), human_review=True)
        config = {"configurable": {"thread_id": after_id}}
        result = loop.invoke(
            {"messages": [HumanMessage(content=f"Compare runs R-104 and {after_id}.")]}, config,
        )
        report = result["report"]
        # Score each workflow against its own intended result. An explanation
        # from the fixed rule and a completed evidence report mean different things.
        if after_id == "R-105":
            config_ids = {"CONFIG-CFG-104", "CONFIG-CFG-105"}
            fixed_pass = (
                fixed["status"] == "explained"
                and fixed["evidence"]["before"]["config"]["detection_threshold"] == 0.4
                and fixed["evidence"]["after"]["config"]["detection_threshold"] == 0.7
                and all(source in fixed["report"] for source in config_ids)
            )
            loop_pass = report["status"] == "completed" and any(
                finding.get("configuration_field") == "detection_threshold"
                and "0.4 -> 0.7" in finding["text"]
                and set(finding["evidence"]) == config_ids
                for finding in report["findings"]
            )
        else:
            missing = "runs/R-999.json"
            fixed_pass = fixed["status"] == "incomplete" and missing in fixed["missing_evidence"]
            loop_pass = (
                report["status"] == "incomplete"
                and missing in report["missing_information"]
                and not result.get("__interrupt__")
            )
        rows.extend([
            (case, "Fixed workflow", fixed["status"], fixed_pass),
            (case, "Scripted loop", report["status"], loop_pass),
        ])

    # Only the loop has a tool budget. A stopped run should keep its first result.
    limited = build_agent(data_dir, ScriptedModel(), max_tool_calls=1).invoke(
        {"messages": [HumanMessage(content="Compare runs R-104 and R-105.")]}
    )
    report = limited["report"]
    rows.append(("One-call limit", "Scripted loop", report["status"], (
        report["status"] == "stopped"
        and limited.get("stop_reason") == "tool_call_limit"
        and limited.get("tool_calls_used") == 1
        and report["evidence"] == ["RUN-R-104"]
    )))

    print("SensorAssist | Section 8: offline scorecard")
    for case, workflow, status, passed in rows:
        print(f"{'PASS' if passed else 'FAIL'} | {case} | {workflow} | {status}")
    passed_count = sum(passed for _, _, _, passed in rows)
    print(f"{passed_count}/{len(rows)} checks passed.")
    return int(passed_count != len(rows))
