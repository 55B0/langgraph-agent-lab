"""Verify guided routing, evidence requests, and restart without reloading files."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from langgraph.types import Command

from sensorassist.diagnosis import build_diagnosis


PROJECT = Path(__file__).resolve().parents[1]
CASE = PROJECT / "data" / "cases" / "controller-mismatch"
CONTROLLER = PROJECT / "examples" / "controller-config" / "CTRL-201.json"


def test_diagnosis_pauses_at_the_missing_controller_and_resumes_from_saved_evidence():
    from langgraph.checkpoint.memory import InMemorySaver

    saver = InMemorySaver()
    config = {"configurable": {"thread_id": "guided-test"}}
    graph = build_diagnosis(CASE, saver)
    paused = graph.invoke({"run_id": "R-207"}, config)
    assert paused["status"] == "awaiting_evidence"
    assert paused["__interrupt__"][0].value["config_id"] == "CTRL-201"
    assert len(paused["checks"]) == 4

    # Rebuild with an unavailable source directory. Earlier work must stay saved.
    rebuilt = build_diagnosis(Path("unavailable-source-directory"), saver)
    record = json.loads(CONTROLLER.read_text(encoding="utf-8"))
    result = rebuilt.invoke(Command(resume=record), config)
    assert result["status"] == "explained"
    assert result["evidence"] == paused["evidence"]
    assert result["checks"][:4] == paused["checks"]
    assert len(result["checks"]) == 6
    assert "different conventions" in result["next_check"]
    assert "CONTROLLER-CTRL-201" in result["checks"][-1]


@pytest.fixture
def case_copy(tmp_path):
    target = tmp_path / "case"
    shutil.copytree(CASE, target)
    return target


@pytest.mark.parametrize(("replacements", "expected_next"), [
    ({"signal=0.55 decision=OBJECT_PRESENT": "signal=0.20 decision=OBJECT_ABSENT"}, "sensor signal"),
    ({"digital_output_level=LOW": "digital_output_level=HIGH"}, "output configuration"),
    ({"input_level=LOW": "input_level=HIGH"}, "wiring and input assignment"),
])
def test_diagnosis_stops_at_the_first_failed_layer(case_copy, replacements, expected_next):
    log_path = case_copy / "logs" / "R-207.log"
    text = log_path.read_text(encoding="utf-8")
    for before, after in replacements.items():
        text = text.replace(before, after)
    log_path.write_text(text, encoding="utf-8")
    result = build_diagnosis(case_copy).invoke(
        {"run_id": "R-207"}, {"configurable": {"thread_id": "layer-test"}},
    )
    assert result["status"] == "needs_check"
    assert expected_next in result["next_check"]
    assert "__interrupt__" not in result


def test_diagnosis_rejects_a_contradictory_sensor_decision(case_copy):
    log_path = case_copy / "logs" / "R-207.log"
    log_path.write_text(
        log_path.read_text(encoding="utf-8").replace("signal=0.55", "signal=0.20"), encoding="utf-8",
    )
    result = build_diagnosis(case_copy).invoke(
        {"run_id": "R-207"}, {"configurable": {"thread_id": "contradiction"}},
    )
    assert result["status"] == "unresolved"
    assert "__interrupt__" not in result


def test_supplied_controller_config_can_contradict_the_log():
    graph = build_diagnosis(CASE)
    config = {"configurable": {"thread_id": "controller-contradiction"}}
    graph.invoke({"run_id": "R-207"}, config)
    record = json.loads(CONTROLLER.read_text(encoding="utf-8"))
    record["controller_active_level"] = "LOW"
    result = graph.invoke(Command(resume=record), config)
    assert result["status"] == "unresolved"
    assert "contradicts the recorded count" in result["next_check"]


def test_passing_case_with_controller_config_finishes_without_pause(case_copy):
    folder = case_copy / "controller-configs"
    folder.mkdir()
    shutil.copyfile(CONTROLLER, folder / "CTRL-201.json")
    result = build_diagnosis(case_copy).invoke(
        {"run_id": "R-206"}, {"configurable": {"thread_id": "passing-case"}},
    )
    assert result["status"] == "consistent"
    assert "__interrupt__" not in result


def test_guided_cli_validates_file_before_resuming_in_a_new_process(tmp_path):
    def run_cli(*args):
        return subprocess.run(
            [sys.executable, "-m", "sensorassist", *args],
            cwd=tmp_path, capture_output=True, text=True, timeout=20,
        )

    started = run_cli("--diagnose", "R-207", "--data-dir", str(CASE))
    assert started.returncode == 0, started.stderr
    assert "awaiting_evidence" in started.stdout
    thread_id = started.stdout.split("Diagnosis ID: ", 1)[1].splitlines()[0]

    wrong_file = tmp_path / "wrong-controller.json"
    wrong = json.loads(CONTROLLER.read_text(encoding="utf-8"))
    wrong["controller_id"] = "C-999"
    wrong_file.write_text(json.dumps(wrong), encoding="utf-8")
    invalid = run_cli("--resume-diagnosis", thread_id, "--controller-config", str(wrong_file))
    assert invalid.returncode == 1
    assert "not accepted" in invalid.stdout

    resumed = run_cli("--resume-diagnosis", thread_id, "--controller-config", str(CONTROLLER))
    assert resumed.returncode == 0, resumed.stderr
    assert "Status: explained" in resumed.stdout
    assert "Node: load_evidence" not in resumed.stdout
    assert "Node: check_sensor" not in resumed.stdout

    repeated = run_cli("--resume-diagnosis", thread_id, "--controller-config", str(CONTROLLER))
    assert repeated.returncode == 1
    assert "No pending evidence request" in repeated.stdout
