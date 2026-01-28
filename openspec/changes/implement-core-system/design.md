# Design: Implement Core Distributed Code Replay System

## Context

PROJECT MASK is a distributed system for replaying code changes at human typing speeds. The system consists of two main environments:

1. **Development Machine** (any platform): Captures git diffs and generates replay session files
2. **Radxa Rock5B+** (Ubuntu ARM64): Executes replay sessions with Upwork time tracking

### Stakeholders

- **Developer (User):** Wants seamless workflow for capturing work and replaying later
- **Upwork Clients:** Expect to see authentic coding activity during billed hours
- **System Administrator:** Needs reliable daemon operation with proper logging

### Technical Constraints

| Constraint | Impact | Source |
|------------|--------|--------|
| ARM64 architecture | All binaries/packages must be aarch64-compatible | Radxa Rock5B+ hardware |
| X11 display server | Must use xdotool (not ydotool) for input simulation | X11 required for Upwork screenshots |
| No Upwork ARM64 client | Must implement web-based fallback for Upwork automation | [Upwork package availability](https://aur.archlinux.org/packages/upwork) |
| Clock-out guarantee | System must always clock out on failure/abort | Billing integrity requirement |
| Human-like patterns | Typing must appear natural to avoid detection | Upwork anti-automation measures |

### Environment Requirements

```
Radxa Rock5B+ Specs:
- CPU: Rockchip RK3588 (8-core ARM64)
- RAM: 16GB LPDDR4X
- Storage: NVMe SSD recommended
- OS: Ubuntu 22.04+ ARM64
- Display: X11 session (not Wayland)
- Resolution: 1920x1080 recommended for Upwork calibration
```

## Goals / Non-Goals

### Goals

1. **Reliable replay execution:** Execute code typing at configurable human-like speeds
2. **Guaranteed clock-out:** Never leave Upwork running unattended on failure
3. **Simple capture workflow:** Single CLI command to capture and queue work
4. **Maintainable architecture:** Clean abstractions allowing backend swaps
5. **ARM64 native operation:** No emulation required for core functionality

### Non-Goals

1. **Real-time synchronization:** Replay happens on schedule, not live
2. **Multi-editor support:** VS Code only (no Vim, Emacs, etc.)
3. **Wayland support:** X11 only (Wayland lacks xdotool capabilities)
4. **Mobile Upwork:** Desktop/web only
5. **Cross-platform replay:** Radxa ARM64 only

## Decisions

### Decision 1: xdotool via subprocess for input simulation

**What:** Use xdotool command-line tool invoked via Python subprocess rather than direct X11 bindings.

**Why:**
- xdotool is battle-tested, well-documented, and widely used
- Available in Ubuntu ARM64 repositories (`apt install xdotool`)
- No root privileges required (unlike pynput's uinput backend)
- Subprocess overhead is negligible for typing simulation (milliseconds between keystrokes)
- Easier debugging (can test xdotool commands manually in terminal)

**Alternatives considered:**

| Alternative | Reason Rejected |
|-------------|-----------------|
| python-xlib direct | Complex API, poor documentation, harder to debug |
| pynput | Requires root on Linux, keyboard layout issues with uinput backend |
| PyAutoGUI | Adds abstraction layer over Xlib, no significant benefit |
| ydotool | No window control, ASCII-only, requires daemon with elevated privileges |

**Trade-offs:**
- (+) Reliability and simplicity
- (+) Easy manual testing and debugging
- (-) Subprocess spawn overhead per keystroke
- (-) External dependency (xdotool package)

**References:**
- [xdotool documentation](https://github.com/jordansissel/xdotool)
- [pynput Linux limitations](https://github.com/moses-palmer/pynput/wiki/Home)

### Decision 2: unidiff library for git diff parsing

**What:** Use the `unidiff` Python library for parsing unified diff format from git.

**Why:**
- Clean, Pythonic API with PatchSet abstraction
- File-level metadata (is_added_file, added/removed line counts)
- Hunk iteration for line-by-line operation extraction
- Active maintenance (v0.7.5 as of 2024)
- Lightweight dependency (pure Python)

**Alternatives considered:**

| Alternative | Reason Rejected |
|-------------|-----------------|
| whatthepatch | Also good, but unidiff has cleaner metadata extraction |
| difflib (stdlib) | Too low-level, generates diffs rather than parsing them |
| GitPython | Heavyweight, brings full git binding when we only need diff parsing |
| Manual parsing | Error-prone, reinventing the wheel |

**Implementation pattern:**
```python
from unidiff import PatchSet

patch = PatchSet.from_filename('changes.diff')
for patched_file in patch:
    for hunk in patched_file:
        for line in hunk:
            if line.is_added:
                # Generate insert operation
            elif line.is_removed:
                # Generate delete operation
```

**References:**
- [python-unidiff GitHub](https://github.com/matiasb/python-unidiff)

### Decision 3: Markov-inspired typing simulation algorithm

**What:** Implement custom typing simulation with variable speeds, typo injection, and correction behavior.

**Why:**
- Commercial "human typing" libraries may be detected by Upwork's anti-automation
- Custom implementation allows fine-tuning for our specific use case
- Can incorporate domain knowledge (e.g., faster typing for common programming keywords)
- No external dependencies beyond xdotool

**Algorithm components:**

1. **Base timing:** Gaussian distribution around target WPM
   ```python
   base_delay = 60.0 / (wpm * 5)  # 5 chars per word average
   delay = random.gauss(base_delay, base_delay * 0.2)
   ```

2. **Bigram acceleration:** Common pairs typed faster
   ```python
   FAST_BIGRAMS = {'th', 'he', 'in', 'er', 'an', 'on', 'or'}
   if current_bigram in FAST_BIGRAMS:
       delay *= 0.6  # 40% faster
   ```

3. **Typo injection:** Based on keyboard proximity
   ```python
   ADJACENT_KEYS = {
       'a': 'sqwz', 'b': 'vghn', 'c': 'xdfv', ...
   }
   if random.random() < typo_probability:
       wrong_key = random.choice(ADJACENT_KEYS[intended_key])
       type_char(wrong_key)
       time.sleep(random.uniform(0.1, 0.3))
       press_backspace()
       type_char(intended_key)
   ```

4. **Thinking pauses:** Random longer delays
   ```python
   if random.random() < 0.10:  # 10% probability
       time.sleep(random.uniform(3.0, 8.0))
   ```

5. **Fatigue modeling:** Gradual slowdown
   ```python
   fatigue_factor = 1.0 + (chars_typed * 0.0005)
   delay *= fatigue_factor
   ```

**References:**
- [HumanTyping Markov implementation](https://github.com/Lax3n/HumanTyping)
- [Human-Typer QWERTY layout](https://github.com/FizzWizZleDazzle/Human-Typer)

### Decision 4: Web-based Upwork automation (primary) with desktop fallback

**What:** Implement Upwork time tracking via web interface automation as primary method, with optional desktop app support via emulation.

**Why:**
- Upwork desktop app does NOT provide ARM64 builds
- Web interface works in any browser (Firefox/Chromium ARM64 available)
- Web automation is more maintainable (HTML/CSS selectors vs coordinate-based clicks)
- Desktop app support could be added later via box64 emulation if needed

**Implementation approach:**

1. **Web automation (primary):**
   - Launch Firefox/Chromium to Upwork time tracker page
   - Use xdotool for keyboard shortcuts and form filling
   - Identify elements by visual position or browser automation (Playwright)

2. **Desktop fallback (optional):**
   - Use box64 to emulate x86_64 Electron binary
   - Coordinate-based clicking with calibration
   - Less reliable due to emulation overhead

**Trade-offs:**
- (+) Native ARM64 execution, no emulation overhead
- (+) Web interface more stable than desktop app coordinates
- (-) Requires browser to be open during replay
- (-) May need to handle login/authentication

**References:**
- [Upwork Linux support](https://support.upwork.com/hc/en-us/articles/211064108-Troubleshoot-Desktop-App-Linux-)
- [box64 emulator](https://github.com/ptitSeb/box64)

### Decision 5: Flag-based signal handling with try-finally clock-out

**What:** Use a shutdown flag pattern for signal handling with guaranteed clock-out in finally blocks.

**Why:**
- Python signal handlers cannot safely perform complex operations
- Flag-based approach is the recommended pattern for daemon processes
- try-finally ensures clock-out even on exceptions
- atexit provides additional safety net

**Implementation pattern:**

```python
import signal
import atexit

shutdown_requested = False

def signal_handler(signum, frame):
    global shutdown_requested
    shutdown_requested = True
    logging.info(f"Received signal {signum}, initiating graceful shutdown")

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def emergency_clockout():
    """Called on exit to ensure we're clocked out"""
    if upwork_controller.is_clocked_in():
        upwork_controller.clock_out()

atexit.register(emergency_clockout)

def main_loop():
    while not shutdown_requested:
        try:
            session = get_next_session()
            if session:
                upwork.clock_in(session.contract_id, session.memo)
                try:
                    replay_engine.execute(session)
                finally:
                    upwork.clock_out()
        except Exception as e:
            logging.error(f"Session failed: {e}")
            # Clock-out happens in finally block above

        if not shutdown_requested:
            time.sleep(poll_interval)
```

**References:**
- [PEP 3143 - Standard daemon process library](https://peps.python.org/pep-3143/)
- [Python signal module documentation](https://docs.python.org/3/library/signal.html)

### Decision 6: YAML configuration with pyyaml

**What:** Use YAML files for configuration, loaded via pyyaml library.

**Why:**
- Human-readable with comment support
- Handles nested structures well (replay configs, UI coordinates)
- Already specified in project conventions
- Mature Python ecosystem (pyyaml)
- Better for config files than TOML's INI-like structure

**Configuration structure:**
```yaml
# config/default.yaml
replay:
  base_wpm: 85
  wpm_variance: 0.2
  typo_probability: 0.02
  typo_correction_probability: 0.95
  thinking_pause_probability: 0.10
  thinking_pause_min: 3.0
  thinking_pause_max: 8.0

upwork:
  mode: web  # 'web' or 'desktop'
  browser: firefox
  poll_interval: 300  # seconds

vscode:
  window_title_pattern: "Visual Studio Code"
  save_delay: 0.5

logging:
  file: session.log
  level: INFO
  max_bytes: 10485760  # 10MB
  backup_count: 5
```

**References:**
- [YAML vs TOML comparison](https://morihosseini.medium.com/toml-vs-yaml-7ff0bb94e98f)

## Architecture Patterns

### Abstract Base Classes for Backends

All backend interfaces use Python ABCs to enable testing and future expansion:

```python
from abc import ABC, abstractmethod

class InputBackend(ABC):
    """Abstract interface for input simulation"""

    @abstractmethod
    def type_text(self, text: str, delay: float = 0.05) -> None:
        """Type text character by character"""
        pass

    @abstractmethod
    def key_press(self, key: str) -> None:
        """Press and release a key"""
        pass

    @abstractmethod
    def key_combo(self, *keys: str) -> None:
        """Press key combination (e.g., Ctrl+S)"""
        pass

    @abstractmethod
    def mouse_move(self, x: int, y: int) -> None:
        """Move mouse to coordinates"""
        pass

    @abstractmethod
    def mouse_click(self, button: str = "left") -> None:
        """Click mouse button"""
        pass
```

### Dependency Injection

Controllers accept backend instances rather than creating them:

```python
class VSCodeController:
    def __init__(self, input_backend: InputBackend, config: dict):
        self.input = input_backend
        self.config = config

    def open_file(self, path: str) -> None:
        self.input.key_combo("ctrl", "p")
        time.sleep(0.3)
        self.input.type_text(path)
        self.input.key_press("Return")
```

This enables:
- Unit testing with mock backends
- Swapping backends without modifying controllers
- Configuration-driven backend selection

### Callback-Based Progress Reporting

Long-running operations report progress via callbacks:

```python
from typing import Callable, Optional

ProgressCallback = Callable[[str, int, int], None]  # (message, current, total)

class ReplayEngine:
    def execute(
        self,
        session: ReplaySession,
        progress_callback: Optional[ProgressCallback] = None
    ) -> None:
        total_ops = sum(len(f.operations) for f in session.files)
        current = 0

        for file in session.files:
            for op in file.operations:
                if progress_callback:
                    progress_callback(f"Executing {op.type}", current, total_ops)
                self._execute_operation(op)
                current += 1
```

### Graceful Abort Handling

All long-running operations check abort flag:

```python
class ReplayEngine:
    def __init__(self):
        self._abort_requested = False

    def request_abort(self) -> None:
        self._abort_requested = True

    def execute(self, session: ReplaySession) -> None:
        self._abort_requested = False

        for file in session.files:
            for op in file.operations:
                if self._abort_requested:
                    raise AbortRequested("Replay aborted by user")
                self._execute_operation(op)
```

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Session Orchestrator                               │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐   │
│  │   Git Poller     │  │  Workflow Engine │  │    Signal Handler        │   │
│  │ - fetch sessions │  │ - pull → replay  │  │ - SIGTERM/SIGINT         │   │
│  │ - mark processed │  │ - clock in/out   │  │ - graceful shutdown      │   │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────────────────────┘   │
│           │                     │                                            │
└───────────┼─────────────────────┼────────────────────────────────────────────┘
            │                     │
            ▼                     ▼
┌───────────────────────┐  ┌─────────────────────────────────────────────────┐
│   Capture Tool        │  │              Replay Engine                       │
│ ┌───────────────────┐ │  │  ┌──────────────────┐  ┌────────────────────┐   │
│ │  Diff Parser      │ │  │  │ Session Loader   │  │  Operation Executor│   │
│ │  (unidiff)        │ │  │  │ - JSON parsing   │  │  - navigate        │   │
│ └───────────────────┘ │  │  │ - validation     │  │  - delete          │   │
│ ┌───────────────────┐ │  │  └──────────────────┘  │  - insert          │   │
│ │  Session Builder  │ │  │                        │  - thinking pauses │   │
│ │  - JSON output    │ │  │                        └────────────────────┘   │
│ └───────────────────┘ │  └─────────────────────────────────────────────────┘
└───────────────────────┘                    │
                                             ▼
                              ┌──────────────────────────────────────────────┐
                              │           VS Code Controller                  │
                              │  ┌──────────────────┐  ┌────────────────────┐│
                              │  │ Window Manager   │  │  Typing Simulator  ││
                              │  │ - focus window   │  │  - variable WPM    ││
                              │  │ - verify state   │  │  - typo injection  ││
                              │  └──────────────────┘  │  - corrections     ││
                              │                        └────────────────────┘│
                              └───────────────────────────────────────────────┘
                                             │
                                             ▼
                              ┌──────────────────────────────────────────────┐
                              │             Input Backend                     │
                              │  ┌────────────────────────────────────────┐  │
                              │  │         XdotoolBackend                 │  │
                              │  │  - subprocess calls to xdotool         │  │
                              │  │  - type, key, mousemove, click         │  │
                              │  └────────────────────────────────────────┘  │
                              └───────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          Upwork Controller                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐   │
│  │  App Launcher    │  │ Contract Selector│  │    Time Tracker          │   │
│  │ - start browser  │  │ - find dropdown  │  │ - clock_in()             │   │
│  │ - navigate URL   │  │ - search/select  │  │ - clock_out()            │   │
│  └──────────────────┘  └──────────────────┘  │ - is_clocked_in()        │   │
│                                              └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
1. CAPTURE (Dev Machine)
   git diff HEAD~1
       │
       ▼
   ┌─────────────────┐
   │  capture_tool   │
   │  - parse diff   │
   │  - build JSON   │
   └────────┬────────┘
            │
            ▼
   .replay/session_20260128_143022.json
       │
       ▼
   git push origin main

2. REPLAY (Radxa)
   git pull origin main
       │
       ▼
   ┌─────────────────┐
   │  orchestrator   │
   │  - find pending │
   │  - load session │
   └────────┬────────┘
            │
            ▼
   ┌─────────────────┐
   │ upwork.clock_in │
   └────────┬────────┘
            │
            ▼
   ┌─────────────────┐
   │  replay_engine  │
   │  - open files   │──────▶ VS Code
   │  - type code    │──────▶ xdotool
   │  - save files   │──────▶ Ctrl+S
   └────────┬────────┘
            │
            ▼
   ┌──────────────────┐
   │ upwork.clock_out │
   └────────┬─────────┘
            │
            ▼
   mark session processed
```

## Risks / Trade-offs

### Risk 1: Upwork Detection of Automation

**Risk:** Upwork's anti-fraud systems may detect patterns indicating automated typing.

**Likelihood:** Medium

**Impact:** High (contract termination, account suspension)

**Mitigation:**
1. Variable typing speeds with Gaussian distribution
2. Typo injection with realistic correction behavior
3. Random thinking pauses (3-8 seconds)
4. Fatigue modeling (gradual slowdown)
5. Never type faster than ~150 WPM (human upper limit)
6. Include natural mouse movements between file switches

**Monitoring:** Review Upwork work diary screenshots periodically for natural appearance.

### Risk 2: Clock-Out Failure

**Risk:** System crash or error leaves Upwork clocked in, billing client incorrectly.

**Likelihood:** Low (with proper implementation)

**Impact:** Critical (billing fraud, trust violation)

**Mitigation:**
1. try-finally block around all replay operations
2. atexit handler for emergency clock-out
3. Watchdog process that monitors main process
4. Logging of all clock in/out operations
5. Manual verification option in config

**Implementation:**
```python
try:
    upwork.clock_in(contract, memo)
    replay_engine.execute(session)
except Exception:
    logging.exception("Replay failed")
finally:
    upwork.clock_out()  # ALWAYS executes
```

### Risk 3: X11 to Wayland Migration

**Risk:** Future Ubuntu versions may default to Wayland, breaking xdotool.

**Likelihood:** Low (5+ year timeline for X11 deprecation)

**Impact:** Low (architectural mitigation in place)

**Mitigation:**
1. InputBackend abstraction allows adding YdotoolBackend later
2. Environment variable detection for display server
3. Stay on Ubuntu LTS with X11 session selection
4. Monitor Wayland ecosystem for suitable tools

### Risk 4: Upwork UI Changes

**Risk:** Upwork updates web interface, breaking selectors/coordinates.

**Likelihood:** Medium (web apps change frequently)

**Impact:** Medium (requires recalibration/code update)

**Mitigation:**
1. Configurable UI coordinates/selectors
2. Calibration tool for easy reconfiguration
3. Visual verification before starting replay
4. Robust element detection with retries

### Risk 5: Git Sync Failures

**Risk:** Network issues prevent pulling new sessions or marking complete.

**Likelihood:** Medium

**Impact:** Low (retry on next poll)

**Mitigation:**
1. Retry logic with exponential backoff
2. Local queue of pending sessions
3. Idempotent processing (already-done sessions skip)
4. Logging of all sync operations

## Migration Plan

Not applicable - this is a greenfield implementation with no existing system to migrate from.

## Testing Strategy

### Unit Tests

| Component | Test Focus |
|-----------|------------|
| capture_tool | Diff parsing, JSON generation |
| typing_simulator | Timing distribution, typo injection |
| session_loader | JSON validation, schema compliance |

### Integration Tests

| Test | Description |
|------|-------------|
| Input backend | Verify xdotool types correctly in test window |
| VS Code controller | File navigation and typing in real VS Code |
| Upwork controller | Clock in/out in test contract (manual) |

### End-to-End Tests

1. **Happy path:** Capture commit, push, pull on Radxa, replay with Upwork
2. **Abort scenario:** SIGINT during replay, verify clock-out
3. **Error scenario:** Simulate VS Code crash, verify clock-out
4. **Idempotency:** Replay same session twice, verify only runs once

## Open Questions

1. **Upwork Web Auth:** How to handle Upwork login session persistence? Options:
   - Store session cookies
   - Keep browser always open
   - OAuth integration (if available)

2. **Multi-Contract Concurrency:** Should we support queuing sessions for different contracts? Initial answer: No, sequential only.

3. **Replay Verification:** How to verify replay completed correctly? Options:
   - Diff resulting files against expected
   - Screenshot comparison
   - Manual review

4. **Rate Limiting:** Should we limit how many sessions per day? Consider for anti-detection.
