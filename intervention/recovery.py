"""Recovery action executor for AI intervention system.

This module executes recovery actions recommended by Claude to restore
normal replay operation. Actions are translated from high-level commands
to xdotool operations via the existing InputBackend.
"""

from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING
import logging
import re
import time

if TYPE_CHECKING:
    from replay.input_backend import InputBackend
    from replay.vscode_controller import VSCodeController

logger = logging.getLogger(__name__)


class RecoveryError(Exception):
    """Exception raised when recovery action fails."""

    def __init__(self, message: str, action: Optional[str] = None):
        """Initialize the error.

        Args:
            message: Error description.
            action: The action that failed.
        """
        self.action = action
        super().__init__(message)


@dataclass
class RecoveryResult:
    """Result of a recovery attempt.

    Attributes:
        success: Whether the action succeeded.
        action_taken: The action that was executed.
        error: Error message if failed.
        duration_ms: Time taken to execute in milliseconds.
    """
    success: bool
    action_taken: str
    error: Optional[str] = None
    duration_ms: float = 0.0


class RecoveryExecutor:
    """Executes recovery actions using the input backend.

    Translates high-level action strings from Claude into xdotool
    commands executed through the InputBackend.

    Action vocabulary:
        - "press <key>": Press single key (Escape, Return, etc.)
        - "key <combo>": Press key combination (ctrl+p, ctrl+shift+k)
        - "type <text>": Type text characters
        - "focus_vscode": Bring VS Code window to front
        - "click <x>,<y>": Click at screen coordinates
        - "wait <seconds>": Wait for specified duration

    Example:
        executor = RecoveryExecutor(input_backend, vscode_controller)
        results = executor.execute([
            "press Escape",
            "wait 0.5",
            "focus_vscode",
            "key ctrl+1"
        ])
    """

    # Mapping of action prefixes to handler methods
    ACTION_HANDLERS = {
        'press ': '_handle_key_press',
        'key ': '_handle_key_combo',
        'type ': '_handle_type',
        'focus_vscode': '_handle_focus_vscode',
        'click ': '_handle_click',
        'click_editor': '_handle_click_editor',
        'wait ': '_handle_wait',
        'close_dialog': '_handle_close_dialog',
        'open_file ': '_handle_open_file',
        'nudge_typing': '_handle_nudge_typing',
    }

    def __init__(
        self,
        input_backend: 'InputBackend',
        vscode_controller: 'VSCodeController',
        action_delay: float = 0.3,
    ):
        """Initialize the recovery executor.

        Args:
            input_backend: XdotoolBackend instance for input simulation.
            vscode_controller: VSCodeController for VS Code operations.
            action_delay: Default delay between actions in seconds.
        """
        self.input = input_backend
        self.vscode = vscode_controller
        self.action_delay = action_delay

    def execute(self, actions: List[str]) -> List[RecoveryResult]:
        """Execute a list of recovery actions in order.

        Stops on first failure to prevent cascading issues.

        Args:
            actions: List of action strings from Claude.

        Returns:
            List of RecoveryResult objects for each action attempted.
        """
        if not actions:
            logger.info("No recovery actions to execute")
            return []

        logger.info(f"Executing {len(actions)} recovery actions")
        results = []

        for i, action in enumerate(actions):
            logger.debug(f"Recovery action {i+1}/{len(actions)}: {action}")

            result = self._execute_single(action)
            results.append(result)

            if not result.success:
                logger.warning(f"Recovery action failed: {action} - {result.error}")
                # Stop on first failure
                break

            # Delay between actions (unless wait action already handled it)
            if not action.lower().startswith('wait '):
                time.sleep(self.action_delay)

        successful = sum(1 for r in results if r.success)
        logger.info(f"Recovery completed: {successful}/{len(results)} actions successful")

        return results

    def _execute_single(self, action: str) -> RecoveryResult:
        """Execute a single recovery action.

        Args:
            action: Action string to execute.

        Returns:
            RecoveryResult with success status.
        """
        start_time = time.time()
        action_lower = action.lower().strip()

        # Find matching handler
        for prefix, handler_name in self.ACTION_HANDLERS.items():
            if action_lower.startswith(prefix.lower()):
                try:
                    handler = getattr(self, handler_name)
                    # Extract argument (everything after prefix)
                    arg = action[len(prefix):].strip() if prefix.endswith(' ') else ''
                    handler(arg)

                    duration_ms = (time.time() - start_time) * 1000
                    return RecoveryResult(
                        success=True,
                        action_taken=action,
                        duration_ms=duration_ms,
                    )

                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    return RecoveryResult(
                        success=False,
                        action_taken=action,
                        error=str(e),
                        duration_ms=duration_ms,
                    )

        # No handler found
        return RecoveryResult(
            success=False,
            action_taken=action,
            error=f"Unknown action pattern: {action}",
            duration_ms=0.0,
        )

    def _handle_key_press(self, key: str) -> None:
        """Handle 'press <key>' action.

        Args:
            key: Key name (e.g., 'Escape', 'Return', 'Tab').
        """
        if not key:
            raise RecoveryError("No key specified for press action")

        logger.debug(f"Pressing key: {key}")
        self.input.key_press(key)

    def _handle_key_combo(self, combo: str) -> None:
        """Handle 'key <combo>' action.

        Args:
            combo: Key combination (e.g., 'ctrl+p', 'ctrl+shift+k').
        """
        if not combo:
            raise RecoveryError("No key combination specified")

        # Parse combo: "ctrl+p" -> ["ctrl", "p"]
        # Handle both "ctrl+p" and "ctrl p" formats
        if '+' in combo:
            keys = [k.strip() for k in combo.split('+')]
        else:
            keys = combo.split()

        if not keys:
            raise RecoveryError(f"Invalid key combination: {combo}")

        logger.debug(f"Pressing key combo: {keys}")
        self.input.key_combo(*keys)

    def _handle_type(self, text: str) -> None:
        """Handle 'type <text>' action.

        Args:
            text: Text to type.
        """
        if not text:
            raise RecoveryError("No text specified for type action")

        # Strip quotes if present
        if (text.startswith('"') and text.endswith('"')) or \
           (text.startswith("'") and text.endswith("'")):
            text = text[1:-1]

        logger.debug(f"Typing text: {text[:50]}{'...' if len(text) > 50 else ''}")
        self.input.type_text(text, delay=0.05)

    def _handle_focus_vscode(self, _: str) -> None:
        """Handle 'focus_vscode' action.

        Brings VS Code window to the front.
        """
        logger.debug("Focusing VS Code window")

        # Try using the VSCodeController's method first
        if hasattr(self.vscode, 'focus_window'):
            try:
                self.vscode.focus_window()
                return
            except Exception as e:
                logger.debug(f"VSCodeController.focus_window failed: {e}")

        # Fallback: search and activate via input backend
        if hasattr(self.input, 'search_window') and hasattr(self.input, 'activate_window'):
            window_id = self.input.search_window("Visual Studio Code")
            if window_id:
                if self.input.activate_window(window_id):
                    return
                raise RecoveryError("Failed to activate VS Code window")
            raise RecoveryError("VS Code window not found")

        raise RecoveryError("Unable to focus VS Code: no suitable method available")

    def _handle_click(self, coords: str) -> None:
        """Handle 'click <x>,<y>' action.

        Args:
            coords: Coordinates in format "x,y" or "x y".
        """
        if not coords:
            raise RecoveryError("No coordinates specified for click action")

        # Parse coordinates
        match = re.match(r'(\d+)[,\s]+(\d+)', coords)
        if not match:
            raise RecoveryError(f"Invalid coordinates format: {coords}")

        x, y = int(match.group(1)), int(match.group(2))

        logger.debug(f"Clicking at ({x}, {y})")

        if hasattr(self.input, 'mouse_move_click'):
            self.input.mouse_move_click(x, y)
        else:
            self.input.mouse_move(x, y)
            self.input.mouse_click('left')

    def _handle_wait(self, seconds: str) -> None:
        """Handle 'wait <seconds>' action.

        Args:
            seconds: Duration to wait as string.
        """
        if not seconds:
            raise RecoveryError("No duration specified for wait action")

        try:
            duration = float(seconds)
        except ValueError:
            raise RecoveryError(f"Invalid wait duration: {seconds}")

        if duration < 0 or duration > 60:
            raise RecoveryError(f"Wait duration out of range (0-60s): {duration}")

        logger.debug(f"Waiting {duration}s")
        time.sleep(duration)

    def _handle_close_dialog(self, _: str) -> None:
        """Handle 'close_dialog' action.

        Attempts to close any open dialog using multiple methods.
        """
        logger.debug("Closing dialog")

        # Try Escape key first (most common)
        self.input.key_press('Escape')
        time.sleep(0.1)

        # Press Escape again for nested dialogs
        self.input.key_press('Escape')
        time.sleep(0.1)

    def _handle_open_file(self, filename: str) -> None:
        """Handle 'open_file <filename>' action.

        Opens a file in VS Code using Ctrl+P quick open.

        Args:
            filename: File name or path to open.
        """
        if not filename:
            raise RecoveryError("No filename specified for open_file action")

        # Strip quotes
        if (filename.startswith('"') and filename.endswith('"')) or \
           (filename.startswith("'") and filename.endswith("'")):
            filename = filename[1:-1]

        logger.debug(f"Opening file: {filename}")

        # Use Ctrl+P to open quick open
        self.input.key_combo('ctrl', 'p')
        time.sleep(0.3)

        # Type filename
        self.input.type_text(filename, delay=0.03)
        time.sleep(0.3)

        # Press Enter to open
        self.input.key_press('Return')
        time.sleep(0.5)

    def _handle_click_editor(self, _: str) -> None:
        """Handle 'click_editor' action.

        Clicks in the center-ish area of the screen where the editor typically is.
        This helps regain focus when typing has stopped responding.
        """
        logger.debug("Clicking in editor area")

        # Get screen dimensions if possible, otherwise use reasonable defaults
        # Using conservative coordinates that work on 1280x720 and larger
        # Editor area is typically center-right of screen
        editor_x = 640  # Center horizontally (works for 1280+ width)
        editor_y = 360  # Upper-middle of editor area (below toolbar)

        if hasattr(self.input, 'mouse_move_click'):
            self.input.mouse_move_click(editor_x, editor_y)
        else:
            self.input.mouse_move(editor_x, editor_y)
            time.sleep(0.05)
            self.input.mouse_click('left')

        time.sleep(0.1)

    def _handle_nudge_typing(self, _: str) -> None:
        """Handle 'nudge_typing' action.

        Performs a sequence to try to unstick typing:
        1. Click in editor area
        2. Press End key (safe, moves to end of line)
        3. Small delay

        This is useful when the replay appears stuck but VS Code is responsive.
        """
        logger.debug("Nudging typing to resume")

        # Click editor to ensure focus
        self._handle_click_editor('')

        time.sleep(0.2)

        # Press End key - safe key that doesn't insert text
        # This can "wake up" xdotool or the input pipeline
        self.input.key_press('End')

        time.sleep(0.1)

        # Press Home to go back to start of line
        self.input.key_press('Home')

        time.sleep(0.1)

    def execute_preset(self, preset_name: str) -> List[RecoveryResult]:
        """Execute a predefined recovery sequence.

        Presets are common recovery patterns that bundle multiple actions.

        Args:
            preset_name: Name of the preset to execute.

        Returns:
            List of RecoveryResult objects.
        """
        presets = {
            'dismiss_dialog': [
                'press Escape',
                'wait 0.2',
                'press Escape',
            ],
            'refocus_editor': [
                'focus_vscode',
                'wait 0.3',
                'key ctrl+1',
            ],
            'close_all_dialogs': [
                'press Escape',
                'press Escape',
                'press Escape',
                'key ctrl+1',
            ],
            'reset_view': [
                'focus_vscode',
                'press Escape',
                'press Escape',
                'key ctrl+1',
                'key ctrl+Home',
            ],
            'unstick_typing': [
                'click_editor',
                'wait 0.3',
                'press Escape',
                'wait 0.2',
                'key ctrl+1',
                'wait 0.2',
                'nudge_typing',
            ],
        }

        if preset_name not in presets:
            raise RecoveryError(f"Unknown preset: {preset_name}")

        logger.info(f"Executing preset: {preset_name}")
        return self.execute(presets[preset_name])
