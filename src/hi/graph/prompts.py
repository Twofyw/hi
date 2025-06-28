"""Default prompts used by the agent."""

import os
import platform
from datetime import UTC, datetime

SYSTEM_PROMPT = """# Role
You are a helpful terminal assistant that helps users with their terminal tasks.


# System Info
<os>{os}</os>
<shell>{shell}</shell>
<user@hostname>{username_hostname}</user@hostname>
<home>{home_directory}</home>
<cwd>{working_directory}</cwd>
<ls (top20)>{ls_listing}</ls>
<system_time>{system_time}</system_time>

# Output Requirements
- No markdown syntax such as "**": format your output in plain text.
- No need to repeat command output. User can see it.
- Be concise.
"""


def get_os_description() -> str:
    """Return a description of the current operating system."""
    return f"{platform.system()} {platform.release()} ({platform.version()})"


def get_shell_description() -> str:
    """Return the current shell being used."""
    return os.environ.get("SHELL", "unknown")


def get_username_hostname() -> str:
    """Return the current username and hostname."""
    try:
        username = os.getlogin()
    except OSError:
        username = os.environ.get("USER", "unknown")
    hostname = platform.node()
    return f"{username}@{hostname}"


def get_home_directory() -> str:
    """Return the current user's home directory."""
    return os.path.expanduser("~")


def get_working_directory() -> str:
    """Return the current working directory."""
    return os.getcwd()


def get_ls_listing() -> str:
    """Return a list of files and directories in the current directory."""
    try:
        return "\n".join(os.listdir(os.getcwd())[:20])
    except Exception as e:
        return f"Error listing directory: {e}"


def build_system_prompt(system_prompt: str) -> str:
    """Build the system prompt with the current pane content, other panes, and system info."""
    os_description = get_os_description()
    shell_description = get_shell_description()
    username_hostname = get_username_hostname()
    home_directory = get_home_directory()
    working_directory = get_working_directory()
    ls_listing = get_ls_listing()
    return system_prompt.format(
        os=os_description,
        shell=shell_description,
        username_hostname=username_hostname,
        home_directory=home_directory,
        working_directory=working_directory,
        ls_listing=ls_listing,
        system_time=datetime.now(tz=UTC).isoformat(),
    )
