#!/usr/bin/env python3
"""Run replay with AI intervention enabled."""

import sys
import os
import time
import subprocess
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from replay.input_backend import create_backend
from replay.vscode_controller import VSCodeController
from replay.replay_engine import ReplayEngine

from intervention import (
    InterventionOrchestrator, InterventionConfig,
    ClaudeAnalyzer, create_screenshot_backend, RecoveryExecutor,
    remediate_after_replay,
)


def main():
    print("=" * 60)
    print("PROJECT MASK - Replay with AI Intervention")
    print("=" * 60)
    print()

    # Get project dir from args or use default
    if len(sys.argv) > 1:
        project_dir = Path(sys.argv[1]).resolve()
    else:
        project_dir = PROJECT_ROOT

    # Get session path
    if len(sys.argv) > 2:
        session_path = Path(sys.argv[2])
    else:
        session_path = project_dir / '.replay' / 'fast_calc.json'

    print(f"Project: {project_dir}")
    print(f"Session: {session_path}")
    print()

    # Create replay components
    backend = create_backend()
    print(f"Input backend: {backend.__class__.__name__}")

    controller = VSCodeController(backend, project_root=project_dir)

    # Create intervention components
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)
    print(f"API key present: Yes")

    screenshot_backend = create_screenshot_backend({
        'intervention': {'screenshot_backend': 'scrot'}
    })
    print(f"Screenshot backend: {screenshot_backend.__class__.__name__}")

    analyzer = ClaudeAnalyzer(api_key=api_key)
    print(f"Analyzer model: {analyzer.model}")

    recovery = RecoveryExecutor(backend, controller)
    print("Recovery executor ready")

    # Configure intervention - check every 30 seconds for this test
    config = InterventionConfig(
        enabled=True,
        interval_seconds=30,
        confidence_threshold=0.8,
        max_retries=3,
        min_cooldown_seconds=10,
    )

    orchestrator = InterventionOrchestrator(
        config=config,
        screenshot_backend=screenshot_backend,
        analyzer=analyzer,
        recovery_executor=recovery,
    )
    print("Intervention orchestrator ready")
    print()

    # Create engine with intervention
    engine = ReplayEngine(
        vscode_controller=controller,
        project_root=project_dir,
        intervention_orchestrator=orchestrator,
    )

    # Load session
    session = engine.load_session(str(session_path))
    print(f"Loaded session: {session.session_id}")
    print(f"Files: {len(session.files)}")
    print()

    # Kill any existing VS Code instances to ensure clean state
    print("Closing any existing VS Code instances...")
    subprocess.run(['pkill', '-f', 'code'], capture_output=True)
    time.sleep(2)

    # Open VS Code with the project folder in a new window
    print("Opening VS Code...")
    subprocess.Popen(
        ['code', '--new-window', str(project_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(5)  # More time for VS Code to fully start

    # Focus VS Code
    print("Focusing VS Code...")
    controller.focus_window()
    time.sleep(1)

    def on_progress(msg, current, total):
        pct = (current / total * 100) if total > 0 else 0
        print(f"  [{current}/{total}] ({pct:.0f}%) {msg}")

    print()
    print("Starting replay with AI intervention...")
    print("(Intervention will check every 30 seconds)")
    print()

    try:
        engine.execute(session, progress_callback=on_progress)
        print()
        print("=" * 60)
        print("REPLAY COMPLETE - Starting verification...")
        print("=" * 60)

        # Post-replay verification and remediation
        print()
        print("Verifying and remediating files...")
        remediation_result = remediate_after_replay(
            session=session,
            vscode_controller=controller,
            workspace_root=project_dir,
        )

        print()
        print("Remediation Summary:")
        print(f"  Files OK:        {remediation_result.files_ok}")
        print(f"  Files fixed:     {remediation_result.files_remediated}")
        print(f"  Files failed:    {remediation_result.files_failed}")

        for result in remediation_result.results:
            status = "✓" if result.success else "✗"
            if result.attempts > 0:
                print(f"  {status} {result.file_path}: "
                      f"{result.original_similarity:.1%} → {result.final_similarity:.1%} "
                      f"({result.attempts} attempts)")
            else:
                print(f"  {status} {result.file_path}: {result.final_similarity:.1%}")

        if remediation_result.files_failed == 0:
            print()
            print("=" * 60)
            print("ALL FILES VERIFIED OK!")
            print("=" * 60)
        else:
            print()
            print("=" * 60)
            print(f"WARNING: {remediation_result.files_failed} files could not be fixed")
            print("=" * 60)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    # Show intervention stats
    stats = orchestrator.get_statistics()
    print()
    print("Intervention Statistics:")
    print(f"  Total checks: {stats['total_checks']}")
    print(f"  Interventions: {stats['intervention_count']}")
    print(f"  Success rate: {stats['recovery_success_rate']:.0%}")


if __name__ == '__main__':
    main()
