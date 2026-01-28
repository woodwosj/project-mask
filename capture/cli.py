#!/usr/bin/env python3
"""Command-line interface for PROJECT MASK capture tool.

Usage:
    mask-capture --commit HEAD --contract "ClientName" --memo "Description"
    mask-capture --commit HEAD~3..HEAD --contract "ClientName" --memo "Multiple features"
    mask-capture --commit HEAD --contract "ClientName" --memo "Work" --output ./session.json
    mask-capture --commit HEAD --contract "ClientName" --memo "Work" --dry-run
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from capture.capture_tool import (
    CaptureError,
    DiffParser,
    DiffParseError,
    GitError,
    SessionBuilder,
    generate_session,
    is_git_repository,
    get_repo_root,
    parse_commit,
    parse_commit_range,
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)


def setup_argparser() -> argparse.ArgumentParser:
    """Set up the argument parser.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        prog='mask-capture',
        description='Capture git changes and generate replay session JSON.',
        epilog='Example: mask-capture --commit HEAD --contract "ClientName" --memo "Feature work"',
    )

    parser.add_argument(
        '--commit', '-c',
        required=True,
        help='Git commit reference (e.g., HEAD, abc1234, HEAD~3..HEAD)',
    )

    parser.add_argument(
        '--contract', '-C',
        required=True,
        help='Upwork contract name/identifier',
    )

    parser.add_argument(
        '--memo', '-m',
        required=True,
        help='Work description for time tracking',
    )

    parser.add_argument(
        '--output', '-o',
        help='Output file path (default: .replay/session_<timestamp>.json)',
    )

    parser.add_argument(
        '--repo', '-r',
        help='Path to git repository (default: current directory)',
    )

    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Generate session but only print to stdout, do not write file',
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output',
    )

    parser.add_argument(
        '--wpm',
        type=int,
        help='Override base typing speed (WPM)',
    )

    parser.add_argument(
        '--typo-prob',
        type=float,
        help='Override typo probability (0.0-1.0)',
    )

    parser.add_argument(
        '--no-pauses',
        action='store_true',
        help='Disable thinking pauses during replay',
    )

    return parser


def get_output_path(
    args: argparse.Namespace,
    repo_root: Optional[str],
) -> Path:
    """Determine the output file path.

    Args:
        args: Parsed command-line arguments.
        repo_root: Git repository root path.

    Returns:
        Output file path.
    """
    if args.output:
        return Path(args.output)

    # Default to .replay directory in repo root
    base_dir = Path(repo_root) if repo_root else Path.cwd()
    replay_dir = base_dir / '.replay'

    # Generate filename with timestamp
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    filename = f'session_{timestamp}.json'

    return replay_dir / filename


def ensure_output_directory(output_path: Path) -> None:
    """Ensure the output directory exists.

    Args:
        output_path: Path to output file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)


def build_replay_config(args: argparse.Namespace) -> Optional[dict]:
    """Build replay configuration from command-line arguments.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Replay configuration dictionary or None if no overrides.
    """
    config = {}

    if args.wpm is not None:
        if args.wpm < 1 or args.wpm > 300:
            logger.warning(f"Unusual WPM value: {args.wpm}")
        config['base_wpm'] = args.wpm

    if args.typo_prob is not None:
        if not 0 <= args.typo_prob <= 1:
            raise ValueError(f"typo-prob must be between 0 and 1, got {args.typo_prob}")
        config['typo_probability'] = args.typo_prob

    if args.no_pauses:
        config['thinking_pauses'] = False

    return config if config else None


def print_summary(session: dict, warnings: list) -> None:
    """Print a summary of the captured session.

    Args:
        session: Generated session dictionary.
        warnings: List of warnings from parsing.
    """
    files = session.get('files', [])
    total_ops = sum(len(f.get('operations', [])) for f in files)

    print(f"\nSession Summary:")
    print(f"  Session ID: {session.get('session_id')}")
    print(f"  Contract: {session.get('contract_id')}")
    print(f"  Memo: {session.get('memo')}")
    print(f"  Files: {len(files)}")
    print(f"  Operations: {total_ops}")

    if warnings:
        print(f"\nWarnings:")
        for warning in warnings:
            print(f"  - {warning}")

    # Show file details in verbose mode
    if files:
        print(f"\nFiles changed:")
        for file_entry in files:
            path = file_entry.get('path')
            ops = file_entry.get('operations', [])
            inserts = sum(1 for o in ops if o.get('type') == 'insert')
            deletes = sum(1 for o in ops if o.get('type') == 'delete')
            print(f"  {path}: +{inserts} -{deletes}")


def main(argv: Optional[list] = None) -> int:
    """Main entry point for the CLI.

    Args:
        argv: Command-line arguments (default: sys.argv[1:]).

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    parser = setup_argparser()
    args = parser.parse_args(argv)

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Determine repository path
    repo_path = args.repo or os.getcwd()

    # Validate git repository
    if not is_git_repository(repo_path):
        print(f"Error: Not a git repository: {repo_path}", file=sys.stderr)
        return 1

    repo_root = get_repo_root(repo_path)
    logger.debug(f"Repository root: {repo_root}")

    try:
        # Get the diff
        commit_ref = args.commit
        logger.info(f"Capturing changes from: {commit_ref}")

        if '..' in commit_ref:
            diff_text = parse_commit_range(commit_ref, repo_path)
        else:
            diff_text = parse_commit(commit_ref, repo_path)

        if not diff_text.strip():
            print("No changes found in the specified commit(s).", file=sys.stderr)
            return 1

        # Parse the diff
        parser_obj = DiffParser()
        file_changes = parser_obj.parse_diff_text(diff_text)
        warnings = parser_obj.warnings

        if not file_changes:
            print("No file changes to capture.", file=sys.stderr)
            if warnings:
                for warning in warnings:
                    print(f"Warning: {warning}", file=sys.stderr)
            return 1

        # Build replay config from args
        replay_config = build_replay_config(args)

        # Build the session
        builder = SessionBuilder()
        session = builder.build_session(
            file_changes=file_changes,
            contract_id=args.contract,
            memo=args.memo,
            replay_config=replay_config,
        )

        # Validate the session
        errors = builder.validate_session(session)
        if errors:
            print("Session validation errors:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return 1

        # Convert to JSON
        session_json = builder.to_json(session)

        # Print summary
        print_summary(session, warnings)

        # Handle dry run
        if args.dry_run:
            print("\n--- Session JSON (dry run) ---")
            print(session_json)
            return 0

        # Write to file
        output_path = get_output_path(args, repo_root)
        ensure_output_directory(output_path)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(session_json)

        print(f"\nSession written to: {output_path}")
        return 0

    except GitError as e:
        print(f"Git error: {e}", file=sys.stderr)
        return 1
    except DiffParseError as e:
        print(f"Diff parse error: {e}", file=sys.stderr)
        return 1
    except CaptureError as e:
        print(f"Capture error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Invalid argument: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 130
    except Exception as e:
        logger.exception("Unexpected error")
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
