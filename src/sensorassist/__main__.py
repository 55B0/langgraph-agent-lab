"""Choose a learning mode and display what happens during execution.

No flag: inspect records (Section 1). --graph: evidence-state workflow (2-3).
--tools: direct tool calls (4). --simulate: a scripted model/tool loop (5).
This module handles terminal input/output; the graph modules define execution.
"""

import argparse
import json
from pathlib import Path

from sensorassist.case_data import load_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect fictional sensor test evidence.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--graph", action="store_true", help="Run the LangGraph investigation.")
    mode.add_argument("--tools", action="store_true", help="Run a scripted evidence-tool demonstration.")
    mode.add_argument("--simulate", action="store_true", help="Run the model/tool loop with a scripted model.")
    parser.add_argument("--trace", action="store_true", help="Print complete graph state snapshots.")
    parser.add_argument("--before-run", default="R-104", help="Earlier test run ID.")
    parser.add_argument("--after-run", default="R-105", help="Later test run ID.")
    parser.add_argument("--max-tool-calls", type=int, default=6, help="Tool execution limit for --simulate.")
    parser.add_argument("--max-model-turns", type=int, default=8, help="Model turn limit for --simulate.")
    args = parser.parse_args()
    if args.trace and not (args.graph or args.simulate):
        parser.error("--trace requires --graph or --simulate")
    if args.max_tool_calls < 0 or args.max_model_turns < 1:
        parser.error("--max-tool-calls must be nonnegative; --max-model-turns must be positive")
    if args.simulate:
        from langchain_core.messages import HumanMessage

        from sensorassist.agent import build_agent
        from sensorassist.simulation import ScriptedModel

        print("SensorAssist | Section 5: SIMULATION (scripted model; no LLM or API key)")
        print("START -> model -> tools -> model ... -> END\n")
        # The script gets the scenario IDs explicitly; it does not understand
        # the natural-language request like a real LLM would.
        model = ScriptedModel(args.before_run, args.after_run)
        workflow = build_agent(
            args.data_dir, model,
            max_tool_calls=args.max_tool_calls, max_model_turns=args.max_model_turns,
        )
        # The HumanMessage is the initial state. AI requests and ToolMessage
        # results will accumulate alongside it through the add_messages reducer.
        request = {"messages": [HumanMessage(content=f"Compare runs {args.before_run} and {args.after_run}.")]}
        final_state = {}
        for part in workflow.stream(request, stream_mode=["updates", "values"], version="v2"):
            if part["type"] == "updates":
                # updates contains only the fields returned by the current node.
                for node, update in part["data"].items():
                    print(f"Node: {node}")
                    for message in update.get("messages", []):
                        if message.type == "ai" and message.tool_calls:
                            for call in message.tool_calls:
                                print(f"  Script requests {call['name']} {json.dumps(call['args'])} [{call['id']}]")
                        elif message.type == "tool":
                            # "success" means the tool returned normally. Its
                            # content may still report an expected not_found.
                            print(f"  Tool result: {message.name} [{message.tool_call_id}], {message.status}")
            elif part["type"] == "values":
                # values is the full state after LangGraph applies the update.
                # Read this snapshot rather than rebuilding state ourselves.
                final_state = part["data"]
                if args.trace:
                    snapshot = {**final_state, "messages": [message.model_dump() for message in final_state["messages"]]}
                    print(json.dumps(snapshot, indent=2))
        print(f"\nStatus: {final_state['status']}")
        print(f"Model turns: {final_state['model_turns']}; tool calls executed: {final_state.get('tool_calls_used', 0)}")
        print(final_state["messages"][-1].content)
        return
    if args.tools:
        from sensorassist.tools import build_tools

        tools = build_tools(args.data_dir)
        print("SensorAssist | Section 4: scripted tool calls (no LLM)")

        def call_tool(name: str, arguments: dict) -> dict:
            print(f"\nTool: {name}")
            print("Input: " + json.dumps(arguments))
            result = tools[name].invoke(arguments)
            print("Result: " + json.dumps(result, indent=2))
            return result

        # This recipe calls tools directly. There is no model node or graph
        # loop in --tools mode; --simulate demonstrates those additional parts.
        before = call_tool("read_test_run", {"run_id": args.before_run})
        after = call_tool("read_test_run", {"run_id": args.after_run})
        if before["status"] == "found" and after["status"] == "found":
            call_tool("compare_configs", {
                "before_config_id": before["run"]["config_id"],
                "after_config_id": after["run"]["config_id"],
            })
        else:
            print("\nConfiguration comparison skipped: a required run was not found.")
        call_tool("search_spec", {"query": "detection threshold"})
        return
    if args.graph:
        from sensorassist.graph import build_graph

        print("SensorAssist | Section 3: conditional LangGraph workflow")
        print("START -> load_case -> assess_case -> report -> END")
        print("                   -> missing_data -> END (when evidence is missing)\n")
        # This earlier graph uses evidence fields rather than message history.
        # The route changes when load_case records missing evidence.
        request = {"before_run_id": args.before_run, "after_run_id": args.after_run}
        final_state = {}
        for part in build_graph(args.data_dir).stream(
            request, stream_mode=["updates", "values"], version="v2"
        ):
            if part["type"] == "updates":
                for node, update in part["data"].items():
                    print(f"Node {node} writes: {', '.join(update)}")
            elif part["type"] == "values":
                final_state = part["data"]
                print(f"State contains: {', '.join(final_state)}")
                if args.trace:
                    print(json.dumps(final_state, indent=2))
        print("\n" + final_state["report"])
        return

    print("SensorAssist | Section 1: synthetic evidence inspection")
    print("This is a deterministic data inspector; the LangGraph agent is planned.\n")
    for run_id in (args.before_run, args.after_run):
        run, config = load_run(args.data_dir, run_id)
        observed = run["observation"]
        calculated = observed["signal"] >= config["detection_threshold"]
        print(f"{run_id} [{run['source_id']}, {config['source_id']}]")
        print(f"  Signal: {observed['signal']}; threshold: {config['detection_threshold']}")
        print(f"  Recorded detection: {observed['actual_detection']}; rule result: {calculated}")
        print(f"  Test expected: {observed['expected_detection']}; outcome: {run['outcome']}")
    print("\nSpecification: data/specs/SPEC-DETECTION-V1.md")
    print("Open question: was the threshold change intentional?")


if __name__ == "__main__":
    main()
