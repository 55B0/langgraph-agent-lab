"""Verify the evidence fixture, not the behavior of a future agent."""

from pathlib import Path

import pytest

from sensorassist.case_data import load_run


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.mark.parametrize("run_id", ["R-104", "R-105"])
def test_recorded_runs_agree_with_specification(run_id):
    run, config = load_run(DATA_DIR, run_id)
    observation = run["observation"]
    assert run["synthetic"] is True and config["synthetic"] is True
    assert run["run_id"] == run_id
    assert run["config_id"] == config["config_id"]
    assert run["sensor_id"] == config["sensor_id"]
    assert run["spec_id"] == config["spec_id"]
    assert (DATA_DIR / "specs" / f"{run['spec_id']}.md").is_file()
    assert 0 <= observation["signal"] <= 1
    assert 0 <= config["detection_threshold"] <= 1
    assert observation["actual_detection"] == (
        observation["signal"] >= config["detection_threshold"]
    )
    passed = observation["actual_detection"] == observation["expected_detection"]
    assert run["outcome"] == ("passed" if passed else "failed")


def test_comparison_isolates_threshold_change():
    before, before_config = load_run(DATA_DIR, "R-104")
    after, after_config = load_run(DATA_DIR, "R-105")
    for key in ("sensor_id", "firmware_version", "test_id", "spec_id"):
        assert before[key] == after[key]
    assert before["observation"]["signal"] == after["observation"]["signal"]
    assert before["observation"]["expected_detection"] is True
    assert after["observation"]["expected_detection"] is True
    assert before_config["detection_threshold"] == 0.4
    assert after_config["detection_threshold"] == 0.7
    assert before["outcome"] == "passed"
    assert after["outcome"] == "failed"
