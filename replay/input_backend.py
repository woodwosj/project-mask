"""Input backend abstraction for keyboard and mouse simulation.

This module provides an abstract interface for input simulation and an
implementation using xdotool for X11 environments.
"""

from abc import ABC, abstractmethod
import logging
import os
import subprocess
import threading
import time
from typing import Dict, Optional


logger = logging.getLogger(__name__)


class InputBackendError(Exception):
    """Exception raised when an input backend operation fails."""

    def __init__(self, message: str, command: Optional[str] = None):
        """Initialize the error.

        Args:
            message: Error description.
            command: The failed command, if applicable.
        """
        self.command = command
        super().__init__(message)


class UnsupportedDisplayServerError(Exception):
    """Exception raised when the display server is not supported."""
    pass


class InputBackend(ABC):
    """Abstract base class for input simulation backends.

    This interface defines the contract for input simulation implementations,
    allowing different backends (xdotool, ydotool, etc.) to be swapped.
    """

    @abstractmethod
    def type_text(self, text: str, delay: float = 0.05) -> None:
        """Type text character by character.

        Args:
            text: The text to type.
            delay: Delay between keystrokes in seconds.
        """
        pass

    @abstractmethod
    def key_press(self, key: str) -> None:
        """Press and release a single key.

        Args:
            key: The key name (e.g., 'Return', 'BackSpace', 'a').
        """
        pass

    @abstractmethod
    def key_combo(self, *keys: str) -> None:
        """Press a key combination simultaneously.

        Args:
            *keys: Key names to press together (e.g., 'ctrl', 's').
        """
        pass

    @abstractmethod
    def mouse_move(self, x: int, y: int) -> None:
        """Move the mouse cursor to screen coordinates.

        Args:
            x: X coordinate.
            y: Y coordinate.
        """
        pass

    @abstractmethod
    def mouse_click(self, button: str = "left") -> None:
        """Click a mouse button at the current cursor position.

        Args:
            button: Button name ('left', 'middle', 'right').
        """
        pass


class XdotoolBackend(InputBackend):
    """Input backend implementation using xdotool for X11.

    This backend uses subprocess calls to xdotool for all input operations.
    It requires X11 display server and xdotool to be installed.
    """

    # Mapping of mouse button names to xdotool button numbers
    MOUSE_BUTTONS: Dict[str, int] = {
        'left': 1,
        'middle': 2,
        'right': 3,
        'scroll_up': 4,
        'scroll_down': 5,
    }

    # Keys that don't need translation
    SPECIAL_KEYS: set = {
        'Return', 'BackSpace', 'Tab', 'Escape', 'Delete', 'Home', 'End',
        'Page_Up', 'Page_Down', 'Up', 'Down', 'Left', 'Right', 'Insert',
        'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12',
        'space', 'ctrl', 'alt', 'shift', 'super', 'Menu',
    }

    def __init__(
        self,
        key_press_delay: float = 0.012,
        type_delay: float = 0.05,
        mouse_move_delay: float = 0.05,
        click_delay: float = 0.1,
        check_display: bool = True,
    ):
        """Initialize the xdotool backend.

        Args:
            key_press_delay: Delay after each keypress in seconds.
            type_delay: Base delay between characters when typing.
            mouse_move_delay: Delay after mouse movement.
            click_delay: Delay after mouse click.
            check_display: Whether to verify X11 session on init.

        Raises:
            UnsupportedDisplayServerError: If not running on X11.
            InputBackendError: If xdotool is not available.
        """
        self.key_press_delay = key_press_delay
        self.type_delay = type_delay
        self.mouse_move_delay = mouse_move_delay
        self.click_delay = click_delay

        # Lock for thread-safe operations
        self._lock = threading.Lock()

        # Abort flag for interruptible operations
        self._abort_requested = False

        if check_display:
            self._check_display_server()
            self._check_xdotool_available()

    def _check_display_server(self) -> None:
        """Verify the display server is X11.

        Raises:
            UnsupportedDisplayServerError: If running on Wayland.
        """
        session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()

        if session_type == 'wayland':
            raise UnsupportedDisplayServerError(
                "Wayland session detected. XdotoolBackend requires X11. "
                "Please switch to an X11 session or use a Wayland-compatible backend."
            )

        if session_type and session_type != 'x11':
            logger.warning(
                f"Unknown session type '{session_type}'. Assuming X11 compatibility."
            )
        elif not session_type:
            logger.warning(
                "XDG_SESSION_TYPE not set. Assuming X11 compatibility."
            )

    def _check_xdotool_available(self) -> None:
        """Verify xdotool is installed and available.

        Raises:
            InputBackendError: If xdotool is not found.
        """
        try:
            subprocess.run(
                ['xdotool', 'version'],
                capture_output=True,
                check=True,
                timeout=5,
            )
        except FileNotFoundError:
            raise InputBackendError(
                "xdotool not found. Please install it with: sudo apt install xdotool"
            )
        except subprocess.CalledProcessError as e:
            raise InputBackendError(
                f"xdotool verification failed: {e.stderr.decode() if e.stderr else str(e)}",
                command='xdotool version'
            )

    def _run_xdotool(self, *args: str) -> subprocess.CompletedProcess:
        """Run an xdotool command.

        Args:
            *args: Command arguments for xdotool.

        Returns:
            CompletedProcess instance with command result.

        Raises:
            InputBackendError: If the command fails.
        """
        cmd = ['xdotool'] + list(args)
        cmd_str = ' '.join(cmd)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                timeout=10,
            )
            logger.debug(f"xdotool command succeeded: {cmd_str}")
            return result
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode().strip() if e.stderr else str(e)
            raise InputBackendError(
                f"xdotool command failed: {error_msg}",
                command=cmd_str
            )
        except subprocess.TimeoutExpired:
            raise InputBackendError(
                f"xdotool command timed out",
                command=cmd_str
            )

    def _translate_key(self, key: str) -> str:
        """Translate key name to xdotool format.

        Args:
            key: Key name to translate.

        Returns:
            Key name in xdotool format.
        """
        # Common key name mappings
        key_map = {
            'enter': 'Return',
            'esc': 'Escape',
            'backspace': 'BackSpace',
            'pageup': 'Page_Up',
            'pagedown': 'Page_Down',
            'control': 'ctrl',
            'meta': 'super',
            'win': 'super',
            'windows': 'super',
        }

        lower_key = key.lower()
        if lower_key in key_map:
            return key_map[lower_key]

        # Check if it's already a valid special key
        if key in self.SPECIAL_KEYS:
            return key

        # For single lowercase letters, return as-is
        if len(key) == 1:
            return key

        return key

    def request_abort(self) -> None:
        """Request abort of current operation."""
        self._abort_requested = True

    def reset_abort(self) -> None:
        """Reset the abort flag."""
        self._abort_requested = False

    def type_text(self, text: str, delay: float = 0.05) -> None:
        """Type text character by character using xdotool.

        Args:
            text: The text to type.
            delay: Delay between keystrokes in seconds.
        """
        with self._lock:
            self._abort_requested = False

            for char in text:
                if self._abort_requested:
                    logger.info("Typing aborted by request")
                    break

                # Use xdotool type for the character
                # The --clearmodifiers flag prevents modifier key interference
                self._run_xdotool('type', '--clearmodifiers', '--delay', '0', char)

                if delay > 0:
                    time.sleep(delay)

    def key_press(self, key: str) -> None:
        """Press and release a single key using xdotool.

        Args:
            key: The key name (e.g., 'Return', 'BackSpace', 'a').
        """
        with self._lock:
            translated_key = self._translate_key(key)
            self._run_xdotool('key', '--clearmodifiers', translated_key)

            if self.key_press_delay > 0:
                time.sleep(self.key_press_delay)

    def key_combo(self, *keys: str) -> None:
        """Press a key combination using xdotool.

        Args:
            *keys: Key names to press together (e.g., 'ctrl', 's').
        """
        with self._lock:
            # Translate all keys
            translated = [self._translate_key(k) for k in keys]

            # Join with '+' for xdotool
            combo = '+'.join(translated)

            self._run_xdotool('key', '--clearmodifiers', combo)

            if self.key_press_delay > 0:
                time.sleep(self.key_press_delay)

    def mouse_move(self, x: int, y: int) -> None:
        """Move mouse cursor to screen coordinates using xdotool.

        Args:
            x: X coordinate.
            y: Y coordinate.
        """
        with self._lock:
            self._run_xdotool('mousemove', str(x), str(y))

            if self.mouse_move_delay > 0:
                time.sleep(self.mouse_move_delay)

    def mouse_click(self, button: str = "left") -> None:
        """Click a mouse button using xdotool.

        Args:
            button: Button name ('left', 'middle', 'right').

        Raises:
            InputBackendError: If the button name is invalid.
        """
        with self._lock:
            button_lower = button.lower()
            if button_lower not in self.MOUSE_BUTTONS:
                raise InputBackendError(
                    f"Invalid mouse button: {button}. "
                    f"Valid options: {', '.join(self.MOUSE_BUTTONS.keys())}"
                )

            button_num = self.MOUSE_BUTTONS[button_lower]
            self._run_xdotool('click', str(button_num))

            if self.click_delay > 0:
                time.sleep(self.click_delay)

    def mouse_move_click(self, x: int, y: int, button: str = "left") -> None:
        """Move mouse to coordinates and click.

        Args:
            x: X coordinate.
            y: Y coordinate.
            button: Button name.
        """
        self.mouse_move(x, y)
        self.mouse_click(button)

    def get_active_window(self) -> Optional[str]:
        """Get the currently active window ID.

        Returns:
            Window ID string or None if unable to determine.
        """
        try:
            result = self._run_xdotool('getactivewindow')
            return result.stdout.decode().strip()
        except InputBackendError:
            return None

    def get_active_window_name(self) -> Optional[str]:
        """Get the name/title of the currently active window.

        Returns:
            Window title or None if unable to determine.
        """
        window_id = self.get_active_window()
        if not window_id:
            return None

        try:
            result = self._run_xdotool('getwindowname', window_id)
            return result.stdout.decode().strip()
        except InputBackendError:
            return None

    def search_window(self, name_pattern: str) -> Optional[str]:
        """Search for a window by name pattern.

        Args:
            name_pattern: Window name pattern to search for.

        Returns:
            First matching window ID or None if not found.
        """
        try:
            result = self._run_xdotool('search', '--name', name_pattern)
            windows = result.stdout.decode().strip().split('\n')
            if windows and windows[0]:
                return windows[0]
            return None
        except InputBackendError:
            return None

    def activate_window(self, window_id: str) -> bool:
        """Activate (focus) a window by ID.

        Args:
            window_id: Window ID to activate.

        Returns:
            True if successful, False otherwise.
        """
        try:
            self._run_xdotool('windowactivate', '--sync', window_id)
            return True
        except InputBackendError:
            return False


def create_backend(config: Optional[dict] = None) -> InputBackend:
    """Factory function to create an appropriate input backend.

    Args:
        config: Optional configuration dictionary.

    Returns:
        An InputBackend instance.

    Raises:
        UnsupportedDisplayServerError: If no compatible backend is available.
    """
    config = config or {}
    input_config = config.get('input', {})

    # Currently only X11/xdotool is supported
    return XdotoolBackend(
        key_press_delay=input_config.get('key_press_delay', 0.012),
        type_delay=input_config.get('type_delay', 0.05),
        mouse_move_delay=input_config.get('mouse_move_delay', 0.05),
        click_delay=input_config.get('click_delay', 0.1),
    )
