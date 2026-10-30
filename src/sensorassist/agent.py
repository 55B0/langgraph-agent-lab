"""Section 5: coordinate model requests and real tools through message state.

Read AgentState first, then the node functions inside build_agent, then the
edges at the bottom. The normal path is model -> tools -> model -> ... -> END.
The model is currently ScriptedModel; this module supplies the orchestration.
"""

import json
from pathlib import Path
from typing import Annotated, Literal, Protocol, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from sensorassist.tools import build_tools


class ToolCallingModel(Protocol):
    """The interface the graph needs, regardless of the model implementation.

    invoke receives the conversation and returns either tool requests or a
    final response as an AIMessage. A future live adapter must bind the tool
    schemas beforehand; this interface does not create or authenticate an LLM.
    """

    def invoke(self, messages: list[AnyMessage]) -> AIMessage: ...


class AgentState(TypedDict, total=False):
    """The working record for one run; fields appear as nodes add updates."""

    # HumanMessage: request; AIMessage: model request/answer; ToolMessage: result.
    # add_messages retains the conversation when a node returns new messages.
    # Without this reducer, the new list would replace the previous history.
    messages: Annotated[list[AnyMessage], add_messages]
    # Counters are ordinary state fields: new values replace the old values.
    model_turns: int
    tool_calls_used: int
    # "completed" means the model finished, not that it proved a diagnosis.
    status: Literal["running", "completed", "stopped"]
    stop_reason: str


def build_agent(
    data_dir: Path,
    model: ToolCallingModel,
    *,
    max_tool_calls: int = 6,
    max_model_turns: int = 8,
) -> CompiledStateGraph:
    """Build an executable graph; building alone does not run the investigation.

    data_dir, model, and limits are application configuration captured by the
    nodes. The changing messages and counters belong in AgentState instead.
    No checkpointer is configured yet, so this graph does not save progress
    across process restarts.
    """
    if max_tool_calls < 0 or max_model_turns < 1:
        raise ValueError("Tool budget must be nonnegative and model-turn budget positive.")
    # ToolNode is a reusable LangGraph component. It dispatches a tool by name,
    # validates its arguments, and constructs a ToolMessage carrying the result.
    executor = ToolNode(list(build_tools(data_dir).values()))

    def model_step(state: AgentState) -> dict:
        """Read the history and append one model response to message state."""
        # A response may REQUEST a tool. Calling the model does not execute it.
        response = model.invoke(state["messages"])
        if not isinstance(response, AIMessage):
            raise TypeError("The model adapter must return an AIMessage.")
        # Return only changes. LangGraph applies them to the existing state,
        # using add_messages for the message list and overwrite for the counter.
        return {
            "messages": [response],
            "model_turns": state.get("model_turns", 0) + 1,
            "status": "running" if response.tool_calls else "completed",
        }

    def execute_tools(state: AgentState) -> dict:
        """Answer every request in the latest AIMessage, within the tool budget."""
        results = []
        used = state.get("tool_calls_used", 0)
        stop_reason = ""
        for call in state["messages"][-1].tool_calls:
            # Check EACH call before dispatch. A batch must not bypass the cap.
            if used >= max_tool_calls:
                stop_reason = "tool_call_limit"
                # Even a refused request needs a matching result. Otherwise the
                # history would contain a tool request that was never answered.
                # This call is not dispatched and does not increase "used".
                results.append(ToolMessage(
                    content=json.dumps({"status": "budget_exhausted", "message": "Tool call was not executed."}),
                    tool_call_id=call["id"], name=call["name"], status="error",
                ))
                continue
            # Give ToolNode one request at a time so our counter controls dispatch.
            # This temporary AIMessage is not added to the conversation again;
            # only its ToolMessage result is returned to the outer graph state.
            output = executor.invoke({"messages": [AIMessage(content="", tool_calls=[call])]})
            results.extend(output["messages"])
            used += 1  # Count dispatch attempts, including returned tool errors.
        return {"messages": results, "tool_calls_used": used, "stop_reason": stop_reason}

    def stop(state: AgentState) -> dict:
        """Write a terminal explanation without making another model call."""
        reason = state.get("stop_reason") or "model_turn_limit"
        return {
            "messages": [AIMessage(content=f"Investigation stopped: {reason}. No completed diagnosis is claimed.")],
            "status": "stopped", "stop_reason": reason,
        }

    def after_model(state: AgentState) -> Literal["tools", "done"]:
        # A router reads state and returns a route label, not a state update.
        # No tool requests means the model has supplied its final response.
        return "tools" if state["messages"][-1].tool_calls else "done"

    def after_tools(state: AgentState) -> Literal["model", "stop"]:
        # All requests have results before we decide to stop or call the model
        # again. This keeps the request/result message protocol complete.
        if state.get("stop_reason") or state["model_turns"] >= max_model_turns:
            return "stop"
        return "model"

    # Register the work (nodes), then declare which step can run next (edges).
    builder = StateGraph(AgentState)
    builder.add_node("model", model_step)
    builder.add_node("tools", execute_tools)
    builder.add_node("stop", stop)
    builder.add_edge(START, "model")
    # Only one outgoing route is chosen by each of these conditional routers.
    builder.add_conditional_edges("model", after_model, {"tools": "tools", "done": END})
    builder.add_conditional_edges("tools", after_tools, {"model": "model", "stop": "stop"})
    builder.add_edge("stop", END)
    # compile prepares the runnable graph. The recursion limit is an additional
    # cap on graph super-steps, not Python recursion or a wall-clock timeout.
    # Each model turn can use a model and tool step; leave room for stopping.
    return builder.compile().with_config({"recursion_limit": 2 * max_model_turns + 4})
