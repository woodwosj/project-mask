#!/usr/bin/env python3
"""Interactive calibration tool for Upwork UI coordinates.

This script guides you through recording the positions of Upwork UI elements
so that the automation can interact with them correctly.

Usage:
    python scripts/calibrate_upwork.py

Make sure Upwork is open and visible before running this script.
"""

import os
import sys

# Add project root to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_DIR)


def main():
    """Run the Upwork calibration tool."""
    print("=" * 60)
    print("PROJECT MASK - Upwork UI Calibration Tool")
    print("=" * 60)
    print()

    # Check for X11
    session_type = os.environ.get('XDG_SESSION_TYPE', 'unknown')
    if session_type == 'wayland':
        print("Warning: Wayland detected. This tool works best with X11.")
        print()

    # Import modules
    try:
        from replay.input_backend import XdotoolBackend
        from upwork.upwork_controller import UpworkCalibrator
    except ImportError as e:
        print(f"Error importing modules: {e}")
        print("Make sure you've installed the package: pip install -e .")
        return 1

    # Check xdotool
    try:
        backend = XdotoolBackend(check_display=False)
    except Exception as e:
        print(f"Error initializing input backend: {e}")
        print("Make sure xdotool is installed: sudo apt install xdotool")
        return 1

    # Instructions
    print("This tool will help you record the positions of Upwork UI elements.")
    print()
    print("Before starting:")
    print("1. Open Upwork in your browser (or desktop app)")
    print("2. Navigate to the time tracker page")
    print("3. Make sure the Upwork window is fully visible")
    print()
    print("During calibration:")
    print("- You'll be asked to position your mouse over each UI element")
    print("- Press Enter, then click on the element")
    print("- The position will be recorded")
    print()

    response = input("Ready to start? (y/n): ")
    if response.lower() != 'y':
        print("Calibration cancelled.")
        return 0

    # Run calibration
    calibrator = UpworkCalibrator(backend)

    try:
        coordinates = calibrator.run()
    except KeyboardInterrupt:
        print("\nCalibration interrupted.")
        return 1

    # Show results
    print()
    print("=" * 60)
    print("Calibration Results")
    print("=" * 60)
    print()

    coords_dict = coordinates.to_dict()
    for key, value in coords_dict.items():
        if isinstance(value, dict):
            if 'x' in value and 'y' in value:
                print(f"  {key}: ({value['x']}, {value['y']})")
            elif 'width' in value:
                print(f"  {key}: {value['width']}x{value['height']}")
        else:
            print(f"  {key}: {value}")

    # Save option
    print()
    response = input("Save calibration to config file? (y/n): ")

    if response.lower() == 'y':
        config_path = os.path.join(PROJECT_DIR, 'config', 'default.yaml')

        # Check if file exists
        if os.path.exists(config_path):
            backup_response = input(f"Config file exists. Create backup? (y/n): ")
            if backup_response.lower() == 'y':
                import shutil
                backup_path = config_path + '.backup'
                shutil.copy(config_path, backup_path)
                print(f"Backup created: {backup_path}")

        # Save coordinates
        if calibrator.save_to_config(config_path, coordinates):
            print(f"\nCalibration saved to: {config_path}")
        else:
            print("\nFailed to save calibration.")

            # Offer to print YAML snippet
            print("\nYou can manually add this to your config file:")
            print()
            print("upwork:")
            print("  coordinates:")
            for key, value in coords_dict.items():
                if isinstance(value, dict):
                    print(f"    {key}:")
                    for k, v in value.items():
                        print(f"      {k}: {v}")
    else:
        # Print YAML snippet for manual addition
        print("\nTo use these coordinates, add the following to your config file:")
        print()
        print("upwork:")
        print("  coordinates:")
        for key, value in coords_dict.items():
            if isinstance(value, dict):
                print(f"    {key}:")
                for k, v in value.items():
                    print(f"      {k}: {v}")

    print()
    print("Calibration complete!")
    print()
    print("Next steps:")
    print("1. Test the automation with a test contract")
    print("2. Adjust coordinates if clicking is off-target")
    print("3. Re-calibrate if you change screen resolution")

    return 0


if __name__ == '__main__':
    sys.exit(main())
