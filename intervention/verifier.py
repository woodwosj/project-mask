"""File content verification for AI intervention system.

This module compares output files against expected content from the session
JSON to detect content drift or typing errors during replay.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher, unified_diff
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from replay.replay_engine import ReplaySession, FileOperation

logger = logging.getLogger(__name__)


@dataclass
class FileComparison:
    """Result of comparing expected vs actual file content.

    Attributes:
        path: File path relative to workspace.
        exists: Whether the file exists on disk.
        similarity: Similarity ratio (0.0 to 1.0).
        match_status: Classification ("match", "partial", "mismatch", "missing").
        diff_lines: Unified diff output for debugging.
        expected_lines: Number of lines in expected content.
        actual_lines: Number of lines in actual file.
        expected_chars: Number of characters in expected content.
        actual_chars: Number of characters in actual file.
    """
    path: str
    exists: bool
    similarity: float
    match_status: str
    diff_lines: List[str]
    expected_lines: int
    actual_lines: int
    expected_chars: int = 0
    actual_chars: int = 0


@dataclass
class VerificationResult:
    """Overall verification result for a session.

    Attributes:
        success: Whether all files match expected content.
        comparisons: List of per-file comparison results.
        summary: Human-readable summary of verification.
        match_count: Number of files that match.
        partial_count: Number of files with partial matches.
        mismatch_count: Number of files that don't match.
        missing_count: Number of expected files that are missing.
    """
    success: bool
    comparisons: List[FileComparison]
    summary: str
    match_count: int = 0
    partial_count: int = 0
    mismatch_count: int = 0
    missing_count: int = 0


class FileVerifier:
    """Verifies output files match expected content from session JSON.

    Uses difflib's SequenceMatcher for semantic comparison, allowing for
    minor differences while still detecting significant content drift.

    Thresholds:
        - >= 98%: "match" (acceptable)
        - >= 90%: "partial" (review recommended)
        - < 90%: "mismatch" (intervention needed)
    """

    # Similarity thresholds
    MATCH_THRESHOLD = 0.98     # >= 98% is a match
    PARTIAL_THRESHOLD = 0.90   # >= 90% is partial match (review needed)

    def __init__(
        self,
        workspace_root: Path,
        match_threshold: float = 0.98,
        partial_threshold: float = 0.90,
    ):
        """Initialize the verifier.

        Args:
            workspace_root: Root directory of VS Code workspace.
            match_threshold: Minimum similarity ratio to consider a match.
            partial_threshold: Minimum similarity for partial match status.
        """
        self.workspace_root = Path(workspace_root)
        self.match_threshold = match_threshold
        self.partial_threshold = partial_threshold

    def verify_session(
        self,
        session: 'ReplaySession',
        expected_contents: Optional[dict] = None,
    ) -> VerificationResult:
        """Verify all files in a session match expected content.

        Args:
            session: ReplaySession with file operations.
            expected_contents: Optional dict mapping file paths to expected content.
                             If not provided, content is reconstructed from operations.

        Returns:
            VerificationResult with per-file comparisons and summary.
        """
        logger.info(f"Verifying session '{session.session_id}' with "
                   f"{len(session.files)} files")

        comparisons = []
        match_count = 0
        partial_count = 0
        mismatch_count = 0
        missing_count = 0

        for file_ops in session.files:
            # Get expected content
            if expected_contents and file_ops.path in expected_contents:
                expected = expected_contents[file_ops.path]
            else:
                expected = self._build_expected_content(file_ops)

            # Compare file
            comparison = self._compare_file(file_ops.path, expected)
            comparisons.append(comparison)

            # Count by status
            if comparison.match_status == "match":
                match_count += 1
            elif comparison.match_status == "partial":
                partial_count += 1
            elif comparison.match_status == "missing":
                missing_count += 1
            else:
                mismatch_count += 1

            logger.debug(f"File {file_ops.path}: {comparison.match_status} "
                        f"(similarity: {comparison.similarity:.2%})")

        # Determine overall success and summary
        total = len(comparisons)
        success = (match_count == total)

        if success:
            summary = f"All {total} files match expected content"
        elif missing_count > 0:
            missing_files = [c.path for c in comparisons if c.match_status == "missing"]
            summary = f"Missing {missing_count} files: {', '.join(missing_files[:3])}"
            if missing_count > 3:
                summary += f" (+{missing_count - 3} more)"
        elif mismatch_count > 0:
            mismatch_files = [c.path for c in comparisons if c.match_status == "mismatch"]
            summary = f"{mismatch_count} files have significant differences: {', '.join(mismatch_files[:3])}"
        else:
            partial_files = [c.path for c in comparisons if c.match_status == "partial"]
            summary = f"{partial_count} files have minor differences: {', '.join(partial_files[:3])}"

        logger.info(f"Verification complete: {summary}")

        return VerificationResult(
            success=success,
            comparisons=comparisons,
            summary=summary,
            match_count=match_count,
            partial_count=partial_count,
            mismatch_count=mismatch_count,
            missing_count=missing_count,
        )

    def verify_file(
        self,
        path: str,
        expected_content: str,
    ) -> FileComparison:
        """Verify a single file matches expected content.

        Args:
            path: File path relative to workspace.
            expected_content: Expected file content.

        Returns:
            FileComparison with similarity and diff.
        """
        return self._compare_file(path, expected_content)

    def _build_expected_content(self, file_ops: 'FileOperation') -> str:
        """Build expected file content from operations.

        Reconstructs what the file should contain after all insert
        operations have been applied.

        Note: This is a simplified reconstruction that assumes the file
        started empty and all operations are inserts. For more complex
        scenarios, expected_contents should be passed directly.

        Args:
            file_ops: FileOperation containing operations for a file.

        Returns:
            Reconstructed expected content.
        """
        # Extract content from insert operations
        content_parts = []

        for op in file_ops.operations:
            if op.op_type.value == 'insert' and op.content:
                content_parts.append(op.content)

        return ''.join(content_parts)

    def _compare_file(
        self,
        path: str,
        expected: str,
    ) -> FileComparison:
        """Compare a file against expected content.

        Args:
            path: File path relative to workspace.
            expected: Expected file content.

        Returns:
            FileComparison with detailed comparison results.
        """
        full_path = self.workspace_root / path

        # Handle missing file
        if not full_path.exists():
            return FileComparison(
                path=path,
                exists=False,
                similarity=0.0,
                match_status="missing",
                diff_lines=[f"--- expected/{path}", f"+++ missing/{path}",
                           "@@ File does not exist @@"],
                expected_lines=expected.count('\n') + (1 if expected else 0),
                actual_lines=0,
                expected_chars=len(expected),
                actual_chars=0,
            )

        # Read actual content
        try:
            actual = full_path.read_text(encoding='utf-8')
        except IOError as e:
            logger.error(f"Failed to read {path}: {e}")
            return FileComparison(
                path=path,
                exists=True,
                similarity=0.0,
                match_status="mismatch",
                diff_lines=[f"Error reading file: {e}"],
                expected_lines=expected.count('\n') + (1 if expected else 0),
                actual_lines=0,
                expected_chars=len(expected),
                actual_chars=0,
            )
        except UnicodeDecodeError as e:
            logger.error(f"Failed to decode {path}: {e}")
            return FileComparison(
                path=path,
                exists=True,
                similarity=0.0,
                match_status="mismatch",
                diff_lines=[f"Encoding error: {e}"],
                expected_lines=expected.count('\n') + (1 if expected else 0),
                actual_lines=0,
                expected_chars=len(expected),
                actual_chars=0,
            )

        # Calculate similarity
        if not expected and not actual:
            similarity = 1.0
        elif not expected or not actual:
            similarity = 0.0 if (expected or actual) else 1.0
        else:
            similarity = SequenceMatcher(None, expected, actual).ratio()

        # Generate unified diff
        expected_lines_list = expected.splitlines(keepends=True)
        actual_lines_list = actual.splitlines(keepends=True)

        diff_lines = list(unified_diff(
            expected_lines_list,
            actual_lines_list,
            fromfile=f"expected/{path}",
            tofile=f"actual/{path}",
            lineterm=""
        ))

        # Limit diff output for very long diffs
        if len(diff_lines) > 100:
            diff_lines = diff_lines[:100] + [f"... ({len(diff_lines) - 100} more lines)"]

        # Determine match status
        if similarity >= self.match_threshold:
            match_status = "match"
        elif similarity >= self.partial_threshold:
            match_status = "partial"
        else:
            match_status = "mismatch"

        return FileComparison(
            path=path,
            exists=True,
            similarity=similarity,
            match_status=match_status,
            diff_lines=diff_lines,
            expected_lines=len(expected_lines_list),
            actual_lines=len(actual_lines_list),
            expected_chars=len(expected),
            actual_chars=len(actual),
        )

    def get_discrepancies(
        self,
        comparison: FileComparison,
    ) -> List[dict]:
        """Extract specific discrepancies from a file comparison.

        Parses the unified diff to identify individual differences.

        Args:
            comparison: FileComparison to analyze.

        Returns:
            List of discrepancy dictionaries with line info.
        """
        discrepancies = []
        current_line = 0

        for line in comparison.diff_lines:
            if line.startswith('@@'):
                # Parse hunk header: @@ -start,count +start,count @@
                # Extract the starting line number
                parts = line.split(' ')
                if len(parts) >= 3:
                    try:
                        # +start,count format
                        new_start = parts[2].split(',')[0].lstrip('+')
                        current_line = int(new_start) - 1
                    except (IndexError, ValueError):
                        pass

            elif line.startswith('-') and not line.startswith('---'):
                # Line removed/changed
                discrepancies.append({
                    'type': 'removed',
                    'line': current_line,
                    'content': line[1:].rstrip('\n'),
                })

            elif line.startswith('+') and not line.startswith('+++'):
                # Line added
                current_line += 1
                discrepancies.append({
                    'type': 'added',
                    'line': current_line,
                    'content': line[1:].rstrip('\n'),
                })

            elif not line.startswith(('-', '+', '@')):
                # Context line
                current_line += 1

        return discrepancies

    def format_report(
        self,
        result: VerificationResult,
        verbose: bool = False,
    ) -> str:
        """Format verification result as a human-readable report.

        Args:
            result: VerificationResult to format.
            verbose: Include full diffs for mismatched files.

        Returns:
            Formatted report string.
        """
        lines = [
            "=" * 60,
            "FILE VERIFICATION REPORT",
            "=" * 60,
            "",
            f"Overall: {'PASS' if result.success else 'FAIL'}",
            f"Summary: {result.summary}",
            "",
            f"  Matches:    {result.match_count}",
            f"  Partial:    {result.partial_count}",
            f"  Mismatch:   {result.mismatch_count}",
            f"  Missing:    {result.missing_count}",
            "",
        ]

        # Add details for non-matching files
        non_matching = [c for c in result.comparisons if c.match_status != "match"]

        if non_matching:
            lines.append("Details:")
            lines.append("-" * 40)

            for comp in non_matching:
                lines.append(f"\n{comp.path}:")
                lines.append(f"  Status: {comp.match_status}")
                lines.append(f"  Similarity: {comp.similarity:.1%}")
                lines.append(f"  Expected: {comp.expected_lines} lines, {comp.expected_chars} chars")
                lines.append(f"  Actual: {comp.actual_lines} lines, {comp.actual_chars} chars")

                if verbose and comp.diff_lines:
                    lines.append("  Diff:")
                    for diff_line in comp.diff_lines[:20]:
                        lines.append(f"    {diff_line}")
                    if len(comp.diff_lines) > 20:
                        lines.append(f"    ... ({len(comp.diff_lines) - 20} more lines)")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)
