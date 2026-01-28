# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PROJECT MASK is a distributed code replay system that replays code changes at human typing speeds on an ARM64 SBC while Upwork's time tracker captures the activity. Two deployment targets:
- **Main dev machine** (Linux/macOS): Capture tool parses git diffs, generates replay session JSON
- **Raspberry Pi 5 / Radxa Rock5B+** (Ubuntu ARM64): Replay engine types code in VS Code while Upwork tracks time

## Architecture

```
Main Dev Machine                    Git Remote                 Raspberry Pi 5
┌──────────────────┐               ┌──────────┐               ┌─────────────────────────┐
│ capture/         │──git push───▶│ .replay/ │◀──git pull────│ orchestrator/           │
│ - Parse git diff │               │ sessions │               │ ├─ Pull sessions        │
│ - Generate JSON  │               └──────────┘               │ ├─ Clock in (Upwork)    │
└──────────────────┘                                          │ ├─ Execute replay       │
                                                              │ └─ Clock out            │
                                                              │                         │
                                                              │ replay/                 │
                                                              │ ├─ input_backend.py     │
                                                              │ ├─ vscode_controller.py │
                                                              │ └─ replay_engine.py     │
                                                              │                         │
                                                              │ upwork/                 │
                                                              │ └─ upwork_controller.py │
                                                              └─────────────────────────┘
```

### Key Components

- **capture/**: Git diff parsing via `unidiff`, CLI for generating session JSON
- **replay/input_backend.py**: Abstract `InputBackend` ABC with `XdotoolBackend` (X11) implementation
- **replay/vscode_controller.py**: VS Code automation via keyboard shortcuts (Ctrl+P, Ctrl+G, Ctrl+S)
- **replay/replay_engine.py**: Executes session JSON, simulates typing with variable WPM/typos
- **upwork/upwork_controller.py**: UI automation for Upwork client (launch, select contract, clock in/out)
- **orchestrator/session_orchestrator.py**: Daemon that polls git, coordinates replay with Upwork tracking

### Data Flow

1. Developer commits code on main machine
2. `mask-capture --commit HEAD --contract "Client" --memo "Work"` generates `.replay/*.json`
3. Push to git remote
4. Radxa daemon pulls, finds pending sessions
5. Clock in to Upwork, replay typing in VS Code, clock out
6. Mark session processed

## Tech Stack

- **Python 3.10+** with type annotations
- **xdotool** for X11 input simulation (primary)
- **wmctrl** for window management
- **unidiff** for git diff parsing
- **python-xlib** for X11 bindings
- **pyyaml** for configuration

## Development Commands

```bash
# Raspberry Pi 5 setup (run on Pi)
./scripts/setup_pi5.sh

# Or manual install (Ubuntu/Debian)
sudo apt install xdotool wmctrl
pip install -r requirements.txt
pip install -e .

# Run capture tool (main dev machine)
mask-capture --commit HEAD --contract "ClientName" --memo "Feature work"

# Test input backend (Pi 5)
python scripts/test_input.py

# Calibrate Upwork UI positions (Pi 5)
python scripts/calibrate_upwork.py

# Run orchestrator daemon (Pi 5)
mask-daemon

# Or run as systemd service
sudo systemctl enable mask-daemon
sudo systemctl start mask-daemon
```

## Code Conventions

- PEP 8, 100-char line limit
- Type hints on public functions
- Google-style docstrings
- ABCs for backend interfaces (`InputBackend`)
- Dependency injection for controllers
- Callbacks for progress reporting
- SIGINT/SIGTERM handlers for graceful shutdown

## Critical Reliability Requirements

- **Clock-out guarantee**: Must always clock out on failure/abort (emergency handler)
- **Idempotent processing**: Sessions marked processed to prevent re-runs
- **ARM64 compatibility**: All deps must work on aarch64

## Replay Session JSON Format

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
        {"type": "insert", "line": 15, "content": "new code..."}
      ]
    }
  ],
  "replay_config": {"base_wpm": 85, "typo_probability": 0.02}
}
```

<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->
