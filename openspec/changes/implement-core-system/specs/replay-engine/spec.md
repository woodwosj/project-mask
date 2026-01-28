# Replay Engine Specification

## ADDED Requirements

### Requirement: Session Data Model

The system SHALL define data classes representing replay sessions and their operations.

The data model MUST include:
- `ReplaySession` - Top-level session container
- `FileOperation` - Individual file-level operations
- `OperationType` - Enumeration of operation types (navigate, delete, insert)

#### Scenario: Valid session structure

- **WHEN** a replay session JSON is loaded
- **THEN** it SHALL contain:
  - `session_id` (string) - Unique identifier
  - `contract_id` (string) - Upwork contract name
  - `memo` (string) - Work description
  - `files` (array) - List of file operations
  - `replay_config` (object, optional) - Override typing parameters

#### Scenario: Valid file operation structure

- **WHEN** a file entry in the session is parsed
- **THEN** it SHALL contain:
  - `path` (string) - Relative or absolute file path
  - `operations` (array) - List of operations for this file

#### Scenario: Valid operation structure

- **WHEN** an operation entry is parsed
- **THEN** it SHALL contain:
  - `type` (string) - One of "navigate", "delete", "insert"
  - `line` (integer) - Target line number
  - `line_end` (integer, optional) - End line for delete range
  - `content` (string, optional) - Text content for insert
  - `typing_style` (string, optional) - Override typing behavior

---

### Requirement: Session Loading and Validation

The system SHALL load replay sessions from JSON files with validation.

#### Scenario: Load valid session

- **WHEN** `load_session("/path/to/session.json")` is called
- **THEN** the JSON file SHALL be parsed
- **AND** a `ReplaySession` object SHALL be returned
- **AND** all required fields SHALL be validated

#### Scenario: Handle missing file

- **WHEN** the session file does not exist
- **THEN** `SessionNotFoundError` SHALL be raised
- **AND** the error message SHALL include the file path

#### Scenario: Handle malformed JSON

- **WHEN** the session file contains invalid JSON
- **THEN** `SessionParseError` SHALL be raised
- **AND** the error message SHALL include the parse error details

#### Scenario: Handle missing required fields

- **WHEN** the session JSON is missing required fields
- **THEN** `SessionValidationError` SHALL be raised
- **AND** the error message SHALL identify the missing fields

#### Scenario: Handle invalid operation type

- **WHEN** an operation has an unrecognized type
- **THEN** `SessionValidationError` SHALL be raised
- **AND** the error message SHALL identify the invalid operation

---

### Requirement: Operation Execution

The system SHALL execute file operations in sequence using the VS Code controller.

#### Scenario: Execute navigate operation

- **WHEN** an operation with `type: "navigate"` is executed
- **THEN** `vscode_controller.goto_line(line)` SHALL be called
- **AND** the cursor SHALL move to the specified line

#### Scenario: Execute delete operation

- **WHEN** an operation with `type: "delete"` is executed
- **THEN** `vscode_controller.delete_lines(line, line_end)` SHALL be called
- **AND** the specified lines SHALL be removed

#### Scenario: Execute insert operation

- **WHEN** an operation with `type: "insert"` is executed
- **THEN** the cursor SHALL move to the specified line
- **AND** `vscode_controller.type_code(content)` SHALL be called
- **AND** the content SHALL be typed with human-like simulation

#### Scenario: Execute operations in order

- **WHEN** a file has multiple operations
- **THEN** operations SHALL be executed in array order
- **AND** each operation SHALL complete before the next begins

#### Scenario: Handle file changes

- **WHEN** moving to a new file in the session
- **THEN** `vscode_controller.open_file(path)` SHALL be called first
- **AND** the system SHALL wait for the file to load
- **AND** then execute the file's operations

---

### Requirement: Thinking Pause Simulation

The system SHALL insert thinking pauses during replay to simulate developer cognition.

#### Scenario: Pause between files

- **WHEN** transitioning from one file to another
- **THEN** a thinking pause MAY be inserted
- **AND** the pause duration SHALL be 1-3 seconds

#### Scenario: Pause within file

- **WHEN** executing operations within a file
- **THEN** thinking pauses MAY be inserted according to probability
- **AND** the probability SHALL be configurable (default 10%)
- **AND** pause duration SHALL be 3-8 seconds

#### Scenario: Configure pause behavior

- **WHEN** `replay_config.thinking_pauses` is set to `false`
- **THEN** no thinking pauses SHALL be inserted during replay

---

### Requirement: Progress Reporting

The system SHALL report progress during session execution via callbacks.

The progress callback signature MUST be:
```python
Callable[[str, int, int], None]  # (message, current, total)
```

#### Scenario: Report operation progress

- **WHEN** an operation begins execution
- **THEN** the progress callback SHALL be called
- **AND** `message` SHALL describe the current operation
- **AND** `current` SHALL be the operation index (0-based)
- **AND** `total` SHALL be the total operation count

#### Scenario: Report file transitions

- **WHEN** opening a new file
- **THEN** the progress callback SHALL be called
- **AND** `message` SHALL include the file path

#### Scenario: Handle missing callback

- **WHEN** no progress callback is provided
- **THEN** execution SHALL proceed normally without callbacks

---

### Requirement: Abort Handling

The system SHALL support graceful abort of session execution.

#### Scenario: Request abort

- **WHEN** `replay_engine.request_abort()` is called
- **THEN** an internal abort flag SHALL be set
- **AND** the current operation MAY complete
- **AND** no further operations SHALL be executed

#### Scenario: Abort raises exception

- **WHEN** an abort is detected during execution
- **THEN** `AbortRequested` exception SHALL be raised
- **AND** the caller SHALL handle cleanup (e.g., clock out)

#### Scenario: Reset abort flag

- **WHEN** `execute()` is called
- **THEN** the abort flag SHALL be reset to `False`
- **AND** previous abort requests SHALL not affect new execution

#### Scenario: Abort during typing

- **WHEN** abort is requested while `type_code()` is in progress
- **THEN** the current character MAY complete typing
- **AND** typing SHALL stop after the current character
- **AND** `AbortRequested` SHALL be raised

---

### Requirement: Error Handling

The system SHALL handle errors during replay with appropriate recovery.

#### Scenario: VS Code window lost

- **WHEN** VS Code window is closed during replay
- **THEN** `VSCodeNotFoundError` SHALL be raised
- **AND** the current session SHALL be aborted
- **AND** the caller SHALL handle clock-out

#### Scenario: Input backend failure

- **WHEN** xdotool fails during input simulation
- **THEN** `InputBackendError` SHALL be raised
- **AND** the error SHALL include the failed command
- **AND** the session SHALL be aborted

#### Scenario: File open failure

- **WHEN** VS Code fails to open a file
- **THEN** the system MAY retry (configurable, default 1 retry)
- **AND** if retry fails, `FileOpenError` SHALL be raised
- **AND** the session SHALL be aborted

---

### Requirement: Replay Configuration Override

The system SHALL support per-session configuration overrides.

#### Scenario: Override typing speed

- **WHEN** `replay_config.base_wpm` is set in the session JSON
- **THEN** that value SHALL be used instead of the global default
- **AND** the override SHALL apply only to this session

#### Scenario: Override typo probability

- **WHEN** `replay_config.typo_probability` is set in the session JSON
- **THEN** that value SHALL be used for typing simulation
- **AND** the override SHALL apply only to this session

#### Scenario: Merge with defaults

- **WHEN** `replay_config` contains partial configuration
- **THEN** specified values SHALL override defaults
- **AND** unspecified values SHALL use global configuration
