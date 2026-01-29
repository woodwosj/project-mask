"""Claude Opus 4.5 vision analyzer for screenshot analysis.

This module provides AI-powered analysis of VS Code screenshots to detect
replay issues such as dialogs, wrong files, or errors.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, TYPE_CHECKING
import json
import logging
import re

if TYPE_CHECKING:
    from intervention.screenshot import Screenshot

logger = logging.getLogger(__name__)


class AnalyzerError(Exception):
    """Exception raised when analysis fails."""

    def __init__(self, message: str, recoverable: bool = True):
        """Initialize the error.

        Args:
            message: Error description.
            recoverable: Whether the error is recoverable (e.g., retry later).
        """
        self.recoverable = recoverable
        super().__init__(message)


class ReplayStatus(Enum):
    """Detected replay status from screenshot analysis.

    Values:
        NORMAL: Replay progressing as expected.
        DIALOG_BLOCKING: Modal dialog blocking input.
        WRONG_FILE: Incorrect file/project open.
        ERROR_STATE: Error message or exception visible.
        TERMINAL_FOCUS: Terminal has focus instead of editor.
        UNKNOWN: Unable to determine state.
    """
    NORMAL = "normal"
    DIALOG_BLOCKING = "dialog"
    WRONG_FILE = "wrong_file"
    ERROR_STATE = "error"
    TERMINAL_FOCUS = "terminal"
    UNKNOWN = "unknown"


@dataclass
class AnalysisResult:
    """Result of screenshot analysis.

    Attributes:
        status: Detected replay status.
        confidence: Confidence in the detection (0.0 to 1.0).
        description: Human-readable description of what was detected.
        recovery_actions: Ordered list of recovery steps to execute.
        expected_file: What file should be open (if known).
        actual_file: What file appears to be open.
        raw_response: Full Claude response for debugging.
    """
    status: ReplayStatus
    confidence: float
    description: str
    recovery_actions: List[str]
    expected_file: Optional[str]
    actual_file: Optional[str]
    raw_response: str


class ClaudeAnalyzer:
    """Analyzes screenshots using Claude Opus 4.5 vision capabilities.

    This class sends screenshots to the Anthropic API and interprets the
    response to determine if the replay is progressing normally or if
    intervention is needed.
    """

    # System prompt for screenshot analysis
    SYSTEM_PROMPT = """You are a QA assistant for an automated code replay system.
You analyze screenshots of VS Code to detect if the replay is proceeding normally or if intervention is needed.

Analyze the screenshot and respond with a JSON object containing:
{
    "status": "normal" | "dialog" | "wrong_file" | "error" | "terminal" | "unknown",
    "confidence": 0.0-1.0,
    "description": "Brief description of what you see",
    "recovery_actions": ["action1", "action2"],
    "expected_file": "filename or null if unknown",
    "actual_file": "filename visible in tab or null"
}

Status definitions:
- "normal": VS Code editor is visible with code, no blocking elements
- "dialog": A modal dialog, notification, or popup is blocking the editor
- "wrong_file": A file is open but it appears to be the wrong one (e.g., welcome tab, settings)
- "error": Error messages, exceptions, or crash dialogs are visible
- "terminal": The terminal/panel has focus instead of the editor
- "unknown": Cannot determine the state (e.g., screen is black, not VS Code)

Recovery actions should be specific commands like:
- "press Escape" - Close dialogs or cancel operations
- "press Return" - Confirm/accept dialogs
- "key ctrl+p" - Open file picker
- "key ctrl+shift+p" - Open command palette
- "key ctrl+w" - Close current tab
- "key ctrl+1" - Focus first editor group
- "key ctrl+grave" - Toggle terminal visibility
- "focus_vscode" - Bring VS Code window to front
- "type <text>" - Type text (for file picker, etc.)
- "click <x>,<y>" - Click at screen coordinates
- "wait <seconds>" - Wait before next action

Be conservative: only suggest recovery if confidence > 0.8.
If the screenshot shows normal coding activity in VS Code, return status "normal" with empty recovery_actions.
Recovery actions should be minimal - prefer simple solutions (Escape, focus) over complex ones.

Respond with valid JSON only, no markdown code blocks or additional text."""

    # Default model - Claude Opus 4.5
    DEFAULT_MODEL = "claude-opus-4-5-20251101"

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        timeout: float = 30.0,
        max_tokens: int = 1024,
    ):
        """Initialize the analyzer with Anthropic API credentials.

        Args:
            api_key: Anthropic API key.
            model: Model ID to use for analysis. Defaults to Claude Opus 4.5.
            timeout: API request timeout in seconds.
            max_tokens: Maximum tokens in response.

        Raises:
            AnalyzerError: If the Anthropic SDK is not installed.
        """
        try:
            import anthropic
            self._anthropic = anthropic
        except ImportError:
            raise AnalyzerError(
                "anthropic library not installed. Install with: pip install anthropic",
                recoverable=False
            )

        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.timeout = timeout
        self.max_tokens = max_tokens

        # Create client
        self.client = anthropic.Anthropic(
            api_key=api_key,
            timeout=timeout,
        )

        logger.info(f"ClaudeAnalyzer initialized with model: {self.model}")

    def analyze(
        self,
        screenshot: 'Screenshot',
        context: Optional[str] = None,
    ) -> AnalysisResult:
        """Analyze a screenshot to determine replay status.

        Args:
            screenshot: Screenshot to analyze.
            context: Optional context about current replay state
                    (e.g., "Currently typing file src/main.py").

        Returns:
            AnalysisResult with status, confidence, and recovery actions.

        Note:
            This method does not raise exceptions for API errors; instead it
            returns an AnalysisResult with status=UNKNOWN and confidence=0.
        """
        logger.info(f"Analyzing screenshot ({screenshot.width}x{screenshot.height}, "
                   f"{screenshot.size_kb:.1f}KB)")

        # Build message content with image and prompt
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
                max_tokens=self.max_tokens,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}]
            )

            # Extract text response
            response_text = response.content[0].text
            logger.debug(f"Raw Claude response: {response_text}")

            # Parse the response
            result = self._parse_response(response_text)

            logger.info(f"Analysis result: status={result.status.value}, "
                       f"confidence={result.confidence:.2f}")

            return result

        except self._anthropic.APIError as e:
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
        except self._anthropic.APIConnectionError as e:
            logger.error(f"Anthropic connection error: {e}")
            return AnalysisResult(
                status=ReplayStatus.UNKNOWN,
                confidence=0.0,
                description=f"Connection error: {e}",
                recovery_actions=[],
                expected_file=None,
                actual_file=None,
                raw_response=""
            )
        except Exception as e:
            logger.error(f"Unexpected error during analysis: {e}", exc_info=True)
            return AnalysisResult(
                status=ReplayStatus.UNKNOWN,
                confidence=0.0,
                description=f"Unexpected error: {e}",
                recovery_actions=[],
                expected_file=None,
                actual_file=None,
                raw_response=""
            )

    def _build_prompt(self, context: Optional[str]) -> str:
        """Build the analysis prompt.

        Args:
            context: Optional context about current replay state.

        Returns:
            Prompt string for the user message.
        """
        prompt = "Analyze this screenshot of the VS Code window during an automated code replay session."

        if context:
            prompt += f"\n\nContext: {context}"

        prompt += "\n\nRespond with JSON only."

        return prompt

    def _parse_response(self, response_text: str) -> AnalysisResult:
        """Parse Claude's JSON response into AnalysisResult.

        Handles various response formats including markdown code blocks.

        Args:
            response_text: Raw response text from Claude.

        Returns:
            Parsed AnalysisResult.
        """
        raw_response = response_text

        try:
            # Strip whitespace
            text = response_text.strip()

            # Handle markdown code blocks
            if text.startswith("```"):
                # Extract content between code fences
                match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
                if match:
                    text = match.group(1).strip()
                else:
                    # Just remove the leading fence and try
                    text = re.sub(r'^```(?:json)?\s*', '', text)
                    text = re.sub(r'\s*```$', '', text)

            # Parse JSON
            data = json.loads(text)

            # Extract and validate fields
            status_str = data.get("status", "unknown")
            try:
                status = ReplayStatus(status_str)
            except ValueError:
                logger.warning(f"Unknown status value: {status_str}")
                status = ReplayStatus.UNKNOWN

            confidence = float(data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]

            description = str(data.get("description", ""))

            recovery_actions = data.get("recovery_actions", [])
            if not isinstance(recovery_actions, list):
                recovery_actions = []
            recovery_actions = [str(a) for a in recovery_actions]

            expected_file = data.get("expected_file")
            if expected_file is not None:
                expected_file = str(expected_file)

            actual_file = data.get("actual_file")
            if actual_file is not None:
                actual_file = str(actual_file)

            return AnalysisResult(
                status=status,
                confidence=confidence,
                description=description,
                recovery_actions=recovery_actions,
                expected_file=expected_file,
                actual_file=actual_file,
                raw_response=raw_response
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Claude response as JSON: {e}")
            logger.debug(f"Response text: {response_text}")

            return AnalysisResult(
                status=ReplayStatus.UNKNOWN,
                confidence=0.0,
                description=f"Failed to parse response: {e}",
                recovery_actions=[],
                expected_file=None,
                actual_file=None,
                raw_response=raw_response
            )

        except Exception as e:
            logger.warning(f"Error processing Claude response: {e}")

            return AnalysisResult(
                status=ReplayStatus.UNKNOWN,
                confidence=0.0,
                description=f"Processing error: {e}",
                recovery_actions=[],
                expected_file=None,
                actual_file=None,
                raw_response=raw_response
            )

    def health_check(self) -> bool:
        """Check if the analyzer can connect to the API.

        Returns:
            True if the API is accessible.
        """
        try:
            # Use a minimal API call to check connectivity
            # Count tokens is a lightweight operation
            self.client.messages.count_tokens(
                model=self.model,
                messages=[{"role": "user", "content": "test"}]
            )
            return True
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
