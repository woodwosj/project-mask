# Change: Add AI-Powered Self-Healing Intervention System

## Why

PROJECT MASK operates unattended on a VPS or Raspberry Pi, replaying code changes while Upwork captures activity. However, several failure modes can cause sessions to stall silently without recovery:

1. **VS Code workspace issues** - Wrong project open, file not found, or workspace stuck on welcome screen
2. **Dialog interruptions** - Extension prompts, update notifications, or Git authentication dialogs blocking replay
3. **Silent failures** - Input backend errors that don't raise exceptions, leaving VS Code in unexpected state
4. **Content drift** - Output files diverging from expected content due to missed operations or cursor misplacement

Currently, these issues require manual intervention, defeating the purpose of unattended operation. A session that fails at minute 5 of a 60-minute replay wastes 55 minutes of billed time with nothing to show.

**Key Problem Statements:**
1. No visibility into replay progress beyond text logs
2. No mechanism to detect or recover from visual anomalies (dialogs, wrong file, etc.)
3. No validation that typed content matches expected output
4. No automatic recovery from recoverable failure states

## What Changes

This proposal adds an AI intervention layer that monitors replay progress via periodic screenshots, analyzes them using Claude Opus 4.5's vision capabilities, and takes corrective action when problems are detected.

### New Capability: AI Intervention System (`intervention/`)

**Core Components:**

1. **Screenshot Capture** (`intervention/screenshot.py`)
   - Capture full-screen screenshots at configurable intervals (default: 10 minutes)
   - Support for both X11 (via pyscreenshot/scrot) and Wayland (via DBus portal)
   - Save screenshots to timestamped files for debugging
   - Minimal resource footprint suitable for SBC operation

2. **Claude Vision Analyzer** (`intervention/analyzer.py`)
   - Send screenshots to Claude Opus 4.5 via Anthropic API
   - Structured prompt for detecting common failure modes:
     - VS Code dialogs (Git auth, extension prompts, updates)
     - Wrong file/project open
     - Error messages or exceptions visible
     - Terminal focus (instead of editor)
     - Upwork tracker state verification
   - Return structured assessment with confidence scores

3. **Recovery Actions** (`intervention/recovery.py`)
   - Library of recovery procedures using existing input backend:
     - Close dialogs (Escape key, clicking X buttons)
     - Focus VS Code window
     - Open correct file via Ctrl+P
     - Restart from last checkpoint
   - Claude provides recovery instructions, system executes them

4. **File Verification** (`intervention/verifier.py`)
   - Compare output files with expected content from session JSON
   - Use difflib for semantic comparison (not byte-exact)
   - Identify lines that differ from expected
   - Optionally trigger manual re-type of discrepant sections

5. **Intervention Orchestrator** (`intervention/orchestrator.py`)
   - Timer-based screenshot capture during replay
   - Integrate with replay engine via callback hooks
   - Manage intervention state and cooldowns
   - Log all interventions for post-session review

### Integration Points

- **Replay Engine:** Add hooks for intervention checks between file operations
- **Session Orchestrator:** Enable/disable AI intervention via config
- **Config:** New `intervention` section in default.yaml

### Non-Goals (Explicit Exclusions)

- **Real-time keystroke monitoring:** Too resource-intensive for SBC
- **Mouse tracking:** Focus is on visual state, not input tracing
- **Upwork automation recovery:** Keep scope to VS Code replay only
- **Learning/adaptation:** No persistent model training; each session is independent

## Impact

- **Affected specs:** `replay-engine` (minor hooks), `session-orchestrator` (integration)
- **Affected code:**
  - New module: `intervention/` with 5 Python files
  - Modified: `replay/replay_engine.py` (add intervention hooks)
  - Modified: `orchestrator/session_orchestrator.py` (enable intervention)
  - Modified: `config/default.yaml` (intervention config section)
- **New dependencies:**
  - Python: `anthropic` (Anthropic API SDK)
  - Python: `pyscreenshot` or `mss` (screenshot capture)
  - System: `scrot` (lightweight X11 screenshot, optional)
- **API requirements:** Anthropic API key with Claude Opus 4.5 access

## Research Findings

### Anthropic Python SDK Vision Capabilities

Claude Opus 4.5 supports vision input via the Messages API with images encoded as base64. The SDK provides both synchronous and asynchronous interfaces.

**Image input format:**
```python
{
    "type": "image",
    "source": {
        "type": "base64",
        "media_type": "image/png",
        "data": base64_encoded_string
    }
}
```

**Supported formats:** JPEG, PNG, GIF, WebP
**Max image size:** 20MB per image (recommended: optimize to ~1MB for latency)

**Sources:**
- [Claude Vision Documentation](https://platform.claude.com/docs/en/build-with-claude/vision)
- [Anthropic SDK Python](https://github.com/anthropics/anthropic-sdk-python)
- [Vision API Examples](https://medium.com/@judeaugustinej/vision-capability-from-claude-4150e6023d98)

### Screenshot Capture on Linux

**Recommended approach: pyscreenshot library**

Multiple backends supported for maximum compatibility:
- `scrot` - Lightweight X11 tool, fast (~100ms)
- `imagemagick` - Widely available fallback
- `PyQt5/PySide2` - If already installed
- `mss` - Pure Python, high performance (~60fps)

For ARM64/aarch64, both `scrot` and `mss` are confirmed to work.

**Sources:**
- [pyscreenshot GitHub](https://github.com/ponty/pyscreenshot)
- [mss - fast cross-platform screenshots](https://github.com/mherkazandjian/fastgrab)
- [Linux screenshot methods](https://dnmtechs.com/capturing-screenshots-with-python-script-on-linux/)

### VS Code Recovery via xdotool

Existing xdotool backend already supports required operations:

| Recovery Action | xdotool Command |
|-----------------|-----------------|
| Close dialog | `xdotool key Escape` or `xdotool key Return` |
| Focus VS Code | `xdotool search --name "Visual Studio Code" windowactivate` |
| Open file | `xdotool key ctrl+p` then type filename |
| Close notification | `xdotool key ctrl+shift+m` (toggle problems) |

**Sources:**
- [xdotool documentation](https://manpages.ubuntu.com/manpages/trusty/man1/xdotool.1.html)
- [Python xdotool wrapper](https://gist.github.com/joaoescribano/118607eb7b0afdc05e7f0f491f20f4ef)

### File Comparison Techniques

Python's `difflib` module provides semantic comparison:
- `unified_diff()` - Line-by-line differences with context
- `SequenceMatcher.ratio()` - Similarity score (0.0 to 1.0)
- `HtmlDiff` - Visual diff reports for debugging

**Tolerance approach:** Consider files matching if >98% similar, flagging for review if 95-98%, and failing if <95%.

**Sources:**
- [difflib documentation](https://docs.python.org/3/library/difflib.html)
- [filecmp module](https://docs.python.org/3/library/filecmp.html)

### Agentic Workflow Best Practices

Key patterns from agentic AI workflow research:

1. **Plan-Execute-Reflect loop:** Claude analyzes screenshot, proposes action, system executes, Claude verifies outcome
2. **Bounded retries:** Maximum 3 recovery attempts per intervention window
3. **Graceful degradation:** If AI intervention fails, continue replay without it
4. **Observability:** Log all AI requests/responses for debugging
5. **Cooldown periods:** Minimum 60 seconds between interventions to avoid loops

**Sources:**
- [Agentic AI Workflows Guide](https://arxiv.org/html/2512.08769v1)
- [Agentic Workflow Patterns](https://www.techtarget.com/searchenterpriseai/tip/A-technical-guide-to-agentic-AI-workflows)
- [Production AI Agent Design](https://devcom.com/tech-blog/ai-agentic-workflows/)

## Cost Analysis

**API Costs (Anthropic Claude Opus 4.5):**
- Input: $15/million tokens
- Output: $75/million tokens
- Estimated tokens per screenshot analysis: ~2,000 input + ~500 output
- Cost per intervention check: ~$0.07

**For a typical 60-minute session with 6 checks (every 10 min):**
- Normal (no issues): 6 x $0.07 = $0.42
- With recovery: Add ~$0.14 per recovery attempt

**Recommendation:** Make interval configurable; 15-minute default reduces cost to ~$0.28/session.

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| API rate limits | Low | Medium | Implement exponential backoff, local queuing |
| False positive recovery | Medium | Medium | Require high confidence (>0.85) before action |
| Recovery makes things worse | Low | High | Snapshot state before recovery, rollback if needed |
| API key exposure | Low | High | Environment variable, never in config files |
| High API costs | Medium | Low | Configurable interval, per-session budget cap |
| Screenshot capture fails | Low | Low | Graceful degradation, continue without AI |

## Approval Checklist

- [ ] Anthropic API integration approach approved
- [ ] Screenshot capture method confirmed for target platform
- [ ] Recovery action library scope agreed
- [ ] Cost budget per session acceptable
- [ ] File verification tolerance thresholds approved
- [ ] Integration with existing replay engine accepted
