"""A bounded model/tool loop with an injected model interface."""

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
    """A future live adapter must return AIMessage and bind tools beforehand."""

    def invoke(self, messages: list[AnyMessage]) -> AIMessage: ...


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    model_turns: int
    tool_calls_used: int
    status: Literal["running", "completed", "stopped"]
    stop_reason: str


def build_agent(
    data_dir: Path,
    model: ToolCallingModel,
    *,
    max_tool_calls: int = 6,
    max_model_turns: int = 8,
) -> CompiledStateGraph:
    """Use the same graph for a scripted model or a future bound live model."""
    if max_tool_calls < 0 or max_model_turns < 1:
        raise ValueError("Tool budget must be nonnegative and model-turn budget positive.")
    executor = ToolNode(list(build_tools(data_dir).values()))

    def model_step(state: AgentState) -> dict:
        response = model.invoke(state["messages"])
        if not isinstance(response, AIMessage):
            raise TypeError("The model adapter must return an AIMessage.")
        return {
            "messages": [response],
            "model_turns": state.get("model_turns", 0) + 1,
            "status": "running" if response.tool_calls else "completed",
        }

    def execute_tools(state: AgentState) -> dict:
        results = []
        used = state.get("tool_calls_used", 0)
        stop_reason = ""
        for call in state["messages"][-1].tool_calls:
            if used >= max_tool_calls:
                stop_reason = "tool_call_limit"
                results.append(ToolMessage(
                    content=json.dumps({"status": "budget_exhausted", "message": "Tool call was not executed."}),
                    tool_call_id=call["id"], name=call["name"], status="error",
                ))
                continue
            # Execute a single request with the built-in ToolNode, preserving its ID.
            output = executor.invoke({"messages": [AIMessage(content="", tool_calls=[call])]})
            results.extend(output["messages"])
            used += 1
        return {"messages": results, "tool_calls_used": used, "stop_reason": stop_reason}

    def stop(state: AgentState) -> dict:
        reason = state.get("stop_reason") or "model_turn_limit"
        return {
            "messages": [AIMessage(content=f"Investigation stopped: {reason}. No completed diagnosis is claimed.")],
            "status": "stopped", "stop_reason": reason,
        }

    def after_model(state: AgentState) -> Literal["tools", "done"]:
        return "tools" if state["messages"][-1].tool_calls else "done"

    def after_tools(state: AgentState) -> Literal["model", "stop"]:
        if state.get("stop_reason") or state["model_turns"] >= max_model_turns:
            return "stop"
        return "model"

    builder = StateGraph(AgentState)
    builder.add_node("model", model_step)
    builder.add_node("tools", execute_tools)
    builder.add_node("stop", stop)
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", after_model, {"tools": "tools", "done": END})
    builder.add_conditional_edges("tools", after_tools, {"model": "model", "stop": "stop"})
    builder.add_edge("stop", END)
    # Independent outer guard: each turn can use a model and a tool super-step.
    return builder.compile().with_config({"recursion_limit": 2 * max_model_turns + 4})
