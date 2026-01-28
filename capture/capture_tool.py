"""Capture tool for parsing git diffs and generating replay sessions.

This module converts git diff output into structured replay session JSON
that can be executed by the replay engine.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from unidiff import PatchSet, PatchedFile, Hunk


logger = logging.getLogger(__name__)


class CaptureError(Exception):
    """Exception raised during capture operations."""
    pass


class GitError(CaptureError):
    """Exception raised when git operations fail."""
    pass


class DiffParseError(CaptureError):
    """Exception raised when diff parsing fails."""
    pass


@dataclass
class DiffOperation:
    """A single operation derived from a diff hunk.

    Attributes:
        op_type: Type of operation ('navigate', 'delete', 'insert').
        line: Target line number.
        line_end: End line for delete range (optional).
        content: Text content for insert operations.
    """
    op_type: str
    line: int
    line_end: Optional[int] = None
    content: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation.
        """
        result: Dict[str, Any] = {
            'type': self.op_type,
            'line': self.line,
        }

        if self.line_end is not None and self.line_end != self.line:
            result['line_end'] = self.line_end

        if self.content is not None:
            result['content'] = self.content

        return result


@dataclass
class FileChanges:
    """Changes for a single file.

    Attributes:
        path: File path.
        is_new: True if this is a new file.
        is_deleted: True if this file was deleted.
        operations: List of operations for this file.
    """
    path: str
    is_new: bool = False
    is_deleted: bool = False
    operations: List[DiffOperation] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation.
        """
        return {
            'path': self.path,
            'operations': [op.to_dict() for op in self.operations],
        }


class DiffParser:
    """Parser for unified diff format.

    This class converts git diff output into structured operations
    suitable for replay.
    """

    def __init__(self):
        """Initialize the diff parser."""
        self._warnings: List[str] = []

    @property
    def warnings(self) -> List[str]:
        """Get warnings generated during parsing."""
        return self._warnings.copy()

    def clear_warnings(self) -> None:
        """Clear accumulated warnings."""
        self._warnings = []

    def parse_diff_text(self, diff_text: str) -> List[FileChanges]:
        """Parse unified diff text.

        Args:
            diff_text: Unified diff text.

        Returns:
            List of FileChanges objects.

        Raises:
            DiffParseError: If the diff cannot be parsed.
        """
        self.clear_warnings()

        if not diff_text.strip():
            logger.warning("Empty diff provided")
            return []

        try:
            patch_set = PatchSet(diff_text)
        except Exception as e:
            raise DiffParseError(f"Failed to parse diff: {e}") from e

        return self._process_patch_set(patch_set)

    def parse_diff_file(self, filepath: str) -> List[FileChanges]:
        """Parse unified diff from a file.

        Args:
            filepath: Path to the diff file.

        Returns:
            List of FileChanges objects.

        Raises:
            CaptureError: If the file cannot be read.
            DiffParseError: If the diff cannot be parsed.
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                diff_text = f.read()
        except IOError as e:
            raise CaptureError(f"Failed to read diff file: {e}") from e

        return self.parse_diff_text(diff_text)

    def _process_patch_set(self, patch_set: PatchSet) -> List[FileChanges]:
        """Process a PatchSet into FileChanges.

        Args:
            patch_set: Parsed PatchSet from unidiff.

        Returns:
            List of FileChanges objects.
        """
        result: List[FileChanges] = []

        for patched_file in patch_set:
            changes = self._process_patched_file(patched_file)
            if changes:
                result.append(changes)

        # Sort by path for consistent replay order
        result.sort(key=lambda x: x.path)

        return result

    def _process_patched_file(self, patched_file: PatchedFile) -> Optional[FileChanges]:
        """Process a single patched file.

        Args:
            patched_file: PatchedFile from unidiff.

        Returns:
            FileChanges object or None if skipped.
        """
        # Get the target path (after the change)
        path = patched_file.path
        if path.startswith('b/'):
            path = path[2:]

        # Check for binary files
        if patched_file.is_binary_file:
            self._warnings.append(f"Skipping binary file: {path}")
            logger.warning(f"Skipping binary file: {path}")
            return None

        # Check for deleted files
        if patched_file.is_removed_file:
            self._warnings.append(f"Skipping deleted file: {path}")
            logger.warning(f"Skipping deleted file: {path}")
            return None

        changes = FileChanges(
            path=path,
            is_new=patched_file.is_added_file,
        )

        # Process all hunks
        for hunk in patched_file:
            operations = self._process_hunk(hunk, patched_file.is_added_file)
            changes.operations.extend(operations)

        logger.debug(
            f"Processed file '{path}': {len(changes.operations)} operations"
        )

        return changes

    def _process_hunk(self, hunk: Hunk, is_new_file: bool) -> List[DiffOperation]:
        """Process a single hunk into operations.

        For mixed hunks (both deletions and additions), we:
        1. First delete removed lines
        2. Then insert added lines at the same position

        Args:
            hunk: Hunk from unidiff.
            is_new_file: True if this is a new file.

        Returns:
            List of DiffOperation objects.
        """
        operations: List[DiffOperation] = []

        # Collect removed and added lines with their positions
        removed_lines: List[Tuple[int, str]] = []
        added_lines: List[Tuple[int, str]] = []

        # Track line positions
        # For removed lines, use source line numbers
        # For added lines, use target line numbers
        source_line = hunk.source_start
        target_line = hunk.target_start

        for line in hunk:
            if line.is_removed:
                removed_lines.append((source_line, line.value))
                source_line += 1
            elif line.is_added:
                added_lines.append((target_line, line.value))
                target_line += 1
            else:
                # Context line - advance both counters
                source_line += 1
                target_line += 1

        # Process removals (deletions)
        if removed_lines and not is_new_file:
            operations.extend(self._build_delete_operations(removed_lines))

        # Process additions (inserts)
        if added_lines:
            operations.extend(self._build_insert_operations(added_lines))

        return operations

    def _build_delete_operations(
        self,
        removed_lines: List[Tuple[int, str]],
    ) -> List[DiffOperation]:
        """Build delete operations from removed lines.

        Consecutive removed lines are combined into a single delete range.

        Args:
            removed_lines: List of (line_number, content) tuples.

        Returns:
            List of delete operations.
        """
        if not removed_lines:
            return []

        operations: List[DiffOperation] = []

        # Group consecutive lines
        groups: List[Tuple[int, int]] = []  # (start, end)
        current_start = removed_lines[0][0]
        current_end = current_start

        for i in range(1, len(removed_lines)):
            line_num = removed_lines[i][0]
            if line_num == current_end + 1:
                # Consecutive
                current_end = line_num
            else:
                # Gap - save current group and start new
                groups.append((current_start, current_end))
                current_start = line_num
                current_end = line_num

        # Don't forget the last group
        groups.append((current_start, current_end))

        # Create operations for each group
        # Note: We need to process deletions from bottom to top
        # to preserve line numbers, but we'll generate them top-down
        # and let the replay engine handle them correctly
        for start, end in groups:
            operations.append(DiffOperation(
                op_type='delete',
                line=start,
                line_end=end if end != start else None,
            ))

        return operations

    def _build_insert_operations(
        self,
        added_lines: List[Tuple[int, str]],
    ) -> List[DiffOperation]:
        """Build insert operations from added lines.

        Consecutive added lines are combined into a single insert.

        Args:
            added_lines: List of (line_number, content) tuples.

        Returns:
            List of insert operations.
        """
        if not added_lines:
            return []

        operations: List[DiffOperation] = []

        # Group consecutive lines
        groups: List[List[Tuple[int, str]]] = []
        current_group: List[Tuple[int, str]] = [added_lines[0]]

        for i in range(1, len(added_lines)):
            line_num, content = added_lines[i]
            prev_line_num = current_group[-1][0]

            if line_num == prev_line_num + 1:
                # Consecutive
                current_group.append((line_num, content))
            else:
                # Gap - save current group and start new
                groups.append(current_group)
                current_group = [(line_num, content)]

        # Don't forget the last group
        groups.append(current_group)

        # Create operations for each group
        for group in groups:
            start_line = group[0][0]
            content = ''.join(line[1] for line in group)

            # Remove trailing newline if it's just one
            # (will be added by the enter key)
            if content.endswith('\n') and content.count('\n') == len(group):
                # Keep content as-is for proper formatting
                pass

            operations.append(DiffOperation(
                op_type='insert',
                line=start_line,
                content=content,
            ))

        return operations


class SessionBuilder:
    """Builder for creating replay session JSON."""

    # Default replay configuration
    DEFAULT_REPLAY_CONFIG = {
        'base_wpm': 85,
        'typo_probability': 0.02,
        'thinking_pause_probability': 0.10,
    }

    def __init__(self):
        """Initialize the session builder."""
        pass

    def generate_session_id(self) -> str:
        """Generate a unique session ID based on timestamp.

        Returns:
            Session ID in format 'session_YYYYMMDD_HHMMSS'.
        """
        now = datetime.now(timezone.utc)
        return f"session_{now.strftime('%Y%m%d_%H%M%S')}"

    def build_session(
        self,
        file_changes: List[FileChanges],
        contract_id: str,
        memo: str,
        session_id: Optional[str] = None,
        replay_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build a complete session JSON structure.

        Args:
            file_changes: List of FileChanges from diff parsing.
            contract_id: Upwork contract name.
            memo: Work description.
            session_id: Optional custom session ID.
            replay_config: Optional replay configuration overrides.

        Returns:
            Complete session dictionary ready for JSON serialization.
        """
        if session_id is None:
            session_id = self.generate_session_id()

        # Merge replay config with defaults
        config = self.DEFAULT_REPLAY_CONFIG.copy()
        if replay_config:
            config.update(replay_config)

        session = {
            'session_id': session_id,
            'contract_id': contract_id,
            'memo': memo,
            'files': [fc.to_dict() for fc in file_changes],
            'replay_config': config,
        }

        return session

    def to_json(
        self,
        session: Dict[str, Any],
        indent: int = 2,
    ) -> str:
        """Convert session to JSON string.

        Args:
            session: Session dictionary.
            indent: JSON indentation level.

        Returns:
            JSON string.
        """
        return json.dumps(session, indent=indent, ensure_ascii=False)

    def validate_session(self, session: Dict[str, Any]) -> List[str]:
        """Validate a session structure.

        Args:
            session: Session dictionary to validate.

        Returns:
            List of validation errors (empty if valid).
        """
        errors: List[str] = []

        # Check required fields
        required = ['session_id', 'contract_id', 'memo', 'files']
        for field in required:
            if field not in session:
                errors.append(f"Missing required field: {field}")

        # Validate session_id format
        session_id = session.get('session_id', '')
        if not session_id or not isinstance(session_id, str):
            errors.append("session_id must be a non-empty string")

        # Validate files
        files = session.get('files', [])
        if not isinstance(files, list):
            errors.append("'files' must be a list")
        else:
            for i, file_entry in enumerate(files):
                file_errors = self._validate_file_entry(file_entry, i)
                errors.extend(file_errors)

        return errors

    def _validate_file_entry(
        self,
        file_entry: Dict[str, Any],
        index: int,
    ) -> List[str]:
        """Validate a file entry.

        Args:
            file_entry: File entry dictionary.
            index: Index in files array for error messages.

        Returns:
            List of validation errors.
        """
        errors: List[str] = []
        prefix = f"files[{index}]"

        if not isinstance(file_entry, dict):
            errors.append(f"{prefix}: must be an object")
            return errors

        path = file_entry.get('path')
        if not path or not isinstance(path, str):
            errors.append(f"{prefix}.path: must be a non-empty string")

        operations = file_entry.get('operations', [])
        if not isinstance(operations, list):
            errors.append(f"{prefix}.operations: must be a list")
        else:
            for j, op in enumerate(operations):
                op_errors = self._validate_operation(op, f"{prefix}.operations[{j}]")
                errors.extend(op_errors)

        return errors

    def _validate_operation(
        self,
        operation: Dict[str, Any],
        prefix: str,
    ) -> List[str]:
        """Validate an operation.

        Args:
            operation: Operation dictionary.
            prefix: Prefix for error messages.

        Returns:
            List of validation errors.
        """
        errors: List[str] = []

        if not isinstance(operation, dict):
            errors.append(f"{prefix}: must be an object")
            return errors

        op_type = operation.get('type')
        if op_type not in ('navigate', 'delete', 'insert'):
            errors.append(f"{prefix}.type: must be 'navigate', 'delete', or 'insert'")

        line = operation.get('line')
        if not isinstance(line, int) or line < 1:
            errors.append(f"{prefix}.line: must be a positive integer")

        line_end = operation.get('line_end')
        if line_end is not None:
            if not isinstance(line_end, int) or line_end < line:
                errors.append(f"{prefix}.line_end: must be >= line")

        if op_type == 'insert':
            content = operation.get('content')
            if content is None:
                errors.append(f"{prefix}.content: required for insert operations")

        return errors


def parse_commit(
    commit_ref: str = "HEAD",
    repo_path: Optional[str] = None,
) -> str:
    """Get diff output from a git commit.

    Args:
        commit_ref: Git commit reference (default: HEAD).
        repo_path: Path to git repository (default: current directory).

    Returns:
        Unified diff text.

    Raises:
        GitError: If git command fails.
    """
    cmd = ['git', 'show', commit_ref, '--unified=3', '--no-color']

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_path,
            timeout=30,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise GitError(
            f"Failed to get diff for '{commit_ref}': {e.stderr}"
        ) from e
    except subprocess.TimeoutExpired:
        raise GitError(f"Git command timed out for '{commit_ref}'")
    except FileNotFoundError:
        raise GitError("Git is not installed or not in PATH")


def parse_commit_range(
    range_ref: str,
    repo_path: Optional[str] = None,
) -> str:
    """Get diff output from a commit range.

    Args:
        range_ref: Git range reference (e.g., 'HEAD~3..HEAD').
        repo_path: Path to git repository.

    Returns:
        Unified diff text.

    Raises:
        GitError: If git command fails.
    """
    cmd = ['git', 'diff', range_ref, '--unified=3', '--no-color']

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_path,
            timeout=30,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise GitError(
            f"Failed to get diff for range '{range_ref}': {e.stderr}"
        ) from e
    except subprocess.TimeoutExpired:
        raise GitError(f"Git command timed out for range '{range_ref}'")


def is_git_repository(path: Optional[str] = None) -> bool:
    """Check if a path is inside a git repository.

    Args:
        path: Path to check (default: current directory).

    Returns:
        True if inside a git repository.
    """
    try:
        subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            capture_output=True,
            check=True,
            cwd=path,
            timeout=5,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_repo_root(path: Optional[str] = None) -> Optional[str]:
    """Get the root directory of a git repository.

    Args:
        path: Path inside the repository.

    Returns:
        Repository root path or None if not in a repository.
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True,
            cwd=path,
            timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def generate_session(
    commit_ref: str,
    contract_id: str,
    memo: str,
    repo_path: Optional[str] = None,
    replay_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate a complete replay session from a git commit.

    This is a convenience function that combines parsing and building.

    Args:
        commit_ref: Git commit reference.
        contract_id: Upwork contract name.
        memo: Work description.
        repo_path: Path to git repository.
        replay_config: Optional replay configuration overrides.

    Returns:
        Complete session dictionary.

    Raises:
        GitError: If git operations fail.
        DiffParseError: If diff parsing fails.
    """
    # Determine if this is a range or single commit
    if '..' in commit_ref:
        diff_text = parse_commit_range(commit_ref, repo_path)
    else:
        diff_text = parse_commit(commit_ref, repo_path)

    # Parse the diff
    parser = DiffParser()
    file_changes = parser.parse_diff_text(diff_text)

    # Log any warnings
    for warning in parser.warnings:
        logger.warning(warning)

    # Build the session
    builder = SessionBuilder()
    session = builder.build_session(
        file_changes=file_changes,
        contract_id=contract_id,
        memo=memo,
        replay_config=replay_config,
    )

    # Validate
    errors = builder.validate_session(session)
    if errors:
        for error in errors:
            logger.error(f"Validation error: {error}")
        raise CaptureError(f"Session validation failed: {errors[0]}")

    return session
