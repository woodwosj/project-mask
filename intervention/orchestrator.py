"""Intervention orchestrator for AI-powered replay monitoring.

This module coordinates all intervention components:
- Periodic screenshot capture
- AI analysis via Claude
- Recovery action execution
- Event logging and state management
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Event, Thread, Lock
from typing import Callable, List, Optional, TYPE_CHECKING
import logging
import time
import os

if TYPE_CHECKING:
    from intervention.screenshot import ScreenshotBackend, Screenshot
    from intervention.analyzer import ClaudeAnalyzer, AnalysisResult, ReplayStatus
    from intervention.recovery import RecoveryExecutor, RecoveryResult
    from intervention.stuck_detector import StuckDetector, StuckCheckResult

logger = logging.getLogger(__name__)


@dataclass
class InterventionEvent:
    """Record of an intervention attempt.

    Attributes:
        timestamp: When the intervention occurred.
        status: Detected replay status.
        confidence: Confidence in the detection.
        actions_taken: List of recovery actions executed.
        recovery_success: Whether recovery was successful.
        screenshot_path: Path to saved screenshot (if saved).
        description: Description from analysis.
        duration_ms: Total duration of intervention in milliseconds.
    """
    timestamp: datetime
    status: str  # ReplayStatus value
    confidence: float
    actions_taken: List[str]
    recovery_success: bool
    screenshot_path: Optional[Path]
    description: str = ""
    duration_ms: float = 0.0


@dataclass
class InterventionConfig:
    """Configuration for intervention system.

    Attributes:
        enabled: Whether intervention monitoring is enabled.
        interval_seconds: Time between checks (default: 600 = 10 minutes).
        min_cooldown_seconds: Minimum time between recovery attempts.
        max_retries: Maximum recovery attempts before critical failure.
        confidence_threshold: Minimum confidence to trigger recovery.
        screenshot_dir: Directory for saved screenshots.
        save_screenshots: Whether to save screenshots for debugging.
        check_on_file_change: Perform check after each file completes.
        stuck_detection_enabled: Enable stuck detection via screenshot comparison.
        stuck_threshold_seconds: Seconds of no change before flagging stuck.
        stuck_similarity_threshold: Similarity ratio (0-1) to consider unchanged.
    """
    enabled: bool = True
    interval_seconds: int = 600
    min_cooldown_seconds: int = 60
    max_retries: int = 3
    confidence_threshold: float = 0.85
    screenshot_dir: Path = field(default_factory=lambda: Path.home() / ".mask" / "screenshots")
    save_screenshots: bool = True
    check_on_file_change: bool = True
    stuck_detection_enabled: bool = False  # Disabled - causes interference during long typing
    stuck_threshold_seconds: float = 300.0  # 5 minutes - typing large files takes time
    stuck_similarity_threshold: float = 0.995  # Higher threshold - small changes count

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> 'InterventionConfig':
        """Create config from dictionary.

        Args:
            data: Configuration dictionary (may be None).

        Returns:
            InterventionConfig instance.
        """
        if not data:
            return cls()

        # Handle screenshot_dir path expansion
        screenshot_dir = data.get('screenshot_dir')
        if screenshot_dir:
            screenshot_dir = Path(os.path.expanduser(screenshot_dir))
        else:
            screenshot_dir = Path.home() / ".mask" / "screenshots"

        return cls(
            enabled=data.get('enabled', True),
            interval_seconds=data.get('interval_seconds', 600),
            min_cooldown_seconds=data.get('min_cooldown_seconds', 60),
            max_retries=data.get('max_retries', 3),
            confidence_threshold=data.get('confidence_threshold', 0.85),
            screenshot_dir=screenshot_dir,
            save_screenshots=data.get('save_screenshots', True),
            check_on_file_change=data.get('check_on_file_change', True),
            stuck_detection_enabled=data.get('stuck_detection_enabled', True),
            stuck_threshold_seconds=data.get('stuck_threshold_seconds', 60.0),
            stuck_similarity_threshold=data.get('stuck_similarity_threshold', 0.98),
        )


class InterventionOrchestrator:
    """Orchestrates periodic screenshot analysis and recovery.

    This class manages:
    - Background monitoring thread with configurable interval
    - Screenshot capture and optional persistence
    - AI analysis via ClaudeAnalyzer
    - Recovery action execution with cooldown and retry limits
    - Event recording for post-session review

    Example:
        orchestrator = InterventionOrchestrator(
            config=InterventionConfig(interval_seconds=600),
            screenshot_backend=MSSBackend(),
            analyzer=ClaudeAnalyzer(api_key="..."),
            recovery_executor=RecoveryExecutor(input_backend, vscode_controller),
        )

        orchestrator.start()
        try:
            # Run replay...
            pass
        finally:
            orchestrator.stop()
    """

    def __init__(
        self,
        config: InterventionConfig,
        screenshot_backend: 'ScreenshotBackend',
        analyzer: 'ClaudeAnalyzer',
        recovery_executor: 'RecoveryExecutor',
    ):
        """Initialize the orchestrator.

        Args:
            config: Intervention configuration.
            screenshot_backend: Backend for capturing screenshots.
            analyzer: Claude analyzer for screenshot analysis.
            recovery_executor: Executor for recovery actions.
        """
        self.config = config
        self.screenshot = screenshot_backend
        self.analyzer = analyzer
        self.recovery = recovery_executor

        # State
        self._events: List[InterventionEvent] = []
        self._stop_event = Event()
        self._monitor_thread: Optional[Thread] = None
        self._last_intervention: float = 0
        self._retry_count: int = 0
        self._lock = Lock()

        # Current context for analysis
        self._current_context: Optional[str] = None

        # Stuck detector
        self._stuck_detector: Optional['StuckDetector'] = None
        if config.stuck_detection_enabled:
            from intervention.stuck_detector import StuckDetector
            self._stuck_detector = StuckDetector(
                stuck_threshold_seconds=config.stuck_threshold_seconds,
                similarity_threshold=config.stuck_similarity_threshold,
            )
            logger.info(f"Stuck detection enabled (threshold={config.stuck_threshold_seconds}s)")

        # Callbacks
        self._on_critical_failure: Optional[Callable[[], None]] = None
        self._on_intervention: Optional[Callable[[InterventionEvent], None]] = None

        logger.info(f"InterventionOrchestrator initialized "
                   f"(interval={config.interval_seconds}s, "
                   f"threshold={config.confidence_threshold})")

    def start(self) -> None:
        """Start the intervention monitoring thread.

        Does nothing if intervention is disabled or already running.
        """
        if not self.config.enabled:
            logger.info("Intervention system disabled by config")
            return

        with self._lock:
            if self._monitor_thread and self._monitor_thread.is_alive():
                logger.warning("Intervention monitoring already running")
                return

            self._stop_event.clear()
            self._retry_count = 0
            self._last_intervention = 0

            self._monitor_thread = Thread(
                target=self._monitor_loop,
                name="intervention-monitor",
                daemon=True,
            )
            self._monitor_thread.start()

        logger.info(f"Intervention monitoring started "
                   f"(check every {self.config.interval_seconds}s)")

    def stop(self) -> None:
        """Stop the intervention monitoring thread.

        Waits up to 5 seconds for graceful shutdown.
        """
        self._stop_event.set()

        with self._lock:
            if self._monitor_thread:
                self._monitor_thread.join(timeout=5)
                if self._monitor_thread.is_alive():
                    logger.warning("Intervention thread did not stop gracefully")
                self._monitor_thread = None

        logger.info(f"Intervention monitoring stopped "
                   f"({len(self._events)} events recorded)")

    def is_running(self) -> bool:
        """Check if the monitoring thread is running.

        Returns:
            True if monitoring is active.
        """
        with self._lock:
            return (self._monitor_thread is not None and
                    self._monitor_thread.is_alive())

    def set_context(self, context: str) -> None:
        """Set the current context for analysis.

        The context provides information about what the replay is doing,
        helping Claude make better analysis decisions.

        Args:
            context: Description of current state (e.g., "Typing file.py line 42").
        """
        self._current_context = context

    def check_now(self, context: Optional[str] = None) -> InterventionEvent:
        """Perform an immediate intervention check.

        Can be called from the main thread (e.g., between file operations)
        in addition to the background periodic checks.

        Performs both stuck detection (fast, local) and AI analysis.

        Args:
            context: Optional context about current replay state.
                    Overrides any context set via set_context().

        Returns:
            InterventionEvent with results.
        """
        start_time = time.time()
        check_context = context or self._current_context

        logger.info("Performing intervention check...")

        # Capture screenshot
        try:
            screenshot = self.screenshot.capture_screen()
        except Exception as e:
            logger.error(f"Screenshot capture failed: {e}")
            return self._record_event(
                status="unknown",
                confidence=0.0,
                description=f"Screenshot failed: {e}",
                actions_taken=[],
                recovery_success=True,  # Don't count as failure
                screenshot_path=None,
                duration_ms=(time.time() - start_time) * 1000,
            )

        # Save screenshot if enabled
        screenshot_path = None
        if self.config.save_screenshots:
            screenshot_path = self._save_screenshot(screenshot)

        # Check for stuck state first (fast, no API call)
        stuck_result = None
        if self._stuck_detector:
            stuck_result = self._stuck_detector.check(screenshot)
            logger.debug(f"Stuck check: {stuck_result.status.value} "
                        f"(unchanged {stuck_result.seconds_unchanged:.0f}s, "
                        f"similarity {stuck_result.similarity:.2%})")

            if stuck_result.status.value == "stuck":
                logger.warning(f"STUCK DETECTED: {stuck_result.description}")

                # Execute stuck recovery actions
                if self._can_intervene():
                    logger.info(f"Executing stuck recovery: {stuck_result.recovery_actions}")
                    try:
                        recovery_results = self.recovery.execute(stuck_result.recovery_actions)
                        actions_taken = [r.action_taken for r in recovery_results]
                        recovery_success = all(r.success for r in recovery_results)
                    except Exception as e:
                        logger.error(f"Stuck recovery failed: {e}")
                        actions_taken = [f"ERROR: {e}"]
                        recovery_success = False

                    self._last_intervention = time.time()

                    # Reset stuck detector after recovery attempt
                    self._stuck_detector.reset()

                    if not recovery_success:
                        self._retry_count += 1
                        if self._retry_count >= self.config.max_retries:
                            logger.error(f"Max recovery retries ({self.config.max_retries}) reached")
                            self._trigger_critical_failure()
                    else:
                        self._retry_count = 0

                    duration_ms = (time.time() - start_time) * 1000
                    return self._record_event(
                        status="stuck",
                        confidence=1.0,
                        description=stuck_result.description,
                        actions_taken=actions_taken,
                        recovery_success=recovery_success,
                        screenshot_path=screenshot_path,
                        duration_ms=duration_ms,
                    )
                else:
                    logger.debug("Stuck intervention skipped (cooldown active)")

        # Analyze screenshot with AI
        try:
            result = self.analyzer.analyze(screenshot, context=check_context)
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return self._record_event(
                status="unknown",
                confidence=0.0,
                description=f"Analysis failed: {e}",
                actions_taken=[],
                recovery_success=True,
                screenshot_path=screenshot_path,
                duration_ms=(time.time() - start_time) * 1000,
            )

        logger.info(f"Analysis result: {result.status.value} "
                   f"(confidence: {result.confidence:.2f})")

        # Determine if recovery is needed
        actions_taken = []
        recovery_success = True

        if result.status.value != "normal":
            if result.confidence >= self.config.confidence_threshold:
                if self._can_intervene():
                    # Execute recovery
                    logger.info(f"Executing recovery: {result.recovery_actions}")
                    try:
                        recovery_results = self.recovery.execute(result.recovery_actions)
                        actions_taken = [r.action_taken for r in recovery_results]
                        recovery_success = all(r.success for r in recovery_results)
                    except Exception as e:
                        logger.error(f"Recovery execution failed: {e}")
                        actions_taken = [f"ERROR: {e}"]
                        recovery_success = False

                    self._last_intervention = time.time()

                    if not recovery_success:
                        self._retry_count += 1
                        if self._retry_count >= self.config.max_retries:
                            logger.error(f"Max recovery retries ({self.config.max_retries}) reached")
                            self._trigger_critical_failure()
                    else:
                        # Reset retry count on successful recovery
                        self._retry_count = 0
                else:
                    logger.debug("Intervention skipped (cooldown active)")
            else:
                logger.debug(f"Confidence {result.confidence:.2f} below threshold "
                           f"{self.config.confidence_threshold}")

        duration_ms = (time.time() - start_time) * 1000

        return self._record_event(
            status=result.status.value,
            confidence=result.confidence,
            description=result.description,
            actions_taken=actions_taken,
            recovery_success=recovery_success,
            screenshot_path=screenshot_path,
            duration_ms=duration_ms,
        )

    def set_critical_failure_callback(
        self,
        callback: Callable[[], None],
    ) -> None:
        """Set callback for critical failure notification.

        The callback is invoked when max retries are exceeded.

        Args:
            callback: Function to call on critical failure.
        """
        self._on_critical_failure = callback

    def set_intervention_callback(
        self,
        callback: Callable[[InterventionEvent], None],
    ) -> None:
        """Set callback for intervention events.

        The callback is invoked after each intervention check.

        Args:
            callback: Function to call with each InterventionEvent.
        """
        self._on_intervention = callback

    def get_events(self) -> List[InterventionEvent]:
        """Get all recorded intervention events.

        Returns:
            Copy of the events list.
        """
        with self._lock:
            return self._events.copy()

    def get_statistics(self) -> dict:
        """Get intervention statistics.

        Returns:
            Dictionary with counts and rates.
        """
        with self._lock:
            events = self._events.copy()

        total = len(events)
        if total == 0:
            return {
                'total_checks': 0,
                'normal_count': 0,
                'intervention_count': 0,
                'recovery_success_rate': 1.0,
            }

        normal = sum(1 for e in events if e.status == "normal")
        interventions = [e for e in events if e.actions_taken]
        intervention_count = len(interventions)
        successful = sum(1 for e in interventions if e.recovery_success)

        return {
            'total_checks': total,
            'normal_count': normal,
            'intervention_count': intervention_count,
            'recovery_success_rate': successful / intervention_count if intervention_count > 0 else 1.0,
            'current_retry_count': self._retry_count,
        }

    def reset_retry_count(self) -> None:
        """Reset the retry counter.

        Call this when replay state is known to be good (e.g., after
        successful file operation).
        """
        self._retry_count = 0

    def reset_stuck_detector(self) -> None:
        """Reset the stuck detector baseline.

        Call this when the screen is expected to change significantly
        (e.g., after opening a new file, after recovery).
        """
        if self._stuck_detector:
            self._stuck_detector.reset()
            logger.debug("Stuck detector reset")

    def on_file_change(self) -> None:
        """Notify orchestrator that a file change occurred.

        Call this when switching to a new file during replay.
        Resets stuck detector since file changes cause visual changes.
        """
        self.reset_stuck_detector()
        self.reset_retry_count()

    def _monitor_loop(self) -> None:
        """Background monitoring loop.

        Runs until stop_event is set, performing checks at configured interval.
        """
        logger.debug("Monitor loop started")

        while not self._stop_event.wait(timeout=self.config.interval_seconds):
            try:
                self.check_now()
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
                # Continue monitoring despite errors

        logger.debug("Monitor loop exited")

    def _can_intervene(self) -> bool:
        """Check if enough time has passed since last intervention.

        Returns:
            True if cooldown period has elapsed.
        """
        elapsed = time.time() - self._last_intervention
        return elapsed >= self.config.min_cooldown_seconds

    def _save_screenshot(self, screenshot: 'Screenshot') -> Path:
        """Save screenshot to debug directory.

        Args:
            screenshot: Screenshot to save.

        Returns:
            Path where screenshot was saved.
        """
        self.config.screenshot_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = "jpg" if screenshot.media_type == "image/jpeg" else "png"
        filename = f"check_{timestamp}.{ext}"
        filepath = self.config.screenshot_dir / filename

        screenshot.save(filepath)
        logger.debug(f"Screenshot saved: {filepath}")

        return filepath

    def _record_event(
        self,
        status: str,
        confidence: float,
        description: str,
        actions_taken: List[str],
        recovery_success: bool,
        screenshot_path: Optional[Path],
        duration_ms: float,
    ) -> InterventionEvent:
        """Record an intervention event.

        Args:
            status: Detected status.
            confidence: Detection confidence.
            description: Analysis description.
            actions_taken: List of executed actions.
            recovery_success: Whether recovery succeeded.
            screenshot_path: Path to saved screenshot.
            duration_ms: Check duration.

        Returns:
            The recorded event.
        """
        event = InterventionEvent(
            timestamp=datetime.now(),
            status=status,
            confidence=confidence,
            description=description,
            actions_taken=actions_taken,
            recovery_success=recovery_success,
            screenshot_path=screenshot_path,
            duration_ms=duration_ms,
        )

        with self._lock:
            self._events.append(event)

        # Invoke callback if set
        if self._on_intervention:
            try:
                self._on_intervention(event)
            except Exception as e:
                logger.warning(f"Intervention callback error: {e}")

        return event

    def _trigger_critical_failure(self) -> None:
        """Trigger critical failure callback.

        Called when max retries are exceeded.
        """
        logger.error("Critical intervention failure - triggering callback")

        if self._on_critical_failure:
            try:
                self._on_critical_failure()
            except Exception as e:
                logger.error(f"Critical failure callback error: {e}")


def create_orchestrator(
    config: dict,
    input_backend: 'InputBackend',
    vscode_controller: 'VSCodeController',
) -> Optional[InterventionOrchestrator]:
    """Factory function to create an InterventionOrchestrator.

    Creates all required components and assembles the orchestrator.
    Returns None if intervention is disabled or API key is missing.

    Args:
        config: Full configuration dictionary.
        input_backend: Input backend for recovery actions.
        vscode_controller: VS Code controller for recovery actions.

    Returns:
        InterventionOrchestrator or None if disabled/unavailable.
    """
    from intervention.screenshot import create_screenshot_backend
    from intervention.analyzer import ClaudeAnalyzer
    from intervention.recovery import RecoveryExecutor

    intervention_config = InterventionConfig.from_dict(config.get('intervention'))

    if not intervention_config.enabled:
        logger.info("Intervention system disabled")
        return None

    # Get API key from environment
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set - intervention disabled")
        return None

    try:
        # Create components
        screenshot_backend = create_screenshot_backend(config)
        analyzer = ClaudeAnalyzer(
            api_key=api_key,
            model=config.get('intervention', {}).get('model'),
        )
        recovery_executor = RecoveryExecutor(input_backend, vscode_controller)

        # Create orchestrator
        orchestrator = InterventionOrchestrator(
            config=intervention_config,
            screenshot_backend=screenshot_backend,
            analyzer=analyzer,
            recovery_executor=recovery_executor,
        )

        logger.info("Intervention orchestrator created successfully")
        return orchestrator

    except Exception as e:
        logger.error(f"Failed to create intervention orchestrator: {e}")
        return None
