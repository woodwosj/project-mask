# AI Intervention System - Technical Design

## Context

PROJECT MASK runs unattended replay sessions that can fail silently due to VS Code dialogs, wrong files, or input errors. This design introduces an AI-powered monitoring layer that periodically captures screenshots, sends them to Claude Opus 4.5 for analysis, and executes recovery actions when problems are detected.

**Stakeholders:**
- Developers running unattended replay sessions
- Upwork clients expecting consistent activity capture

**Constraints:**
- Must run on ARM64 SBC (Raspberry Pi 5 / Radxa Rock5B+)
- Limited memory and CPU budget
- External API dependency (Anthropic)
- Must not interfere with Upwork's screenshot capture timing

## Goals / Non-Goals

### Goals
- Detect common failure modes via visual analysis
- Execute automated recovery without human intervention
- Verify output files match expected content
- Maintain detailed logs for debugging failed interventions
- Gracefully degrade when AI service unavailable

### Non-Goals
- Real-time monitoring (too resource-intensive)
- Training custom models (use Claude as-is)
- Recovering from hardware failures
- Modifying Upwork tracker behavior

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Intervention System                                │
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────┐ │
│  │  Screenshot  │───▶│   Claude     │───▶│   Recovery   │───▶│  Input    │ │
│  │   Capture    │    │   Analyzer   │    │   Actions    │    │  Backend  │ │
│  └──────────────┘    └──────────────┘    └──────────────┘    └───────────┘ │
│         │                   │                   │                          │
│         │                   ▼                   │                          │
│         │            ┌──────────────┐           │                          │
│         └───────────▶│ Intervention │◀──────────┘                          │
│                      │ Orchestrator │                                       │
│                      └──────────────┘                                       │
│                             │                                               │
│                             ▼                                               │
│                      ┌──────────────┐                                       │
│                      │    File      │                                       │
│                      │   Verifier   │                                       │
│                      └──────────────┘                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Existing Systems                                    │
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │   Replay     │◀──▶│   VS Code    │◀──▶│   Session    │                  │
│  │   Engine     │    │  Controller  │    │ Orchestrator │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Design

### 1. Screenshot Capture (`intervention/screenshot.py`)

**Responsibilities:**
- Capture full-screen or VS Code window screenshots
- Compress images for API efficiency
- Save debug copies with timestamps

**Implementation:**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import base64
import io
import logging

logger = logging.getLogger(__name__)


@dataclass
class Screenshot:
    """Captured screenshot with metadata."""
    image_data: bytes
    media_type: str  # "image/png" or "image/jpeg"
    width: int
    height: int
    timestamp: float

    def to_base64(self) -> str:
        """Encode image as base64 for API submission."""
        return base64.b64encode(self.image_data).decode('utf-8')

    def save(self, path: Path) -> None:
        """Save screenshot to file for debugging."""
        path.write_bytes(self.image_data)


class ScreenshotBackend(ABC):
    """Abstract base class for screenshot capture backends."""

    @abstractmethod
    def capture_screen(self) -> Screenshot:
        """Capture the entire screen."""
        pass

    @abstractmethod
    def capture_window(self, window_id: str) -> Screenshot:
        """Capture a specific window by ID."""
        pass


class ScrotBackend(ScreenshotBackend):
    """Screenshot backend using scrot (X11)."""

    def capture_screen(self) -> Screenshot:
        # Use subprocess to call scrot, capture to stdout
        # Compress to JPEG for smaller payload
        pass

    def capture_window(self, window_id: str) -> Screenshot:
        # scrot -u for focused window, or specify window ID
        pass


class MSSBackend(ScreenshotBackend):
    """Screenshot backend using mss (pure Python, cross-platform)."""

    def capture_screen(self) -> Screenshot:
        # Use mss.mss() context manager
        # Grab primary monitor
        pass

    def capture_window(self, window_id: str) -> Screenshot:
        # Get window geometry via xdotool getwindowgeometry
        # Capture region using mss
        pass


def create_screenshot_backend(config: dict) -> ScreenshotBackend:
    """Factory function to create appropriate backend."""
    backend_type = config.get('intervention', {}).get('screenshot_backend', 'auto')

    if backend_type == 'scrot':
        return ScrotBackend()
    elif backend_type == 'mss':
        return MSSBackend()
    else:
        # Auto-detect: prefer mss for portability, fall back to scrot
        try:
            import mss
            return MSSBackend()
        except ImportError:
            return ScrotBackend()
```

**Optimization Strategy:**
- Capture as JPEG (smaller than PNG for photos/screenshots)
- Resize to max 1920x1080 if larger
- Target file size: ~200KB-500KB per screenshot
- Compression quality: 85% JPEG

### 2. Claude Vision Analyzer (`intervention/analyzer.py`)

**Responsibilities:**
- Submit screenshots to Anthropic API
- Parse structured responses
- Handle API errors gracefully

**Implementation:**

```python
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import anthropic
import json
import logging

logger = logging.getLogger(__name__)


class ReplayStatus(Enum):
    """Detected replay status from screenshot analysis."""
    NORMAL = "normal"           # Replay progressing as expected
    DIALOG_BLOCKING = "dialog"  # Modal dialog blocking input
    WRONG_FILE = "wrong_file"   # Incorrect file/project open
    ERROR_STATE = "error"       # Error message or exception visible
    TERMINAL_FOCUS = "terminal" # Terminal has focus instead of editor
    UNKNOWN = "unknown"         # Unable to determine state


@dataclass
class AnalysisResult:
    """Result of screenshot analysis."""
    status: ReplayStatus
    confidence: float  # 0.0 to 1.0
    description: str
    recovery_actions: List[str]  # Ordered list of recovery steps
    expected_file: Optional[str]  # What file should be open
    actual_file: Optional[str]   # What file appears to be open
    raw_response: str            # Full Claude response for debugging


class ClaudeAnalyzer:
    """Analyzes screenshots using Claude Opus 4.5 vision."""

    SYSTEM_PROMPT = """You are a QA assistant for an automated code replay system.
You analyze screenshots of VS Code to detect if the replay is proceeding normally or if intervention is needed.

Analyze the screenshot and respond with a JSON object containing:
{
    "status": "normal" | "dialog" | "wrong_file" | "error" | "terminal" | "unknown",
    "confidence": 0.0-1.0,
    "description": "Brief description of what you see",
    "recovery_actions": ["action1", "action2"],  // Empty if status is normal
    "expected_file": "filename or null if unknown",
    "actual_file": "filename visible in tab or null"
}

Recovery actions should be specific xdotool-compatible instructions like:
- "press Escape" (close dialogs)
- "press Return" (confirm dialogs)
- "key ctrl+p" (open file picker)
- "key ctrl+shift+p" (command palette)
- "key ctrl+w" (close current tab)
- "focus_vscode" (bring VS Code to front)
- "type <filename>" (type in file picker)

Be conservative: only suggest recovery if confidence > 0.8.
If the screenshot shows normal coding activity in VS Code, return status "normal"."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-5-20250514"):
        """Initialize the analyzer with Anthropic API credentials.

        Args:
            api_key: Anthropic API key.
            model: Model ID to use for analysis.
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def analyze(
        self,
        screenshot: 'Screenshot',
        context: Optional[str] = None,
    ) -> AnalysisResult:
        """Analyze a screenshot to determine replay status.

        Args:
            screenshot: Screenshot to analyze.
            context: Optional context about current replay state.

        Returns:
            AnalysisResult with status and recovery actions.
        """
        user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": screenshot.media_type,
                    "data": screenshot.to_base64(),
                }
            },
            {
                "type": "text",
                "text": self._build_prompt(context)
            }
        ]

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}]
            )

            return self._parse_response(response.content[0].text)

        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            return AnalysisResult(
                status=ReplayStatus.UNKNOWN,
                confidence=0.0,
                description=f"API error: {e}",
                recovery_actions=[],
                expected_file=None,
                actual_file=None,
                raw_response=""
            )

    def _build_prompt(self, context: Optional[str]) -> str:
        """Build the analysis prompt."""
        prompt = "Analyze this screenshot of the VS Code window during an automated code replay session."
        if context:
            prompt += f"\n\nContext: {context}"
        prompt += "\n\nRespond with JSON only, no markdown."
        return prompt

    def _parse_response(self, response_text: str) -> AnalysisResult:
        """Parse Claude's JSON response into AnalysisResult."""
        try:
            # Handle potential markdown code blocks
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]

            data = json.loads(text)

            return AnalysisResult(
                status=ReplayStatus(data.get("status", "unknown")),
                confidence=float(data.get("confidence", 0.5)),
                description=data.get("description", ""),
                recovery_actions=data.get("recovery_actions", []),
                expected_file=data.get("expected_file"),
                actual_file=data.get("actual_file"),
                raw_response=response_text
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse Claude response: {e}")
            return AnalysisResult(
                status=ReplayStatus.UNKNOWN,
                confidence=0.0,
                description=f"Parse error: {e}",
                recovery_actions=[],
                expected_file=None,
                actual_file=None,
                raw_response=response_text
            )
```

### 3. Recovery Actions (`intervention/recovery.py`)

**Responsibilities:**
- Execute recovery instructions from Claude
- Translate high-level actions to xdotool commands
- Verify recovery success

**Implementation:**

```python
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""
    success: bool
    action_taken: str
    error: Optional[str] = None


class RecoveryExecutor:
    """Executes recovery actions using the input backend."""

    # Action parsers: map action strings to execution methods
    ACTION_PATTERNS = {
        "press ": "_execute_key_press",
        "key ": "_execute_key_combo",
        "type ": "_execute_type",
        "focus_vscode": "_execute_focus_vscode",
        "click ": "_execute_click",
        "wait ": "_execute_wait",
    }

    def __init__(
        self,
        input_backend: 'InputBackend',
        vscode_controller: 'VSCodeController',
    ):
        """Initialize with input backend and VS Code controller.

        Args:
            input_backend: XdotoolBackend instance for input simulation.
            vscode_controller: VSCodeController for VS Code operations.
        """
        self.input = input_backend
        self.vscode = vscode_controller

    def execute(self, actions: List[str]) -> List[RecoveryResult]:
        """Execute a list of recovery actions in order.

        Args:
            actions: List of action strings from Claude.

        Returns:
            List of RecoveryResult objects.
        """
        results = []

        for action in actions:
            result = self._execute_action(action)
            results.append(result)

            if not result.success:
                logger.warning(f"Recovery action failed: {action}")
                break

            # Brief pause between actions
            time.sleep(0.5)

        return results

    def _execute_action(self, action: str) -> RecoveryResult:
        """Execute a single recovery action."""
        action_lower = action.lower().strip()

        for pattern, method_name in self.ACTION_PATTERNS.items():
            if action_lower.startswith(pattern):
                try:
                    method = getattr(self, method_name)
                    arg = action[len(pattern):].strip()
                    method(arg)
                    return RecoveryResult(success=True, action_taken=action)
                except Exception as e:
                    return RecoveryResult(
                        success=False,
                        action_taken=action,
                        error=str(e)
                    )

        return RecoveryResult(
            success=False,
            action_taken=action,
            error=f"Unknown action pattern: {action}"
        )

    def _execute_key_press(self, key: str) -> None:
        """Press a single key (e.g., 'Escape', 'Return')."""
        self.input.key_press(key)

    def _execute_key_combo(self, combo: str) -> None:
        """Press a key combination (e.g., 'ctrl+p')."""
        keys = combo.replace('+', ' ').split()
        self.input.key_combo(*keys)

    def _execute_type(self, text: str) -> None:
        """Type text."""
        self.input.type_text(text)

    def _execute_focus_vscode(self, _: str) -> None:
        """Focus VS Code window."""
        window_id = self.input.search_window("Visual Studio Code")
        if window_id:
            self.input.activate_window(window_id)
        else:
            raise RuntimeError("VS Code window not found")

    def _execute_click(self, coords: str) -> None:
        """Click at coordinates (x,y)."""
        x, y = map(int, coords.split(','))
        self.input.mouse_move_click(x, y)

    def _execute_wait(self, seconds: str) -> None:
        """Wait for specified seconds."""
        time.sleep(float(seconds))
```

### 4. File Verifier (`intervention/verifier.py`)

**Responsibilities:**
- Compare output files with expected content
- Calculate similarity scores
- Identify specific discrepancies

**Implementation:**

```python
from dataclasses import dataclass
from difflib import SequenceMatcher, unified_diff
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class FileComparison:
    """Result of comparing expected vs actual file content."""
    path: str
    exists: bool
    similarity: float  # 0.0 to 1.0
    match_status: str  # "match", "partial", "mismatch", "missing"
    diff_lines: List[str]  # Unified diff output
    expected_lines: int
    actual_lines: int


@dataclass
class VerificationResult:
    """Overall verification result for a session."""
    success: bool
    comparisons: List[FileComparison]
    summary: str


class FileVerifier:
    """Verifies output files match expected content from session JSON."""

    # Similarity thresholds
    MATCH_THRESHOLD = 0.98     # >= 98% is a match
    PARTIAL_THRESHOLD = 0.90   # >= 90% is partial match (review needed)

    def __init__(
        self,
        workspace_root: Path,
        tolerance: float = 0.98,
    ):
        """Initialize the verifier.

        Args:
            workspace_root: Root directory of VS Code workspace.
            tolerance: Minimum similarity ratio to consider a match.
        """
        self.workspace_root = Path(workspace_root)
        self.tolerance = tolerance

    def verify_session(
        self,
        session: 'ReplaySession',
    ) -> VerificationResult:
        """Verify all files in a session match expected content.

        Args:
            session: ReplaySession with expected file operations.

        Returns:
            VerificationResult with per-file comparisons.
        """
        comparisons = []

        for file_ops in session.files:
            expected_content = self._build_expected_content(file_ops)
            comparison = self._compare_file(file_ops.path, expected_content)
            comparisons.append(comparison)

        # Determine overall success
        all_match = all(c.match_status == "match" for c in comparisons)
        any_missing = any(c.match_status == "missing" for c in comparisons)

        if all_match:
            success = True
            summary = f"All {len(comparisons)} files match expected content"
        elif any_missing:
            success = False
            missing = [c.path for c in comparisons if c.match_status == "missing"]
            summary = f"Missing files: {', '.join(missing)}"
        else:
            partial = [c for c in comparisons if c.match_status == "partial"]
            mismatch = [c for c in comparisons if c.match_status == "mismatch"]
            success = len(mismatch) == 0
            summary = f"Partial matches: {len(partial)}, Mismatches: {len(mismatch)}"

        return VerificationResult(
            success=success,
            comparisons=comparisons,
            summary=summary
        )

    def _build_expected_content(self, file_ops: 'FileOperation') -> str:
        """Build expected file content from operations.

        This reconstructs what the file should contain after all
        operations have been applied.
        """
        # For insert operations, we can reconstruct expected content
        # For delete/navigate, we'd need the original file content
        # Simplified: extract all insert operation content
        lines = []
        for op in file_ops.operations:
            if op.op_type == 'insert' and op.content:
                lines.append(op.content)
        return ''.join(lines)

    def _compare_file(
        self,
        path: str,
        expected: str,
    ) -> FileComparison:
        """Compare a file against expected content."""
        full_path = self.workspace_root / path

        if not full_path.exists():
            return FileComparison(
                path=path,
                exists=False,
                similarity=0.0,
                match_status="missing",
                diff_lines=[],
                expected_lines=expected.count('\n'),
                actual_lines=0
            )

        try:
            actual = full_path.read_text(encoding='utf-8')
        except IOError as e:
            logger.error(f"Failed to read {path}: {e}")
            return FileComparison(
                path=path,
                exists=True,
                similarity=0.0,
                match_status="mismatch",
                diff_lines=[f"Read error: {e}"],
                expected_lines=expected.count('\n'),
                actual_lines=0
            )

        # Calculate similarity
        similarity = SequenceMatcher(None, expected, actual).ratio()

        # Generate diff
        diff_lines = list(unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=f"expected/{path}",
            tofile=f"actual/{path}",
            lineterm=""
        ))

        # Determine match status
        if similarity >= self.MATCH_THRESHOLD:
            match_status = "match"
        elif similarity >= self.PARTIAL_THRESHOLD:
            match_status = "partial"
        else:
            match_status = "mismatch"

        return FileComparison(
            path=path,
            exists=True,
            similarity=similarity,
            match_status=match_status,
            diff_lines=diff_lines,
            expected_lines=expected.count('\n'),
            actual_lines=actual.count('\n')
        )
```

### 5. Intervention Orchestrator (`intervention/orchestrator.py`)

**Responsibilities:**
- Timer-based screenshot scheduling
- Coordinate analysis and recovery
- Manage intervention state and cooldowns
- Integrate with replay engine

**Implementation:**

```python
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Event, Thread
from typing import Callable, List, Optional
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class InterventionEvent:
    """Record of an intervention attempt."""
    timestamp: datetime
    status: 'ReplayStatus'
    confidence: float
    actions_taken: List[str]
    recovery_success: bool
    screenshot_path: Optional[Path]


@dataclass
class InterventionConfig:
    """Configuration for intervention system."""
    enabled: bool = True
    interval_seconds: int = 600  # 10 minutes
    min_cooldown_seconds: int = 60
    max_retries: int = 3
    confidence_threshold: float = 0.85
    screenshot_dir: Path = field(default_factory=lambda: Path("screenshots"))
    save_screenshots: bool = True


class InterventionOrchestrator:
    """Orchestrates periodic screenshot analysis and recovery."""

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

        self._events: List[InterventionEvent] = []
        self._stop_event = Event()
        self._monitor_thread: Optional[Thread] = None
        self._last_intervention: float = 0
        self._retry_count: int = 0

        # Callback for notifying replay engine of issues
        self._on_critical_failure: Optional[Callable[[], None]] = None

    def start(self) -> None:
        """Start the intervention monitoring thread."""
        if not self.config.enabled:
            logger.info("Intervention system disabled by config")
            return

        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("Intervention monitoring already running")
            return

        self._stop_event.clear()
        self._monitor_thread = Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info(f"Intervention monitoring started (interval: {self.config.interval_seconds}s)")

    def stop(self) -> None:
        """Stop the intervention monitoring thread."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("Intervention monitoring stopped")

    def check_now(self, context: Optional[str] = None) -> InterventionEvent:
        """Perform an immediate intervention check.

        Args:
            context: Optional context about current replay state.

        Returns:
            InterventionEvent with results.
        """
        logger.info("Performing intervention check...")

        # Capture screenshot
        screenshot = self.screenshot.capture_screen()
        screenshot_path = None

        if self.config.save_screenshots:
            self.config.screenshot_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = self.config.screenshot_dir / f"check_{timestamp}.jpg"
            screenshot.save(screenshot_path)

        # Analyze
        result = self.analyzer.analyze(screenshot, context)
        logger.info(f"Analysis result: {result.status.value} (confidence: {result.confidence:.2f})")

        # Determine if recovery needed
        actions_taken = []
        recovery_success = True

        if result.status != ReplayStatus.NORMAL:
            if result.confidence >= self.config.confidence_threshold:
                if self._can_intervene():
                    # Execute recovery
                    logger.info(f"Executing recovery: {result.recovery_actions}")
                    recovery_results = self.recovery.execute(result.recovery_actions)
                    actions_taken = [r.action_taken for r in recovery_results]
                    recovery_success = all(r.success for r in recovery_results)

                    self._last_intervention = time.time()

                    if not recovery_success:
                        self._retry_count += 1
                        if self._retry_count >= self.config.max_retries:
                            logger.error("Max recovery retries reached")
                            if self._on_critical_failure:
                                self._on_critical_failure()
                    else:
                        self._retry_count = 0
                else:
                    logger.info("Intervention skipped (cooldown active)")
            else:
                logger.info(f"Confidence too low for intervention: {result.confidence:.2f}")

        # Record event
        event = InterventionEvent(
            timestamp=datetime.now(),
            status=result.status,
            confidence=result.confidence,
            actions_taken=actions_taken,
            recovery_success=recovery_success,
            screenshot_path=screenshot_path
        )
        self._events.append(event)

        return event

    def set_critical_failure_callback(self, callback: Callable[[], None]) -> None:
        """Set callback for critical failure notification."""
        self._on_critical_failure = callback

    def get_events(self) -> List[InterventionEvent]:
        """Get all intervention events."""
        return self._events.copy()

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while not self._stop_event.wait(timeout=self.config.interval_seconds):
            try:
                self.check_now()
            except Exception as e:
                logger.error(f"Intervention check failed: {e}", exc_info=True)

    def _can_intervene(self) -> bool:
        """Check if enough time has passed since last intervention."""
        elapsed = time.time() - self._last_intervention
        return elapsed >= self.config.min_cooldown_seconds
```

## Configuration Schema

Add to `config/default.yaml`:

```yaml
# =============================================================================
# AI Intervention Configuration
# =============================================================================
intervention:
  # Enable/disable AI intervention system
  enabled: true

  # Interval between checks in seconds (600 = 10 minutes)
  interval_seconds: 600

  # Minimum time between recovery attempts in seconds
  min_cooldown_seconds: 60

  # Maximum recovery attempts before failing session
  max_retries: 3

  # Minimum confidence to trigger recovery action
  confidence_threshold: 0.85

  # Screenshot backend: 'auto', 'scrot', or 'mss'
  screenshot_backend: auto

  # Save screenshots for debugging
  save_screenshots: true

  # Directory for saved screenshots
  screenshot_dir: "~/.mask/screenshots"

  # Claude model for analysis
  model: "claude-opus-4-5-20250514"

  # File verification settings
  verification:
    enabled: true
    similarity_threshold: 0.98
    verify_on_completion: true
```

## Integration with Replay Engine

Modify `replay/replay_engine.py` to add intervention hooks:

```python
class ReplayEngine:
    def __init__(
        self,
        vscode_controller: VSCodeController,
        intervention_orchestrator: Optional[InterventionOrchestrator] = None,
    ):
        self.vscode = vscode_controller
        self.intervention = intervention_orchestrator

    def execute(self, session: ReplaySession, ...) -> None:
        # Start intervention monitoring
        if self.intervention:
            self.intervention.start()
            self.intervention.set_critical_failure_callback(self.request_abort)

        try:
            for file_ops in session.files:
                self._execute_file(file_ops)

                # Check point between files
                if self.intervention and self._should_check():
                    self.intervention.check_now(
                        context=f"Just finished: {file_ops.path}"
                    )
        finally:
            if self.intervention:
                self.intervention.stop()
```

## Decisions

### Decision 1: Periodic vs Event-Driven Analysis

**Chosen: Periodic (timer-based)**

**Rationale:**
- Simpler implementation with predictable behavior
- Lower API costs than continuous monitoring
- Event detection (e.g., "input failed") would require wrapping all input calls
- 10-minute interval balances responsiveness vs cost

**Alternatives considered:**
- Event-driven on input errors: More responsive but adds coupling
- Hybrid (event + periodic): Added complexity without clear benefit

### Decision 2: Screenshot Scope

**Chosen: Full screen capture**

**Rationale:**
- Captures all relevant context (dialogs may appear outside VS Code)
- Simpler than window-specific capture with geometry tracking
- Claude can analyze entire screen context

**Alternatives considered:**
- VS Code window only: Would miss system dialogs
- Multiple targeted regions: Added complexity

### Decision 3: Recovery Action Format

**Chosen: High-level action strings parsed by Python**

**Rationale:**
- Claude doesn't need to know exact xdotool syntax
- Allows validation/sanitization before execution
- More maintainable than direct xdotool commands

**Alternatives considered:**
- Raw xdotool commands: Security risk, brittleness
- Structured action objects: Over-engineering for current needs

### Decision 4: API Key Storage

**Chosen: Environment variable `ANTHROPIC_API_KEY`**

**Rationale:**
- Standard practice for secret management
- Easy to set in systemd unit files
- Never stored in config files or code

**Alternatives considered:**
- Config file: Security risk
- Secrets manager: Over-engineering for single-machine deployment

## Risks / Trade-offs

| Risk | Trade-off | Mitigation |
|------|-----------|------------|
| API latency delays replay | Async analysis in background thread | Thread isolation, timeout handling |
| False positives trigger unnecessary recovery | May briefly interrupt normal replay | High confidence threshold (0.85) |
| API unavailable | Replay continues without AI monitoring | Graceful degradation, local logging |
| Recovery actions cause new problems | Could corrupt file state | State snapshot before recovery, verification after |
| Cost overruns | Unbounded API usage | Per-session budget cap, interval configuration |

## Migration Plan

1. **Phase 1: Core implementation** (no integration)
   - Implement all intervention components
   - Unit tests with mock API responses
   - Manual testing with saved screenshots

2. **Phase 2: Replay engine integration**
   - Add hooks to replay_engine.py
   - Integration tests with actual API
   - Measure latency impact

3. **Phase 3: Session orchestrator integration**
   - Enable via config
   - End-to-end testing
   - Documentation update

**Rollback:** Disable via `intervention.enabled: false` in config

## Open Questions

1. **Q: Should we support recovery from Upwork issues?**
   A: Out of scope for initial implementation; Upwork has separate failure modes

2. **Q: How to handle screenshots during Upwork's screenshot capture?**
   A: Intervention screenshots use separate timing; no conflict expected

3. **Q: Should recovery actions be user-customizable?**
   A: Not initially; rely on Claude's judgment with predefined action vocabulary
