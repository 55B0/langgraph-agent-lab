"""A scripted model substitute. It reads messages, never source files or APIs."""

import json

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


class ScriptedModel:
    """Follow a fixed investigation recipe using actual tool results as inputs."""

    def __init__(self, before_run_id: str = "R-104", after_run_id: str = "R-105"):
        self.before_run_id = before_run_id
        self.after_run_id = after_run_id

    def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        results = [json.loads(message.content) for message in messages if isinstance(message, ToolMessage)]
        step = len(results)
        if results and results[-1]["status"] in ("not_found", "invalid_argument"):
            return AIMessage(content="[SIMULATION] Incomplete evidence: " + json.dumps(results[-1]))
        if step == 0:
            name, arguments = "read_test_run", {"run_id": self.before_run_id}
        elif step == 1:
            name, arguments = "read_test_run", {"run_id": self.after_run_id}
        elif step == 2:
            name, arguments = "compare_configs", {
                "before_config_id": results[0]["run"]["config_id"],
                "after_config_id": results[1]["run"]["config_id"],
            }
        elif step == 3:
            name, arguments = "search_spec", {"query": "detection threshold"}
        else:
            lines = ["[SIMULATION: scripted decisions; no LLM reasoning]"]
            for result in results[:2]:
                run = result["run"]
                lines.append(f"Run {run['run_id']}: {run['outcome']}. [{run['source_id']}]")
            changes = results[2]
            for change in changes["changes"]:
                lines.append(
                    f"Configuration change: {change['field']}: {change['before']} -> {change['after']}. "
                    f"[{', '.join(changes['source_ids'])}]"
                )
            if not changes["changes"]:
                lines.append("No configuration field changes were found.")
            search = results[3]
            for match in search["matches"]:
                lines.append(f"Specification passage: {match['source_id']}, lines {match['start_line']}-{match['end_line']}.")
            if not search["matches"]:
                lines.append("No specification passages matched; supporting documentation is missing.")
            lines.append("This lists retrieved evidence. Confirm intended behavior before deciding on a fix.")
            return AIMessage(content="\n".join(lines))
        return AIMessage(content="", tool_calls=[{
            "name": name, "args": arguments, "id": f"sim-call-{step + 1}", "type": "tool_call",
        }])
