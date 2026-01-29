# AI Intervention Specification

## ADDED Requirements

### Requirement: Screenshot Capture

The system SHALL capture screenshots of the display at configurable intervals during replay sessions.

The screenshot capture MUST support:
- Full-screen capture
- Window-specific capture (by window ID)
- Multiple backends (mss, scrot)
- Image format conversion (PNG to JPEG)
- Base64 encoding for API submission

#### Scenario: Capture full screen

- **WHEN** `screenshot_backend.capture_screen()` is called
- **THEN** a `Screenshot` object SHALL be returned
- **AND** `image_data` SHALL contain the full screen image bytes
- **AND** `media_type` SHALL be "image/jpeg" or "image/png"
- **AND** `width` and `height` SHALL match screen dimensions

#### Scenario: Capture VS Code window

- **WHEN** `screenshot_backend.capture_window(window_id)` is called
- **THEN** a `Screenshot` object SHALL be returned
- **AND** `image_data` SHALL contain only the specified window
- **AND** window geometry SHALL be obtained via xdotool

#### Scenario: Backend auto-detection

- **WHEN** `create_screenshot_backend()` is called with `backend: "auto"`
- **THEN** mss backend SHALL be used if mss is installed
- **AND** scrot backend SHALL be used as fallback

#### Scenario: Save screenshot for debugging

- **WHEN** `screenshot.save(path)` is called
- **THEN** image SHALL be written to the specified path
- **AND** file format SHALL match the media_type

---

### Requirement: Claude Vision Analysis

The system SHALL analyze screenshots using Claude Opus 4.5 vision capabilities to detect replay issues.

The analyzer MUST detect:
- Normal replay progress
- Modal dialogs blocking input
- Wrong file or project open
- Error messages or exceptions visible
- Terminal focus instead of editor

#### Scenario: Analyze screenshot via API

- **WHEN** `analyzer.analyze(screenshot)` is called
- **THEN** the screenshot SHALL be sent to Anthropic API
- **AND** an `AnalysisResult` SHALL be returned
- **AND** `status` SHALL be one of the defined `ReplayStatus` values
- **AND** `confidence` SHALL be between 0.0 and 1.0

#### Scenario: Detect dialog blocking

- **WHEN** a modal dialog is visible in the screenshot
- **THEN** `status` SHALL be `ReplayStatus.DIALOG_BLOCKING`
- **AND** `recovery_actions` SHALL include dialog dismissal steps
- **AND** `confidence` SHALL reflect detection certainty

#### Scenario: Detect wrong file open

- **WHEN** the visible file differs from expected
- **THEN** `status` SHALL be `ReplayStatus.WRONG_FILE`
- **AND** `actual_file` SHALL contain the visible filename
- **AND** `recovery_actions` SHALL include file navigation steps

#### Scenario: Handle API errors gracefully

- **WHEN** the Anthropic API returns an error
- **THEN** `status` SHALL be `ReplayStatus.UNKNOWN`
- **AND** `confidence` SHALL be 0.0
- **AND** `description` SHALL include error details
- **AND** execution SHALL NOT raise an exception

#### Scenario: Parse Claude JSON response

- **WHEN** Claude returns a valid JSON response
- **THEN** all fields SHALL be extracted to `AnalysisResult`
- **AND** markdown code block wrappers SHALL be stripped if present

---

### Requirement: Recovery Action Execution

The system SHALL execute recovery actions recommended by Claude using the existing input backend.

Recovery actions MUST support:
- Key presses (single keys)
- Key combinations (ctrl+key, alt+key)
- Text typing
- VS Code window focusing
- Mouse clicks at coordinates
- Wait/delay operations

#### Scenario: Execute key press action

- **WHEN** recovery action "press Escape" is executed
- **THEN** `input_backend.key_press("Escape")` SHALL be called
- **AND** `RecoveryResult.success` SHALL be True if no error

#### Scenario: Execute key combination action

- **WHEN** recovery action "key ctrl+p" is executed
- **THEN** `input_backend.key_combo("ctrl", "p")` SHALL be called

#### Scenario: Execute focus VS Code action

- **WHEN** recovery action "focus_vscode" is executed
- **THEN** VS Code window SHALL be searched by title
- **AND** window SHALL be activated using xdotool

#### Scenario: Execute multiple actions in sequence

- **WHEN** `recovery.execute([action1, action2, action3])` is called
- **THEN** actions SHALL be executed in order
- **AND** each action SHALL wait for previous to complete
- **AND** execution SHALL stop on first failure

#### Scenario: Handle unknown action pattern

- **WHEN** an unrecognized action string is provided
- **THEN** `RecoveryResult.success` SHALL be False
- **AND** `RecoveryResult.error` SHALL describe the issue

---

### Requirement: File Content Verification

The system SHALL verify that output files match expected content from the session JSON.

#### Scenario: Compare file with expected content

- **WHEN** `verifier._compare_file(path, expected)` is called
- **THEN** actual file content SHALL be read
- **AND** similarity SHALL be calculated using SequenceMatcher
- **AND** `FileComparison` SHALL include match status

#### Scenario: Classify match by similarity

- **WHEN** similarity >= 0.98
- **THEN** `match_status` SHALL be "match"
- **WHEN** similarity >= 0.90 and < 0.98
- **THEN** `match_status` SHALL be "partial"
- **WHEN** similarity < 0.90
- **THEN** `match_status` SHALL be "mismatch"

#### Scenario: Handle missing file

- **WHEN** expected file does not exist
- **THEN** `FileComparison.exists` SHALL be False
- **AND** `match_status` SHALL be "missing"
- **AND** `similarity` SHALL be 0.0

#### Scenario: Verify entire session

- **WHEN** `verifier.verify_session(session)` is called
- **THEN** all files in session SHALL be compared
- **AND** `VerificationResult.success` SHALL be True if all match
- **AND** `summary` SHALL describe overall results

---

### Requirement: Intervention Orchestration

The system SHALL orchestrate periodic screenshot analysis and recovery during replay sessions.

#### Scenario: Start monitoring thread

- **WHEN** `orchestrator.start()` is called
- **THEN** a background thread SHALL be started
- **AND** the thread SHALL perform checks at configured interval

#### Scenario: Stop monitoring thread

- **WHEN** `orchestrator.stop()` is called
- **THEN** the monitoring thread SHALL be signaled to stop
- **AND** the thread SHALL exit gracefully within 5 seconds

#### Scenario: Perform immediate check

- **WHEN** `orchestrator.check_now()` is called
- **THEN** a screenshot SHALL be captured
- **AND** the screenshot SHALL be analyzed
- **AND** recovery SHALL be executed if needed
- **AND** an `InterventionEvent` SHALL be recorded

#### Scenario: Respect cooldown period

- **WHEN** less than `min_cooldown_seconds` since last intervention
- **THEN** recovery actions SHALL NOT be executed
- **AND** logging SHALL indicate cooldown is active

#### Scenario: Trigger on confidence threshold

- **WHEN** analysis returns status != NORMAL
- **AND** confidence >= `confidence_threshold`
- **THEN** recovery actions SHALL be executed
- **WHEN** confidence < `confidence_threshold`
- **THEN** recovery actions SHALL NOT be executed

#### Scenario: Track retry count

- **WHEN** recovery fails
- **THEN** retry count SHALL be incremented
- **WHEN** retry count exceeds `max_retries`
- **THEN** critical failure callback SHALL be invoked
- **AND** session abort SHALL be requested

#### Scenario: Record intervention events

- **WHEN** any intervention check completes
- **THEN** an `InterventionEvent` SHALL be recorded
- **AND** event SHALL include timestamp, status, actions, and result

---

### Requirement: Intervention Configuration

The system SHALL support comprehensive configuration of intervention behavior.

#### Scenario: Enable/disable intervention

- **WHEN** `intervention.enabled` is False
- **THEN** no monitoring thread SHALL be started
- **AND** replay SHALL proceed without AI intervention

#### Scenario: Configure check interval

- **WHEN** `intervention.interval_seconds` is set
- **THEN** checks SHALL occur at that interval
- **AND** default SHALL be 600 seconds (10 minutes)

#### Scenario: Configure confidence threshold

- **WHEN** `intervention.confidence_threshold` is set
- **THEN** that value SHALL be used for recovery decisions
- **AND** default SHALL be 0.85

#### Scenario: Configure screenshot directory

- **WHEN** `intervention.screenshot_dir` is set
- **THEN** debug screenshots SHALL be saved to that directory
- **AND** directory SHALL be created if it doesn't exist

#### Scenario: Load API key from environment

- **WHEN** intervention is enabled
- **THEN** API key SHALL be read from `ANTHROPIC_API_KEY` environment variable
- **AND** error SHALL be raised if variable is not set

---

### Requirement: Replay Engine Integration

The system SHALL integrate with the existing replay engine via optional hooks.

#### Scenario: Initialize with intervention orchestrator

- **WHEN** `ReplayEngine(intervention_orchestrator=orchestrator)` is called
- **THEN** orchestrator SHALL be stored for use during execution
- **WHEN** `intervention_orchestrator` is None
- **THEN** replay SHALL proceed without intervention

#### Scenario: Start intervention during replay

- **WHEN** `execute()` is called with intervention enabled
- **THEN** `orchestrator.start()` SHALL be called
- **AND** monitoring thread SHALL run throughout execution

#### Scenario: Stop intervention after replay

- **WHEN** replay execution completes (success or failure)
- **THEN** `orchestrator.stop()` SHALL be called in finally block
- **AND** monitoring thread SHALL be terminated

#### Scenario: Abort on critical intervention failure

- **WHEN** intervention orchestrator invokes critical failure callback
- **THEN** `request_abort()` SHALL be called on replay engine
- **AND** replay SHALL stop at next safe point

---

### Requirement: Graceful Degradation

The system SHALL continue replay even when AI intervention fails.

#### Scenario: API unavailable

- **WHEN** Anthropic API is unreachable
- **THEN** intervention check SHALL return UNKNOWN status
- **AND** replay SHALL continue without recovery
- **AND** warning SHALL be logged

#### Scenario: Screenshot capture fails

- **WHEN** screenshot backend raises exception
- **THEN** intervention check SHALL log error
- **AND** no API call SHALL be made
- **AND** replay SHALL continue uninterrupted

#### Scenario: Recovery action fails

- **WHEN** a recovery action raises exception
- **THEN** remaining actions SHALL NOT be executed
- **AND** failure SHALL be recorded in event
- **AND** replay SHALL continue if under retry limit
