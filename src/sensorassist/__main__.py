"""Inspect the first synthetic case before adding graph orchestration."""

import argparse
from pathlib import Path

from sensorassist.case_data import load_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect fictional sensor test evidence.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()

    print("SensorAssist | Section 1: synthetic evidence inspection")
    print("This is a deterministic data inspector; the LangGraph agent is planned.\n")
    for run_id in ("R-104", "R-105"):
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
