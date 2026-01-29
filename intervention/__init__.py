"""AI Intervention System for PROJECT MASK.

This module provides AI-powered monitoring and recovery capabilities for
unattended replay sessions. It captures periodic screenshots, analyzes them
using Claude Opus 4.5 vision, and executes recovery actions when problems
are detected.

Components:
    - ScreenshotBackend: Screenshot capture abstraction (mss, scrot)
    - ClaudeAnalyzer: Claude Opus 4.5 vision analysis
    - RecoveryExecutor: Recovery action execution via xdotool
    - FileVerifier: Output file verification against expected content
    - InterventionOrchestrator: Coordinates all components

Example:
    from intervention import (
        InterventionOrchestrator,
        InterventionConfig,
        ClaudeAnalyzer,
        create_screenshot_backend,
        RecoveryExecutor,
    )

    # Create components
    screenshot_backend = create_screenshot_backend()
    analyzer = ClaudeAnalyzer(api_key=os.environ['ANTHROPIC_API_KEY'])
    recovery = RecoveryExecutor(input_backend, vscode_controller)

    # Create orchestrator
    config = InterventionConfig(interval_seconds=600)
    orchestrator = InterventionOrchestrator(
        config=config,
        screenshot_backend=screenshot_backend,
        analyzer=analyzer,
        recovery_executor=recovery,
    )

    # Use during replay
    orchestrator.start()
    try:
        engine.execute(session)
    finally:
        orchestrator.stop()
"""

from intervention.screenshot import (
    Screenshot,
    ScreenshotBackend,
    MSSBackend,
    ScrotBackend,
    create_screenshot_backend,
    ScreenshotError,
)

from intervention.analyzer import (
    ReplayStatus,
    AnalysisResult,
    ClaudeAnalyzer,
    AnalyzerError,
)

from intervention.recovery import (
    RecoveryResult,
    RecoveryExecutor,
    RecoveryError,
)

from intervention.verifier import (
    FileComparison,
    VerificationResult,
    FileVerifier,
)

from intervention.orchestrator import (
    InterventionEvent,
    InterventionConfig,
    InterventionOrchestrator,
)


__all__ = [
    # Screenshot
    'Screenshot',
    'ScreenshotBackend',
    'MSSBackend',
    'ScrotBackend',
    'create_screenshot_backend',
    'ScreenshotError',
    # Analyzer
    'ReplayStatus',
    'AnalysisResult',
    'ClaudeAnalyzer',
    'AnalyzerError',
    # Recovery
    'RecoveryResult',
    'RecoveryExecutor',
    'RecoveryError',
    # Verifier
    'FileComparison',
    'VerificationResult',
    'FileVerifier',
    # Orchestrator
    'InterventionEvent',
    'InterventionConfig',
    'InterventionOrchestrator',
]
