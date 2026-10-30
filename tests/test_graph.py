"""Exercise the compiled graph and changes in its evidence."""

import json
import shutil
from pathlib import Path

from sensorassist.graph import build_graph


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REQUEST = {"before_run_id": "R-104", "after_run_id": "R-105"}


def test_graph_explains_case_and_keeps_input_state():
    result = build_graph(DATA_DIR).invoke(REQUEST)
    assert result["status"] == "explained"
    assert result["before_run_id"] == "R-104"
    assert result["after_run_id"] == "R-105"
    assert result["evidence"]["after"]["config"]["detection_threshold"] == 0.7
    for source_id in ("RUN-R-104", "RUN-R-105", "CONFIG-CFG-104", "CONFIG-CFG-105", "SPEC-DETECTION-V1"):
        assert source_id in result["report"]
    assert "intentional" in result["report"]


def test_stream_exposes_real_node_updates_and_accumulated_state():
    parts = list(build_graph(DATA_DIR).stream(REQUEST, stream_mode=["updates", "values"], version="v2"))
    updates = [part["data"] for part in parts if part["type"] == "updates"]
    assert [next(iter(update)) for update in updates] == ["load_case", "assess_case", "report"]
    states = [part["data"] for part in parts if part["type"] == "values"]
    assert "evidence" not in states[0]
    assert "evidence" in states[1] and "findings" not in states[1]
    assert "findings" in states[2] and "report" not in states[2]
    assert states[-1]["status"] == "explained" and states[-1]["report"]
    assert all(state["before_run_id"] == "R-104" for state in states)


def test_changed_evidence_cannot_reuse_the_original_explanation(tmp_path):
    copied_data = tmp_path / "data"
    shutil.copytree(DATA_DIR, copied_data)
    config_path = copied_data / "configs" / "CFG-105.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["detection_threshold"] = 0.4
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result = build_graph(copied_data).invoke(REQUEST)
    assert result["status"] == "unresolved"
    assert "contradicts" in result["report"]
    assert "The threshold change explains" not in result["report"]
