#!/usr/bin/env python3
"""Test script for verifying xdotool input backend functionality.

This script performs basic input tests to verify that xdotool
is working correctly on the system.

Usage:
    python scripts/test_input.py

The script will open a test window and perform typing tests.
"""

import os
import sys
import time

# Add project root to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_DIR)


def check_display_server():
    """Check the current display server."""
    session_type = os.environ.get('XDG_SESSION_TYPE', 'unknown')
    display = os.environ.get('DISPLAY', 'not set')

    print(f"Display server: {session_type}")
    print(f"DISPLAY: {display}")

    if session_type == 'wayland':
        print("\nWarning: Wayland detected. xdotool may not work correctly.")
        print("Consider switching to an X11 session.")
        return False

    return True


def check_xdotool():
    """Check if xdotool is available."""
    import subprocess

    try:
        result = subprocess.run(
            ['xdotool', 'version'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        print(f"xdotool version: {result.stdout.strip()}")
        return True
    except FileNotFoundError:
        print("Error: xdotool not found!")
        print("Install with: sudo apt install xdotool")
        return False
    except subprocess.TimeoutExpired:
        print("Error: xdotool timed out")
        return False


def test_basic_typing():
    """Test basic text typing."""
    from replay.input_backend import XdotoolBackend, InputBackendError

    print("\n=== Basic Typing Test ===")
    print("A text editor window will open. The test will type some text.")
    print("Press Ctrl+C to abort.")

    input("\nPress Enter to start the test...")

    # Open a simple text editor
    import subprocess
    editor_process = None

    try:
        # Try to open a text editor
        editors = ['gedit', 'xed', 'pluma', 'leafpad', 'mousepad', 'kate', 'kwrite']
        for editor in editors:
            try:
                editor_process = subprocess.Popen(
                    [editor],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                print(f"Opened {editor}")
                break
            except FileNotFoundError:
                continue

        if editor_process is None:
            print("No text editor found. Please open a text editor manually.")
            input("Press Enter when a text editor is focused...")
        else:
            print("Waiting for editor to open...")
            time.sleep(2)

        # Create backend and test typing
        backend = XdotoolBackend(check_display=False)

        test_text = "Hello, World! This is a test of PROJECT MASK input backend."
        print(f"\nTyping: {test_text}")

        backend.type_text(test_text, delay=0.05)

        print("\nTyping complete!")

        # Test key presses
        print("\nTesting key presses...")
        time.sleep(0.5)
        backend.key_press('Return')
        backend.type_text("New line after Enter key.", delay=0.05)

        # Test key combo
        print("Testing key combo (Ctrl+A to select all)...")
        time.sleep(0.5)
        backend.key_combo('ctrl', 'a')

        print("\nAll basic tests passed!")
        return True

    except InputBackendError as e:
        print(f"\nInput backend error: {e}")
        return False
    except KeyboardInterrupt:
        print("\nTest aborted.")
        return False
    finally:
        if editor_process:
            print("\nClosing editor...")
            editor_process.terminate()


def test_mouse():
    """Test mouse movement and clicking."""
    from replay.input_backend import XdotoolBackend, InputBackendError

    print("\n=== Mouse Test ===")
    print("The mouse cursor will move around the screen.")

    input("\nPress Enter to start the mouse test...")

    try:
        backend = XdotoolBackend(check_display=False)

        # Get current position
        import subprocess
        result = subprocess.run(
            ['xdotool', 'getmouselocation'],
            capture_output=True,
            text=True,
        )
        print(f"Current position: {result.stdout.strip()}")

        # Move to different positions
        positions = [(100, 100), (500, 300), (300, 500), (100, 100)]

        for x, y in positions:
            print(f"Moving to ({x}, {y})...")
            backend.mouse_move(x, y)
            time.sleep(0.5)

        print("\nMouse test complete!")
        return True

    except InputBackendError as e:
        print(f"\nMouse test error: {e}")
        return False
    except KeyboardInterrupt:
        print("\nTest aborted.")
        return False


def test_window_management():
    """Test window finding and focusing."""
    from replay.input_backend import XdotoolBackend

    print("\n=== Window Management Test ===")

    try:
        backend = XdotoolBackend(check_display=False)

        # Get active window
        window_id = backend.get_active_window()
        window_name = backend.get_active_window_name()

        print(f"Active window ID: {window_id}")
        print(f"Active window name: {window_name}")

        # Search for a window
        print("\nSearching for 'Terminal' window...")
        terminal_id = backend.search_window('Terminal')
        if terminal_id:
            print(f"Found terminal window: {terminal_id}")
        else:
            print("No terminal window found (this is OK)")

        print("\nWindow management test complete!")
        return True

    except Exception as e:
        print(f"\nWindow test error: {e}")
        return False


def test_vscode_controller():
    """Test VS Code controller if VS Code is running."""
    from replay.input_backend import XdotoolBackend
    from replay.vscode_controller import VSCodeController, VSCodeNotFoundError

    print("\n=== VS Code Controller Test ===")

    try:
        backend = XdotoolBackend(check_display=False)
        controller = VSCodeController(backend, {})

        # Try to find VS Code
        window_id = controller.find_vscode_window()

        if window_id:
            print(f"Found VS Code window: {window_id}")

            response = input("\nWould you like to test typing in VS Code? (y/n): ")
            if response.lower() == 'y':
                print("Focusing VS Code...")
                controller.focus_window()
                time.sleep(0.5)

                print("Opening new file (Ctrl+N)...")
                backend.key_combo('ctrl', 'n')
                time.sleep(0.5)

                print("Typing test code...")
                controller.type_code(
                    "# This is a test\ndef hello():\n    print('Hello, World!')\n",
                    wpm=60,
                    typo_probability=0.02,
                )

                print("\nVS Code test complete!")
        else:
            print("VS Code is not running.")
            print("Start VS Code to test the VS Code controller.")

        return True

    except VSCodeNotFoundError as e:
        print(f"VS Code not found: {e}")
        return True  # Not a failure, just not available
    except Exception as e:
        print(f"\nVS Code test error: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("PROJECT MASK - Input Backend Test Suite")
    print("=" * 60)

    # Check environment
    if not check_display_server():
        print("\nContinuing anyway, but tests may fail on Wayland.")

    print("")

    if not check_xdotool():
        return 1

    # Run tests
    tests = [
        ("Basic Typing", test_basic_typing),
        ("Mouse Movement", test_mouse),
        ("Window Management", test_window_management),
        ("VS Code Controller", test_vscode_controller),
    ]

    results = []

    for name, test_func in tests:
        print(f"\n{'=' * 60}")
        response = input(f"Run {name} test? (y/n/q to quit): ")

        if response.lower() == 'q':
            break
        elif response.lower() == 'y':
            success = test_func()
            results.append((name, success))
        else:
            results.append((name, None))  # Skipped

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for name, result in results:
        if result is None:
            status = "SKIPPED"
        elif result:
            status = "PASSED"
        else:
            status = "FAILED"
        print(f"  {name}: {status}")

    failed = sum(1 for _, r in results if r is False)
    return 1 if failed > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
