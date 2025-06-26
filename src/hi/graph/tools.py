"""Agent tools."""

import asyncio
from asyncio import subprocess
from typing import Annotated, Any, Callable, List, Optional, cast

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import InjectedState

from hi.graph.configuration import Configuration
from hi.graph.state import State

pending_comm_tasks = {}


async def execute_command(
    command: str,
    explanation: str,
    config: RunnableConfig,
    state: Annotated[State, InjectedState],
) -> Optional[dict[str, Any]]:
    """Execute a command in the current shell using subprocess.

    This function runs a shell command and captures its output.

    Args:
        command (str): The shell command to execute.
        explanation (str): A brief explanation of why the command will help with the request.
    """
    # Parallel command execution is not supported in this tool.

    configuration = Configuration.from_context()

    try:
        proc = await subprocess.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        comm_task = asyncio.create_task(proc.communicate())
    except Exception as e:
        return {"error": str(e), "code": proc.returncode}

    done, pending = await asyncio.wait(
        [comm_task], timeout=configuration.command_timeout
    )
    if done:
        return proc2output(done.pop())
    else:
        tool_call_message = cast(AIMessage, state.messages[-1])
        tool_call_id = tool_call_message.tool_calls[0]["id"]
        pending_comm_tasks[tool_call_id] = pending.pop()
        return {
            "error": f"Command execution timed out after {configuration.command_timeout} seconds. Adding to pending tasks. Will update code output once finished",
        }


def proc2output(comm_task: asyncio.Task) -> dict[str, Any]:
    """Convert a completed command task to output format."""
    try:
        stdout, stderr = comm_task.result()
    except Exception as e:
        return {
            "error": str(e),
        }

    return {
        "stdout": stdout.decode().strip(),
        "stderr": stderr.decode().strip(),
        "code": 0,
    }


TOOLS: List[Callable[..., Any]] = [execute_command]
