"""Turn retrieved evidence into a structured investigation report."""

import json
from typing import Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage, ToolMessage


class Finding(TypedDict):
    text: str
    evidence: list[str]
    configuration_field: NotRequired[str]


class InvestigationReport(TypedDict):
    status: Literal["completed", "incomplete", "tool_error", "stopped"]
    findings: list[Finding]
    evidence: list[str]
    missing_information: list[str]
    next_check: str


def build_report(messages: list[AnyMessage], stop_reason: str = "") -> InvestigationReport:
    # Build claims and citations together from tool output. The model's prose
    # can remain in the conversation without becoming evidence for the report.
    findings: list[Finding] = []
    evidence: list[str] = []
    missing: list[str] = []
    failed_tools: list[str] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        if message.status == "error":
            failed_tools.append(message.name or "unknown tool")
            continue
        result = json.loads(message.content)
        if result["status"] == "not_found":
            missing.extend(result["missing_evidence"])
        elif result["status"] == "invalid_argument":
            failed_tools.append(message.name or "unknown tool")
        elif message.name == "read_test_run":
            run = result["run"]
            findings.append({"text": f"Run {run['run_id']}: {run['outcome']}.", "evidence": [run["source_id"]]})
        elif message.name == "read_event_log":
            lines = result["lines"]
            if lines:
                findings.append({
                    "text": f"Event log passage at lines {lines[0]['line_number']}-{lines[-1]['line_number']}.",
                    "evidence": [result["source_id"]],
                })
            else:
                missing.append(f"No lines in the requested page of {result['path']}.")
        elif message.name == "compare_configs":
            sources = result["source_ids"]
            evidence.extend(sources)
            for change in result["changes"]:
                before = change["before"] if change["before_present"] else "(absent)"
                after = change["after"] if change["after_present"] else "(absent)"
                findings.append({
                    "text": f"Configuration change: {change['field']}: {before} -> {after}.",
                    "evidence": sources,
                    "configuration_field": change["field"],
                })
            if not result["changes"]:
                findings.append({"text": "No configuration field changes were found.", "evidence": sources})
        elif message.name == "search_spec":
            for match in result["matches"]:
                findings.append({
                    "text": f"Specification passage at lines {match['start_line']}-{match['end_line']}.",
                    "evidence": [match["source_id"]],
                })
            if not result["matches"]:
                missing.append("Specification passage matching the search.")

    if stop_reason:
        status, next_check = "stopped", f"Review the run limit ({stop_reason}) before rerunning."
    elif failed_tools:
        status, next_check = "tool_error", f"Check inputs and evidence files for {', '.join(dict.fromkeys(failed_tools))}."
    elif missing or not findings:
        status, next_check = "incomplete", "Supply the missing evidence and rerun the investigation."
    else:
        status, next_check = "completed", "Confirm intended behavior before deciding on a fix."
    if not findings and not missing:
        missing.append("Retrieved evidence for the investigation.")
    for finding in findings:
        evidence.extend(finding["evidence"])
    return {
        "status": status, "findings": findings, "evidence": list(dict.fromkeys(evidence)),
        "missing_information": list(dict.fromkeys(missing)), "next_check": next_check,
    }
