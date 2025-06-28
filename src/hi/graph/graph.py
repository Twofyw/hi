"""Main graph.

This module defines the main graph structure and logic for handling conversational state,
tool usage, and model interaction in the hi application.
"""

import json
from typing import Dict, List, Literal, cast

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import msg_content_output
from langgraph.types import Command, interrupt

from hi.graph.configuration import Configuration
from hi.graph.prompts import build_system_prompt
from hi.graph.state import InputState, State
from hi.graph.tools import TOOLS, pending_comm_tasks, proc2output
from hi.graph.utils import load_chat_model


async def call_model(state: State) -> Dict[str, List[AnyMessage]]:
    """Call the LLM powering our "agent".

    This function prepares the prompt, initializes the model, and processes the response.

    Args:
        state (State): The current state of the conversation.
        config (RunnableConfig): Configuration for the model run.

    Returns:
        dict: A dictionary containing the model's response message.
    """
    configuration = Configuration.from_context()

    # Initialize the model with tool binding. Change the model or add more tools here.
    if configuration.default_model == "big_model":
        model_args = configuration.smart_model
    else:
        model_args = configuration.fast_model or configuration.smart_model

    model = load_chat_model(model_args).bind_tools(TOOLS)

    # Format the system prompt. Customize this to change the agent's behavior.
    messages = []
    if len(state.messages) == 1:
        other_pane_content = "\n".join(
            f"<pane id='{pane_id}'>{content}</pane>"
            for pane_id, content in state.get_other_panes_content().items()
        )

        first_message = state.messages[0]
        first_message.content = f"""## Current tmux window state:
<current_pane>{state.get_current_pane_content()}</current_pane>
<other_panes>{other_pane_content}</other_panes>

## User Prompt
{first_message.content}"""
        messages.append(first_message)

    # Get the model's response
    system_message = build_system_prompt(configuration.system_prompt)
    response = cast(
        AIMessage,
        await model.ainvoke(
            [{"role": "system", "content": system_message}, *state.messages]
        ),
    )
    messages.append(response)
    if response.invalid_tool_calls:
        messages.append(
            ToolMessage(
                f"Invalid tool call: {json.dumps(response.invalid_tool_calls[0], ensure_ascii=False)}"
            )
        )

    # Handle the case when it's the last step and the model still wants to use a tool
    if state.is_last_step and response.tool_calls:
        return {
            "messages": [
                AIMessage(
                    id=response.id,
                    content="Sorry, I could not find an answer to your question in the specified number of steps.",
                )
            ]
        }

    # Return the model's response as a list to be added to existing messages

    return {"messages": messages}


async def handle_pending_tasks(state: State) -> dict:
    """Check for any pending tasks and update their status."""
    messages = []
    for tool_call_id, task in pending_comm_tasks.items():
        if task.done():
            for message in state.messages:
                if (
                    isinstance(message, ToolMessage)
                    and message.tool_call_id == tool_call_id
                ):
                    # Update the tool message with the result
                    message.content = msg_content_output(proc2output(task))  # type: ignore
                    break
            messages.append(message)

            # Remove the task from the pending list
            del pending_comm_tasks[tool_call_id]

    return {"messages": messages}


async def human_feedback(
    state: State,
) -> Command[Literal["__end__", "handle_pending_tasks", "tools"]]:
    """Confirm the tool calls and return the results.

    This function is called after the tools have been executed to confirm the actions taken.

    Args:
        state (State): The current state of the conversation.

    Returns:
        dict: A dictionary containing the confirmation message.
    """
    last_message = state.messages[-1]
    if not isinstance(last_message, AIMessage):
        raise ValueError(
            f"Expected AIMessage in output edges, but got {type(last_message).__name__}"
        )

    response = cast(AIMessage, last_message)

    # If there is no tool call, then we finish
    if not response.tool_calls:
        # return Command(goto="__end__")
        return Command()

    tool_call = response.tool_calls[0]

    print("interrupting")
    feedback = interrupt({"tool_call": tool_call["args"]})

    update = {"feedback": feedback}

    if feedback == "continue":
        return Command(goto="tools", update=update)
    else:
        # If the user has provided feedback to continue, we return to the model
        update["messages"] = ToolMessage(
            tool_call_id=tool_call["id"],
            name=tool_call["name"],
            content=feedback,
        )
        return Command(goto="handle_pending_tasks", update=update)


# Define a new graph
builder = StateGraph(State, input=InputState, config_schema=Configuration)

# Define the two nodes we will cycle between
builder.add_node(call_model)
builder.add_node("tools", ToolNode(TOOLS))
builder.add_node(human_feedback)
builder.add_node(handle_pending_tasks)

# Set the entrypoint as `call_model`
# This means that this node is the first one called
builder.add_edge("__start__", "handle_pending_tasks")
builder.add_edge("handle_pending_tasks", "call_model")
builder.add_edge("call_model", "human_feedback")


# Add a normal edge from `tools` to `call_model`
# This creates a cycle: after using tools, we always return to the model
builder.add_edge("tools", "handle_pending_tasks")

# Compile the builder into an executable graph
graph = builder.compile(name="hi", checkpointer=InMemorySaver())
