"""Replay engine for executing code replay sessions.

This module handles loading session files and executing file operations
through the VS Code controller.
"""

from dataclasses import dataclass, field
from enum import Enum
import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union


logger = logging.getLogger(__name__)


class AbortRequested(Exception):
    """Exception raised when replay is aborted."""
    pass


class SessionNotFoundError(Exception):
    """Exception raised when session file is not found."""
    pass


class SessionParseError(Exception):
    """Exception raised when session JSON is malformed."""
    pass


class SessionValidationError(Exception):
    """Exception raised when session data is invalid."""
    pass


class FileOpenError(Exception):
    """Exception raised when a file cannot be opened."""
    pass


class OperationType(Enum):
    """Types of file operations in a replay session."""
    NAVIGATE = "navigate"
    DELETE = "delete"
    INSERT = "insert"


@dataclass
class Operation:
    """A single operation within a file.

    Attributes:
        op_type: Type of operation (navigate, delete, insert).
        line: Target line number.
        line_end: End line for delete range (optional).
        content: Text content for insert operations.
        typing_style: Override typing behavior (optional).
    """
    op_type: OperationType
    line: int
    line_end: Optional[int] = None
    content: Optional[str] = None
    typing_style: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Operation':
        """Create an Operation from a dictionary.

        Args:
            data: Dictionary containing operation data.

        Returns:
            Operation instance.

        Raises:
            SessionValidationError: If the operation data is invalid.
        """
        try:
            op_type = OperationType(data['type'])
        except (KeyError, ValueError) as e:
            raise SessionValidationError(
                f"Invalid operation type: {data.get('type', 'missing')}"
            ) from e

        line = data.get('line')
        if line is None or not isinstance(line, int) or line < 1:
            raise SessionValidationError(
                f"Invalid line number: {line}. Must be a positive integer."
            )

        line_end = data.get('line_end')
        if line_end is not None:
            if not isinstance(line_end, int) or line_end < line:
                raise SessionValidationError(
                    f"Invalid line_end: {line_end}. Must be >= line ({line})."
                )

        content = data.get('content')
        if op_type == OperationType.INSERT and content is None:
            raise SessionValidationError(
                "Insert operation requires 'content' field."
            )

        return cls(
            op_type=op_type,
            line=line,
            line_end=line_end,
            content=content,
            typing_style=data.get('typing_style'),
        )


@dataclass
class FileOperation:
    """Operations for a single file.

    Attributes:
        path: File path (relative or absolute).
        operations: List of operations for this file.
    """
    path: str
    operations: List[Operation]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FileOperation':
        """Create a FileOperation from a dictionary.

        Args:
            data: Dictionary containing file operation data.

        Returns:
            FileOperation instance.

        Raises:
            SessionValidationError: If the data is invalid.
        """
        path = data.get('path')
        if not path or not isinstance(path, str):
            raise SessionValidationError(
                f"Invalid file path: {path}. Must be a non-empty string."
            )

        # Validate path doesn't contain dangerous patterns
        if '..' in path:
            logger.warning(f"File path contains '..': {path}")

        operations_data = data.get('operations', [])
        if not isinstance(operations_data, list):
            raise SessionValidationError(
                f"'operations' must be a list, got {type(operations_data).__name__}"
            )

        operations = [Operation.from_dict(op) for op in operations_data]

        return cls(path=path, operations=operations)


@dataclass
class ReplayConfig:
    """Configuration overrides for a replay session.

    Attributes:
        base_wpm: Override base typing speed.
        typo_probability: Override typo probability.
        thinking_pause_probability: Override thinking pause probability.
        thinking_pauses: Enable/disable thinking pauses.
    """
    base_wpm: Optional[int] = None
    typo_probability: Optional[float] = None
    thinking_pause_probability: Optional[float] = None
    thinking_pauses: bool = True

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'ReplayConfig':
        """Create a ReplayConfig from a dictionary.

        Args:
            data: Dictionary containing config data (may be None).

        Returns:
            ReplayConfig instance.
        """
        if not data:
            return cls()

        return cls(
            base_wpm=data.get('base_wpm'),
            typo_probability=data.get('typo_probability'),
            thinking_pause_probability=data.get('thinking_pause_probability'),
            thinking_pauses=data.get('thinking_pauses', True),
        )


@dataclass
class ReplaySession:
    """A complete replay session.

    Attributes:
        session_id: Unique session identifier.
        contract_id: Upwork contract name.
        memo: Work description for time tracking.
        files: List of file operations.
        replay_config: Optional configuration overrides.
    """
    session_id: str
    contract_id: str
    memo: str
    files: List[FileOperation]
    replay_config: ReplayConfig = field(default_factory=ReplayConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReplaySession':
        """Create a ReplaySession from a dictionary.

        Args:
            data: Dictionary containing session data.

        Returns:
            ReplaySession instance.

        Raises:
            SessionValidationError: If required fields are missing.
        """
        # Validate required fields
        required_fields = ['session_id', 'contract_id', 'memo', 'files']
        missing = [f for f in required_fields if f not in data]
        if missing:
            raise SessionValidationError(
                f"Missing required fields: {', '.join(missing)}"
            )

        session_id = data['session_id']
        if not isinstance(session_id, str) or not session_id:
            raise SessionValidationError(
                f"Invalid session_id: {session_id}. Must be a non-empty string."
            )

        contract_id = data['contract_id']
        if not isinstance(contract_id, str) or not contract_id:
            raise SessionValidationError(
                f"Invalid contract_id: {contract_id}. Must be a non-empty string."
            )

        memo = data['memo']
        if not isinstance(memo, str):
            raise SessionValidationError(
                f"Invalid memo: must be a string, got {type(memo).__name__}"
            )

        files_data = data['files']
        if not isinstance(files_data, list):
            raise SessionValidationError(
                f"'files' must be a list, got {type(files_data).__name__}"
            )

        files = [FileOperation.from_dict(f) for f in files_data]

        replay_config = ReplayConfig.from_dict(data.get('replay_config'))

        return cls(
            session_id=session_id,
            contract_id=contract_id,
            memo=memo,
            files=files,
            replay_config=replay_config,
        )

    def total_operations(self) -> int:
        """Get total number of operations in the session.

        Returns:
            Total operation count.
        """
        return sum(len(f.operations) for f in self.files)


# Progress callback type: (message, current, total) -> None
ProgressCallback = Callable[[str, int, int], None]


class ReplayEngine:
    """Engine for executing replay sessions.

    This class coordinates the execution of replay sessions by:
    - Loading and validating session files
    - Executing file operations through VS Code controller
    - Handling progress reporting and abort requests
    """

    def __init__(self, vscode_controller: Any, config: Optional[Dict] = None):
        """Initialize the replay engine.

        Args:
            vscode_controller: VSCodeController instance for executing operations.
            config: Optional configuration dictionary.
        """
        self.vscode = vscode_controller
        self.config = config or {}

        # Abort handling
        self._abort_requested = False

        # Current session state
        self._current_file: Optional[str] = None

    def request_abort(self) -> None:
        """Request abort of current replay."""
        self._abort_requested = True
        self.vscode.request_abort()
        logger.info("Abort requested")

    def _reset_abort(self) -> None:
        """Reset the abort flag."""
        self._abort_requested = False
        self.vscode.reset_abort()

    def _check_abort(self) -> None:
        """Check if abort has been requested.

        Raises:
            AbortRequested: If abort has been requested.
        """
        if self._abort_requested:
            raise AbortRequested("Replay aborted by request")

    def load_session(self, filepath: Union[str, Path]) -> ReplaySession:
        """Load and validate a replay session from a JSON file.

        Args:
            filepath: Path to the session JSON file.

        Returns:
            ReplaySession instance.

        Raises:
            SessionNotFoundError: If the file does not exist.
            SessionParseError: If the JSON is malformed.
            SessionValidationError: If the session data is invalid.
        """
        path = Path(filepath)

        if not path.exists():
            raise SessionNotFoundError(f"Session file not found: {path}")

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise SessionParseError(
                f"Failed to parse session JSON: {e}"
            ) from e

        session = ReplaySession.from_dict(data)

        logger.info(
            f"Loaded session '{session.session_id}' with "
            f"{len(session.files)} files, {session.total_operations()} operations"
        )

        return session

    def execute(
        self,
        session: ReplaySession,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> bool:
        """Execute a replay session.

        Args:
            session: ReplaySession to execute.
            progress_callback: Optional callback for progress reporting.

        Returns:
            True if completed successfully, False if aborted.

        Raises:
            AbortRequested: If abort is requested during execution.
            VSCodeNotFoundError: If VS Code is not available.
            FileOpenError: If a file cannot be opened.
        """
        self._reset_abort()
        self._current_file = None

        total_ops = session.total_operations()
        current_op = 0

        logger.info(
            f"Starting replay session '{session.session_id}': "
            f"{len(session.files)} files, {total_ops} operations"
        )

        # Reset typing state for fresh fatigue calculation
        self.vscode.reset_typing_state()

        # Apply session-specific config overrides
        original_config = self._apply_session_config(session.replay_config)

        try:
            for file_op in session.files:
                self._check_abort()

                # Open the file if different from current
                if file_op.path != self._current_file:
                    if progress_callback:
                        progress_callback(
                            f"Opening file: {file_op.path}",
                            current_op,
                            total_ops
                        )

                    # Maybe pause between files
                    if self._current_file is not None:
                        self._maybe_pause_between_files(session.replay_config)

                    if not self._open_file_with_retry(file_op.path):
                        raise FileOpenError(f"Failed to open file: {file_op.path}")

                    self._current_file = file_op.path

                # Execute operations for this file
                for op in file_op.operations:
                    self._check_abort()

                    if progress_callback:
                        progress_callback(
                            f"Executing {op.op_type.value} at line {op.line}",
                            current_op,
                            total_ops
                        )

                    self._execute_operation(op, session.replay_config)
                    current_op += 1

                # Save the file after operations
                self.vscode.save_file()

            logger.info(f"Replay session '{session.session_id}' completed successfully")
            return True

        except AbortRequested:
            logger.warning(f"Replay session '{session.session_id}' was aborted")
            raise

        finally:
            # Restore original config
            self._restore_config(original_config)

    def _apply_session_config(
        self,
        replay_config: ReplayConfig,
    ) -> Dict[str, Any]:
        """Apply session-specific configuration overrides.

        Args:
            replay_config: Session's replay configuration.

        Returns:
            Dictionary of original values for restoration.
        """
        original = {}

        if replay_config.base_wpm is not None:
            original['base_wpm'] = self.vscode.base_wpm
            self.vscode.base_wpm = replay_config.base_wpm

        if replay_config.typo_probability is not None:
            original['typo_probability'] = self.vscode.typo_probability
            self.vscode.typo_probability = replay_config.typo_probability

        if replay_config.thinking_pause_probability is not None:
            original['thinking_pause_probability'] = self.vscode.thinking_pause_probability
            self.vscode.thinking_pause_probability = replay_config.thinking_pause_probability

        if not replay_config.thinking_pauses:
            original['thinking_pause_probability'] = self.vscode.thinking_pause_probability
            self.vscode.thinking_pause_probability = 0.0

        return original

    def _restore_config(self, original: Dict[str, Any]) -> None:
        """Restore original configuration values.

        Args:
            original: Dictionary of original values.
        """
        for key, value in original.items():
            setattr(self.vscode, key, value)

    def _open_file_with_retry(self, path: str) -> bool:
        """Open a file with retry on failure.

        Args:
            path: File path to open.

        Returns:
            True if successful, False otherwise.
        """
        retries = getattr(self.vscode, 'file_open_retries', 1)

        for attempt in range(retries + 1):
            try:
                if self.vscode.open_file(path):
                    return True
            except Exception as e:
                logger.warning(f"File open attempt {attempt + 1} failed: {e}")

            if attempt < retries:
                time.sleep(0.5)

        return False

    def _maybe_pause_between_files(self, replay_config: ReplayConfig) -> None:
        """Maybe insert a pause when transitioning between files.

        Args:
            replay_config: Session's replay configuration.
        """
        if not replay_config.thinking_pauses:
            return

        # Short pause between files (1-3 seconds)
        pause_duration = random.uniform(1.0, 3.0)
        logger.debug(f"Pausing {pause_duration:.1f}s between files")
        time.sleep(pause_duration)

    def _execute_operation(
        self,
        op: Operation,
        replay_config: ReplayConfig,
    ) -> None:
        """Execute a single operation.

        Args:
            op: Operation to execute.
            replay_config: Session's replay configuration.
        """
        if op.op_type == OperationType.NAVIGATE:
            self._execute_navigate(op)
        elif op.op_type == OperationType.DELETE:
            self._execute_delete(op)
        elif op.op_type == OperationType.INSERT:
            self._execute_insert(op, replay_config)
        else:
            logger.warning(f"Unknown operation type: {op.op_type}")

    def _execute_navigate(self, op: Operation) -> None:
        """Execute a navigate operation.

        Args:
            op: Navigate operation.
        """
        logger.debug(f"Navigating to line {op.line}")
        self.vscode.goto_line(op.line)

    def _execute_delete(self, op: Operation) -> None:
        """Execute a delete operation.

        Args:
            op: Delete operation.
        """
        end_line = op.line_end if op.line_end is not None else op.line
        logger.debug(f"Deleting lines {op.line}-{end_line}")
        self.vscode.delete_lines(op.line, end_line)

    def _execute_insert(self, op: Operation, replay_config: ReplayConfig) -> None:
        """Execute an insert operation.

        Args:
            op: Insert operation.
            replay_config: Session's replay configuration.
        """
        if not op.content:
            logger.warning("Insert operation with empty content")
            return

        logger.debug(f"Inserting {len(op.content)} chars at line {op.line}")

        # Navigate to the line
        self.vscode.goto_line(op.line)
        time.sleep(0.1)

        # Type the content with human-like patterns
        wpm = None
        typo_prob = None

        # Apply typing style overrides
        if op.typing_style == 'fast':
            wpm = int(self.vscode.base_wpm * 1.5)
            typo_prob = self.vscode.typo_probability * 0.5
        elif op.typing_style == 'slow':
            wpm = int(self.vscode.base_wpm * 0.7)
            typo_prob = self.vscode.typo_probability * 1.5
        elif op.typing_style == 'precise':
            typo_prob = 0.0

        self.vscode.type_code(op.content, wpm=wpm, typo_probability=typo_prob)


def load_session(filepath: Union[str, Path]) -> ReplaySession:
    """Convenience function to load a session without creating an engine.

    Args:
        filepath: Path to the session JSON file.

    Returns:
        ReplaySession instance.
    """
    path = Path(filepath)

    if not path.exists():
        raise SessionNotFoundError(f"Session file not found: {path}")

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return ReplaySession.from_dict(data)
