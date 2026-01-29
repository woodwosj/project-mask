"""Post-replay remediation for fixing content mismatches.

After replay completes, this module verifies file content against expected
content and automatically re-types any files that don't match.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from .verifier import FileVerifier, VerificationResult, FileComparison

if TYPE_CHECKING:
    from replay.vscode_controller import VSCodeController
    from replay.replay_engine import ReplaySession

logger = logging.getLogger(__name__)


@dataclass
class RemediationResult:
    """Result of remediation attempt.

    Attributes:
        file_path: Path to the file that was remediated.
        original_similarity: Similarity before remediation.
        final_similarity: Similarity after remediation.
        success: Whether remediation achieved acceptable match.
        attempts: Number of remediation attempts made.
        error: Error message if remediation failed.
    """
    file_path: str
    original_similarity: float
    final_similarity: float
    success: bool
    attempts: int
    error: Optional[str] = None


@dataclass
class RemediationSummary:
    """Summary of all remediation attempts.

    Attributes:
        total_files: Total files checked.
        files_ok: Files that matched without remediation.
        files_remediated: Files successfully remediated.
        files_failed: Files that couldn't be fixed.
        results: Individual remediation results.
    """
    total_files: int
    files_ok: int
    files_remediated: int
    files_failed: int
    results: List[RemediationResult]


class Remediator:
    """Fixes files that don't match expected content after replay.

    Strategy: If a file doesn't match, clear it completely and re-type
    the correct content. This is more reliable than surgical fixes.
    """

    def __init__(
        self,
        vscode_controller: 'VSCodeController',
        workspace_root: Path,
        match_threshold: float = 0.98,
        max_attempts: int = 2,
    ):
        """Initialize the remediator.

        Args:
            vscode_controller: VS Code controller for typing.
            workspace_root: Root directory of workspace.
            match_threshold: Minimum similarity to consider fixed.
            max_attempts: Maximum remediation attempts per file.
        """
        self.vscode = vscode_controller
        self.workspace_root = Path(workspace_root)
        self.match_threshold = match_threshold
        self.max_attempts = max_attempts
        self.verifier = FileVerifier(
            workspace_root,
            match_threshold=match_threshold,
        )

    def remediate_session(
        self,
        session: 'ReplaySession',
        expected_contents: Optional[dict] = None,
    ) -> RemediationSummary:
        """Verify and remediate all files in a session.

        Args:
            session: The replay session with expected content.
            expected_contents: Optional dict of path -> expected content.
                             If not provided, built from session operations.

        Returns:
            RemediationSummary with results for all files.
        """
        logger.info(f"Starting post-replay verification and remediation")

        results = []
        files_ok = 0
        files_remediated = 0
        files_failed = 0

        for file_ops in session.files:
            # Get expected content
            if expected_contents and file_ops.path in expected_contents:
                expected = expected_contents[file_ops.path]
            else:
                expected = self._build_expected_content(file_ops)

            if not expected:
                logger.warning(f"No expected content for {file_ops.path}, skipping")
                continue

            # Verify the file
            comparison = self.verifier.verify_file(file_ops.path, expected)

            if comparison.match_status == "match":
                logger.info(f"✓ {file_ops.path}: OK ({comparison.similarity:.1%})")
                files_ok += 1
                results.append(RemediationResult(
                    file_path=file_ops.path,
                    original_similarity=comparison.similarity,
                    final_similarity=comparison.similarity,
                    success=True,
                    attempts=0,
                ))
                continue

            # File needs remediation
            logger.warning(
                f"✗ {file_ops.path}: {comparison.match_status} "
                f"({comparison.similarity:.1%}) - attempting remediation"
            )

            result = self._remediate_file(
                file_ops.path,
                expected,
                comparison.similarity,
            )
            results.append(result)

            if result.success:
                files_remediated += 1
                logger.info(
                    f"✓ {file_ops.path}: FIXED "
                    f"({result.original_similarity:.1%} → {result.final_similarity:.1%})"
                )
            else:
                files_failed += 1
                logger.error(
                    f"✗ {file_ops.path}: FAILED to remediate "
                    f"({result.final_similarity:.1%})"
                )

        total = len(session.files)
        logger.info(
            f"Remediation complete: {files_ok} OK, "
            f"{files_remediated} fixed, {files_failed} failed"
        )

        return RemediationSummary(
            total_files=total,
            files_ok=files_ok,
            files_remediated=files_remediated,
            files_failed=files_failed,
            results=results,
        )

    def _remediate_file(
        self,
        path: str,
        expected_content: str,
        original_similarity: float,
    ) -> RemediationResult:
        """Remediate a single file by directly writing the correct content.

        Since the purpose of replay is to generate authentic typing activity
        during the replay phase (when Upwork is capturing), post-replay
        remediation can write files directly - no need to re-type through
        VS Code which has IntelliSense interference issues.

        Args:
            path: File path relative to workspace.
            expected_content: The content that should be in the file.
            original_similarity: Similarity before remediation.

        Returns:
            RemediationResult with outcome.
        """
        attempts = 0
        final_similarity = original_similarity
        error = None

        file_path = self.workspace_root / path

        for attempt in range(1, self.max_attempts + 1):
            attempts = attempt
            logger.info(f"Remediation attempt {attempt}/{self.max_attempts} for {path}")

            try:
                # Write file content directly (fast and reliable)
                logger.info(f"Writing {len(expected_content)} characters directly to file...")
                file_path.write_text(expected_content)

                # Verify the fix
                comparison = self.verifier.verify_file(path, expected_content)
                final_similarity = comparison.similarity

                if comparison.match_status == "match":
                    # Reload the file in VS Code to show the fix
                    try:
                        if self.vscode.open_file(path):
                            time.sleep(0.3)
                    except Exception:
                        pass  # Not critical if reload fails

                    return RemediationResult(
                        file_path=path,
                        original_similarity=original_similarity,
                        final_similarity=final_similarity,
                        success=True,
                        attempts=attempts,
                    )
                else:
                    logger.warning(
                        f"Attempt {attempt} result: {comparison.match_status} "
                        f"({final_similarity:.1%})"
                    )
                    error = f"Still {comparison.match_status} after writing"

            except Exception as e:
                logger.error(f"Remediation attempt {attempt} failed: {e}")
                error = str(e)

        return RemediationResult(
            file_path=path,
            original_similarity=original_similarity,
            final_similarity=final_similarity,
            success=False,
            attempts=attempts,
            error=error,
        )

    def _build_expected_content(self, file_ops) -> str:
        """Build expected content from file operations."""
        content_parts = []
        for op in file_ops.operations:
            if op.op_type.value == 'insert' and op.content:
                content_parts.append(op.content)
        return ''.join(content_parts)


def remediate_after_replay(
    session: 'ReplaySession',
    vscode_controller: 'VSCodeController',
    workspace_root: Path,
) -> RemediationSummary:
    """Convenience function to verify and remediate after replay.

    Args:
        session: The completed replay session.
        vscode_controller: VS Code controller for typing fixes.
        workspace_root: Root directory of workspace.

    Returns:
        RemediationSummary with results.
    """
    remediator = Remediator(
        vscode_controller=vscode_controller,
        workspace_root=workspace_root,
    )
    return remediator.remediate_session(session)
