"""Section 2: an explicit, deterministic LangGraph investigation."""

from functools import partial
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from sensorassist.case_data import load_run


class InvestigationState(TypedDict, total=False):
    before_run_id: str
    after_run_id: str
    evidence: dict
    findings: list[str]
    status: Literal["explained", "unresolved"]
    report: str


def load_case(state: InvestigationState, *, data_dir: Path) -> dict:
    """Add raw evidence while leaving the request fields in state."""
    before_run, before_config = load_run(data_dir, state["before_run_id"])
    after_run, after_config = load_run(data_dir, state["after_run_id"])
    records = (before_run, before_config, after_run, after_config)
    if any(record["spec_id"] != "SPEC-DETECTION-V1" for record in records):
        raise ValueError("Section 2 implements only the fictional SPEC-DETECTION-V1 rule.")
    spec_path = data_dir / "specs" / "SPEC-DETECTION-V1.md"
    return {
        "evidence": {
            "before": {"run": before_run, "config": before_config},
            "after": {"run": after_run, "config": after_config},
            "spec_id": "SPEC-DETECTION-V1",
            "specification": spec_path.read_text(encoding="utf-8"),
        }
    }


def assess_case(state: InvestigationState) -> dict:
    """Apply the known fixture rule and avoid explaining contradictory data."""
    evidence = state["evidence"]
    before, after = evidence["before"], evidence["after"]
    findings = []
    rule_matches = []
    for item in (before, after):
        run, config = item["run"], item["config"]
        observation = run["observation"]
        predicted = observation["signal"] >= config["detection_threshold"]
        rule_matches.append(predicted == observation["actual_detection"])
        findings.append(
            f"{run['run_id']}: {observation['signal']} >= "
            f"{config['detection_threshold']} -> {predicted}; "
            f"recorded detection {observation['actual_detection']}, "
            f"expected {observation['expected_detection']}. "
            f"[{run['source_id']}, {config['source_id']}, {evidence['spec_id']}]"
        )
    before_run, after_run = before["run"], after["run"]
    same_context = all(
        before_run[key] == after_run[key]
        for key in ("sensor_id", "firmware_version", "test_id")
    ) and all(
        before_run["observation"][key] == after_run["observation"][key]
        for key in ("signal", "expected_detection")
    )
    thresholds_differ = (
        before["config"]["detection_threshold"] != after["config"]["detection_threshold"]
    )
    detection_changed = (
        before_run["observation"]["actual_detection"]
        != after_run["observation"]["actual_detection"]
    )
    explained = all(rule_matches) and same_context and thresholds_differ and detection_changed
    if explained:
        findings.append("The threshold change explains the recorded detection change under the fictional rule.")
    else:
        findings.append("These records do not isolate a threshold-driven detection change.")
        if not all(rule_matches):
            findings.append("At least one recorded detection contradicts the fictional specification.")
        if not same_context:
            findings.append("Other recorded test conditions also differ.")
    return {"findings": findings, "status": "explained" if explained else "unresolved"}


def report(state: InvestigationState) -> dict:
    """Format findings already present in state; perform no new lookups."""
    next_check = (
        "Confirm whether the threshold change was intentional before changing configuration or test expectations."
        if state["status"] == "explained"
        else "Reconcile the recorded evidence before concluding a cause."
    )
    return {
        "report": "\n".join(
            [f"Status: {state['status']}"]
            + [f"- {finding}" for finding in state["findings"]]
            + [f"Next check: {next_check}"]
        )
    }


def build_graph(data_dir: Path) -> CompiledStateGraph:
    """Wire the three visible nodes with fixed edges, then compile."""
    builder = StateGraph(InvestigationState)
    builder.add_node("load_case", partial(load_case, data_dir=data_dir))
    builder.add_node("assess_case", assess_case)
    builder.add_node("report", report)
    builder.add_edge(START, "load_case")
    builder.add_edge("load_case", "assess_case")
    builder.add_edge("assess_case", "report")
    builder.add_edge("report", END)
    return builder.compile()
