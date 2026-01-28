"""Upwork controller for time tracking automation.

This module provides classes for automating Upwork time tracking,
including launching the browser, selecting contracts, and clock in/out.
"""

import json
import logging
import os
import platform
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from replay.input_backend import InputBackend, InputBackendError


logger = logging.getLogger(__name__)


class UpworkNotFoundError(Exception):
    """Exception raised when Upwork window/tab cannot be found."""
    pass


class UpworkTimeoutError(Exception):
    """Exception raised when Upwork operations timeout."""
    pass


class ContractNotFoundError(Exception):
    """Exception raised when a contract cannot be found."""
    pass


class UnsupportedPlatformError(Exception):
    """Exception raised when platform is not supported for requested mode."""
    pass


class UpworkAuthenticationError(Exception):
    """Exception raised when Upwork authentication fails."""
    pass


@dataclass
class UICoordinates:
    """UI element coordinates for Upwork automation.

    Attributes:
        contract_dropdown: Contract selector dropdown position.
        memo_field: Memo/activity input field position.
        start_button: Start time tracking button position.
        stop_button: Stop time tracking button position.
        screen_width: Screen width when calibrated.
        screen_height: Screen height when calibrated.
    """
    contract_dropdown: tuple = (0, 0)
    memo_field: tuple = (0, 0)
    start_button: tuple = (0, 0)
    stop_button: tuple = (0, 0)
    screen_width: int = 1920
    screen_height: int = 1080

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UICoordinates':
        """Create UICoordinates from a dictionary.

        Args:
            data: Dictionary containing coordinate data.

        Returns:
            UICoordinates instance.
        """
        coords = cls()

        if 'contract_dropdown' in data:
            coords.contract_dropdown = (
                data['contract_dropdown'].get('x', 0),
                data['contract_dropdown'].get('y', 0),
            )

        if 'memo_field' in data:
            coords.memo_field = (
                data['memo_field'].get('x', 0),
                data['memo_field'].get('y', 0),
            )

        if 'start_button' in data:
            coords.start_button = (
                data['start_button'].get('x', 0),
                data['start_button'].get('y', 0),
            )

        if 'stop_button' in data:
            coords.stop_button = (
                data['stop_button'].get('x', 0),
                data['stop_button'].get('y', 0),
            )

        if 'screen_resolution' in data:
            coords.screen_width = data['screen_resolution'].get('width', 1920)
            coords.screen_height = data['screen_resolution'].get('height', 1080)

        return coords

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation.
        """
        return {
            'contract_dropdown': {'x': self.contract_dropdown[0], 'y': self.contract_dropdown[1]},
            'memo_field': {'x': self.memo_field[0], 'y': self.memo_field[1]},
            'start_button': {'x': self.start_button[0], 'y': self.start_button[1]},
            'stop_button': {'x': self.stop_button[0], 'y': self.stop_button[1]},
            'screen_resolution': {'width': self.screen_width, 'height': self.screen_height},
        }


class UpworkController:
    """Controller for Upwork time tracking automation.

    This class handles:
    - Launching Upwork in web browser
    - Selecting contracts
    - Setting work memos
    - Clock in/out operations
    """

    # Supported browsers
    BROWSERS = {
        'firefox': ['firefox', 'firefox-esr'],
        'chromium': ['chromium', 'chromium-browser'],
        'chrome': ['google-chrome', 'google-chrome-stable'],
    }

    # Default Upwork time tracker URL
    DEFAULT_URL = "https://www.upwork.com/ab/account-security/login"
    TRACKER_URL = "https://www.upwork.com/ab/time-tracker/v1/"

    def __init__(
        self,
        input_backend: InputBackend,
        config: Optional[Dict] = None,
    ):
        """Initialize the Upwork controller.

        Args:
            input_backend: Input backend for keyboard/mouse simulation.
            config: Optional configuration dictionary.
        """
        self.input = input_backend
        self.config = config or {}

        # Extract configuration with defaults
        upwork_config = self.config.get('upwork', {})

        self.mode = upwork_config.get('mode', 'web')
        self.browser = upwork_config.get('browser', 'firefox')
        self.url = upwork_config.get('url', self.TRACKER_URL)
        self.click_delay = upwork_config.get('click_delay', 200) / 1000.0
        self.typing_delay = upwork_config.get('typing_delay', 50) / 1000.0
        self.retry_count = upwork_config.get('retry_count', 3)
        self.ready_timeout = upwork_config.get('ready_timeout', 30)

        # Load UI coordinates
        coords_data = upwork_config.get('coordinates', {})
        self.coordinates = UICoordinates.from_dict(coords_data)

        # State tracking
        self._is_clocked_in = False
        self._current_contract: Optional[str] = None
        self._browser_window_id: Optional[str] = None

    def _is_arm64(self) -> bool:
        """Check if running on ARM64 architecture.

        Returns:
            True if ARM64, False otherwise.
        """
        machine = platform.machine().lower()
        return machine in ('aarch64', 'arm64')

    def _find_browser_command(self) -> Optional[str]:
        """Find an available browser command.

        Returns:
            Browser command or None if not found.
        """
        browser_variants = self.BROWSERS.get(self.browser, [self.browser])

        for browser_cmd in browser_variants:
            try:
                result = subprocess.run(
                    ['which', browser_cmd],
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return browser_cmd
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

        return None

    def launch_upwork(self, mode: Optional[str] = None) -> bool:
        """Launch Upwork time tracker.

        Args:
            mode: 'web' or 'desktop' (overrides config).

        Returns:
            True if successful.

        Raises:
            UnsupportedPlatformError: If desktop mode on ARM64.
            UpworkNotFoundError: If browser cannot be launched.
        """
        mode = mode or self.mode

        if mode == 'desktop':
            if self._is_arm64():
                raise UnsupportedPlatformError(
                    "Upwork desktop app is not available for ARM64. "
                    "Please use web mode instead."
                )
            return self._launch_desktop()
        else:
            return self._launch_web()

    def _launch_web(self) -> bool:
        """Launch Upwork in web browser.

        Returns:
            True if successful.

        Raises:
            UpworkNotFoundError: If browser cannot be launched.
        """
        browser_cmd = self._find_browser_command()
        if not browser_cmd:
            raise UpworkNotFoundError(
                f"Browser '{self.browser}' not found. "
                f"Install with: sudo apt install {self.browser}"
            )

        logger.info(f"Launching Upwork in {browser_cmd}")

        try:
            # Launch browser with Upwork URL
            subprocess.Popen(
                [browser_cmd, self.url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Wait for browser to open
            time.sleep(3)

            return True

        except Exception as e:
            raise UpworkNotFoundError(f"Failed to launch browser: {e}") from e

    def _launch_desktop(self) -> bool:
        """Launch Upwork desktop application.

        Returns:
            True if successful.

        Raises:
            UpworkNotFoundError: If app cannot be launched.
        """
        # Try common installation locations
        upwork_paths = [
            '/opt/Upwork/upwork',
            '/usr/bin/upwork',
            os.path.expanduser('~/.local/bin/upwork'),
        ]

        for path in upwork_paths:
            if os.path.exists(path):
                try:
                    subprocess.Popen(
                        [path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    time.sleep(5)  # Desktop app takes longer to load
                    return True
                except Exception as e:
                    logger.warning(f"Failed to launch Upwork from {path}: {e}")

        raise UpworkNotFoundError(
            "Upwork desktop app not found. Please install it or use web mode."
        )

    def is_upwork_running(self) -> bool:
        """Check if Upwork is running.

        Returns:
            True if Upwork window/tab is detected.
        """
        # Search for Upwork window
        if hasattr(self.input, 'search_window'):
            window_id = self.input.search_window('Upwork')
            if window_id:
                self._browser_window_id = window_id
                return True

        # Try wmctrl as fallback
        try:
            result = subprocess.run(
                ['wmctrl', '-l'],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.split('\n'):
                if 'Upwork' in line or 'upwork' in line.lower():
                    self._browser_window_id = line.split()[0]
                    return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return False

    def wait_for_ready(self, timeout: Optional[int] = None) -> bool:
        """Wait for Upwork to be fully loaded.

        Args:
            timeout: Timeout in seconds (default: from config).

        Returns:
            True if ready within timeout.

        Raises:
            UpworkTimeoutError: If timeout exceeded.
        """
        timeout = timeout or self.ready_timeout
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.is_upwork_running():
                logger.info("Upwork is ready")
                return True
            time.sleep(1)

        raise UpworkTimeoutError(
            f"Upwork did not become ready within {timeout} seconds"
        )

    def _focus_upwork(self) -> bool:
        """Focus the Upwork window.

        Returns:
            True if successful.
        """
        if not self._browser_window_id:
            if not self.is_upwork_running():
                return False

        if hasattr(self.input, 'activate_window'):
            return self.input.activate_window(self._browser_window_id)

        try:
            subprocess.run(
                ['wmctrl', '-i', '-a', self._browser_window_id],
                capture_output=True,
                check=True,
                timeout=5,
            )
            time.sleep(0.2)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _click_at(self, x: int, y: int, retries: int = 0) -> bool:
        """Click at screen coordinates with optional retries.

        Args:
            x: X coordinate.
            y: Y coordinate.
            retries: Number of retries (default: from config).

        Returns:
            True if successful.
        """
        retries = retries or self.retry_count

        for attempt in range(retries + 1):
            try:
                self.input.mouse_move(x, y)
                time.sleep(0.1)
                self.input.mouse_click('left')
                time.sleep(self.click_delay)
                return True
            except InputBackendError as e:
                logger.warning(f"Click attempt {attempt + 1} failed: {e}")
                if attempt < retries:
                    delay = 0.1 * (2 ** attempt)  # Exponential backoff
                    time.sleep(delay)

        return False

    def _type_text(self, text: str) -> bool:
        """Type text with configured delay.

        Args:
            text: Text to type.

        Returns:
            True if successful.
        """
        try:
            self.input.type_text(text, delay=self.typing_delay)
            return True
        except InputBackendError as e:
            logger.error(f"Failed to type text: {e}")
            return False

    def select_contract(self, contract_name: str) -> bool:
        """Select a contract from the dropdown.

        Args:
            contract_name: Contract name to select.

        Returns:
            True if successful.

        Raises:
            UpworkNotFoundError: If Upwork is not running.
            ContractNotFoundError: If contract cannot be found.
        """
        if not self._focus_upwork():
            raise UpworkNotFoundError("Cannot focus Upwork window")

        logger.info(f"Selecting contract: {contract_name}")

        # Click on contract dropdown
        x, y = self.coordinates.contract_dropdown
        if x == 0 and y == 0:
            logger.warning("Contract dropdown coordinates not calibrated")
            return False

        if not self._click_at(x, y):
            logger.error("Failed to click contract dropdown")
            return False

        time.sleep(0.5)  # Wait for dropdown to open

        # Type contract name to search/filter
        if not self._type_text(contract_name):
            return False

        time.sleep(0.3)

        # Press Enter to select
        self.input.key_press('Return')
        time.sleep(0.3)

        self._current_contract = contract_name
        logger.info(f"Contract selected: {contract_name}")

        return True

    def set_memo(self, memo: str) -> bool:
        """Set the work memo/activity description.

        Args:
            memo: Memo text.

        Returns:
            True if successful.

        Raises:
            UpworkNotFoundError: If Upwork is not running.
        """
        if not self._focus_upwork():
            raise UpworkNotFoundError("Cannot focus Upwork window")

        logger.info(f"Setting memo: {memo[:50]}...")

        # Click on memo field
        x, y = self.coordinates.memo_field
        if x == 0 and y == 0:
            logger.warning("Memo field coordinates not calibrated")
            return False

        if not self._click_at(x, y):
            logger.error("Failed to click memo field")
            return False

        time.sleep(0.2)

        # Select all existing text and replace
        self.input.key_combo('ctrl', 'a')
        time.sleep(0.1)

        # Type new memo
        # Truncate if too long (Upwork typically has a limit)
        max_length = 500
        if len(memo) > max_length:
            logger.warning(f"Memo truncated from {len(memo)} to {max_length} chars")
            memo = memo[:max_length]

        if not self._type_text(memo):
            return False

        logger.info("Memo set successfully")
        return True

    def clock_in(self) -> bool:
        """Start time tracking.

        Returns:
            True if successful.

        Raises:
            UpworkNotFoundError: If Upwork is not running.
        """
        if self._is_clocked_in:
            logger.warning("Already clocked in")
            return True

        if not self._focus_upwork():
            raise UpworkNotFoundError("Cannot focus Upwork window")

        logger.info("Clocking in...")

        # Click start button
        x, y = self.coordinates.start_button
        if x == 0 and y == 0:
            logger.warning("Start button coordinates not calibrated")
            return False

        if not self._click_at(x, y):
            logger.error("Failed to click start button")
            return False

        time.sleep(1)  # Wait for tracking to start

        self._is_clocked_in = True
        logger.info("Clocked in successfully")

        return True

    def clock_out(self) -> bool:
        """Stop time tracking.

        Returns:
            True if successful.

        Raises:
            UpworkNotFoundError: If Upwork is not running.
        """
        if not self._is_clocked_in:
            logger.warning("Not currently clocked in")
            return True

        if not self._focus_upwork():
            # Even if we can't focus, try to record that we're clocked out
            logger.error("Cannot focus Upwork window for clock out")
            self._is_clocked_in = False
            raise UpworkNotFoundError("Cannot focus Upwork window for clock out")

        logger.info("Clocking out...")

        # Click stop button
        x, y = self.coordinates.stop_button
        if x == 0 and y == 0:
            logger.warning("Stop button coordinates not calibrated")
            # Try start button position as fallback (often same button toggles)
            x, y = self.coordinates.start_button

        if not self._click_at(x, y):
            logger.error("Failed to click stop button")
            self._is_clocked_in = False  # Assume we're out to prevent billing
            return False

        time.sleep(1)  # Wait for tracking to stop

        self._is_clocked_in = False
        logger.info("Clocked out successfully")

        return True

    def is_clocked_in(self) -> bool:
        """Check if currently clocked in.

        Returns:
            True if clocked in.
        """
        return self._is_clocked_in

    def get_selected_contract(self) -> Optional[str]:
        """Get the currently selected contract.

        Returns:
            Contract name or None.
        """
        return self._current_contract

    def start_session(self, contract: str, memo: str) -> bool:
        """Start a complete time tracking session.

        This combines contract selection, memo setting, and clock in.

        Args:
            contract: Contract name.
            memo: Work description.

        Returns:
            True if successful.
        """
        logger.info(f"Starting session for contract: {contract}")

        # Ensure Upwork is running
        if not self.is_upwork_running():
            logger.info("Upwork not running, launching...")
            self.launch_upwork()
            self.wait_for_ready()

        # Select contract
        if not self.select_contract(contract):
            logger.error("Failed to select contract")
            return False

        # Set memo
        if not self.set_memo(memo):
            logger.error("Failed to set memo")
            return False

        # Clock in
        if not self.clock_in():
            logger.error("Failed to clock in")
            return False

        logger.info(f"Session started: {contract}")
        return True

    def end_session(self) -> bool:
        """End the current time tracking session.

        Returns:
            True if successful.
        """
        logger.info("Ending session")

        if not self.clock_out():
            logger.error("Failed to clock out")
            return False

        self._current_contract = None
        logger.info("Session ended")
        return True


class UpworkCalibrator:
    """Interactive calibration tool for Upwork UI coordinates.

    This class guides the user through clicking on UI elements
    to record their positions for automation.
    """

    CALIBRATION_ITEMS = [
        ('contract_dropdown', 'Click on the CONTRACT DROPDOWN'),
        ('memo_field', 'Click on the MEMO/ACTIVITY input field'),
        ('start_button', 'Click on the START/PLAY button'),
        ('stop_button', 'Click on the STOP button (if different from start)'),
    ]

    def __init__(self, input_backend: InputBackend):
        """Initialize the calibrator.

        Args:
            input_backend: Input backend for detecting clicks.
        """
        self.input = input_backend
        self.coordinates = UICoordinates()

    def _get_screen_resolution(self) -> tuple:
        """Get current screen resolution.

        Returns:
            Tuple of (width, height).
        """
        try:
            result = subprocess.run(
                ['xdpyinfo'],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.split('\n'):
                if 'dimensions:' in line:
                    # Format: "dimensions:    1920x1080 pixels"
                    parts = line.split()
                    for part in parts:
                        if 'x' in part and part[0].isdigit():
                            w, h = part.split('x')
                            return (int(w), int(h))
        except Exception as e:
            logger.warning(f"Failed to get screen resolution: {e}")

        return (1920, 1080)  # Default

    def _get_mouse_position(self) -> tuple:
        """Get current mouse position.

        Returns:
            Tuple of (x, y).
        """
        try:
            result = subprocess.run(
                ['xdotool', 'getmouselocation'],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Format: "x:123 y:456 screen:0 window:12345"
            parts = result.stdout.split()
            x = int(parts[0].split(':')[1])
            y = int(parts[1].split(':')[1])
            return (x, y)
        except Exception as e:
            logger.error(f"Failed to get mouse position: {e}")
            return (0, 0)

    def _wait_for_click(self, timeout: int = 30) -> tuple:
        """Wait for user to click and return the position.

        Args:
            timeout: Timeout in seconds.

        Returns:
            Tuple of (x, y) or (0, 0) on timeout.
        """
        print("  Click when ready...")

        # Use xdotool to detect click
        try:
            # This will wait for a mouse button event
            result = subprocess.run(
                ['xdotool', 'getmouselocation', '--shell'],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            # Wait a moment for the click
            time.sleep(0.5)

            # Get the position where they clicked
            return self._get_mouse_position()

        except subprocess.TimeoutExpired:
            print("  Timeout waiting for click")
            return (0, 0)
        except Exception as e:
            print(f"  Error: {e}")
            return (0, 0)

    def run(self) -> UICoordinates:
        """Run the interactive calibration process.

        Returns:
            Calibrated UICoordinates.
        """
        print("\n=== Upwork UI Calibration ===")
        print("This tool will guide you through recording UI element positions.")
        print("Please have Upwork open and visible.\n")

        # Get screen resolution
        width, height = self._get_screen_resolution()
        self.coordinates.screen_width = width
        self.coordinates.screen_height = height
        print(f"Screen resolution: {width}x{height}\n")

        input("Press Enter when Upwork is visible and you're ready to start...")

        for attr_name, prompt in self.CALIBRATION_ITEMS:
            print(f"\n{prompt}")

            # For stop button, allow skip if same as start
            if attr_name == 'stop_button':
                skip = input("  Press Enter to record, or 's' to skip (use same as start): ")
                if skip.lower() == 's':
                    self.coordinates.stop_button = self.coordinates.start_button
                    print(f"  Using start button position: {self.coordinates.stop_button}")
                    continue

            input("  Position your mouse and press Enter, then click...")
            time.sleep(0.5)

            pos = self._get_mouse_position()

            if pos[0] == 0 and pos[1] == 0:
                print("  Failed to record position, using (0, 0)")
            else:
                print(f"  Recorded: {pos}")

            setattr(self.coordinates, attr_name, pos)

        print("\n=== Calibration Complete ===")
        print("\nRecorded coordinates:")
        for attr_name, _ in self.CALIBRATION_ITEMS:
            pos = getattr(self.coordinates, attr_name)
            print(f"  {attr_name}: {pos}")

        return self.coordinates

    def save_to_config(
        self,
        config_path: str,
        coordinates: Optional[UICoordinates] = None,
    ) -> bool:
        """Save calibrated coordinates to a config file.

        Args:
            config_path: Path to the config file.
            coordinates: Coordinates to save (default: self.coordinates).

        Returns:
            True if successful.
        """
        coords = coordinates or self.coordinates

        try:
            import yaml

            # Load existing config if present
            config = {}
            path = Path(config_path)
            if path.exists():
                with open(path, 'r') as f:
                    config = yaml.safe_load(f) or {}

            # Update coordinates section
            if 'upwork' not in config:
                config['upwork'] = {}
            config['upwork']['coordinates'] = coords.to_dict()

            # Write back
            with open(path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)

            print(f"\nCalibration saved to: {config_path}")
            return True

        except Exception as e:
            print(f"\nFailed to save calibration: {e}")
            return False
