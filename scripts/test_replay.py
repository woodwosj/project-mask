#!/usr/bin/env python3
"""
Test script for PROJECT MASK replay system.

This script tests the replay engine without Upwork integration.
It will:
1. Open VS Code with the test project
2. Execute a test session (typing simulation)
3. Report results

Usage:
    python scripts/test_replay.py [session_file]

Examples:
    python scripts/test_replay.py                           # Run test_session_001
    python scripts/test_replay.py .replay/test_session_002_multifile.json
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from replay.input_backend import XdotoolBackend, create_backend
from replay.vscode_controller import VSCodeController
from replay.replay_engine import ReplayEngine, ReplaySession


def print_banner():
    print("=" * 60)
    print("PROJECT MASK - Replay Test")
    print("=" * 60)
    print()


def check_display():
    """Check if we have a display available."""
    display = os.environ.get('DISPLAY')
    if not display:
        print("ERROR: No DISPLAY environment variable set.")
        print("Run this script from a desktop session (X11).")
        return False
    print(f"Display: {display}")

    session_type = os.environ.get('XDG_SESSION_TYPE', 'unknown')
    print(f"Session type: {session_type}")

    if session_type == 'wayland':
        print("WARNING: Wayland detected. xdotool works best with X11.")
        print("Consider running: export XDG_SESSION_TYPE=x11")

    return True


def check_xdotool():
    """Check if xdotool is available."""
    try:
        result = subprocess.run(['xdotool', 'version'], capture_output=True, text=True)
        print(f"xdotool: {result.stdout.strip()}")
        return True
    except FileNotFoundError:
        print("ERROR: xdotool not found. Install with: sudo apt install xdotool")
        return False


def check_vscode():
    """Check if VS Code is installed."""
    try:
        result = subprocess.run(['code', '--version'], capture_output=True, text=True)
        version = result.stdout.strip().split('\n')[0]
        print(f"VS Code: {version}")
        return True
    except FileNotFoundError:
        print("ERROR: VS Code not found. Install from https://code.visualstudio.com/")
        return False


def open_vscode_with_project(project_path: Path):
    """Open VS Code with the test project."""
    print(f"\nOpening VS Code with: {project_path}")
    subprocess.Popen(['code', str(project_path)],
                     stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    print("Waiting for VS Code to start...")
    time.sleep(3)


def progress_callback(event: str, data: dict):
    """Callback for replay progress updates."""
    if event == 'session_start':
        print(f"\n>>> Starting session: {data.get('session_id')}")
    elif event == 'file_start':
        print(f"  File: {data.get('path')}")
    elif event == 'operation':
        op_type = data.get('type', 'unknown')
        line = data.get('line', '?')
        print(f"    [{op_type}] line {line}")
    elif event == 'file_complete':
        print(f"  Completed: {data.get('path')}")
    elif event == 'session_complete':
        print(f"\n>>> Session complete!")


def run_test(session_path: Path, project_path: Path):
    """Run the replay test."""
    print(f"\nLoading session: {session_path}")

    # Create components
    backend = create_backend()
    print(f"Input backend: {backend.__class__.__name__}")

    controller = VSCodeController(backend, project_root=str(project_path))
    engine = ReplayEngine(controller)

    # Load session
    session = engine.load_session(str(session_path))
    print(f"Session ID: {session.session_id}")
    print(f"Contract: {session.contract_id}")
    print(f"Memo: {session.memo}")
    print(f"Files: {len(session.files)}")

    # Confirm before running
    print("\n" + "-" * 40)
    print("The replay will now type code into VS Code.")
    print("Make sure VS Code is focused and ready.")
    print("-" * 40)

    response = input("\nPress Enter to start replay (or 'q' to quit): ")
    if response.lower() == 'q':
        print("Aborted.")
        return False

    # Focus VS Code
    print("\nFocusing VS Code window...")
    try:
        controller.focus_window()
        time.sleep(0.5)
    except Exception as e:
        print(f"Warning: Could not focus VS Code: {e}")
        print("Please manually focus VS Code window.")
        input("Press Enter when VS Code is focused...")

    # Execute replay
    print("\nExecuting replay...")
    try:
        engine.execute(session, progress_callback=progress_callback)
        print("\n" + "=" * 40)
        print("REPLAY SUCCESSFUL!")
        print("=" * 40)
        return True
    except KeyboardInterrupt:
        print("\n\nReplay interrupted by user (Ctrl+C)")
        return False
    except Exception as e:
        print(f"\n\nReplay failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description='Test PROJECT MASK replay system')
    parser.add_argument('session', nargs='?',
                        default='.replay/test_session_001.json',
                        help='Path to session JSON file')
    parser.add_argument('--no-vscode', action='store_true',
                        help='Skip opening VS Code (assume already open)')
    parser.add_argument('--project', default='test_project',
                        help='Project directory to open in VS Code')
    args = parser.parse_args()

    print_banner()

    # Resolve paths
    session_path = PROJECT_ROOT / args.session
    project_path = PROJECT_ROOT / args.project

    if not session_path.exists():
        print(f"ERROR: Session file not found: {session_path}")
        sys.exit(1)

    if not project_path.exists():
        print(f"ERROR: Project directory not found: {project_path}")
        sys.exit(1)

    # Run checks
    print("Checking environment...\n")

    checks = [
        ("Display", check_display),
        ("xdotool", check_xdotool),
        ("VS Code", check_vscode),
    ]

    all_passed = True
    for name, check_fn in checks:
        if not check_fn():
            all_passed = False

    if not all_passed:
        print("\nSome checks failed. Fix the issues above and try again.")
        sys.exit(1)

    print("\nAll checks passed!")

    # Open VS Code
    if not args.no_vscode:
        open_vscode_with_project(project_path)

    # Run the test
    success = run_test(session_path, project_path)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
