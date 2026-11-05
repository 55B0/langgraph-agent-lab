"""A rule-based investigation of the fictional single-object interface test.

Read build_diagnosis's nodes and edges to follow the investigation. Evidence is
loaded once, then saved in state. Only the missing controller record is supplied
on resume. The checks implement the two known fictional interface specifications.
"""

import json
import re
from operator import add
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from sensorassist.tools import build_tools


class DiagnosisState(TypedDict, total=False):
    run_id: str
    evidence: dict
    controller_config: dict | None
    # Keep earlier checks as later nodes append their own observations.
    checks: Annotated[list[str], add]
    status: Literal["running", "incomplete", "unresolved", "needs_check", "awaiting_evidence", "explained", "consistent"]
    next_check: str


def validate_controller_config(record: dict, run: dict) -> dict:
    """Accept only the controller and saved configuration requested by this run."""
    if not isinstance(record, dict):
        raise ValueError("Controller configuration must be a JSON object.")
    expected = {
        "synthetic": True,
        "controller_id": run["controller_id"],
        "config_id": run["controller_config_id"],
        "source_id": f"CONTROLLER-{run['controller_config_id']}",
    }
    if any(record.get(key) != value for key, value in expected.items()) or record.get("synthetic") is not True:
        raise ValueError("Controller configuration identity or synthetic label does not match the investigation.")
    if record.get("controller_active_level") not in ("HIGH", "LOW"):
        raise ValueError("controller_active_level must be HIGH or LOW.")
    return record


def read_source(data_dir: Path, relative_path: str) -> str:
    path = (data_dir / relative_path).resolve()
    if not path.is_relative_to(data_dir.resolve()):
        raise ValueError("Evidence must remain inside the configured data directory.")
    return path.read_text(encoding="utf-8")


def log_event(log: dict, pattern: str) -> dict:
    """Require one unambiguous event of each kind in this single-object test."""
    events = []
    for line in log["lines"]:
        match = re.fullmatch(pattern, line["text"])
        if match:
            events.append({**match.groupdict(), "line_number": line["line_number"]})
    if len(events) != 1:
        raise ValueError("This workflow requires exactly one matching event of each kind in the single-object test.")
    return events[0]


def build_diagnosis(data_dir: Path, checkpointer: BaseCheckpointSaver | None = None):
    tools = build_tools(data_dir)

    def load_evidence(state: DiagnosisState) -> dict:
        """Read source artifacts and freeze the evidence before any human pause."""
        try:
            result = tools["read_test_run"].invoke({"run_id": state["run_id"]})
        except (OSError, ValueError, KeyError, TypeError) as error:
            return {"status": "unresolved", "next_check": f"Check the run record: {error}"}
        if result["status"] != "found":
            return {"status": "incomplete", "next_check": str(result)}
        run = result["run"]
        try:
            if (
                run.get("test_id") != "controller-object-count"
                or not re.fullmatch(r"CFG-[0-9]+", run.get("config_id", ""))
                or not re.fullmatch(r"CTRL-[0-9]+", run.get("controller_config_id", ""))
            ):
                raise ValueError("Use a controller-object-count run with sensor and controller configuration references.")
            config = json.loads(read_source(data_dir, f"configs/{run['config_id']}.json"))
            if not isinstance(config, dict):
                raise ValueError("Sensor configuration must be a JSON object.")
            if (
                config.get("config_id") != run["config_id"]
                or config.get("source_id") != f"CONFIG-{run['config_id']}"
                or config.get("sensor_id") != run["sensor_id"]
                or config.get("controller_id") != run["controller_id"]
                or config.get("synthetic") is not True
            ):
                raise ValueError("Sensor configuration identity does not match the run.")
            threshold = config.get("detection_threshold")
            if type(threshold) not in (float, int) or not 0 <= threshold <= 1:
                raise ValueError("The sensor threshold must be a number between 0 and 1.")
            if config.get("sensor_output_polarity") not in ("active_high", "active_low"):
                raise ValueError("Unknown sensor output polarity.")
            observation = run["observation"]
            if not isinstance(observation, dict):
                raise ValueError("Run observation must be a JSON object.")
            count = observation.get("actual_object_count")
            if (
                type(observation.get("expected_object_count")) is not int
                or observation["expected_object_count"] != 1
                or type(count) is not int or count not in (0, 1)
                or run["outcome"] != ("passed" if count == 1 else "failed")
            ):
                raise ValueError("Run summary is inconsistent with a single-object count test.")
            log = tools["read_event_log"].invoke({"run_id": state["run_id"], "max_lines": 500})
            if log["status"] != "found":
                return {"status": "incomplete", "next_check": str(log)}
            if log["has_more"]:
                raise ValueError("This workflow supports single-object logs of at most 500 lines.")
            sensor = log_event(log, r"(?P<time>[0-9]+) INFO sensor signal=(?P<signal>[0-9.]+) decision=(?P<decision>OBJECT_PRESENT|OBJECT_ABSENT)")
            output = log_event(log, r"(?P<time>[0-9]+) INFO io digital_output_level=(?P<level>HIGH|LOW)")
            controller = log_event(log, r"(?P<time>[0-9]+) INFO controller input_level=(?P<level>HIGH|LOW) object_count=(?P<count>[0-9]+)")
            summary = log_event(log, r"(?P<time>[0-9]+) INFO test expected_object_count=(?P<expected>[0-9]+) actual_object_count=(?P<actual>[0-9]+) result=(?P<result>PASS|FAIL)")
            if (
                not int(sensor["time"]) <= int(output["time"]) <= int(controller["time"])
                or int(controller["time"]) - int(sensor["time"]) != 3
                or int(controller["count"]) != count
                or int(summary["time"]) < int(controller["time"])
                or int(summary["expected"]) != 1
                or int(summary["actual"]) != count
                or summary["result"] != ("PASS" if count == 1 else "FAIL")
                or not 0 <= float(sensor["signal"]) <= 1
            ):
                raise ValueError("Event timing, signal, or controller count contradicts the single-object test.")
            specs = {}
            for spec_id in ("SPEC-OUTPUT-V1", "SPEC-CONTROLLER-V1"):
                specs[spec_id] = read_source(data_dir, f"specs/{spec_id}.md")
                if f"Source ID: {spec_id}" not in specs[spec_id]:
                    raise ValueError("Specification source identity is inconsistent.")
            try:
                controller_config = json.loads(read_source(
                    data_dir, f"controller-configs/{run['controller_config_id']}.json",
                ))
            except FileNotFoundError:
                controller_config = None
            if controller_config is not None:
                validate_controller_config(controller_config, run)
        except FileNotFoundError as error:
            return {"status": "incomplete", "next_check": f"Supply the missing evidence file: {error.filename}"}
        except (OSError, ValueError, KeyError, TypeError) as error:
            return {"status": "unresolved", "next_check": f"Check the evidence: {error}"}
        return {
            "evidence": {"run": run, "config": config, "log": log, "sensor": sensor,
                         "output": output, "controller": controller, "specs": specs},
            "controller_config": controller_config, "status": "running",
            "checks": [f"Loaded run, sensor configuration, log, and two interface specifications. [{run['source_id']}]"],
        }

    def check_sensor(state: DiagnosisState) -> dict:
        evidence = state["evidence"]
        sensor = evidence["sensor"]
        detected = sensor["decision"] == "OBJECT_PRESENT"
        predicted = float(sensor["signal"]) >= evidence["config"]["detection_threshold"]
        check = f"Sensor decision: {sensor['decision']}. [{evidence['log']['source_id']}:{sensor['line_number']}]"
        if detected != predicted:
            return {"checks": [check], "status": "unresolved",
                    "next_check": "The sensor decision contradicts its configured sensing rule. Reconcile those records."}
        if not detected:
            return {"checks": [check], "status": "needs_check",
                    "next_check": "Investigate the sensor signal and sensing settings before checking the controller."}
        return {"checks": [check]}

    def check_output(state: DiagnosisState) -> dict:
        evidence = state["evidence"]
        output = evidence["output"]
        expected = "HIGH" if evidence["config"]["sensor_output_polarity"] == "active_high" else "LOW"
        check = f"Sensor output: {output['level']}; expected {expected} for its polarity. [{evidence['log']['source_id']}:{output['line_number']}, {evidence['config']['source_id']}, SPEC-OUTPUT-V1]"
        if output["level"] != expected:
            return {"checks": [check], "status": "needs_check",
                    "next_check": "Investigate the sensor output configuration and output stage."}
        return {"checks": [check]}

    def check_connection(state: DiagnosisState) -> dict:
        evidence = state["evidence"]
        controller = evidence["controller"]
        check = f"Controller input: {controller['level']}. [{evidence['log']['source_id']}:{controller['line_number']}]"
        if controller["level"] != evidence["output"]["level"]:
            return {"checks": [check], "status": "needs_check",
                    "next_check": "Sensor output and controller input differ. Check wiring and input assignment."}
        if state.get("controller_config") is None:
            return {"checks": [check], "status": "awaiting_evidence",
                    "next_check": f"Supply controller configuration {evidence['run']['controller_config_id']}."}
        return {"checks": [check]}

    def request_controller(state: DiagnosisState) -> dict:
        # This node restarts on resume. It has no file writes before interrupt.
        record = interrupt({
            "kind": "controller_configuration",
            "message": state["next_check"],
            "controller_id": state["evidence"]["run"]["controller_id"],
            "config_id": state["evidence"]["run"]["controller_config_id"],
        })
        record = validate_controller_config(record, state["evidence"]["run"])
        return {"controller_config": record, "status": "running",
                "checks": [f"Accepted controller configuration. [{record['source_id']}]"]}

    def check_interpretation(state: DiagnosisState) -> dict:
        evidence, record = state["evidence"], state["controller_config"]
        controller = evidence["controller"]
        count_expected = int(controller["level"] == record["controller_active_level"])
        check = f"Controller active level: {record['controller_active_level']}; sampled {controller['level']}. [{record['source_id']}, {evidence['log']['source_id']}:{controller['line_number']}, SPEC-CONTROLLER-V1]"
        if count_expected != int(controller["count"]):
            return {"checks": [check], "status": "unresolved",
                    "next_check": "The supplied controller configuration contradicts the recorded count. Verify which configuration was used."}
        if count_expected == 0:
            return {"checks": [check], "status": "explained",
                    "next_check": "The sensor output and controller active level use different conventions. Confirm the intended HIGH/LOW convention with the configuration owner."}
        return {"checks": [check], "status": "consistent",
                "next_check": "The sensor decision, output, controller input, and object count agree."}

    def continue_check(state: DiagnosisState) -> str:
        return "continue" if state["status"] == "running" else "end"

    def after_connection(state: DiagnosisState) -> str:
        return {"running": "interpret", "awaiting_evidence": "request"}.get(state["status"], "end")

    builder = StateGraph(DiagnosisState)
    builder.add_node("load_evidence", load_evidence)
    builder.add_node("check_sensor", check_sensor)
    builder.add_node("check_output", check_output)
    builder.add_node("check_connection", check_connection)
    builder.add_node("request_controller", request_controller)
    builder.add_node("check_interpretation", check_interpretation)
    builder.add_edge(START, "load_evidence")
    builder.add_conditional_edges("load_evidence", continue_check, {"continue": "check_sensor", "end": END})
    builder.add_conditional_edges("check_sensor", continue_check, {"continue": "check_output", "end": END})
    builder.add_conditional_edges("check_output", continue_check, {"continue": "check_connection", "end": END})
    builder.add_conditional_edges("check_connection", after_connection, {
        "interpret": "check_interpretation", "request": "request_controller", "end": END,
    })
    builder.add_edge("request_controller", "check_interpretation")
    builder.add_edge("check_interpretation", END)
    return builder.compile(checkpointer=checkpointer if checkpointer is not None else InMemorySaver())
