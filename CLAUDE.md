# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PROJECT MASK replays code changes at human typing speeds while Upwork's time tracker runs. The typing generates authentic keystroke/click/scroll metrics that Upwork counts, and screenshots show real code being written.

**Workflow:**
1. Capture git diffs on dev machine → generate session JSON
2. Transfer session to replay machine (Pi 5 or any Linux box)
3. Manually start Upwork time tracker
4. Run `mask-replay` → types code in VS Code at human speed
5. Upwork captures activity metrics and screenshots
6. Manually stop Upwork when done

## Architecture

```
Dev Machine                         Replay Machine (Pi 5 / Linux)
┌──────────────────┐               ┌─────────────────────────────┐
│ mask-capture     │───scp/git────▶│ mask-replay                 │
│ - Parse git diff │               │ ├─ Open VS Code             │
│ - Generate JSON  │               │ ├─ Type real code           │
└──────────────────┘               │ ├─ Navigate files           │
                                   │ └─ Save files               │
                                   │                             │
                                   │ Upwork (manual)             │
                                   │ └─ Counts keystrokes/clicks │
                                   │ └─ Takes screenshots        │
                                   └─────────────────────────────┘
```

## Project Structure

```
capture/              # Git diff → session JSON
  capture_tool.py     # DiffParser, SessionBuilder
  cli.py              # mask-capture CLI

replay/               # Session execution
  input_backend.py    # InputBackend ABC, XdotoolBackend
  vscode_controller.py # VS Code automation, human-like typing
  replay_engine.py    # Session loading and execution
  cli.py              # mask-replay CLI

config/
  default.yaml        # Typing speed, delays, etc.

scripts/
  setup_pi5.sh        # Raspberry Pi 5 setup
  test_input.py       # Test xdotool
```

## Commands

```bash
# On dev machine - capture a commit
mask-capture --commit HEAD --contract "ClientName" --memo "Feature work"

# On replay machine - list available sessions
mask-replay --list

# Preview without typing
mask-replay session.json --dry-run

# Execute replay (start Upwork first!)
mask-replay session.json
```

## Session JSON Format

```json
{
  "session_id": "session_20260128_143022",
  "contract_id": "client_name",
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

## Code Conventions

- Python 3.9+, PEP 8, 100-char line limit
- Type hints on public functions
- Google-style docstrings
- ABCs for backend interfaces (`InputBackend`)

## Key Design Decisions

- **xdotool via subprocess**: More reliable than python-xlib on ARM64
- **Human-like typing**: Gaussian WPM variance, bigram acceleration, typo injection
- **Manual Upwork**: No automation needed - just counts activity metrics

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
