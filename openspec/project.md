# Project Context

## Purpose
PROJECT MASK is a distributed code replay system that replays code changes at human typing speeds on a Radxa Rock5B+ single-board computer while Upwork's time tracker captures the activity. It solves privacy concerns when working on multiple client projects simultaneously by allowing developers to batch their work and replay it later during dedicated time-tracking sessions.

**Key Goals:**
- Capture git diffs and convert them to replayable session files
- Simulate realistic human typing (60-120 WPM with typos and corrections)
- Automate Upwork time tracking (clock in/out, contract selection, memos)
- Run as a daemon that polls for new replay sessions

## Tech Stack
- **Language:** Python 3.10+
- **Target Platforms:**
  - Main dev machine (any Linux/macOS) - capture tool
  - Radxa Rock5B+ (Ubuntu ARM64) - replay engine
- **Display Server:** X11 (primary), Wayland (fallback)
- **Editor:** VS Code (ARM64 build)
- **Time Tracker:** Upwork Linux client (Electron-based)

**System Dependencies (apt):**
- `xdotool` - X11 input simulation
- `ydotool` - Wayland fallback
- `wmctrl` - Window management

**Python Dependencies:**
- `unidiff` - Git diff parsing
- `python-xlib` - X11 bindings for window detection
- `pyyaml` - Configuration files

## Project Conventions

### Code Style
- **Formatting:** Follow PEP 8 with 100-character line limit
- **Type Hints:** Use type annotations on all public functions
- **Naming:**
  - `snake_case` for functions, variables, modules
  - `PascalCase` for classes
  - `UPPER_SNAKE_CASE` for constants
- **Docstrings:** Google-style docstrings for public APIs
- **Imports:** Standard library, third-party, local (separated by blank lines)

### Architecture Patterns
- **Abstract Base Classes:** Use ABCs for backend interfaces (e.g., `InputBackend`)
- **Dependency Injection:** Controllers accept backend instances rather than creating them
- **Callbacks:** Use callbacks for progress reporting rather than return values
- **Signal Handling:** Graceful shutdown via SIGINT/SIGTERM handlers
- **Configuration:** YAML files in `config/` directory, loaded at startup

### Module Structure
```
capture/          # Runs on main dev machine
  capture_tool.py # Git diff parsing
  cli.py          # Command-line interface

replay/           # Runs on Radxa
  input_backend.py    # Abstract input + xdotool/ydotool implementations
  vscode_controller.py # VS Code automation
  replay_engine.py    # Session execution

upwork/           # Runs on Radxa
  upwork_controller.py # Upwork UI automation

orchestrator/     # Runs on Radxa
  session_orchestrator.py # Full workflow coordination
```

### Testing Strategy
- **Unit Tests:** Test capture tool diff parsing with sample diffs
- **Integration Tests:**
  - Input backend: verify xdotool types correctly
  - VS Code controller: file navigation and typing
  - Upwork controller: UI element detection
- **Manual Tests:**
  - Full end-to-end: capture → push → pull → replay with Upwork
  - Abort scenarios: ensure clock-out always happens on failure
- **Calibration Scripts:** Interactive tools in `scripts/` for UI position mapping

### Git Workflow
- **Branching:** Feature branches off `main`, merged via PR
- **Commits:** Conventional commits (`feat:`, `fix:`, `refactor:`, etc.)
- **Replay Sessions:** Stored in `.replay/` directory as JSON files
- **Processed Marker:** Sessions marked complete after successful replay

## Domain Context

### Replay Session Format
Sessions are JSON files containing:
- `session_id` - Unique identifier (timestamp-based)
- `contract_id` - Upwork contract name for time tracking
- `memo` - Work description for Upwork
- `files[]` - Array of file operations:
  - `navigate` - Move cursor to line
  - `delete` - Remove lines
  - `insert` - Type new content
- `replay_config` - Typing speed, typo probability, etc.

### Human Simulation Parameters
- **Base WPM:** 60-120 words per minute (configurable)
- **Typo Probability:** ~2% chance per keystroke
- **Thinking Pauses:** 10% probability, 3-8 seconds duration
- **Variable Delays:** Randomized to avoid robotic patterns

### Upwork Integration
- Launch app if not running
- Select correct contract from dropdown
- Set memo describing work
- Click Start/Stop to clock in/out
- Emergency clock-out on any failure

## Important Constraints

### Technical Constraints
- **ARM64 Compatibility:** All dependencies must work on aarch64
- **X11 Required:** xdotool is primary; Wayland support via ydotool is fallback only
- **No Root Required:** xdotool works without elevated privileges
- **Upwork ARM64:** Verify Electron client works on ARM64, or use web fallback

### Reliability Requirements
- **Clock-out Guarantee:** Must always clock out on failure/abort
- **Graceful Shutdown:** Handle SIGINT/SIGTERM for clean exit
- **Idempotent Processing:** Sessions marked processed to prevent re-runs
- **Logging:** Comprehensive logs to `session.log` for debugging

### Performance Constraints
- **Poll Interval:** Default 5 minutes between git fetches
- **Typing Realism:** Must appear human (variable speed, occasional errors)
- **Resource Usage:** Light enough for SBC (Radxa Rock5B+ has 16GB RAM)

## External Dependencies

### Git Remote
- Replay sessions pushed to `.replay/` directory in git repo
- Radxa pulls from remote to get new sessions
- Processed sessions tracked locally

### Upwork Desktop Client
- Electron-based Linux application
- UI automation via coordinate-based clicking
- Requires calibration for screen resolution

### VS Code
- ARM64 build from Microsoft repositories
- Controlled via keyboard shortcuts (Ctrl+P, Ctrl+G, Ctrl+S)
- Window focused via wmctrl/xdotool

### System Tools
- `xdotool` - Keystrokes and mouse events
- `wmctrl` - Window focus and management
- `git` - Fetching replay sessions
