"""Drive a saved diagnosis and validate a human-supplied evidence file."""

import json
from argparse import Namespace
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from sensorassist.diagnosis import build_diagnosis, validate_controller_config


def run_guided_diagnosis(args: Namespace) -> int:
    database = Path(".checkpoints") / "diagnoses.sqlite"
    if args.resume_diagnosis and not database.is_file():
        print("No saved diagnoses in this project folder.")
        return 1
    database.parent.mkdir(exist_ok=True)
    thread_id = args.resume_diagnosis or uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}
    with SqliteSaver.from_conn_string(str(database)) as saver:
        workflow = build_diagnosis(args.data_dir, saver)
        if args.resume_diagnosis:
            snapshot = workflow.get_state(config)
            if not snapshot.interrupts:
                print(f"No pending evidence request for diagnosis {thread_id}.")
                return 1
            try:
                # Read and validate BEFORE submitting Command. A wrong file
                # leaves the saved question pending so the user can retry.
                record = json.loads(args.controller_config.read_text(encoding="utf-8-sig"))
                validate_controller_config(record, snapshot.values["evidence"]["run"])
            except (OSError, ValueError) as error:
                print(f"Configuration was not accepted: {error}")
                return 1
            request = Command(resume=record)
            print("Resuming with saved evidence and the supplied controller configuration.")
        else:
            request = {"run_id": args.diagnose}
        for update in workflow.stream(request, config, stream_mode="updates", durability="sync"):
            for node, fields in update.items():
                if node == "__interrupt__":
                    continue
                print(f"Node: {node}")
                for check in fields.get("checks", []):
                    print(f"- {check}")
        snapshot = workflow.get_state(config)
        state = snapshot.values
        print(f"Status: {state['status']}")
        print(f"Next check: {state['next_check']}")
        print(f"Diagnosis ID: {thread_id}")
        if snapshot.interrupts:
            print("Node: request_controller (paused)")
            print("The diagnosis is saved. Supply the requested JSON controller configuration to continue.")
        if args.trace:
            print(json.dumps(state, indent=2))
    return 0
