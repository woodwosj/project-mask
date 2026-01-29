# AI Intervention System - Implementation Tasks

## Overview

This document breaks down the implementation of the AI intervention system into discrete, testable tasks. Tasks are ordered by dependency and grouped by component.

**Estimated total effort:** 3-4 days

---

## 1. Project Setup and Dependencies

### 1.1 Add Python Dependencies
- [ ] Add `anthropic>=0.25.0` to requirements.txt
- [ ] Add `mss>=9.0.0` to requirements.txt (screenshot capture)
- [ ] Add `Pillow>=10.0.0` to requirements.txt (image processing)
- [ ] Run `pip install -r requirements.txt` to verify installation
- [ ] Document optional `scrot` system dependency in README

**Files:** `requirements.txt`, `README.md`

### 1.2 Create Module Structure
- [ ] Create `intervention/` directory
- [ ] Create `intervention/__init__.py` with public exports
- [ ] Create placeholder files for all components:
  - `intervention/screenshot.py`
  - `intervention/analyzer.py`
  - `intervention/recovery.py`
  - `intervention/verifier.py`
  - `intervention/orchestrator.py`

**Files:** `intervention/*.py`

### 1.3 Add Configuration Schema
- [ ] Add `intervention` section to `config/default.yaml`
- [ ] Include all configurable parameters from design.md
- [ ] Add inline comments documenting each option
- [ ] Verify YAML parsing loads new config correctly

**Files:** `config/default.yaml`

---

## 2. Screenshot Capture Component

### 2.1 Implement Screenshot Data Class
- [ ] Define `Screenshot` dataclass with `image_data`, `media_type`, `width`, `height`, `timestamp`
- [ ] Implement `to_base64()` method for API submission
- [ ] Implement `save()` method for debug output
- [ ] Add unit tests for serialization

**Files:** `intervention/screenshot.py`, `tests/test_screenshot.py`

### 2.2 Implement ScreenshotBackend ABC
- [ ] Define abstract `ScreenshotBackend` base class
- [ ] Define `capture_screen()` abstract method
- [ ] Define `capture_window()` abstract method with window_id parameter

**Files:** `intervention/screenshot.py`

### 2.3 Implement MSSBackend
- [ ] Implement `capture_screen()` using `mss` library
- [ ] Capture primary monitor as PNG
- [ ] Convert to JPEG with 85% quality for size optimization
- [ ] Implement `capture_window()` using xdotool geometry + region capture
- [ ] Add error handling for display not available

**Files:** `intervention/screenshot.py`

### 2.4 Implement ScrotBackend (Fallback)
- [ ] Implement `capture_screen()` using subprocess `scrot -o -`
- [ ] Parse stdout as image data
- [ ] Implement `capture_window()` using `scrot -u`
- [ ] Add error handling for scrot not installed

**Files:** `intervention/screenshot.py`

### 2.5 Implement Backend Factory
- [ ] Create `create_screenshot_backend(config)` factory function
- [ ] Implement auto-detection logic (prefer mss, fallback to scrot)
- [ ] Support explicit backend selection via config

**Files:** `intervention/screenshot.py`

### 2.6 Screenshot Integration Test
- [ ] Create manual test script to capture and save screenshot
- [ ] Verify screenshot quality and file size
- [ ] Test on X11 environment
- [ ] Document any platform-specific issues

**Files:** `scripts/test_screenshot.py`

---

## 3. Claude Vision Analyzer Component

### 3.1 Define Analysis Data Structures
- [ ] Define `ReplayStatus` enum (NORMAL, DIALOG_BLOCKING, WRONG_FILE, ERROR_STATE, TERMINAL_FOCUS, UNKNOWN)
- [ ] Define `AnalysisResult` dataclass with all fields from design
- [ ] Add docstrings explaining each status type

**Files:** `intervention/analyzer.py`

### 3.2 Implement ClaudeAnalyzer Class
- [ ] Implement `__init__()` with API key and model configuration
- [ ] Create Anthropic client instance
- [ ] Store model ID (default: claude-opus-4-5-20250514)

**Files:** `intervention/analyzer.py`

### 3.3 Implement System Prompt
- [ ] Write comprehensive system prompt for screenshot analysis
- [ ] Include JSON response format specification
- [ ] Document expected recovery action vocabulary
- [ ] Store as class constant

**Files:** `intervention/analyzer.py`

### 3.4 Implement analyze() Method
- [ ] Build message content with base64 image and prompt
- [ ] Call Anthropic messages.create() API
- [ ] Handle API errors gracefully (timeout, rate limit, etc.)
- [ ] Return AnalysisResult with appropriate status on error

**Files:** `intervention/analyzer.py`

### 3.5 Implement Response Parser
- [ ] Parse JSON from Claude response
- [ ] Handle markdown code block wrapping
- [ ] Validate required fields present
- [ ] Map status string to ReplayStatus enum
- [ ] Handle parse errors with UNKNOWN status

**Files:** `intervention/analyzer.py`

### 3.6 Analyzer Unit Tests
- [ ] Test response parsing with valid JSON
- [ ] Test response parsing with markdown-wrapped JSON
- [ ] Test error handling for malformed responses
- [ ] Test API error handling (mock httpx errors)
- [ ] Test confidence threshold logic

**Files:** `tests/test_analyzer.py`

### 3.7 Analyzer Integration Test
- [ ] Create test script with sample screenshot
- [ ] Verify API connectivity
- [ ] Log full response for debugging
- [ ] Measure latency

**Files:** `scripts/test_analyzer.py`

---

## 4. Recovery Actions Component

### 4.1 Define Recovery Data Structures
- [ ] Define `RecoveryResult` dataclass
- [ ] Include success, action_taken, error fields

**Files:** `intervention/recovery.py`

### 4.2 Implement RecoveryExecutor Class
- [ ] Implement `__init__()` accepting input_backend and vscode_controller
- [ ] Define action pattern mapping dictionary

**Files:** `intervention/recovery.py`

### 4.3 Implement Action Executors
- [ ] Implement `_execute_key_press()` for single keys
- [ ] Implement `_execute_key_combo()` for key combinations
- [ ] Implement `_execute_type()` for text typing
- [ ] Implement `_execute_focus_vscode()` for window activation
- [ ] Implement `_execute_click()` for mouse clicks
- [ ] Implement `_execute_wait()` for delays

**Files:** `intervention/recovery.py`

### 4.4 Implement execute() Method
- [ ] Parse action strings and dispatch to appropriate executor
- [ ] Execute actions in order
- [ ] Stop on first failure
- [ ] Return list of RecoveryResult objects

**Files:** `intervention/recovery.py`

### 4.5 Recovery Unit Tests
- [ ] Test action string parsing
- [ ] Test each executor with mock input backend
- [ ] Test failure handling and early termination
- [ ] Test unknown action pattern handling

**Files:** `tests/test_recovery.py`

---

## 5. File Verifier Component

### 5.1 Define Verification Data Structures
- [ ] Define `FileComparison` dataclass
- [ ] Define `VerificationResult` dataclass
- [ ] Include all fields from design

**Files:** `intervention/verifier.py`

### 5.2 Implement FileVerifier Class
- [ ] Implement `__init__()` with workspace_root and tolerance
- [ ] Define similarity thresholds as class constants

**Files:** `intervention/verifier.py`

### 5.3 Implement File Comparison
- [ ] Implement `_compare_file()` method
- [ ] Read actual file content with error handling
- [ ] Calculate similarity ratio using SequenceMatcher
- [ ] Generate unified diff for mismatches
- [ ] Determine match status from similarity

**Files:** `intervention/verifier.py`

### 5.4 Implement Expected Content Builder
- [ ] Implement `_build_expected_content()` from file operations
- [ ] Extract insert operation content
- [ ] Handle empty/missing operations

**Files:** `intervention/verifier.py`

### 5.5 Implement verify_session() Method
- [ ] Iterate through session files
- [ ] Compare each file
- [ ] Aggregate results
- [ ] Generate summary message

**Files:** `intervention/verifier.py`

### 5.6 Verifier Unit Tests
- [ ] Test file comparison with matching content
- [ ] Test file comparison with partial match
- [ ] Test file comparison with mismatch
- [ ] Test missing file handling
- [ ] Test session-level verification

**Files:** `tests/test_verifier.py`

---

## 6. Intervention Orchestrator Component

### 6.1 Define Orchestrator Data Structures
- [ ] Define `InterventionEvent` dataclass
- [ ] Define `InterventionConfig` dataclass with defaults

**Files:** `intervention/orchestrator.py`

### 6.2 Implement InterventionOrchestrator Class
- [ ] Implement `__init__()` with all required components
- [ ] Initialize event list and state variables
- [ ] Set up threading primitives (Event, Thread)

**Files:** `intervention/orchestrator.py`

### 6.3 Implement start() and stop() Methods
- [ ] Start background monitoring thread
- [ ] Use threading.Event for graceful shutdown
- [ ] Verify thread lifecycle management

**Files:** `intervention/orchestrator.py`

### 6.4 Implement check_now() Method
- [ ] Capture screenshot
- [ ] Save to debug directory if enabled
- [ ] Call analyzer
- [ ] Evaluate recovery need based on confidence
- [ ] Execute recovery if appropriate
- [ ] Respect cooldown period
- [ ] Record intervention event
- [ ] Return event for caller inspection

**Files:** `intervention/orchestrator.py`

### 6.5 Implement Monitor Loop
- [ ] Background thread with configurable interval
- [ ] Use Event.wait() for interruptible sleep
- [ ] Exception handling to prevent thread death
- [ ] Logging of each check

**Files:** `intervention/orchestrator.py`

### 6.6 Implement Retry and Cooldown Logic
- [ ] Track retry count
- [ ] Implement cooldown check
- [ ] Trigger critical failure callback on max retries

**Files:** `intervention/orchestrator.py`

### 6.7 Orchestrator Integration Test
- [ ] Create test script that runs full intervention cycle
- [ ] Use mock analyzer returning test responses
- [ ] Verify thread start/stop
- [ ] Verify event recording

**Files:** `scripts/test_orchestrator.py`

---

## 7. Replay Engine Integration

### 7.1 Add Intervention to ReplayEngine Constructor
- [ ] Add optional `intervention_orchestrator` parameter
- [ ] Store as instance variable
- [ ] Default to None for backward compatibility

**Files:** `replay/replay_engine.py`

### 7.2 Add Intervention Lifecycle to execute()
- [ ] Start intervention monitoring at execution start
- [ ] Set critical failure callback to request_abort
- [ ] Stop intervention monitoring in finally block

**Files:** `replay/replay_engine.py`

### 7.3 Add Checkpoint Hooks
- [ ] Add intervention check between file operations
- [ ] Pass context with current file information
- [ ] Make check conditional on configuration

**Files:** `replay/replay_engine.py`

### 7.4 Update Session Orchestrator
- [ ] Create intervention orchestrator if enabled
- [ ] Pass to replay engine
- [ ] Handle intervention events in session logging

**Files:** `orchestrator/session_orchestrator.py`

---

## 8. Testing and Documentation

### 8.1 Unit Test Suite
- [ ] Ensure all unit tests pass
- [ ] Achieve >80% code coverage for new code
- [ ] Add integration test markers

**Files:** `tests/test_*.py`

### 8.2 Integration Test Script
- [ ] Create end-to-end test script
- [ ] Test with actual Anthropic API
- [ ] Test full recovery workflow
- [ ] Document test prerequisites

**Files:** `scripts/test_intervention_e2e.py`

### 8.3 Documentation Updates
- [ ] Add intervention system to CLAUDE.md
- [ ] Document configuration options
- [ ] Add troubleshooting section
- [ ] Document API key setup

**Files:** `CLAUDE.md`, `README.md`

### 8.4 Example Configuration
- [ ] Create example intervention config
- [ ] Document recommended settings for different scenarios
- [ ] Include cost estimates

**Files:** `config/examples/intervention.yaml`

---

## 9. Security and Operations

### 9.1 API Key Management
- [ ] Document ANTHROPIC_API_KEY environment variable
- [ ] Add systemd unit file example with API key
- [ ] Verify key is never logged

**Files:** `scripts/mask-replay.service`, docs

### 9.2 Screenshot Privacy
- [ ] Ensure screenshots are not committed to git
- [ ] Add `.mask/screenshots/` to .gitignore
- [ ] Implement automatic cleanup of old screenshots

**Files:** `.gitignore`, `intervention/orchestrator.py`

### 9.3 Logging and Observability
- [ ] Add structured logging for intervention events
- [ ] Log API request/response times
- [ ] Log recovery action outcomes
- [ ] Create log format documentation

**Files:** `intervention/*.py`, docs

---

## Completion Checklist

Before marking this proposal complete:

- [ ] All tasks above are checked
- [ ] All unit tests pass
- [ ] Integration test passes with real API
- [ ] Documentation is updated
- [ ] Configuration defaults are sensible
- [ ] No hardcoded API keys in codebase
- [ ] Screenshots directory is gitignored
- [ ] Manual testing on target platform (ARM64/X11)
