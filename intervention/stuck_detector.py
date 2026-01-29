"""Stuck detection for replay intervention system.

This module detects when the replay appears stuck by comparing consecutive
screenshots. If no visual change is detected for a threshold period,
recovery actions are triggered.
"""

import io
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from intervention.screenshot import Screenshot

logger = logging.getLogger(__name__)


class StuckStatus(Enum):
    """Status of stuck detection.

    Values:
        OK: Normal operation, changes detected.
        POSSIBLY_STUCK: No change detected, but under threshold.
        STUCK: No change detected for threshold duration.
        NO_BASELINE: First screenshot, no comparison possible.
    """
    OK = "ok"
    POSSIBLY_STUCK = "possibly_stuck"
    STUCK = "stuck"
    NO_BASELINE = "no_baseline"


@dataclass
class StuckCheckResult:
    """Result of a stuck detection check.

    Attributes:
        status: Current stuck status.
        seconds_unchanged: How long the screen has been unchanged.
        similarity: Similarity ratio between current and previous (0.0 to 1.0).
        recovery_actions: Suggested recovery actions if stuck.
        description: Human-readable description.
    """
    status: StuckStatus
    seconds_unchanged: float
    similarity: float
    recovery_actions: List[str]
    description: str


class StuckDetector:
    """Detects when replay is stuck by comparing screenshots over time.

    Compares consecutive screenshots using pixel similarity. If the screen
    hasn't changed significantly for the threshold duration, triggers
    stuck recovery.

    Args:
        stuck_threshold_seconds: Duration of no change before flagging stuck.
        similarity_threshold: Minimum similarity (0-1) to consider "unchanged".
        comparison_size: Resize screenshots to this size for faster comparison.
    """

    # Default recovery actions for stuck state
    DEFAULT_RECOVERY_ACTIONS = [
        "click_editor",      # Click in the editor area to ensure focus
        "press Escape",      # Clear any invisible state
        "key ctrl+1",        # Focus first editor group
        "wait 1",            # Brief pause
    ]

    def __init__(
        self,
        stuck_threshold_seconds: float = 60.0,
        similarity_threshold: float = 0.98,
        comparison_size: tuple = (128, 72),
    ):
        """Initialize the stuck detector.

        Args:
            stuck_threshold_seconds: Seconds of no change before "stuck".
            similarity_threshold: Similarity ratio to consider unchanged (0.0-1.0).
            comparison_size: Thumbnail size for comparison (width, height).
        """
        self.stuck_threshold_seconds = stuck_threshold_seconds
        self.similarity_threshold = similarity_threshold
        self.comparison_size = comparison_size

        # State
        self._previous_thumbnail: Optional[bytes] = None
        self._last_change_time: float = time.time()
        self._check_count: int = 0

        logger.info(
            f"StuckDetector initialized: threshold={stuck_threshold_seconds}s, "
            f"similarity={similarity_threshold}, size={comparison_size}"
        )

    def check(self, screenshot: 'Screenshot') -> StuckCheckResult:
        """Check if the replay appears stuck.

        Compares the current screenshot to the previous one. If they're
        too similar for too long, returns STUCK status with recovery actions.

        Args:
            screenshot: Current screenshot to check.

        Returns:
            StuckCheckResult with status and any recovery actions.
        """
        self._check_count += 1
        current_time = time.time()

        # Create thumbnail for comparison
        try:
            current_thumbnail = self._create_thumbnail(screenshot)
        except Exception as e:
            logger.warning(f"Failed to create thumbnail: {e}")
            return StuckCheckResult(
                status=StuckStatus.OK,
                seconds_unchanged=0.0,
                similarity=0.0,
                recovery_actions=[],
                description=f"Thumbnail creation failed: {e}"
            )

        # First screenshot - no comparison possible
        if self._previous_thumbnail is None:
            self._previous_thumbnail = current_thumbnail
            self._last_change_time = current_time
            logger.debug("First screenshot captured for stuck detection baseline")
            return StuckCheckResult(
                status=StuckStatus.NO_BASELINE,
                seconds_unchanged=0.0,
                similarity=0.0,
                recovery_actions=[],
                description="First screenshot, establishing baseline"
            )

        # Compare with previous
        similarity = self._compare_thumbnails(current_thumbnail, self._previous_thumbnail)

        if similarity < self.similarity_threshold:
            # Screen changed - reset timer
            self._previous_thumbnail = current_thumbnail
            self._last_change_time = current_time
            logger.debug(f"Screen changed (similarity={similarity:.3f})")
            return StuckCheckResult(
                status=StuckStatus.OK,
                seconds_unchanged=0.0,
                similarity=similarity,
                recovery_actions=[],
                description=f"Screen changed (similarity={similarity:.2%})"
            )

        # Screen unchanged - check duration
        seconds_unchanged = current_time - self._last_change_time

        # Update thumbnail even when unchanged (in case of gradual drift)
        self._previous_thumbnail = current_thumbnail

        if seconds_unchanged >= self.stuck_threshold_seconds:
            logger.warning(
                f"STUCK DETECTED: No change for {seconds_unchanged:.1f}s "
                f"(similarity={similarity:.3f})"
            )
            return StuckCheckResult(
                status=StuckStatus.STUCK,
                seconds_unchanged=seconds_unchanged,
                similarity=similarity,
                recovery_actions=self.DEFAULT_RECOVERY_ACTIONS.copy(),
                description=f"No change for {seconds_unchanged:.0f}s - appears stuck"
            )

        # Unchanged but not yet at threshold
        logger.debug(
            f"Possibly stuck: unchanged for {seconds_unchanged:.1f}s "
            f"(threshold={self.stuck_threshold_seconds}s)"
        )
        return StuckCheckResult(
            status=StuckStatus.POSSIBLY_STUCK,
            seconds_unchanged=seconds_unchanged,
            similarity=similarity,
            recovery_actions=[],
            description=f"Unchanged for {seconds_unchanged:.0f}s (threshold={self.stuck_threshold_seconds:.0f}s)"
        )

    def reset(self) -> None:
        """Reset the detector state.

        Call this when starting a new file or after recovery to establish
        a new baseline.
        """
        self._previous_thumbnail = None
        self._last_change_time = time.time()
        logger.debug("Stuck detector reset")

    def _create_thumbnail(self, screenshot: 'Screenshot') -> bytes:
        """Create a small thumbnail for fast comparison.

        Args:
            screenshot: Screenshot to thumbnail.

        Returns:
            Raw pixel bytes of the thumbnail.
        """
        try:
            from PIL import Image
        except ImportError:
            raise RuntimeError("Pillow not installed. Install with: pip install Pillow")

        # Load image from screenshot data
        img = Image.open(io.BytesIO(screenshot.data))

        # Convert to RGB if necessary (handles RGBA, etc.)
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Resize to comparison size
        thumbnail = img.resize(self.comparison_size, Image.Resampling.LANCZOS)

        # Return raw pixel bytes
        return thumbnail.tobytes()

    def _compare_thumbnails(self, thumb1: bytes, thumb2: bytes) -> float:
        """Compare two thumbnails and return similarity ratio.

        Uses mean absolute difference of pixel values.

        Args:
            thumb1: First thumbnail bytes.
            thumb2: Second thumbnail bytes.

        Returns:
            Similarity ratio from 0.0 (completely different) to 1.0 (identical).
        """
        if len(thumb1) != len(thumb2):
            logger.warning("Thumbnail size mismatch")
            return 0.0

        if len(thumb1) == 0:
            return 1.0

        # Calculate mean absolute difference
        total_diff = 0
        for b1, b2 in zip(thumb1, thumb2):
            total_diff += abs(b1 - b2)

        # Normalize: max diff per byte is 255
        max_diff = len(thumb1) * 255
        mean_diff = total_diff / max_diff

        # Convert to similarity (1 = identical, 0 = completely different)
        similarity = 1.0 - mean_diff

        return similarity

    @property
    def seconds_since_change(self) -> float:
        """Get seconds since last detected change."""
        return time.time() - self._last_change_time

    @property
    def check_count(self) -> int:
        """Get total number of checks performed."""
        return self._check_count
