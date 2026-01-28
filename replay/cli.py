#!/usr/bin/env python3
"""
PROJECT MASK - Code Replay CLI

Replays git diff sessions in VS Code at human typing speeds.
Run Upwork time tracker manually - the replay generates authentic
keystrokes, mouse clicks, and scrolling that Upwork will count.

Usage:
    mask-replay <session.json>              # Replay a session
    mask-replay <session.json> --dry-run    # Preview without typing
    mask-replay --list                      # List available sessions
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from replay.input_backend import create_backend
from replay.vscode_controller import VSCodeController
from replay.replay_engine import ReplayEngine


def check_environment():
    """Check if the environment is ready for replay."""
    errors = []

    # Check DISPLAY
    if not os.environ.get('DISPLAY'):
        errors.append("No DISPLAY set - run from a desktop session")

    # Check xdotool
    try:
        subprocess.run(['xdotool', 'version'], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        errors.append("xdotool not found - install with: sudo apt install xdotool")

    # Check VS Code
    try:
        subprocess.run(['code', '--version'], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        errors.append("VS Code not found - install from https://code.visualstudio.com/")

    return errors


def list_sessions(replay_dir: Path):
    """List available session files."""
    if not replay_dir.exists():
        print(f"No replay directory found at {replay_dir}")
        return

    sessions = list(replay_dir.glob("*.json"))
    if not sessions:
        print(f"No session files found in {replay_dir}")
        return

    print(f"Available sessions in {replay_dir}:\n")
    for session_file in sorted(sessions):
        try:
            with open(session_file) as f:
                data = json.load(f)
            session_id = data.get('session_id', 'unknown')
            memo = data.get('memo', 'No description')
            file_count = len(data.get('files', []))
            print(f"  {session_file.name}")
            print(f"    ID: {session_id}")
            print(f"    Memo: {memo}")
            print(f"    Files: {file_count}")
            print()
        except Exception as e:
            print(f"  {session_file.name} (error reading: {e})")


def preview_session(session_path: Path):
    """Preview session contents without executing."""
    with open(session_path) as f:
        data = json.load(f)

    print("=" * 60)
    print("SESSION PREVIEW (dry run)")
    print("=" * 60)
    print(f"Session ID: {data.get('session_id')}")
    print(f"Memo: {data.get('memo')}")
    print(f"Contract: {data.get('contract_id', 'N/A')}")
    print()

    config = data.get('replay_config', {})
    print(f"Typing speed: {config.get('base_wpm', 85)} WPM")
    print(f"Typo rate: {config.get('typo_probability', 0.02) * 100:.1f}%")
    print()

    total_ops = 0
    total_chars = 0

    for file_data in data.get('files', []):
        path = file_data.get('path', 'unknown')
        ops = file_data.get('operations', [])
        chars = sum(len(op.get('content', '')) for op in ops if op.get('type') == 'insert')
        total_ops += len(ops)
        total_chars += chars

        print(f"File: {path}")
        print(f"  Operations: {len(ops)}")
        print(f"  Characters to type: {chars}")

        for op in ops:
            op_type = op.get('type')
            line = op.get('line', '?')
            if op_type == 'navigate':
                print(f"    - Navigate to line {line}")
            elif op_type == 'delete':
                line_end = op.get('line_end', line)
                print(f"    - Delete lines {line}-{line_end}")
            elif op_type == 'insert':
                content_preview = op.get('content', '')[:50]
                if len(op.get('content', '')) > 50:
                    content_preview += '...'
                print(f"    - Insert at line {line}: {repr(content_preview)}")
        print()

    # Estimate time
    wpm = config.get('base_wpm', 85)
    chars_per_min = wpm * 5  # ~5 chars per word
    estimated_mins = total_chars / chars_per_min if chars_per_min > 0 else 0

    print("=" * 60)
    print(f"Total operations: {total_ops}")
    print(f"Total characters: {total_chars}")
    print(f"Estimated time: {estimated_mins:.1f} minutes")
    print("=" * 60)


def run_replay(session_path: Path, project_dir: Path):
    """Execute the replay session."""
    print("=" * 60)
    print("PROJECT MASK - Code Replay")
    print("=" * 60)
    print()
    print(f"Session: {session_path.name}")
    print(f"Project: {project_dir}")
    print()

    # Create components
    backend = create_backend()
    print(f"Input backend: {backend.__class__.__name__}")

    controller = VSCodeController(backend, project_root=str(project_dir))
    engine = ReplayEngine(controller)

    # Load session
    session = engine.load_session(str(session_path))
    print(f"Loaded: {session.session_id}")
    print(f"Files to modify: {len(session.files)}")
    print()

    # Open VS Code
    print("Opening VS Code...")
    subprocess.Popen(['code', str(project_dir)],
                     stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    time.sleep(3)

    # Confirm
    print("-" * 40)
    print("Ready to replay. Make sure:")
    print("  1. Upwork time tracker is running (clocked in)")
    print("  2. VS Code is visible on screen")
    print("-" * 40)

    response = input("\nPress Enter to start (or 'q' to quit): ")
    if response.lower() == 'q':
        print("Aborted.")
        return False

    # Focus VS Code
    print("\nFocusing VS Code...")
    try:
        controller.focus_window()
        time.sleep(0.5)
    except Exception as e:
        print(f"Warning: Could not auto-focus VS Code: {e}")
        input("Please click on VS Code, then press Enter...")

    # Progress callback
    def on_progress(event: str, data: dict):
        if event == 'file_start':
            print(f"\n>>> Opening: {data.get('path')}")
        elif event == 'operation':
            op_type = data.get('type', '?')
            line = data.get('line', '?')
            if op_type == 'insert':
                chars = len(data.get('content', ''))
                print(f"    [{op_type}] line {line} ({chars} chars)")
            else:
                print(f"    [{op_type}] line {line}")
        elif event == 'file_complete':
            print(f"    Saved: {data.get('path')}")

    # Execute
    print("\nStarting replay...")
    print("(Press Ctrl+C to abort)\n")

    try:
        engine.execute(session, progress_callback=on_progress)
        print("\n" + "=" * 60)
        print("REPLAY COMPLETE!")
        print("=" * 60)
        print("\nRemember to clock out of Upwork when done.")
        return True
    except KeyboardInterrupt:
        print("\n\nReplay interrupted by user.")
        print("Your progress has been saved in VS Code.")
        return False
    except Exception as e:
        print(f"\n\nReplay error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Replay git diff sessions in VS Code',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mask-replay session.json              # Replay a session
  mask-replay session.json --dry-run    # Preview without typing
  mask-replay --list                    # List available sessions
  mask-replay --list --dir ~/project    # List sessions in specific dir
        """
    )

    parser.add_argument('session', nargs='?', help='Session JSON file to replay')
    parser.add_argument('--list', '-l', action='store_true',
                        help='List available session files')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Preview session without executing')
    parser.add_argument('--dir', '-d', type=Path, default=Path('.'),
                        help='Project directory (default: current)')
    parser.add_argument('--replay-dir', type=Path,
                        help='Directory containing session files (default: .replay/)')

    args = parser.parse_args()

    # Resolve directories
    project_dir = args.dir.resolve()
    replay_dir = args.replay_dir or (project_dir / '.replay')

    # List mode
    if args.list:
        list_sessions(replay_dir)
        return 0

    # Need a session file
    if not args.session:
        parser.print_help()
        return 1

    # Resolve session path
    session_path = Path(args.session)
    if not session_path.is_absolute():
        # Try relative to replay_dir first
        if (replay_dir / session_path).exists():
            session_path = replay_dir / session_path
        elif (replay_dir / f"{session_path}.json").exists():
            session_path = replay_dir / f"{session_path}.json"
        else:
            session_path = session_path.resolve()

    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}")
        return 1

    # Dry run mode
    if args.dry_run:
        preview_session(session_path)
        return 0

    # Check environment
    errors = check_environment()
    if errors:
        print("Environment check failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    # Run replay
    success = run_replay(session_path, project_dir)
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
