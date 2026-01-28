# Tasks: Implement Core Distributed Code Replay System

## 1. Project Setup

- [ ] 1.1 Create project directory structure
  - `capture/`, `replay/`, `upwork/`, `orchestrator/`, `config/`, `scripts/`, `tests/`
- [ ] 1.2 Create `requirements.txt` with dependencies
  - unidiff, python-xlib, pyyaml
- [ ] 1.3 Create `config/default.yaml` with all configuration options
- [ ] 1.4 Create `scripts/install_deps.sh` for system dependencies
  - apt install xdotool wmctrl
- [ ] 1.5 Create `.gitignore` for Python project
- [ ] 1.6 Create `pyproject.toml` or `setup.py` for package installation

## 2. Input Backend (replay/input_backend.py)

- [ ] 2.1 Define `InputBackend` abstract base class
  - `type_text(text, delay)`, `key_press(key)`, `key_combo(*keys)`
  - `mouse_move(x, y)`, `mouse_click(button)`
- [ ] 2.2 Implement `XdotoolBackend` class
  - Subprocess calls to xdotool for all operations
  - Handle special key names (Return, BackSpace, ctrl, alt, shift)
- [ ] 2.3 Add display server detection
  - Check `XDG_SESSION_TYPE` environment variable
  - Raise error if not X11
- [ ] 2.4 Create unit tests for XdotoolBackend
  - Test key name translation
  - Test command generation (no actual execution)
- [ ] 2.5 Create integration test script `scripts/test_input.py`
  - Manual verification of typing in a text editor

## 3. VS Code Controller (replay/vscode_controller.py)

- [ ] 3.1 Implement window focus functions
  - `find_vscode_window()` using wmctrl or xdotool search
  - `focus_window()` to bring VS Code to front
  - `is_vscode_focused()` verification
- [ ] 3.2 Implement file navigation
  - `open_file(path)` using Ctrl+P quick open
  - `goto_line(line_number)` using Ctrl+G
  - `save_file()` using Ctrl+S
- [ ] 3.3 Implement typing simulator
  - `type_code(text, wpm, typo_probability)` with human-like patterns
  - Gaussian distribution for inter-character delays
  - Bigram acceleration for common pairs
  - Typo injection with correction
- [ ] 3.4 Implement line operations
  - `delete_lines(start, end)` using Ctrl+Shift+K or selection + delete
  - `select_line()` using Ctrl+L
- [ ] 3.5 Create unit tests
  - Test delay calculations
  - Test typo injection probability
- [ ] 3.6 Create integration test `scripts/test_vscode.py`
  - Open VS Code, navigate to file, type text, save

## 4. Replay Engine (replay/replay_engine.py)

- [ ] 4.1 Define session data classes
  - `ReplaySession`, `FileOperation`, `OperationType` enum
  - JSON schema validation
- [ ] 4.2 Implement session loader
  - `load_session(filepath)` with validation
  - Error handling for malformed JSON
- [ ] 4.3 Implement operation executor
  - `execute_navigate(op)` - goto line
  - `execute_delete(op)` - delete line range
  - `execute_insert(op)` - type content
- [ ] 4.4 Add thinking pause simulation
  - Random pauses (10% probability, 3-8 seconds)
  - Configurable parameters
- [ ] 4.5 Add progress callbacks
  - `ProgressCallback` type definition
  - Called after each operation
- [ ] 4.6 Add abort handling
  - `request_abort()` method
  - Check abort flag between operations
  - Raise `AbortRequested` exception
- [ ] 4.7 Create unit tests
  - Test session loading
  - Test operation sequencing
- [ ] 4.8 Create integration test
  - Full replay of sample session

## 5. Capture Tool (capture/)

- [ ] 5.1 Implement diff parser (`capture_tool.py`)
  - Parse unified diff using unidiff library
  - Extract file paths, line numbers, content
- [ ] 5.2 Implement operation builder
  - Convert hunks to navigate/delete/insert operations
  - Handle file additions, deletions, modifications
- [ ] 5.3 Implement session builder
  - Generate session JSON with metadata
  - Include replay_config defaults
- [ ] 5.4 Implement CLI (`cli.py`)
  - `mask-capture --commit HEAD --contract "ClientName" --memo "Description"`
  - Output to `.replay/` directory
  - Option to specify output file
- [ ] 5.5 Create unit tests
  - Test with sample diffs (add, delete, modify)
  - Test JSON output format
- [ ] 5.6 Add entry point in pyproject.toml
  - `mask-capture = "capture.cli:main"`

## 6. Upwork Controller (upwork/)

- [ ] 6.1 Implement app launcher
  - `launch_upwork()` - start browser to Upwork time tracker URL
  - `is_upwork_running()` - check if browser/app is open
  - `wait_for_ready()` - wait for page/app to load
- [ ] 6.2 Implement contract selector
  - `select_contract(contract_name)` - click dropdown, search, select
  - Configurable UI coordinates/selectors
- [ ] 6.3 Implement memo setter
  - `set_memo(text)` - click memo field, type description
- [ ] 6.4 Implement time tracker
  - `clock_in()` - click Start button
  - `clock_out()` - click Stop button
  - `is_clocked_in()` - verify current state
- [ ] 6.5 Create calibration tool (`scripts/calibrate_upwork.py`)
  - Interactive mode to capture UI element positions
  - Save to config file
- [ ] 6.6 Add web-based implementation
  - Browser automation for Upwork web interface
  - Handle login session persistence
- [ ] 6.7 Create integration test (manual)
  - Test with real Upwork account on test contract

## 7. Session Orchestrator (orchestrator/)

- [ ] 7.1 Implement git operations
  - `pull_latest()` - fetch and reset to origin
  - `find_pending_sessions()` - scan .replay/ for unprocessed files
  - `mark_session_processed(session_id)` - record completion
- [ ] 7.2 Implement signal handling
  - Register handlers for SIGTERM, SIGINT
  - Set `shutdown_requested` flag
  - Graceful abort of current operation
- [ ] 7.3 Implement main workflow
  - Poll loop with configurable interval
  - For each session: clock_in -> replay -> clock_out
  - Error handling with logging
- [ ] 7.4 Implement clock-out guarantee
  - try-finally around replay
  - atexit handler for emergency clock-out
  - Logging of all clock operations
- [ ] 7.5 Create systemd service file
  - `scripts/mask-daemon.service`
  - Proper restart policy and logging
- [ ] 7.6 Create integration test
  - End-to-end: capture, push, pull, replay (mocked Upwork)

## 8. Configuration & Documentation

- [ ] 8.1 Document all configuration options in `config/default.yaml`
  - Comments explaining each setting
  - Safe defaults
- [ ] 8.2 Create README.md
  - Installation instructions
  - Usage examples
  - Architecture overview
- [ ] 8.3 Create TROUBLESHOOTING.md
  - Common issues and solutions
  - Logging and debugging tips

## 9. Testing & Verification

- [ ] 9.1 Create test fixtures
  - Sample git diffs
  - Sample replay session JSON
- [ ] 9.2 Run full integration test
  - Capture on dev machine
  - Push to test repo
  - Pull on Radxa
  - Replay with mocked Upwork
- [ ] 9.3 Test abort scenarios
  - SIGINT during replay
  - VS Code window closed
  - Network failure during git pull
- [ ] 9.4 Test clock-out guarantee
  - Simulate crashes at various points
  - Verify clock-out always happens
- [ ] 9.5 Verify ARM64 compatibility
  - Test all dependencies on Radxa
  - Document any platform-specific issues

## 10. Deployment

- [ ] 10.1 Install on Radxa Rock5B+
  - Run install_deps.sh
  - pip install package
  - Configure default.yaml
- [ ] 10.2 Calibrate Upwork UI
  - Run calibrate_upwork.py
  - Save coordinates to config
- [ ] 10.3 Set up git remote access
  - Configure SSH keys
  - Test pull from repository
- [ ] 10.4 Enable systemd service
  - Install service file
  - Enable and start daemon
- [ ] 10.5 Verify end-to-end operation
  - Capture real commit
  - Push, wait for poll
  - Observe replay with Upwork tracking

## Dependencies

```
Task Dependencies:
1. Project Setup → all other tasks
2. Input Backend → VS Code Controller, Upwork Controller
3. VS Code Controller → Replay Engine
4. Replay Engine → Session Orchestrator
5. Capture Tool → (independent, can parallel with 2-5)
6. Upwork Controller → Session Orchestrator
7. Session Orchestrator → Testing & Deployment
8. Configuration → Deployment
9. Testing → Deployment
```

## Estimated Effort

| Task Group | Estimated Hours |
|------------|-----------------|
| 1. Project Setup | 2 |
| 2. Input Backend | 4 |
| 3. VS Code Controller | 8 |
| 4. Replay Engine | 6 |
| 5. Capture Tool | 4 |
| 6. Upwork Controller | 8 |
| 7. Session Orchestrator | 6 |
| 8. Configuration & Docs | 3 |
| 9. Testing | 4 |
| 10. Deployment | 3 |
| **Total** | **48 hours** |
