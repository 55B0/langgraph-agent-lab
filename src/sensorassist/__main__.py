"""Inspect evidence or run the LangGraph workflow with conditional routing."""

import argparse
import json
from pathlib import Path

from sensorassist.case_data import load_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect fictional sensor test evidence.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--graph", action="store_true", help="Run the LangGraph investigation.")
    parser.add_argument("--trace", action="store_true", help="Print complete graph state snapshots.")
    parser.add_argument("--before-run", default="R-104", help="Earlier test run ID.")
    parser.add_argument("--after-run", default="R-105", help="Later test run ID.")
    args = parser.parse_args()
    if args.trace and not args.graph:
        parser.error("--trace requires --graph")
    if args.graph:
        from sensorassist.graph import build_graph

        print("SensorAssist | Section 3: conditional LangGraph workflow")
        print("START -> load_case -> assess_case -> report -> END")
        print("                   -> missing_data -> END (when evidence is missing)\n")
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
