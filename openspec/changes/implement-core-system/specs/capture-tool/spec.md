# Capture Tool Specification

## ADDED Requirements

### Requirement: Git Diff Parsing

The system SHALL parse unified diff format from git to extract change information.

The parser MUST:
- Accept unified diff output from `git diff` or `git show`
- Extract file paths (source and target)
- Identify added, removed, and modified files
- Parse hunks with line numbers and content
- Support binary file detection (skip with warning)

#### Scenario: Parse file addition

- **WHEN** parsing a diff that adds a new file
- **THEN** the file SHALL be marked as `is_added_file`
- **AND** all lines SHALL be treated as insertions
- **AND** operations SHALL start at line 1

#### Scenario: Parse file deletion

- **WHEN** parsing a diff that removes a file
- **THEN** the file SHALL be marked as `is_removed_file`
- **AND** the file SHALL be skipped (no replay operations generated)
- **AND** a warning SHALL be logged

#### Scenario: Parse file modification

- **WHEN** parsing a diff that modifies an existing file
- **THEN** both additions and deletions SHALL be extracted
- **AND** line numbers SHALL correspond to the target file state

#### Scenario: Parse multi-hunk changes

- **WHEN** a file has multiple non-contiguous changes
- **THEN** each hunk SHALL generate separate operations
- **AND** operations SHALL be ordered by line number

#### Scenario: Handle binary files

- **WHEN** a binary file is detected in the diff
- **THEN** the file SHALL be skipped
- **AND** a warning SHALL be logged indicating binary files are not supported

---

### Requirement: Operation Builder

The system SHALL convert parsed diff hunks into replay operations.

#### Scenario: Build navigate operation

- **WHEN** moving to a new line position for editing
- **THEN** a navigate operation SHALL be generated
- **AND** `line` SHALL specify the target line number

#### Scenario: Build delete operation

- **WHEN** lines are removed from the file
- **THEN** a delete operation SHALL be generated
- **AND** `line` SHALL specify the start line
- **AND** `line_end` SHALL specify the end line (inclusive)

#### Scenario: Build insert operation

- **WHEN** lines are added to the file
- **THEN** an insert operation SHALL be generated
- **AND** `line` SHALL specify the insertion point
- **AND** `content` SHALL contain the text to insert (with newlines)

#### Scenario: Combine adjacent additions

- **WHEN** multiple consecutive lines are added
- **THEN** they SHALL be combined into a single insert operation
- **AND** `content` SHALL contain all lines with proper line breaks

#### Scenario: Handle mixed hunks

- **WHEN** a hunk contains both deletions and additions
- **THEN** delete operations SHALL be generated first
- **AND** insert operations SHALL follow
- **AND** line numbers SHALL be adjusted for the intended final state

---

### Requirement: Session Builder

The system SHALL build complete replay session JSON from parsed operations.

#### Scenario: Generate session structure

- **WHEN** `build_session(diff, contract_id, memo)` is called
- **THEN** a complete session JSON SHALL be generated
- **AND** `session_id` SHALL be auto-generated (timestamp-based)
- **AND** `contract_id` and `memo` SHALL be set from parameters

#### Scenario: Session ID format

- **WHEN** generating a session ID
- **THEN** the format SHALL be `session_YYYYMMDD_HHMMSS`
- **AND** the timestamp SHALL be in UTC

#### Scenario: Include default replay config

- **WHEN** no replay config is specified
- **THEN** `replay_config` SHALL be included with default values:
  - `base_wpm`: 85
  - `typo_probability`: 0.02
  - `thinking_pause_probability`: 0.10

#### Scenario: Order files by path

- **WHEN** the diff contains multiple files
- **THEN** files SHALL be ordered alphabetically by path
- **AND** this provides consistent replay order

---

### Requirement: Command-Line Interface

The system SHALL provide a CLI for capturing git changes.

CLI command format:
```
mask-capture --commit <ref> --contract <name> --memo <description> [--output <file>]
```

#### Scenario: Capture single commit

- **WHEN** `mask-capture --commit HEAD --contract "ClientName" --memo "Feature work"` is executed
- **THEN** `git show HEAD --unified=3` SHALL be run
- **AND** the diff SHALL be parsed
- **AND** a session JSON SHALL be generated
- **AND** output SHALL be written to `.replay/session_<timestamp>.json`

#### Scenario: Capture commit range

- **WHEN** `mask-capture --commit HEAD~3..HEAD --contract "ClientName" --memo "Multiple features"` is executed
- **THEN** `git diff HEAD~3..HEAD` SHALL be run
- **AND** all changes in the range SHALL be captured
- **AND** a single session SHALL be generated

#### Scenario: Specify output file

- **WHEN** `--output /path/to/output.json` is provided
- **THEN** the session SHALL be written to the specified path
- **AND** parent directories SHALL be created if needed

#### Scenario: Default output location

- **WHEN** `--output` is not provided
- **THEN** output SHALL be written to `.replay/` directory
- **AND** the directory SHALL be created if it doesn't exist
- **AND** filename SHALL be `session_<timestamp>.json`

#### Scenario: Validate git repository

- **WHEN** the command is run outside a git repository
- **THEN** an error SHALL be displayed: "Not a git repository"
- **AND** exit code SHALL be non-zero

#### Scenario: Validate commit reference

- **WHEN** an invalid commit reference is provided
- **THEN** an error SHALL be displayed: "Invalid commit reference: <ref>"
- **AND** exit code SHALL be non-zero

#### Scenario: Display help

- **WHEN** `mask-capture --help` is executed
- **THEN** usage information SHALL be displayed
- **AND** all options SHALL be documented

---

### Requirement: Output Validation

The system SHALL validate generated session JSON before output.

#### Scenario: Validate JSON structure

- **WHEN** a session is generated
- **THEN** the JSON SHALL be validated against the schema
- **AND** all required fields SHALL be present

#### Scenario: Validate file paths

- **WHEN** file operations are generated
- **THEN** file paths SHALL be normalized (no `..` or `.`)
- **AND** absolute paths SHALL be rejected with a warning

#### Scenario: Validate line numbers

- **WHEN** operations are generated
- **THEN** line numbers SHALL be positive integers
- **AND** `line_end` SHALL be >= `line` for delete operations

---

### Requirement: Logging and Diagnostics

The system SHALL provide logging for debugging and verification.

#### Scenario: Log parsed diff summary

- **WHEN** a diff is parsed
- **THEN** a summary SHALL be logged:
  - Number of files changed
  - Total lines added/removed
  - Any warnings (binary files, errors)

#### Scenario: Verbose mode

- **WHEN** `--verbose` flag is provided
- **THEN** detailed operation generation SHALL be logged
- **AND** each file and operation SHALL be listed

#### Scenario: Dry run mode

- **WHEN** `--dry-run` flag is provided
- **THEN** the session SHALL be generated but not written
- **AND** the session JSON SHALL be printed to stdout
- **AND** exit code SHALL be 0 if valid
