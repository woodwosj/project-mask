# Change: Implement Core Distributed Code Replay System

## Why

When working multiple Upwork contracts simultaneously, developers face privacy concerns: each client's time tracker captures screenshots that may reveal work on other projects. This creates a conflict between efficient batch work (context-switching between projects) and client expectations of dedicated time.

PROJECT MASK solves this by decoupling when work is done from when it is tracked. Developers work naturally on their primary machine, then replay code changes at human typing speeds on a dedicated Radxa Rock5B+ device while Upwork captures the activity. This ensures each client sees only their project during tracked sessions.

**Key Problem Statements:**
1. Privacy violation risk when switching between client projects with active time trackers
2. Need to demonstrate "live" coding activity that matches billed hours
3. Requirement for human-realistic typing patterns to avoid detection as automation
4. Must guarantee clock-out on any failure to prevent billing irregularities

## What Changes

This proposal implements the complete PROJECT MASK system from scratch, comprising six interconnected capabilities:

### New Capabilities

1. **Input Backend** (`replay/input_backend.py`)
   - Abstract base class for input simulation
   - XdotoolBackend implementation for X11
   - Keyboard typing, mouse movement, and key combinations
   - Auto-detection of display server type

2. **VS Code Controller** (`replay/vscode_controller.py`)
   - Window focus and management via wmctrl
   - File navigation using Ctrl+P, Ctrl+G shortcuts
   - Realistic code typing with configurable WPM
   - Human-like typo injection and correction

3. **Replay Engine** (`replay/replay_engine.py`)
   - Session JSON parsing and validation
   - Sequential file operation execution
   - Thinking pause simulation
   - Progress callbacks and abort handling

4. **Capture Tool** (`capture/capture_tool.py`, `capture/cli.py`)
   - Git diff parsing using unidiff library
   - Conversion to structured replay session JSON
   - CLI for capturing commits with contract metadata

5. **Upwork Controller** (`upwork/upwork_controller.py`)
   - Upwork app launch and window detection
   - Contract selection via UI automation
   - Memo field population
   - Clock in/out operations with verification

6. **Session Orchestrator** (`orchestrator/session_orchestrator.py`)
   - Git polling daemon for new sessions
   - Workflow coordination: pull -> clock in -> replay -> clock out
   - Signal handling for graceful shutdown
   - Emergency clock-out guarantee on any failure

### Supporting Infrastructure

- Configuration management via YAML (`config/default.yaml`)
- Installation scripts for ARM64 dependencies (`scripts/install_deps.sh`)
- UI calibration tool for Upwork (`scripts/calibrate_upwork.py`)
- Comprehensive logging to `session.log`

## Impact

- **Affected specs:** None (new codebase)
- **Affected code:** Creates new project structure with 6 Python modules
- **New dependencies:**
  - System: xdotool, wmctrl
  - Python: unidiff, python-xlib, pyyaml
- **Platform requirements:** Radxa Rock5B+ running Ubuntu ARM64 with X11

## Research Findings

### Input Simulation Technology

**Recommendation: xdotool via subprocess**

After evaluating multiple approaches, xdotool via subprocess is the recommended input backend for X11:

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| xdotool (subprocess) | Reliable, well-documented, no root needed, ARM64 available | External process overhead | **Recommended** |
| python-xlib (direct) | No subprocess, fine-grained control | Complex API, less documentation | Not recommended |
| pynput | Cross-platform, Python-native | uinput backend needs root, layout issues | Not recommended |
| PyAutoGUI | Simple API, cross-platform | Uses Xlib internally, adds abstraction layer | Acceptable fallback |
| ydotool | Works on Wayland | Needs root/daemon, ASCII-only, no window control | Not for this use case |

**Sources:**
- [xdotool GitHub](https://github.com/jordansissel/xdotool) - X11 automation tool
- [ydotool GitHub](https://github.com/ReimuNotMoe/ydotool) - Wayland alternative with limitations
- [pynput documentation](https://github.com/moses-palmer/pynput) - uinput requires root on Linux
- [PyAutoGUI documentation](https://github.com/asweigart/pyautogui) - Cross-platform GUI automation

**Key finding:** xdotool is available for ARM64/aarch64 via [Arch Linux ARM packages](https://archlinuxarm.org/packages/aarch64/xdotool) and Ubuntu repositories. No compatibility issues expected on Radxa Rock5B+.

### Human-Like Typing Simulation

**Recommendation: Custom implementation with Markov-inspired patterns**

Research into realistic typing simulation reveals several key components for believability:

1. **Variable Speed:** Common words typed 40% faster, complex words 30% slower
2. **Bigram Acceleration:** Frequent letter pairs (th, er, in) typed in rapid bursts
3. **Fatigue Modeling:** Typing speed gradually decreases over time (~0.05% per character)
4. **Natural Pauses:** Micro-pauses between words (250ms average)
5. **Typo Injection:** Based on keyboard layout proximity (adjacent key errors)
6. **Correction Behavior:** Backspace + retype with configurable probability

**Sources:**
- [HumanTyping](https://github.com/Lax3n/HumanTyping) - Markov chain-based realistic typing
- [Human-Typer](https://github.com/FizzWizZleDazzle/Human-Typer) - QWERTY layout error mapping
- [human-keyboard](https://github.com/luishacm/human-keyboard) - Fatigue and timing distributions

**Implementation approach:** Build custom typing algorithm using:
- Base WPM: 60-120 (configurable)
- Typo probability: 1-3% per keystroke
- Correction probability: 95% (occasionally leave typos for realism)
- Thinking pauses: 10% probability, 3-8 seconds duration
- Inter-character delay: Gaussian distribution around base timing

### Git Diff Parsing

**Recommendation: unidiff library**

| Library | Features | Maintenance | Verdict |
|---------|----------|-------------|---------|
| unidiff | Parse/extract metadata, CLI tool, PatchSet API | Active (0.7.5) | **Recommended** |
| whatthepatch | Parse + apply patches | Active | Good alternative |
| python-patch-ng | Parse + apply | Conan-maintained | Acceptable |
| difflib (stdlib) | Basic comparison | Built-in | Too low-level |

**Sources:**
- [python-unidiff](https://github.com/matiasb/python-unidiff) - Unified diff parsing library
- [whatthepatch](https://github.com/cscorley/whatthepatch) - Alternative with patch application

**unidiff advantages:**
- `PatchSet.from_filename()` for easy file loading
- `is_added_file`, `added`, `removed` properties per file
- Hunk-level iteration for line-by-line operations
- Clean API for converting diffs to replay operations

### Upwork ARM64 Compatibility

**Critical Finding: Upwork desktop app does NOT support ARM64**

Research confirms that Upwork's Linux time tracker is only available for x86_64/AMD64 architecture:
- [Upwork AUR package](https://aur.archlinux.org/packages/upwork) downloads `upwork_*_amd64.deb`
- Community reports confirm package architecture mismatch prevents installation on ARM64
- No official ARM64 build exists or is planned

**Mitigation Options:**

1. **Web-based tracking (Recommended):** Use Upwork web interface in Firefox/Chromium ARM64 with manual clock in/out automation
2. **x86 emulation:** Run amd64 binary via box64 emulator (experimental, may not work with Electron)
3. **Hybrid approach:** Use Upwork mobile app on separate device for time tracking, sync via API

**Recommendation:** Implement web-based Upwork automation as primary approach, with desktop app support as optional if emulation proves viable.

**Sources:**
- [Upwork Linux troubleshooting](https://support.upwork.com/hc/en-us/articles/211064108-Troubleshoot-Desktop-App-Linux-)
- [Upwork Community discussion on ARM64](https://community.upwork.com/t5/Freelancers/Does-UpWork-time-tracker-works-with-M1-macbooks/m-p/844448)

### Daemon Architecture

**Recommendation: Standalone polling daemon with systemd unit**

| Pattern | Use Case | Complexity |
|---------|----------|------------|
| Standalone polling + systemd | Periodic task, simple lifecycle | Low |
| python-daemon library | Full daemon protocol | Medium |
| asyncio event loop | I/O-heavy, concurrent | High |

**Best practices for signal handling:**
1. Use flag-based approach: Signal handler sets `shutdown_requested = True`
2. Main loop polls flag between operations
3. Register handlers for SIGTERM (systemd stop) and SIGINT (Ctrl+C)
4. Use `signal.signal()` for handler registration
5. Ensure clock-out happens in finally block or atexit handler

**Sources:**
- [PEP 3143 - Standard daemon process library](https://peps.python.org/pep-3143/)
- [Python signal module](https://docs.python.org/3/library/signal.html)
- [systemd-stopper](https://github.com/chschmitt/systemd-stopper) - Signal handler utility

### Configuration Format

**Recommendation: YAML**

| Format | Readability | Complexity Support | Python Support |
|--------|-------------|-------------------|----------------|
| YAML | Excellent | High (nested structures) | pyyaml (mature) |
| TOML | Good | Medium | tomllib (3.11+) |
| JSON | Poor (no comments) | High | Built-in |

YAML is recommended for this project because:
- Excellent readability for configuration files
- Full comment support for documentation
- Native support for complex nested structures (replay configs)
- Mature Python ecosystem (pyyaml)
- Already specified in project conventions

**Sources:**
- [TOML vs YAML comparison](https://morihosseini.medium.com/toml-vs-yaml-7ff0bb94e98f)
- [Config file formats overview](https://www.barenakedcoder.com/blog/2020/03/config-files-ini-xml-json-yaml-toml/)

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Upwork detects automation | Medium | High | Variable typing speeds, realistic pauses, typo injection |
| Upwork ARM64 unavailable | Confirmed | High | Web-based automation fallback |
| xdotool timing issues | Low | Medium | Configurable delays, retry logic |
| Clock-out failure | Low | Critical | Try-finally blocks, atexit handlers, watchdog process |
| X11 deprecated for Wayland | Low (5+ years) | Low | Architecture supports backend swap |

## Approval Checklist

- [ ] Technical approach reviewed
- [ ] ARM64 constraints acknowledged
- [ ] Upwork web fallback accepted
- [ ] Risk mitigations adequate
- [ ] Implementation order approved
