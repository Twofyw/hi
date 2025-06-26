"""Define the state structures for the agent."""

from dataclasses import dataclass, field
from typing import Annotated, Sequence

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from langgraph.managed import IsLastStep


@dataclass
class InputState:
    messages: Annotated[Sequence[AnyMessage], add_messages] = field(
        default_factory=list
    )
    window_content: dict[str, list[str]] = field(default_factory=dict)
    """Content of the current tmux window, indexed by pane ID."""
    current_pane_id: str = field(default="")
    """ID of the current tmux pane."""


@dataclass
class State(InputState):
    is_last_step: IsLastStep = field(default=False)

    pane_history: dict[str, list[str]] = field(default_factory=dict)
    """History of captured pane outputs, indexed by pane ID."""

    feedback: str = field(default="")
    """Feedback from the user, if any."""

    def get_current_pane_content(self) -> str:
        """Get the content of the current pane."""
        return "\n".join(self.window_content[self.current_pane_id])

    def get_other_panes_content(self) -> dict[str, str]:
        """Get the content of all other panes."""
        return {
            pane_id: "\n".join(content)
            for pane_id, content in self.window_content.items()
            if pane_id != self.current_pane_id
        }
