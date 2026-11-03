"""Offline integration tests for model/tool messages, real tools, and limits."""

import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from sensorassist.agent import build_agent
from sensorassist.simulation import ScriptedModel


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def request():
    return {"messages": [HumanMessage(content="Compare R-104 and R-105.")]}


def assert_protocol_complete(messages):
    pending = set()
    seen = set()
    for message in messages:
        if isinstance(message, AIMessage):
            assert not pending, "A model turn must not skip a pending tool result."
            for call in message.tool_calls:
                assert call["id"] not in seen
                seen.add(call["id"])
                pending.add(call["id"])
        elif isinstance(message, ToolMessage):
            assert message.tool_call_id in pending
            pending.remove(message.tool_call_id)
    assert not pending


def test_simulation_uses_real_results_and_accumulates_messages_without_network(monkeypatch):
    def deny_network(*args, **kwargs):
        raise AssertionError("The offline simulation must not connect to a network.")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    result = build_agent(DATA_DIR, ScriptedModel()).invoke(request())
    assert result["status"] == "completed"
    assert result["model_turns"] == 5
    assert result["tool_calls_used"] == 4
    assert isinstance(result["messages"][0], HumanMessage)
    tools = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert json.loads(tools[1].content)["run"]["outcome"] == "failed"
    assert "0.4 -> 0.7" in result["messages"][-1].content
    assert "SIMULATION" in result["messages"][-1].content
    report = result["report"]
    assert report["status"] == "completed"
    assert report["missing_information"] == []
    assert {
        "text": "Configuration change: detection_threshold: 0.4 -> 0.7.",
        "evidence": ["CONFIG-CFG-104", "CONFIG-CFG-105"],
        "configuration_field": "detection_threshold",
    } in report["findings"]
    assert_protocol_complete(result["messages"])


def test_simulated_report_changes_when_the_actual_configuration_changes(tmp_path):
    copied_data = tmp_path / "data"
    shutil.copytree(DATA_DIR, copied_data)
    path = copied_data / "configs" / "CFG-105.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["detection_threshold"] = 0.4
    path.write_text(json.dumps(record), encoding="utf-8")
    result = build_agent(copied_data, ScriptedModel()).invoke(request())
    assert "No configuration field changes" in result["messages"][-1].content
    assert "0.4 -> 0.7" not in result["messages"][-1].content


def test_missing_run_returns_an_incomplete_summary_without_comparing():
    model = ScriptedModel(after_run_id="R-999")
    result = build_agent(DATA_DIR, model).invoke(request())
    assert result["tool_calls_used"] == 2
    assert "Incomplete evidence" in result["messages"][-1].content
    assert "runs/R-999.json" in result["messages"][-1].content
    assert result["report"]["status"] == "incomplete"
    assert result["report"]["missing_information"] == ["runs/R-999.json"]
    assert result["report"]["evidence"] == ["RUN-R-104"]
    assert_protocol_complete(result["messages"])


def test_malformed_config_reports_tool_error_and_keeps_run_evidence(tmp_path):
    copied_data = tmp_path / "data"
    shutil.copytree(DATA_DIR, copied_data)
    (copied_data / "configs" / "CFG-105.json").write_text("{", encoding="utf-8")
    result = build_agent(copied_data, ScriptedModel()).invoke(request())
    assert result["report"]["status"] == "tool_error"
    assert result["report"]["evidence"] == ["RUN-R-104", "RUN-R-105"]
    assert "compare_configs" in result["report"]["next_check"]
    assert_protocol_complete(result["messages"])


@pytest.mark.parametrize(("answer", "next_check"), [
    ("yes", "test expectation"),
    ("no", "restored"),
    ("unsure", "change history"),
])
def test_review_resumes_with_human_answer_without_retrieving_evidence_again(answer, next_check):
    workflow = build_agent(DATA_DIR, ScriptedModel(), human_review=True)
    config = {"configurable": {"thread_id": "review-test"}}
    paused = workflow.invoke(request(), config)
    assert paused["__interrupt__"]
    assert paused["tool_calls_used"] == 4

    resumed = workflow.invoke(Command(resume=answer), config)
    assert resumed["human_answer"] == answer
    assert next_check in resumed["report"]["next_check"]
    assert resumed["messages"] == paused["messages"]
    assert resumed["tool_calls_used"] == 4


def test_review_skips_incomplete_report():
    workflow = build_agent(DATA_DIR, ScriptedModel(after_run_id="R-999"), human_review=True)
    result = workflow.invoke(request(), {"configurable": {"thread_id": "missing-test"}})
    assert result["report"]["status"] == "incomplete"
    assert "__interrupt__" not in result


def test_saved_review_resumes_in_a_fresh_process(tmp_path):
    command = [sys.executable, "-m", "sensorassist"]

    def run_cli(*args):
        return subprocess.run(
            [*command, *args], cwd=tmp_path, capture_output=True, text=True, timeout=20,
        )

    started = run_cli("--save-review", "--data-dir", str(DATA_DIR))
    assert started.returncode == 0, started.stderr
    thread_id = started.stdout.split("Investigation ID: ", 1)[1].splitlines()[0]
    assert (tmp_path / ".checkpoints" / "investigations.sqlite").is_file()

    # This fresh process has no local data folder. It must use saved evidence.
    resumed = run_cli("--resume-review", thread_id, "--answer", "unsure")
    assert resumed.returncode == 0, resumed.stderr
    assert "Tool calls in this investigation: 4" in resumed.stdout
    assert "CONFIG-CFG-105" in resumed.stdout
    assert "Check the change history" in resumed.stdout

    repeated = run_cli("--resume-review", thread_id, "--answer", "yes")
    assert repeated.returncode == 1
    assert "No pending review" in repeated.stdout


class RepeatingModel:
    def __init__(self, name="read_test_run"):
        self.name = name

    def invoke(self, messages):
        turn = sum(isinstance(message, AIMessage) for message in messages)
        return AIMessage(content="", tool_calls=[{
            "name": self.name, "args": {"run_id": "R-104"}, "id": f"repeat-{turn}",
        }])


def test_tool_limit_stops_a_repeating_model_and_answers_rejected_calls():
    result = build_agent(DATA_DIR, RepeatingModel(), max_tool_calls=1).invoke(request())
    assert result["status"] == "stopped" and result["stop_reason"] == "tool_call_limit"
    assert result["report"]["status"] == "stopped"
    assert result["report"]["evidence"] == ["RUN-R-104"]
    assert result["tool_calls_used"] == 1
    tools = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert len(tools) == 2
    assert json.loads(tools[-1].content)["status"] == "budget_exhausted"
    assert_protocol_complete(result["messages"])


def test_model_turn_limit_stops_after_answering_the_last_tool_request():
    result = build_agent(DATA_DIR, RepeatingModel(), max_model_turns=1).invoke(request())
    assert result["stop_reason"] == "model_turn_limit"
    assert result["model_turns"] == result["tool_calls_used"] == 1
    assert_protocol_complete(result["messages"])


def test_batch_cannot_bypass_tool_limit():
    class BatchModel:
        def invoke(self, messages):
            return AIMessage(content="", tool_calls=[
                {"name": "read_test_run", "args": {"run_id": "R-104"}, "id": f"batch-{i}"}
                for i in range(3)
            ])

    result = build_agent(DATA_DIR, BatchModel(), max_tool_calls=1).invoke(request())
    tools = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert result["tool_calls_used"] == 1
    assert len(tools) == 3 and sum(message.status == "error" for message in tools) == 2
    assert_protocol_complete(result["messages"])


def test_unknown_tools_are_returned_as_errors_and_still_bounded():
    result = build_agent(DATA_DIR, RepeatingModel("unknown_tool"), max_model_turns=1).invoke(request())
    tools = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert tools[0].status == "error"
    assert result["status"] == "stopped"
    assert_protocol_complete(result["messages"])


def test_reusing_graph_does_not_reuse_a_hidden_simulation_counter():
    graph = build_agent(DATA_DIR, ScriptedModel())
    first = graph.invoke(request())
    second = graph.invoke(request())
    assert first["model_turns"] == second["model_turns"] == 5
    assert len(first["messages"]) == len(second["messages"]) == 10


@pytest.mark.parametrize("tools,turns", [(-1, 8), (6, 0)])
def test_invalid_limits_fail_before_execution(tools, turns):
    with pytest.raises(ValueError):
        build_agent(DATA_DIR, ScriptedModel(), max_tool_calls=tools, max_model_turns=turns)


def test_zero_tool_budget_executes_no_tools():
    result = build_agent(DATA_DIR, ScriptedModel(), max_tool_calls=0).invoke(request())
    assert result["status"] == "stopped" and result["tool_calls_used"] == 0
    assert_protocol_complete(result["messages"])


def test_simulation_command_labels_scripted_choices_and_reports_limits():
    result = subprocess.run(
        [sys.executable, "-m", "sensorassist", "--simulate", "--max-tool-calls", "1"],
        cwd=DATA_DIR.parent, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "SIMULATION" in result.stdout and "Script requests" in result.stdout
    assert "Status: stopped" in result.stdout and "tool_call_limit" in result.stdout
