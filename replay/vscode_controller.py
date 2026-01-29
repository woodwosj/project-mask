"""VS Code controller for window management and code typing simulation.

This module provides functions to control VS Code via keyboard shortcuts
and simulate human-like typing behavior.
"""

import logging
import os
import random
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional, Set, Union

from replay.input_backend import InputBackend, InputBackendError


logger = logging.getLogger(__name__)


class VSCodeNotFoundError(Exception):
    """Exception raised when VS Code window cannot be found."""
    pass


class ConfigurationError(Exception):
    """Exception raised when configuration is invalid."""
    pass


class VSCodeController:
    """Controller for VS Code window management and code input.

    This class handles:
    - Finding and focusing VS Code windows
    - File navigation (open file, goto line)
    - Human-like typing simulation with typos and corrections
    - Line operations (delete, select)
    """

    # Common bigrams that are typed faster due to muscle memory
    FAST_BIGRAMS: Set[str] = {
        'th', 'he', 'in', 'er', 'an', 'on', 'or', 're', 'ed', 'nd',
        'ha', 'at', 'en', 'es', 'of', 'nt', 'ea', 'ti', 'to', 'it',
        'st', 'io', 'le', 'is', 'ou', 'ar', 'as', 'de', 'rt', 'ng',
    }

    # Adjacent keys on QWERTY keyboard for typo simulation
    ADJACENT_KEYS: Dict[str, str] = {
        'a': 'qwsz', 'b': 'vghn', 'c': 'xdfv', 'd': 'erfcxs',
        'e': 'wrsdf', 'f': 'rtgvcd', 'g': 'tyhbvf', 'h': 'yujnbg',
        'i': 'uojkl', 'j': 'uikmnh', 'k': 'ioljm', 'l': 'opk',
        'm': 'njk', 'n': 'bhjm', 'o': 'iplk', 'p': 'ol',
        'q': 'wa', 'r': 'etdf', 's': 'wedxza', 't': 'ryfg',
        'u': 'yihj', 'v': 'cfgb', 'w': 'qeas', 'x': 'zsdc',
        'y': 'tugh', 'z': 'asx',
        '1': '2q', '2': '13qw', '3': '24we', '4': '35er',
        '5': '46rt', '6': '57ty', '7': '68yu', '8': '79ui',
        '9': '80io', '0': '9p',
    }

    # Characters that might cause typos (skip punctuation and special chars)
    TYPO_CANDIDATES: Set[str] = set('abcdefghijklmnopqrstuvwxyz0123456789')

    def __init__(
        self,
        input_backend: InputBackend,
        config: Optional[Dict] = None,
        project_root: Optional[Union[str, Path]] = None,
    ):
        """Initialize the VS Code controller.

        Args:
            input_backend: Input backend instance for keyboard/mouse simulation.
            config: Optional configuration dictionary.
            project_root: Root directory of the project for absolute path resolution.

        Raises:
            ConfigurationError: If configuration values are invalid.
        """
        self.input = input_backend
        self.config = config or {}
        self.project_root = Path(project_root) if project_root else None

        # Extract configuration with defaults
        vscode_config = self.config.get('vscode', {})
        replay_config = self.config.get('replay', {})

        # VS Code specific settings
        self.window_title_pattern = vscode_config.get(
            'window_title_pattern', 'Visual Studio Code'
        )
        self.quick_open_delay = vscode_config.get('quick_open_delay', 300) / 1000.0
        self.goto_line_delay = vscode_config.get('goto_line_delay', 200) / 1000.0
        self.save_delay = vscode_config.get('save_delay', 500) / 1000.0
        self.file_load_delay = vscode_config.get('file_load_delay', 500) / 1000.0
        self.file_open_retries = vscode_config.get('file_open_retries', 1)

        # Typing simulation settings
        self.base_wpm = replay_config.get('base_wpm', 85)
        self.wpm_variance = replay_config.get('wpm_variance', 0.2)
        self.typo_probability = replay_config.get('typo_probability', 0.02)
        self.typo_correction_probability = replay_config.get('typo_correction_probability', 0.95)
        self.thinking_pause_probability = replay_config.get('thinking_pause_probability', 0.10)
        self.thinking_pause_min = replay_config.get('thinking_pause_min', 3.0)
        self.thinking_pause_max = replay_config.get('thinking_pause_max', 8.0)
        self.fatigue_factor = replay_config.get('fatigue_factor', 0.0005)
        self.bigram_acceleration = replay_config.get('bigram_acceleration', True)
        self.bigram_factor = replay_config.get('bigram_factor', 0.6)

        # State tracking
        self._window_id: Optional[str] = None
        self._chars_typed = 0
        self._abort_requested = False

        # Validate configuration
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate configuration values.

        Raises:
            ConfigurationError: If any configuration value is invalid.
        """
        if self.base_wpm <= 0:
            raise ConfigurationError(f"base_wpm must be positive, got {self.base_wpm}")

        if not 0 <= self.typo_probability <= 1:
            raise ConfigurationError(
                f"typo_probability must be between 0 and 1, got {self.typo_probability}"
            )

        if not 0 <= self.typo_correction_probability <= 1:
            raise ConfigurationError(
                f"typo_correction_probability must be between 0 and 1, "
                f"got {self.typo_correction_probability}"
            )

        if not 0 <= self.thinking_pause_probability <= 1:
            raise ConfigurationError(
                f"thinking_pause_probability must be between 0 and 1, "
                f"got {self.thinking_pause_probability}"
            )

        if self.thinking_pause_min < 0 or self.thinking_pause_max < self.thinking_pause_min:
            raise ConfigurationError(
                f"Invalid thinking pause range: [{self.thinking_pause_min}, "
                f"{self.thinking_pause_max}]"
            )

    def request_abort(self) -> None:
        """Request abort of current operation."""
        self._abort_requested = True
        self.input.request_abort()

    def reset_abort(self) -> None:
        """Reset the abort flag."""
        self._abort_requested = False
        self.input.reset_abort()

    def find_vscode_window(self) -> Optional[str]:
        """Find VS Code window by title pattern.

        Returns:
            Window ID if found, None otherwise.
        """
        try:
            # Try xdotool search first
            if hasattr(self.input, 'search_window'):
                window_id = self.input.search_window(self.window_title_pattern)
                if window_id:
                    return window_id

            # Fallback to wmctrl
            result = subprocess.run(
                ['wmctrl', '-l'],
                capture_output=True,
                text=True,
                timeout=5,
            )

            for line in result.stdout.strip().split('\n'):
                if self.window_title_pattern in line:
                    window_id = line.split()[0]
                    logger.debug(f"Found VS Code window: {window_id}")
                    return window_id

            return None

        except FileNotFoundError:
            logger.warning("wmctrl not found, using xdotool only")
            return None
        except subprocess.TimeoutExpired:
            logger.warning("Window search timed out")
            return None

    def focus_window(self) -> bool:
        """Focus the VS Code window.

        Returns:
            True if successfully focused, False otherwise.

        Raises:
            VSCodeNotFoundError: If VS Code window cannot be found.
        """
        window_id = self.find_vscode_window()

        if not window_id:
            raise VSCodeNotFoundError(
                f"VS Code window not found. Pattern: '{self.window_title_pattern}'. "
                "Please ensure VS Code is running."
            )

        self._window_id = window_id

        # Try to activate the window
        try:
            if hasattr(self.input, 'activate_window'):
                if self.input.activate_window(window_id):
                    time.sleep(0.1)  # Brief pause for window to settle
                    return True

            # Fallback to wmctrl
            subprocess.run(
                ['wmctrl', '-i', '-a', window_id],
                capture_output=True,
                check=True,
                timeout=5,
            )
            time.sleep(0.1)
            return True

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Failed to focus window: {e}")
            return False

    def is_vscode_focused(self) -> bool:
        """Check if VS Code is the currently focused window.

        Returns:
            True if VS Code is focused, False otherwise.
        """
        if hasattr(self.input, 'get_active_window_name'):
            active_name = self.input.get_active_window_name()
            if active_name:
                return self.window_title_pattern in active_name

        # Fallback: just verify window exists
        return self.find_vscode_window() is not None

    def _ensure_focused(self) -> None:
        """Ensure VS Code is focused before operations.

        Raises:
            VSCodeNotFoundError: If unable to focus VS Code.
        """
        if not self.is_vscode_focused():
            if not self.focus_window():
                raise VSCodeNotFoundError(
                    "Unable to focus VS Code window. Please ensure VS Code is running."
                )

    def open_file(self, path: str) -> bool:
        """Open a file in VS Code reliably.

        Uses `code --goto` command for reliable file opening, then ensures
        focus is on the editor and clears any existing content.

        Args:
            path: File path to open (relative or absolute).

        Returns:
            True if successful.

        Raises:
            VSCodeNotFoundError: If VS Code is not available.
        """
        # Resolve to absolute path
        if os.path.isabs(path):
            full_path = Path(path)
        elif self.project_root:
            full_path = self.project_root / path
        else:
            full_path = Path(path).resolve()

        logger.info(f"Opening file via code command: {full_path}")

        # Use code --goto to open the file at line 1
        # This is more reliable than Ctrl+P for new/empty files
        try:
            subprocess.run(
                ['code', '--goto', f'{full_path}:1:1'],
                capture_output=True,
                timeout=10,
                check=False,  # Don't fail if VS Code returns non-zero
            )
        except subprocess.TimeoutExpired:
            logger.warning("code command timed out, continuing anyway")
        except FileNotFoundError:
            logger.error("code command not found, falling back to Ctrl+P")
            return self._open_file_fallback(path)

        # Wait for file to open
        time.sleep(2.0)

        # Focus VS Code window
        self._ensure_focused()
        time.sleep(0.3)

        # Press Escape multiple times to close any dialogs
        for _ in range(3):
            self.input.key_press('Escape')
            time.sleep(0.1)

        # Ensure we're in the editor (not sidebar or terminal)
        # Ctrl+1 focuses the first editor group
        self.input.key_combo('ctrl', '1')
        time.sleep(0.2)

        # Go to line 1, column 1
        self.input.key_combo('ctrl', 'g')
        time.sleep(0.2)
        self.input.type_text('1', delay=0.02)
        self.input.key_press('Return')
        time.sleep(0.2)

        # Select all and delete to clear any existing content
        self.input.key_combo('ctrl', 'a')
        time.sleep(0.1)
        self.input.key_press('Delete')
        time.sleep(0.1)

        # Now we're at an empty file ready for typing
        logger.info(f"File opened and cleared: {full_path}")
        return True

    def _open_file_fallback(self, path: str) -> bool:
        """Fallback file opening using Ctrl+P.

        Args:
            path: File path to open.

        Returns:
            True if successful.
        """
        self._ensure_focused()

        logger.info(f"Opening file via Ctrl+P: {path}")

        # Press Escape to close any open dialogs
        self.input.key_press('Escape')
        time.sleep(0.2)

        # Press Ctrl+P to open Quick Open
        self.input.key_combo('ctrl', 'p')
        time.sleep(self.quick_open_delay + 0.5)

        # Clear any existing text
        self.input.key_combo('ctrl', 'a')
        time.sleep(0.05)

        # Type the file path
        self.input.type_text(path, delay=0.03)
        time.sleep(0.5)

        # Press Enter to open
        self.input.key_press('Return')
        time.sleep(self.file_load_delay + 1.0)

        # Focus editor
        self.input.key_combo('ctrl', '1')
        time.sleep(0.2)

        return True

    def goto_line(self, line_number: int) -> bool:
        """Navigate to a specific line number using Ctrl+G.

        Args:
            line_number: Line number to navigate to.

        Returns:
            True if successful.

        Raises:
            VSCodeNotFoundError: If VS Code is not available.
        """
        self._ensure_focused()

        logger.debug(f"Going to line: {line_number}")

        # Press Ctrl+G to open Go to Line dialog
        self.input.key_combo('ctrl', 'g')
        time.sleep(self.goto_line_delay)

        # Type the line number
        self.input.type_text(str(line_number), delay=0.02)
        time.sleep(0.05)

        # Press Enter to navigate
        self.input.key_press('Return')
        time.sleep(0.1)

        return True

    def save_file(self) -> bool:
        """Save the current file using Ctrl+S.

        Returns:
            True if successful.
        """
        self._ensure_focused()

        logger.debug("Saving file")

        self.input.key_combo('ctrl', 's')
        time.sleep(self.save_delay)

        return True

    def _calculate_keystroke_delay(
        self,
        char: str,
        prev_char: Optional[str] = None,
    ) -> float:
        """Calculate delay before typing a character based on human patterns.

        Args:
            char: The character to be typed.
            prev_char: The previous character typed.

        Returns:
            Delay in seconds before typing the character.
        """
        # Base delay from WPM (assuming 5 chars per word average)
        base_delay = 60.0 / (self.base_wpm * 5)

        # Apply Gaussian variance
        variance = base_delay * self.wpm_variance
        delay = random.gauss(base_delay, variance)

        # Clamp to reasonable range
        delay = max(0.01, min(delay, base_delay * 3))

        # Bigram acceleration for common pairs
        if self.bigram_acceleration and prev_char:
            bigram = (prev_char + char).lower()
            if bigram in self.FAST_BIGRAMS:
                delay *= self.bigram_factor

        # Fatigue modeling - gradually slow down
        fatigue_multiplier = 1.0 + (self._chars_typed * self.fatigue_factor)
        delay *= fatigue_multiplier

        return delay

    def _should_inject_typo(self, char: str) -> bool:
        """Determine if a typo should be injected for this character.

        Args:
            char: The character being typed.

        Returns:
            True if a typo should be injected.
        """
        if char.lower() not in self.TYPO_CANDIDATES:
            return False

        return random.random() < self.typo_probability

    def _get_typo_char(self, char: str) -> str:
        """Get an adjacent key for typo simulation.

        Args:
            char: The intended character.

        Returns:
            An adjacent character for the typo.
        """
        lower_char = char.lower()

        if lower_char in self.ADJACENT_KEYS:
            adjacent = self.ADJACENT_KEYS[lower_char]
            typo = random.choice(adjacent)

            # Preserve case
            if char.isupper():
                return typo.upper()
            return typo

        # No adjacent keys defined, return a random common typo
        return random.choice('aeiou')

    def _should_correct_typo(self) -> bool:
        """Determine if a typo should be corrected.

        Returns:
            True if the typo should be corrected.
        """
        return random.random() < self.typo_correction_probability

    def _should_pause_to_think(self, char: str) -> bool:
        """Determine if a thinking pause should occur.

        Pauses are more likely at semantic boundaries (end of line, punctuation).

        Args:
            char: The character just typed.

        Returns:
            True if a thinking pause should occur.
        """
        # Base probability
        pause_prob = self.thinking_pause_probability

        # Increase probability at semantic boundaries
        if char in '.\n;{}()':
            pause_prob *= 2

        # Decrease probability mid-word
        if char.isalnum():
            pause_prob *= 0.5

        return random.random() < pause_prob

    def _get_thinking_pause_duration(self) -> float:
        """Get a random thinking pause duration.

        Returns:
            Pause duration in seconds.
        """
        return random.uniform(self.thinking_pause_min, self.thinking_pause_max)

    def type_code(
        self,
        text: str,
        wpm: Optional[int] = None,
        typo_probability: Optional[float] = None,
    ) -> bool:
        """Type code with human-like patterns including typos and corrections.

        Args:
            text: The code text to type.
            wpm: Override base WPM for this call.
            typo_probability: Override typo probability for this call.

        Returns:
            True if completed successfully, False if aborted.

        Raises:
            VSCodeNotFoundError: If VS Code is not available.
        """
        self._ensure_focused()
        self.reset_abort()

        # Apply overrides
        original_wpm = self.base_wpm
        original_typo_prob = self.typo_probability

        if wpm is not None:
            self.base_wpm = wpm
        if typo_probability is not None:
            self.typo_probability = typo_probability

        logger.info(f"Typing {len(text)} characters at ~{self.base_wpm} WPM")

        try:
            prev_char = None

            for i, char in enumerate(text):
                if self._abort_requested:
                    logger.info("Typing aborted")
                    return False

                # Calculate delay based on human patterns
                delay = self._calculate_keystroke_delay(char, prev_char)

                # Check for thinking pause (before typing)
                if prev_char and self._should_pause_to_think(prev_char):
                    pause_duration = self._get_thinking_pause_duration()
                    logger.debug(f"Thinking pause: {pause_duration:.1f}s")
                    time.sleep(pause_duration)

                # Wait before typing
                time.sleep(delay)

                # Check for typo injection
                if self._should_inject_typo(char):
                    typo_char = self._get_typo_char(char)
                    logger.debug(f"Injecting typo: '{char}' -> '{typo_char}'")

                    # Type the wrong character
                    self._type_single_char(typo_char)
                    self._chars_typed += 1

                    # Maybe correct it
                    if self._should_correct_typo():
                        # Brief pause before noticing the mistake
                        time.sleep(random.uniform(0.1, 0.3))

                        # Backspace and correct
                        self.input.key_press('BackSpace')
                        time.sleep(random.uniform(0.05, 0.1))
                        self._type_single_char(char)
                    # else: leave the typo for realism
                else:
                    # Type the correct character
                    self._type_single_char(char)

                self._chars_typed += 1
                prev_char = char

            return True

        finally:
            # Restore original settings
            self.base_wpm = original_wpm
            self.typo_probability = original_typo_prob

    def _type_single_char(self, char: str) -> None:
        """Type a single character, handling special characters.

        Args:
            char: Character to type.
        """
        if char == '\n':
            self.input.key_press('Return')
            # Cancel VS Code's auto-indent by going to column 0 and clearing
            time.sleep(0.05)
            self.input.key_press('Home')
            time.sleep(0.02)
            # Select any auto-inserted indentation and delete it
            self.input.key_combo('shift', 'End')
            time.sleep(0.02)
            self.input.key_press('Delete')
            time.sleep(0.02)
        elif char == '\t':
            self.input.key_press('Tab')
        else:
            self.input.type_text(char, delay=0)

    def delete_lines(self, start_line: int, end_line: int) -> bool:
        """Delete a range of lines.

        Args:
            start_line: First line to delete.
            end_line: Last line to delete (inclusive).

        Returns:
            True if successful.

        Raises:
            VSCodeNotFoundError: If VS Code is not available.
        """
        self._ensure_focused()

        logger.debug(f"Deleting lines {start_line}-{end_line}")

        # Go to the start line
        self.goto_line(start_line)
        time.sleep(0.1)

        # Calculate number of lines to delete
        num_lines = end_line - start_line + 1

        if num_lines == 1:
            # Delete single line with Ctrl+Shift+K
            self.input.key_combo('ctrl', 'shift', 'k')
        else:
            # Select multiple lines and delete
            # First, go to beginning of line
            self.input.key_press('Home')
            time.sleep(0.05)

            # Select down to end line
            for _ in range(num_lines):
                self.input.key_combo('shift', 'Down')
                time.sleep(0.02)

            # Delete selection
            self.input.key_press('BackSpace')

        time.sleep(0.1)
        return True

    def select_line(self) -> bool:
        """Select the current line using Ctrl+L.

        Returns:
            True if successful.
        """
        self._ensure_focused()

        self.input.key_combo('ctrl', 'l')
        time.sleep(0.05)

        return True

    def insert_line_below(self) -> bool:
        """Insert a new line below the current line.

        Returns:
            True if successful.
        """
        self._ensure_focused()

        self.input.key_press('End')
        time.sleep(0.02)
        self.input.key_press('Return')
        time.sleep(0.02)

        return True

    def insert_line_above(self) -> bool:
        """Insert a new line above the current line.

        Returns:
            True if successful.
        """
        self._ensure_focused()

        # VS Code shortcut for insert line above
        self.input.key_combo('ctrl', 'shift', 'Return')
        time.sleep(0.02)

        return True

    def undo(self) -> bool:
        """Undo the last action using Ctrl+Z.

        Returns:
            True if successful.
        """
        self._ensure_focused()

        self.input.key_combo('ctrl', 'z')
        time.sleep(0.1)

        return True

    def close_dialogs(self) -> bool:
        """Close any open dialogs by pressing Escape.

        Returns:
            True if successful.
        """
        self.input.key_press('Escape')
        time.sleep(0.05)
        self.input.key_press('Escape')
        time.sleep(0.05)

        return True

    def reset_typing_state(self) -> None:
        """Reset typing state counters (e.g., fatigue)."""
        self._chars_typed = 0
