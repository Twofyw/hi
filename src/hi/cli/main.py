"""Main CLI entry point for the tmuxai application."""

import asyncio
import json
import logging
import os
import uuid
from typing import cast

import asyncclick as click
import dotenv
from langchain_core.messages import AIMessageChunk, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from hi.context.tmux import Tmux
from hi.graph.configuration import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_ENV_PATH,
    Configuration,
    load_config,
    setup_config,
)
from hi.graph.graph import graph
from hi.graph.utils import get_message_text

dotenv.load_dotenv(DEFAULT_ENV_PATH, override=True)

LANGFUSE_TRACING_ENV = "LANGFUSE_TRACING_ENABLED"
callbacks = []


@click.command()
@click.argument("prompts", required=True, nargs=-1, type=str)
@click.option("-f", "--fast", is_flag=True, help="Run fast model.")
@click.option("-y", "--yolo", is_flag=True, help="Automatically accept all actions.")
@click.option(
    "--enable-langfuse",
    is_flag=False,
    help="Enable Langfuse tracing. This will make launching and exiting hi perceivably slower. You need to configure langfuse client environemt variables.",
)
@click.option(
    "-l", "--max-lines", type=int, help="Max history lines per pane"
)  # TODO: Implement
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=False),
    default=DEFAULT_CONFIG_PATH,
    help="Path to the configuration file.",
)
async def main(
    prompts: list[str],
    fast: bool,
    yolo: bool,
    enable_langfuse: bool,
    max_lines: int,
    config_path: str,
) -> None:
    """Start the tmux server and handle commands."""
    if enable_langfuse:
        setup_langfuse()

    try:
        await _main(prompts, fast, yolo, config_path)
    except asyncio.exceptions.CancelledError:
        click.echo(click.style("\nBye~", fg="green"))


async def _main(prompts: list[str], fast: bool, yolo: bool, config_path: str) -> None:
    """Prepare configuration and initial state, then run the interaction loop."""
    if setup_config():
        click.echo(f"Default configuration file written to {DEFAULT_CONFIG_PATH}.")

    config_obj = load_config(config_path)
    if fast:
        if not config_obj.fast_model:
            click.echo(click.style("Fast model is not configured.", fg="red"), err=True)
            return
        config_obj.default_model = "fast"

    prompt = " ".join(prompts)

    tmux = Tmux()

    graph_input = {
        "messages": prompt,
        "window_content": tmux.capture_current_window(),
        "current_pane_id": tmux.current_pane.id,
    }

    await _run_interaction_loop(graph_input, config_obj, yolo)


async def _run_interaction_loop(
    initial_input: dict, config_obj: Configuration, yolo: bool
):
    """Run the main graph interaction loop."""
    thread_id = uuid.uuid4()
    configurable = config_obj.model_dump(exclude_none=True)
    graph_config = RunnableConfig(
        configurable={"thread_id": thread_id, **configurable}, callbacks=callbacks
    )

    graph_input: dict | Command = initial_input

    while True:
        async for event_type, event in graph.astream(
            graph_input, config=graph_config, stream_mode=["updates", "messages"]
        ):
            if event_type == "updates":
                event = cast(dict, event)
                resume_command = _handle_update_event(event, yolo)
                if resume_command:
                    graph_input = resume_command
                    break  # resume graph
            elif event_type == "messages":
                event = cast(tuple, event)
                _handle_message_event(event)
        else:  # Only stop if no tool calls left
            prompt = click.prompt(
                CMD_PROMPT,
                type=str,
                default="bye",
                show_default=False,
                prompt_suffix="",
            )
            if prompt.lower() == "bye":
                click.echo(click.style("Bye~", fg="green"))
                break  # END
            else:
                graph_input = {
                    "messages": prompt,
                }


def _handle_update_event(event: dict, yolo: bool) -> Command | None:
    """Handle 'updates' from the graph stream."""
    node_name, updates = next(iter(event.items()))

    if node_name == "__interrupt__":
        interrupt_data = updates[0].value
        return _handle_interrupt(interrupt_data, yolo)

    if node_name == "tools":
        tool_message = cast(ToolMessage, updates["messages"][-1])
        content = tool_message.content
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                pass

        if isinstance(content, dict):
            output_parts = []
            if stdout := content.get("stdout", "").strip():
                output_parts.append(f"stdout:\n{stdout}")
            if stderr := content.get("stderr", "").strip():
                output_parts.append(f"stderr:\n{stderr}")
            if error := content.get("error"):
                output_parts.append(f"error: {error}")
            if "code" in content:
                output_parts.append(f"code: {content.get('code')}")
            output = "\n---\n".join(output_parts)
        else:
            output = content

        if output:
            click.echo(click.style(output, "yellow"))

    return None


CMD_PROMPT = click.style("\n> ", "blue")


def _handle_interrupt(interrupt_data: dict, yolo: bool) -> Command:
    """Handle a user interrupt to confirm a tool call."""
    tool_call = interrupt_data["tool_call"]
    command = tool_call["command"]
    explanation = tool_call["explanation"]

    click.echo(
        f"-----\n{click.style('Command to execute: `', 'green')}"
        f"{click.style(command, 'red')}"
        f"{click.style('`', 'green')}"
    )
    click.echo(
        f"{click.style('Explanation: ', 'green')}"
        f"{click.style(explanation, 'bright_green')}"
    )

    if yolo:
        return Command(resume="continue")

    feedback = click.prompt(
        click.style(
            "\nPress Enter to run, or type to provide feedback to the LLM, or Ctrl+C+Enter to exit.",
            "green",
        )
        + CMD_PROMPT,
        type=str,
        default="continue",
        show_default=False,
        prompt_suffix="",
    )
    return Command(resume=feedback)


def _handle_message_event(event: tuple):
    """Handle 'messages' from the graph stream (LLM tokens)."""
    chunk, _ = event
    if isinstance(chunk, AIMessageChunk):
        click.echo(get_message_text(chunk), nl=False)


def setup_langfuse() -> bool:
    """Set up Langfuse tracing if available and enabled."""
    if os.environ.get(LANGFUSE_TRACING_ENV, "").lower() == "false":
        return False

    try:
        import langfuse
        from langfuse.langchain import CallbackHandler
    except ImportError:
        logging.warning(
            "Langfuse is not installed. Install it with `pip install tmuxai[langfuse]` to enable tracing."
        )
        return False

    lf_client = langfuse.get_client()
    if not lf_client.auth_check():
        return False

    callbacks.append(CallbackHandler())
    return True
