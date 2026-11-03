"""Start and resume a local investigation using LangGraph's SQLite saver."""

from argparse import Namespace
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from sensorassist.agent import build_agent
from sensorassist.simulation import ScriptedModel


def run_saved_review(args: Namespace) -> int:
    database = Path(".checkpoints") / "investigations.sqlite"
    if args.resume_review and not database.is_file():
        print("No saved investigations in this project folder.")
        return 1
    database.parent.mkdir(exist_ok=True)
    thread_id = args.resume_review or uuid4().hex
    # The thread ID is the label on the saved backpack. Each CLI process
    # opens a new connection to the same file and can load it by that label.
    config = {"configurable": {"thread_id": thread_id}}
    with SqliteSaver.from_conn_string(str(database)) as saver:
        workflow = build_agent(
            args.data_dir, ScriptedModel(args.before_run, args.after_run),
            max_tool_calls=args.max_tool_calls, max_model_turns=args.max_model_turns,
            human_review=True, checkpointer=saver,
        )
        if args.resume_review:
            snapshot = workflow.get_state(config)
            if not snapshot.interrupts:
                print(f"No pending review for investigation {thread_id}.")
                return 1
            # Resume the saved review node with the human's answer.
            # There is no new HumanMessage to start the investigation again.
            result = workflow.invoke(Command(resume=args.answer), config, durability="sync")
            print(f"Review resumed. Human answer: {result['human_answer']}")
        else:
            request = HumanMessage(content=f"Compare runs {args.before_run} and {args.after_run}.")
            result = workflow.invoke({"messages": [request]}, config, durability="sync")

        report = result["report"]
        print(f"Status: {report['status']}")
        print(f"Tool calls in this investigation: {result.get('tool_calls_used', 0)}")
        for finding in report["findings"]:
            print(f"- {finding['text']} [{', '.join(finding['evidence'])}]")
        for item in report["missing_information"]:
            print(f"- Missing: {item}")
        if result.get("__interrupt__"):
            print(f"Review paused: {result['__interrupt__'][0].value}")
            print(f"Investigation ID: {thread_id}")
            print(f"Resume with --resume-review {thread_id} --answer yes (or no or unsure).")
        else:
            print(f"Next check: {report['next_check']}")
    return 0
