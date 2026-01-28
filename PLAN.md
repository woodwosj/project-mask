# PROJECT MASK - Code Replay System for Upwork Privacy

## Overview
A distributed system that replays code changes at human typing speeds on an ARM64 SBC (Raspberry Pi 5 or Radxa Rock5B+) while Upwork's time tracker captures the activity. Solves privacy concerns when working multiple client projects simultaneously.

## Architecture

```
Main Dev Machine                    Git Remote                 Raspberry Pi 5 (Ubuntu ARM64)
┌──────────────────┐               ┌──────────┐               ┌─────────────────────────────┐
│ Capture Tool     │──git push───▶│ .replay/ │◀──git pull────│ Session Orchestrator        │
│ - Parse git diff │               │ sessions │               │ ├─ Pull replay instructions │
│ - Generate JSON  │               └──────────┘               │ ├─ Clock in (Upwork)        │
│   replay session │                                          │ ├─ Execute Replay Engine    │
└──────────────────┘                                          │ └─ Clock out (Upwork)       │
                                                              │                             │
                                                              │ Replay Engine               │
                                                              │ ├─ Open files in VS Code    │
                                                              │ ├─ Type at 60-120 WPM       │
                                                              │ ├─ Variable pauses/typos    │
                                                              │ └─ Save files naturally     │
                                                              │                             │
                                                              │ Upwork Controller           │
                                                              │ ├─ Launch app               │
                                                              │ ├─ Select contract          │
                                                              │ ├─ Set memo                 │
                                                              │ └─ Clock in/out via UI      │
                                                              └─────────────────────────────┘
```

## Components to Build

### 1. Change Capture Tool (runs on main dev machine)
**Location:** `capture/`

- `capture_tool.py` - Parses git diffs using `unidiff` library, converts to structured replay JSON
- `cli.py` - Command-line interface: `mask-capture --commit HEAD --contract "ClientName" --memo "Feature work"`

**Replay Session JSON Format:**
```json
{
  "session_id": "session_20260128_143022",
  "contract_id": "client_contract_name",
  "memo": "Implementing feature X",
  "files": [
    {
      "path": "src/main.py",
      "operations": [
        {"type": "navigate", "line": 15},
        {"type": "delete", "line": 15, "line_end": 18},
        {"type": "insert", "line": 15, "content": "new code...", "typing_style": "normal"}
      ]
    }
  ],
  "replay_config": {"base_wpm": 85, "typo_probability": 0.02, ...}
}
```

### 2. Input Backend (Radxa)
**Location:** `replay/input_backend.py`

- Abstract `InputBackend` class with `type_text()`, `key_press()`, `key_combo()`, `mouse_move()`, `mouse_click()`
- `XdotoolBackend` - X11 implementation (primary)
- `YdotoolBackend` - Wayland implementation (fallback)
- Auto-detection based on `XDG_SESSION_TYPE`

### 3. VS Code Controller (Radxa)
**Location:** `replay/vscode_controller.py`

- Find/focus VS Code window
- Keyboard shortcuts: Ctrl+P (open file), Ctrl+G (goto line), Ctrl+S (save), etc.
- `type_code()` - Realistic typing with variable WPM, typos, corrections
- `open_file()`, `goto_line()`, `delete_lines()`, `save_file()`

### 4. Replay Engine (Radxa)
**Location:** `replay/replay_engine.py`

- Load session JSON
- Execute file operations in sequence
- Simulate thinking pauses (10% probability, 3-8 seconds)
- Progress reporting via callback
- Abort handling for graceful shutdown

### 5. Upwork Controller (Radxa)
**Location:** `upwork/upwork_controller.py`

- `launch_app()` - Start Upwork if not running
- `select_contract()` - Click dropdown, search, select
- `set_memo()` - Click field, type description
- `clock_in()` / `clock_out()` - Click Start/Stop button
- `UpworkCalibrator` - Interactive tool to find UI element positions for different screen resolutions

### 6. Session Orchestrator (Radxa)
**Location:** `orchestrator/session_orchestrator.py`

**Workflow:**
1. `pull_latest()` - Git fetch/reset to get new replay sessions
2. `find_pending_sessions()` - Scan `.replay/` for unprocessed JSON files
3. `clock_in()` - Start Upwork time tracking
4. `replay_engine.execute()` - Run the typing simulation
5. `clock_out()` - Stop Upwork time tracking
6. `mark_session_processed()` - Record completion

**Error Handling:**
- Signal handlers (SIGINT/SIGTERM) trigger graceful abort
- Emergency clock-out on any failure
- Comprehensive logging to `session.log`

## Directory Structure

```
PROJECT MASK/
├── capture/
│   ├── capture_tool.py
│   └── cli.py
├── replay/
│   ├── input_backend.py
│   ├── vscode_controller.py
│   └── replay_engine.py
├── upwork/
│   └── upwork_controller.py
├── orchestrator/
│   └── session_orchestrator.py
├── config/
│   └── default.yaml
├── scripts/
│   ├── install_deps.sh
│   └── calibrate_upwork.py
├── requirements.txt
└── README.md
```

## Dependencies

**System (apt):**
- `xdotool` (X11 input simulation)
- `ydotool` (Wayland fallback)
- `wmctrl` (window management)

**Python:**
- `unidiff` - Git diff parsing
- `python-xlib` - X11 bindings
- `pyyaml` - Configuration

## ARM64 SBC Specifics (Raspberry Pi 5 / Radxa Rock5B+)

- ARM64 (aarch64) architecture - all deps available
- Use X11 session (xdotool more reliable than ydotool)
- VS Code ARM64 build from Microsoft repos
- Upwork Linux client is Electron-based (no ARM64 support - use web fallback)

### Raspberry Pi 5 Notes
- 4GB or 8GB RAM models supported (8GB recommended)
- Ubuntu 24.04 LTS ARM64 recommended
- Use official Raspberry Pi Imager to flash
- Ensure adequate cooling (active fan recommended for sustained typing)

## Runtime Configuration

- **Trigger Mode:** Daemon/polling - continuously monitors git repo for new sessions
- **Display Server:** X11 - primary focus on xdotool (no ydotool needed)
- **Poll Interval:** Configurable, default 5 minutes

## Verification Plan

1. **Input Backend Test:** Run `scripts/test_input.py` to verify xdotool types correctly
2. **VS Code Controller Test:** Open VS Code, run file navigation and typing tests
3. **Upwork Calibration:** Run `scripts/calibrate_upwork.py` to map UI positions
4. **Capture Tool Test:** Create test commit, verify JSON output structure
5. **Integration Test:** Full end-to-end: capture on main machine, push, pull on Radxa, replay with Upwork tracking
6. **Clock-out Verification:** Test abort scenarios ensure clock-out always happens

## Implementation Order

1. Input backend (xdotool wrapper)
2. VS Code controller (typing simulation)
3. Replay engine (session execution)
4. Capture tool (git diff parsing)
5. Upwork controller (UI automation)
6. Session orchestrator (full workflow)
7. Installation scripts and config
8. Integration testing
