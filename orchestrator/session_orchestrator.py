"""Session orchestrator for coordinating replay sessions with Upwork time tracking.

This module is the main daemon that:
- Polls git for new replay sessions
- Coordinates the full workflow: clock in -> replay -> clock out
- Handles signals for graceful shutdown
- GUARANTEES clock-out on any failure or abort
"""

import atexit
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from replay.input_backend import XdotoolBackend, create_backend
from replay.vscode_controller import VSCodeController, VSCodeNotFoundError
from replay.replay_engine import (
    ReplayEngine,
    ReplaySession,
    AbortRequested,
    SessionNotFoundError,
    SessionParseError,
    SessionValidationError,
    load_session,
)
from upwork.upwork_controller import (
    UpworkController,
    UpworkNotFoundError,
    UpworkTimeoutError,
)
from config import load_config


logger = logging.getLogger(__name__)


class GitSyncError(Exception):
    """Exception raised when git operations fail."""
    pass


class SessionOrchestrator:
    """Orchestrator for replay sessions with Upwork time tracking.

    This class coordinates the complete workflow:
    1. Poll git for new sessions
    2. Load and validate sessions
    3. Clock in to Upwork
    4. Execute replay
    5. Clock out from Upwork (GUARANTEED)
    6. Mark session as processed

    The clock-out guarantee is implemented via:
    - try-finally blocks around all replay operations
    - atexit handler for emergency cleanup
    - Signal handlers for graceful shutdown
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[str] = None,
    ):
        """Initialize the session orchestrator.

        Args:
            config: Configuration dictionary (if not provided, loads from file).
            config_path: Path to config file (if config not provided).
        """
        # Load configuration
        if config is None:
            config = load_config(config_path)
        self.config = config

        # Extract orchestrator config
        orch_config = config.get('orchestrator', {})
        logging_config = config.get('logging', {})

        # Configuration values
        self.poll_interval = orch_config.get('poll_interval', 300)
        self.replay_dir = orch_config.get('replay_dir', '.replay')
        self.processed_file = orch_config.get('processed_file', '.replay/.processed')
        self.git_remote = orch_config.get('git', {}).get('remote', 'origin')
        self.git_branch = orch_config.get('git', {}).get('branch', 'main')
        self.max_consecutive_failures = orch_config.get('max_consecutive_failures', 3)
        self.failure_pause = orch_config.get('failure_pause', 600)

        # Initialize logging
        self._setup_logging(logging_config)

        # Initialize components (lazy - created when needed)
        self._input_backend: Optional[XdotoolBackend] = None
        self._vscode_controller: Optional[VSCodeController] = None
        self._replay_engine: Optional[ReplayEngine] = None
        self._upwork_controller: Optional[UpworkController] = None

        # State tracking
        self._shutdown_requested = False
        self._is_clocked_in = False
        self._current_session: Optional[ReplaySession] = None
        self._consecutive_failures = 0
        self._processed_sessions: Set[str] = set()

        # Register signal handlers
        self._register_signal_handlers()

        # Register emergency cleanup
        atexit.register(self._emergency_cleanup)

        logger.info("Session orchestrator initialized")

    def _setup_logging(self, logging_config: Dict[str, Any]) -> None:
        """Set up logging configuration.

        Args:
            logging_config: Logging configuration dictionary.
        """
        log_file = logging_config.get('file', 'session.log')
        log_level = logging_config.get('level', 'INFO')
        max_bytes = logging_config.get('max_bytes', 10485760)
        backup_count = logging_config.get('backup_count', 5)
        log_format = logging_config.get(
            'format',
            '%(asctime)s %(levelname)s [%(name)s] %(message)s'
        )
        date_format = logging_config.get('date_format', '%Y-%m-%d %H:%M:%S')

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Add rotating file handler
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setFormatter(logging.Formatter(log_format, date_format))
        root_logger.addHandler(file_handler)

        # Add console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(log_format, date_format))
        root_logger.addHandler(console_handler)

    def _register_signal_handlers(self) -> None:
        """Register handlers for graceful shutdown signals."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Optional: SIGHUP for config reload
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, self._sighup_handler)

        # Optional: SIGUSR1 for immediate poll
        if hasattr(signal, 'SIGUSR1'):
            signal.signal(signal.SIGUSR1, self._sigusr1_handler)

        logger.debug("Signal handlers registered")

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals (SIGTERM, SIGINT).

        Args:
            signum: Signal number.
            frame: Current stack frame.
        """
        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name}, initiating graceful shutdown")
        self._shutdown_requested = True

        # Request abort of any ongoing replay
        if self._replay_engine:
            self._replay_engine.request_abort()

    def _sighup_handler(self, signum: int, frame: Any) -> None:
        """Handle SIGHUP for configuration reload.

        Args:
            signum: Signal number.
            frame: Current stack frame.
        """
        logger.info("Received SIGHUP, reloading configuration")
        try:
            self.config = load_config()
            # Update relevant settings
            orch_config = self.config.get('orchestrator', {})
            self.poll_interval = orch_config.get('poll_interval', 300)
            logger.info("Configuration reloaded successfully")
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")

    def _sigusr1_handler(self, signum: int, frame: Any) -> None:
        """Handle SIGUSR1 for immediate poll trigger.

        Args:
            signum: Signal number.
            frame: Current stack frame.
        """
        logger.info("Received SIGUSR1, triggering immediate poll")
        # The main loop will check this and poll immediately

    def _emergency_cleanup(self) -> None:
        """Emergency cleanup handler called on exit.

        This is the last line of defense to ensure we're clocked out.
        """
        if self._is_clocked_in:
            logger.warning("Emergency cleanup: attempting clock out")
            try:
                if self._upwork_controller:
                    self._upwork_controller.clock_out()
                    logger.info("Emergency clock out successful")
            except Exception as e:
                logger.error(f"Emergency clock out failed: {e}")
            finally:
                self._is_clocked_in = False

    def _get_input_backend(self) -> XdotoolBackend:
        """Get or create the input backend.

        Returns:
            XdotoolBackend instance.
        """
        if self._input_backend is None:
            self._input_backend = create_backend(self.config)
        return self._input_backend

    def _get_vscode_controller(self) -> VSCodeController:
        """Get or create the VS Code controller.

        Returns:
            VSCodeController instance.
        """
        if self._vscode_controller is None:
            self._vscode_controller = VSCodeController(
                self._get_input_backend(),
                self.config,
            )
        return self._vscode_controller

    def _get_replay_engine(self) -> ReplayEngine:
        """Get or create the replay engine.

        Returns:
            ReplayEngine instance.
        """
        if self._replay_engine is None:
            self._replay_engine = ReplayEngine(
                self._get_vscode_controller(),
                self.config,
            )
        return self._replay_engine

    def _get_upwork_controller(self) -> UpworkController:
        """Get or create the Upwork controller.

        Returns:
            UpworkController instance.
        """
        if self._upwork_controller is None:
            self._upwork_controller = UpworkController(
                self._get_input_backend(),
                self.config,
            )
        return self._upwork_controller

    def pull_latest(self) -> bool:
        """Pull latest changes from git remote.

        Returns:
            True if successful.

        Raises:
            GitSyncError: If git operations fail.
        """
        logger.info(f"Pulling latest from {self.git_remote}/{self.git_branch}")

        try:
            # Fetch from remote
            result = subprocess.run(
                ['git', 'fetch', self.git_remote],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise GitSyncError(f"git fetch failed: {result.stderr}")

            # Reset to remote branch
            result = subprocess.run(
                ['git', 'reset', '--hard', f'{self.git_remote}/{self.git_branch}'],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise GitSyncError(f"git reset failed: {result.stderr}")

            logger.info("Git pull successful")
            return True

        except subprocess.TimeoutExpired:
            raise GitSyncError("Git operation timed out")
        except FileNotFoundError:
            raise GitSyncError("Git is not installed")

    def _load_processed_sessions(self) -> Set[str]:
        """Load the set of already-processed session IDs.

        Returns:
            Set of processed session IDs.
        """
        processed_path = Path(self.processed_file)

        if not processed_path.exists():
            return set()

        try:
            with open(processed_path, 'r') as f:
                return set(line.strip() for line in f if line.strip())
        except IOError as e:
            logger.warning(f"Failed to load processed sessions: {e}")
            return set()

    def _mark_session_processed(self, session_id: str) -> None:
        """Mark a session as processed.

        Args:
            session_id: Session ID to mark.
        """
        self._processed_sessions.add(session_id)

        processed_path = Path(self.processed_file)
        processed_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(processed_path, 'a') as f:
                f.write(f"{session_id}\n")
            logger.debug(f"Marked session as processed: {session_id}")
        except IOError as e:
            logger.error(f"Failed to mark session as processed: {e}")

    def find_pending_sessions(self) -> List[Path]:
        """Find pending replay session files.

        Returns:
            List of session file paths, sorted by timestamp (oldest first).
        """
        replay_path = Path(self.replay_dir)

        if not replay_path.exists():
            logger.debug(f"Replay directory does not exist: {replay_path}")
            return []

        # Load processed sessions
        processed = self._load_processed_sessions()
        self._processed_sessions = processed

        # Find session files
        session_files = list(replay_path.glob('session_*.json'))

        # Filter out processed sessions
        pending = []
        for session_file in session_files:
            # Extract session ID from filename
            session_id = session_file.stem  # e.g., "session_20260128_143022"
            if session_id not in processed:
                pending.append(session_file)

        # Sort by name (which includes timestamp)
        pending.sort(key=lambda p: p.name)

        if pending:
            logger.info(f"Found {len(pending)} pending sessions")
        else:
            logger.debug("No pending sessions")

        return pending

    def process_session(self, session_path: Path) -> bool:
        """Process a single replay session.

        This method implements the CRITICAL clock-out guarantee via try-finally.

        Args:
            session_path: Path to the session JSON file.

        Returns:
            True if successful, False if failed.
        """
        session: Optional[ReplaySession] = None
        upwork = self._get_upwork_controller()

        try:
            # Load the session
            logger.info(f"Loading session: {session_path}")
            session = load_session(session_path)
            self._current_session = session

            logger.info(
                f"Processing session '{session.session_id}': "
                f"contract='{session.contract_id}', files={len(session.files)}"
            )

            # Check for shutdown before starting
            if self._shutdown_requested:
                logger.info("Shutdown requested, skipping session")
                return False

            # Clock in to Upwork
            logger.info(f"Clocking in: contract='{session.contract_id}'")
            if not upwork.start_session(session.contract_id, session.memo):
                logger.error("Failed to start Upwork session")
                return False

            self._is_clocked_in = True
            logger.info(
                f"CLOCK IN: session={session.session_id}, "
                f"contract={session.contract_id}"
            )

            # Execute the replay
            # THIS IS WHERE THE CRITICAL TRY-FINALLY BEGINS
            try:
                replay_engine = self._get_replay_engine()

                def progress_callback(message: str, current: int, total: int) -> None:
                    logger.debug(f"[{current}/{total}] {message}")

                success = replay_engine.execute(session, progress_callback)

                if not success:
                    logger.warning("Replay did not complete fully")
                    return False

            except AbortRequested:
                logger.warning("Replay was aborted")
                return False

            except VSCodeNotFoundError as e:
                logger.error(f"VS Code error during replay: {e}")
                return False

            except Exception as e:
                logger.exception(f"Error during replay: {e}")
                return False

            finally:
                # GUARANTEED CLOCK OUT
                logger.info(f"Clocking out: session={session.session_id}")
                try:
                    upwork.clock_out()
                    logger.info(
                        f"CLOCK OUT: session={session.session_id}, "
                        f"contract={session.contract_id}"
                    )
                except Exception as e:
                    logger.error(f"CRITICAL: Clock out failed: {e}")
                    # Even if clock_out() raises, mark as clocked out
                    # to prevent infinite retries
                finally:
                    self._is_clocked_in = False

            # Mark session as processed (only on success)
            self._mark_session_processed(session.session_id)

            logger.info(f"Session completed successfully: {session.session_id}")
            self._consecutive_failures = 0
            return True

        except (SessionNotFoundError, SessionParseError, SessionValidationError) as e:
            logger.error(f"Session load error: {e}")
            return False

        except UpworkNotFoundError as e:
            logger.error(f"Upwork error: {e}")
            # Make sure we're marked as clocked out
            self._is_clocked_in = False
            return False

        except Exception as e:
            logger.exception(f"Unexpected error processing session: {e}")
            # Ensure clock out on any unexpected error
            if self._is_clocked_in:
                try:
                    upwork.clock_out()
                except Exception:
                    pass
                finally:
                    self._is_clocked_in = False
            return False

        finally:
            self._current_session = None

    def run_once(self) -> int:
        """Run a single poll cycle.

        Returns:
            Number of sessions processed.
        """
        if self._shutdown_requested:
            return 0

        processed_count = 0

        # Pull latest from git
        try:
            self.pull_latest()
        except GitSyncError as e:
            logger.error(f"Git sync failed, continuing with local sessions: {e}")

        # Find pending sessions
        pending = self.find_pending_sessions()

        if not pending:
            logger.debug("No pending sessions to process")
            return 0

        # Process each session
        for session_path in pending:
            if self._shutdown_requested:
                logger.info("Shutdown requested, stopping session processing")
                break

            success = self.process_session(session_path)

            if success:
                processed_count += 1
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1
                logger.warning(
                    f"Session failed ({self._consecutive_failures} consecutive failures)"
                )

                # Check for too many failures
                if self._consecutive_failures >= self.max_consecutive_failures:
                    logger.error(
                        f"Max consecutive failures reached ({self.max_consecutive_failures}), "
                        f"pausing for {self.failure_pause} seconds"
                    )
                    self._interruptible_sleep(self.failure_pause)
                    self._consecutive_failures = 0

            # Brief pause between sessions
            if not self._shutdown_requested and pending.index(session_path) < len(pending) - 1:
                time.sleep(2)

        return processed_count

    def _interruptible_sleep(self, duration: float) -> None:
        """Sleep for a duration, checking for shutdown periodically.

        Args:
            duration: Sleep duration in seconds.
        """
        interval = 1.0
        elapsed = 0.0

        while elapsed < duration and not self._shutdown_requested:
            time.sleep(min(interval, duration - elapsed))
            elapsed += interval

    def run_daemon(self, poll_interval: Optional[int] = None) -> None:
        """Run as a daemon, polling for sessions.

        Args:
            poll_interval: Override poll interval in seconds.
        """
        poll_interval = poll_interval or self.poll_interval

        logger.info(
            f"Starting daemon with poll interval {poll_interval}s "
            f"(remote: {self.git_remote}/{self.git_branch})"
        )

        # Initial poll on startup
        self.run_once()

        # Main loop
        while not self._shutdown_requested:
            logger.debug(f"Sleeping for {poll_interval}s until next poll")
            self._interruptible_sleep(poll_interval)

            if self._shutdown_requested:
                break

            self.run_once()

        logger.info("Daemon shutting down")

        # Final cleanup
        if self._is_clocked_in:
            logger.warning("Shutting down while clocked in, attempting clock out")
            try:
                self._get_upwork_controller().clock_out()
            except Exception as e:
                logger.error(f"Final clock out failed: {e}")
            finally:
                self._is_clocked_in = False

        logger.info("Daemon stopped")


def main() -> int:
    """Main entry point for the orchestrator daemon.

    Returns:
        Exit code.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description='PROJECT MASK Session Orchestrator Daemon'
    )
    parser.add_argument(
        '--config', '-c',
        help='Path to configuration file',
    )
    parser.add_argument(
        '--poll-interval', '-p',
        type=int,
        help='Override poll interval in seconds',
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Run once and exit (no daemon mode)',
    )

    args = parser.parse_args()

    try:
        orchestrator = SessionOrchestrator(config_path=args.config)

        if args.once:
            count = orchestrator.run_once()
            print(f"Processed {count} sessions")
            return 0
        else:
            orchestrator.run_daemon(poll_interval=args.poll_interval)
            return 0

    except KeyboardInterrupt:
        print("\nInterrupted")
        return 130
    except Exception as e:
        logging.exception(f"Fatal error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
