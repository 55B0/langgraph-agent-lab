"""Sections 2-3: investigate through evidence state and a conditional edge.

This is the --graph mode. Its nodes follow fixed assessment rules. The newer
--simulate mode uses agent.py and message history instead; keeping both makes
the progression from a simple workflow to a model/tool loop visible.
"""

from functools import partial
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from sensorassist.case_data import load_run


class InvestigationState(TypedDict, total=False):
    """The request starts with two IDs; nodes add the remaining fields."""

    # Request: which recorded runs should be compared?
    before_run_id: str
    after_run_id: str
    # Loaded facts and missing-file paths are kept separately so the router
    # can choose a path without opening files or inspecting report text.
    evidence: dict
    missing_evidence: list[str]
    # Assessment and final output. These fields are added later in the run.
    findings: list[str]
    status: Literal["explained", "unresolved", "incomplete"]
    report: str


def load_case(state: InvestigationState, *, data_dir: Path) -> dict:
    """Collect available evidence and record missing files for the router."""
    evidence = {"spec_id": "SPEC-DETECTION-V1"}
    missing = []
    for side, id_field in (("before", "before_run_id"), ("after", "after_run_id")):
        try:
            run, config = load_run(data_dir, state[id_field])
        except FileNotFoundError as error:
            # A missing file is an expected incomplete-evidence outcome.
            # Malformed JSON and other programming/data errors still surface.
            missing.append(Path(error.filename).resolve().relative_to(data_dir.resolve()).as_posix())
            continue
        # The assessment below implements this known specification in code.
        # Loading Markdown does not mean an LLM is interpreting its contents.
        if any(record["spec_id"] != "SPEC-DETECTION-V1" for record in (run, config)):
            raise ValueError("This workflow implements only the fictional SPEC-DETECTION-V1 rule.")
        evidence[side] = {"run": run, "config": config}
    spec_path = data_dir / "specs" / "SPEC-DETECTION-V1.md"
    try:
        evidence["specification"] = spec_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        missing.append("specs/SPEC-DETECTION-V1.md")
    # Return a state UPDATE. The original request IDs remain in shared state.
    return {"evidence": evidence, "missing_evidence": missing}


def route_after_load(state: InvestigationState) -> Literal["assess_case", "missing_data"]:
    """Choose the next node from the evidence availability recorded in state."""
    # Our code chooses the next node's name; LangGraph follows that connection.
    return "missing_data" if state["missing_evidence"] else "assess_case"


def missing_data(state: InvestigationState) -> dict:
    """Finish an incomplete investigation without attempting a diagnosis."""
    # This branch writes its own report and goes directly to END. It does not
    # execute assess_case or the normal report node, or pause for human input.
    missing_lines = [f"- Missing: {path}" for path in state["missing_evidence"]]
    return {
        "status": "incomplete",
        "findings": [],
        "report": "\n".join(
            ["Status: incomplete"]
            + missing_lines
            + ["Next check: verify the requested run IDs and provide the missing evidence files."]
        ),
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
    # Isolate the threshold change before attributing changed detection to it.
    # If the input signal, firmware, or other recorded conditions also changed,
    # this simple comparison is insufficient for that explanation.
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
    # "explained" describes the recorded behavior. It does not establish whether
    # the configuration change was intended or approve any fix.
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
    """Route to assessment or missing-data handling after evidence loading."""
    # The schema declares the shared state. With no custom reducers, an update
    # replaces the named field and leaves fields omitted from the update intact.
    builder = StateGraph(InvestigationState)
    # Bind the source directory as application configuration, outside the state.
    builder.add_node("load_case", partial(load_case, data_dir=data_dir))
    builder.add_node("assess_case", assess_case)
    builder.add_node("report", report)
    builder.add_node("missing_data", missing_data)
    builder.add_edge(START, "load_case")
    # Replace a fixed load_case -> assess_case edge with one exclusive choice.
    # Keeping a fixed edge here as well would cause it to execute too.
    builder.add_conditional_edges(
        "load_case",
        route_after_load,
        {"assess_case": "assess_case", "missing_data": "missing_data"},
    )
    builder.add_edge("assess_case", "report")
    builder.add_edge("report", END)
    builder.add_edge("missing_data", END)
    # Prepare the executable workflow; invoke/stream will actually run it.
    return builder.compile()
