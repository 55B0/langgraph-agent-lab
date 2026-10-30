"""Verify tool contracts, actual evidence, and source-directory boundaries."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from sensorassist.tools import build_tools


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_read_run_returns_evidence_and_a_configuration_reference():
    result = build_tools(DATA_DIR)["read_test_run"].invoke({"run_id": "R-105"})
    assert result["status"] == "found"
    assert result["run"]["source_id"] == "RUN-R-105"
    assert result["run"]["config_id"] == "CFG-105"
    assert result["run"]["observation"]["actual_detection"] is False


def test_unknown_run_is_an_explicit_tool_result():
    result = build_tools(DATA_DIR)["read_test_run"].invoke({"run_id": "R-999"})
    assert result == {"status": "not_found", "missing_evidence": ["runs/R-999.json"]}


@pytest.mark.parametrize("invalid_id", ["../tests/test_graph", "R-105.json", "C:\\secret", "", "R-" + "9" * 100])
def test_tool_rejects_paths_instead_of_accepting_them_as_ids(invalid_id):
    result = build_tools(DATA_DIR)["read_test_run"].invoke({"run_id": invalid_id})
    assert result["status"] == "invalid_argument"


def test_config_comparison_reports_actual_change_and_sources():
    result = build_tools(DATA_DIR)["compare_configs"].invoke({
        "before_config_id": "CFG-104", "after_config_id": "CFG-105",
    })
    assert result["source_ids"] == ["CONFIG-CFG-104", "CONFIG-CFG-105"]
    assert result["changes"] == [{
        "field": "detection_threshold", "before": 0.4, "after": 0.7,
        "before_present": True, "after_present": True,
    }]


def test_config_comparison_uses_changed_file_contents(tmp_path):
    copied_data = tmp_path / "data"
    shutil.copytree(DATA_DIR, copied_data)
    path = copied_data / "configs" / "CFG-105.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["detection_threshold"] = 0.4
    path.write_text(json.dumps(record), encoding="utf-8")
    result = build_tools(copied_data)["compare_configs"].invoke({
        "before_config_id": "CFG-104", "after_config_id": "CFG-105",
    })
    assert result["status"] == "compared" and result["changes"] == []


def test_comparison_names_missing_configuration():
    result = build_tools(DATA_DIR)["compare_configs"].invoke({
        "before_config_id": "CFG-104", "after_config_id": "CFG-999",
    })
    assert result == {"status": "not_found", "missing_evidence": ["configs/CFG-999.json"]}


def test_search_returns_verifiable_source_passages():
    result = build_tools(DATA_DIR)["search_spec"].invoke({"query": "detection threshold"})
    assert result["status"] == "found" and 1 <= len(result["matches"]) <= 3
    first = result["matches"][0]
    assert first["matched_terms"] == ["detection", "threshold"]
    for match in result["matches"]:
        assert not match["text"].startswith(("#", "Source ID:"))
        lines = (DATA_DIR / match["path"]).read_text(encoding="utf-8").splitlines()
        assert match["text"] == "\n".join(lines[match["start_line"] - 1:match["end_line"]])
        assert match["source_id"] == "SPEC-DETECTION-V1"


def test_search_reports_no_match_and_empty_query_separately():
    search = build_tools(DATA_DIR)["search_spec"]
    assert search.invoke({"query": "unobtainium"}) == {"status": "no_matches", "matches": []}
    assert search.invoke({"query": "  "})["status"] == "invalid_argument"


def test_search_reports_missing_spec_directory(tmp_path):
    result = build_tools(tmp_path)["search_spec"].invoke({"query": "detection"})
    assert result == {"status": "not_found", "missing_evidence": ["specs/"]}


def test_tool_schemas_expose_task_arguments_and_not_filesystem_configuration():
    tools = build_tools(DATA_DIR)
    expected = {
        "read_test_run": {"run_id"},
        "compare_configs": {"before_config_id", "after_config_id"},
        "search_spec": {"query"},
    }
    for name, arguments in expected.items():
        assert set(tools[name].args) == arguments
        assert tools[name].description


def test_tool_demo_runs_without_a_model():
    result = subprocess.run(
        [sys.executable, "-m", "sensorassist", "--tools"],
        cwd=DATA_DIR.parent, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    for name in ("read_test_run", "compare_configs", "search_spec"):
        assert f"Tool: {name}" in result.stdout
    assert "scripted tool calls (no LLM)" in result.stdout
