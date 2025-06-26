"""Tmux context manager for capturing pane outputs in a tmux session."""

import libtmux


class TmuxCommandError(Exception):
    """Custom exception for tmux command errors."""

    pass


class Tmux:
    """Tmux context manager for capturing pane outputs in a tmux session."""

    def __init__(self) -> None:
        """Initialize the Tmux context."""
        self.svr = libtmux.Server()

    @property
    def current_window(self) -> libtmux.Window:
        """Get the current window."""
        current_window_idx = self._current_window_idx
        return self.svr.windows[current_window_idx]

    @property
    def current_pane(self) -> libtmux.Pane:
        """Get the current pane."""
        current_pane_idx = self._current_pane_idx
        return self.current_window.panes[current_pane_idx]

    def capture_window(
        self, window: libtmux.Window, lines: int | None = None
    ) -> dict[str, str | list[str]]:
        """Get the output of a specific window."""
        start = None if lines is None else -lines

        # check if current pane is zoomed
        if (
            self.svr.cmd("display-message", "-p", "#{window_zoomed_flag}").stdout[0]
            == "1"
        ):
            panes = [self.current_pane]
        else:
            panes = window.panes

        pane_outputs = {}
        for pane in panes:
            pane_outputs[pane.id] = pane.capture_pane(start=start)

        return pane_outputs

    def capture_current_window(
        self, lines: int | None = None
    ) -> dict[str, str | list[str]]:
        """Get the output of the current window."""
        return self.capture_window(self.current_window, lines)

    @property
    def _current_window_idx(self) -> int:
        """Get the current window ID."""
        try:
            return int(self.svr.cmd("display-message", "-p", "#I").stdout[0])
        except Exception:
            raise TmuxCommandError("Failed to get current window ID. Is tmux running?")

    @property
    def _current_pane_idx(self) -> int:
        """Get the current pane ID."""
        try:
            return int(self.svr.cmd("display-message", "-p", "#P").stdout[0])
        except Exception:
            raise TmuxCommandError("Failed to get current pane ID. Is tmux running?")
