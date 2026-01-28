# Session Orchestrator Specification

## ADDED Requirements

### Requirement: Git Operations

The system SHALL manage git repository synchronization for replay sessions.

#### Scenario: Pull latest changes

- **WHEN** `pull_latest()` is called
- **THEN** `git fetch origin` SHALL be executed
- **AND** `git reset --hard origin/<branch>` SHALL be executed
- **AND** the working directory SHALL match the remote state

#### Scenario: Find pending sessions

- **WHEN** `find_pending_sessions()` is called
- **THEN** the `.replay/` directory SHALL be scanned
- **AND** all JSON files matching `session_*.json` pattern SHALL be listed
- **AND** already-processed sessions SHALL be excluded
- **AND** sessions SHALL be sorted by timestamp (oldest first)

#### Scenario: Mark session processed

- **WHEN** `mark_session_processed(session_id)` is called
- **THEN** the session ID SHALL be recorded in `.replay/.processed`
- **AND** subsequent calls to `find_pending_sessions()` SHALL exclude it

#### Scenario: Idempotent processing

- **WHEN** a session is already marked as processed
- **THEN** attempting to process it again SHALL be skipped
- **AND** a log message SHALL indicate the session was already completed

#### Scenario: Handle git fetch failure

- **WHEN** `git fetch` fails (network error, auth failure)
- **THEN** `GitSyncError` SHALL be raised
- **AND** the error message SHALL include the git error output
- **AND** the orchestrator SHALL continue with existing local sessions

---

### Requirement: Main Workflow Execution

The system SHALL coordinate the full replay workflow.

Workflow steps:
1. Pull latest from git
2. Find pending sessions
3. For each session: clock in -> replay -> clock out
4. Mark session as processed
5. Wait for poll interval
6. Repeat

#### Scenario: Execute single session

- **WHEN** a pending session is found
- **THEN** `upwork_controller.start_session(contract, memo)` SHALL be called
- **AND** `replay_engine.execute(session)` SHALL be called
- **AND** `upwork_controller.end_session()` SHALL be called
- **AND** `mark_session_processed(session_id)` SHALL be called

#### Scenario: Execute multiple sessions

- **WHEN** multiple pending sessions are found
- **THEN** sessions SHALL be processed sequentially
- **AND** each session SHALL complete before the next begins
- **AND** a brief pause MAY occur between sessions

#### Scenario: No pending sessions

- **WHEN** no pending sessions are found after git pull
- **THEN** a log message SHALL indicate no work
- **AND** the orchestrator SHALL wait for the poll interval
- **AND** the cycle SHALL repeat

#### Scenario: Continue after session failure

- **WHEN** a session fails during execution
- **THEN** the session SHALL NOT be marked as processed
- **AND** the failure SHALL be logged with full details
- **AND** the orchestrator SHALL continue with remaining sessions

---

### Requirement: Signal Handling

The system SHALL handle Unix signals for graceful shutdown.

Signals to handle:
- `SIGTERM` - Standard termination (systemd stop)
- `SIGINT` - Interactive interrupt (Ctrl+C)
- `SIGHUP` - Reload configuration (optional)

#### Scenario: Receive SIGTERM

- **WHEN** `SIGTERM` is received
- **THEN** `shutdown_requested` flag SHALL be set to `True`
- **AND** the current operation MAY complete
- **AND** no new sessions SHALL be started
- **AND** graceful shutdown SHALL commence

#### Scenario: Receive SIGINT

- **WHEN** `SIGINT` is received (e.g., Ctrl+C)
- **THEN** identical behavior to SIGTERM SHALL occur
- **AND** a log message SHALL indicate interactive shutdown

#### Scenario: Signal during replay

- **WHEN** a signal is received while replay is in progress
- **THEN** `replay_engine.request_abort()` SHALL be called
- **AND** clock-out SHALL occur via the finally block
- **AND** the session SHALL NOT be marked as processed

#### Scenario: Signal during poll wait

- **WHEN** a signal is received during the poll interval wait
- **THEN** the wait SHALL be interrupted
- **AND** the main loop SHALL exit cleanly

---

### Requirement: Clock-Out Guarantee

The system SHALL guarantee that Upwork clock-out occurs on any failure or abort.

This is the MOST CRITICAL requirement of the system.

#### Scenario: Normal completion

- **WHEN** a session completes successfully
- **THEN** clock-out SHALL occur in the normal workflow
- **AND** `is_clocked_in()` SHALL return `False`

#### Scenario: Exception during replay

- **WHEN** an exception occurs during `replay_engine.execute()`
- **THEN** the exception SHALL be caught
- **AND** clock-out SHALL occur in the `finally` block
- **AND** the exception SHALL be re-raised or logged

#### Scenario: VS Code crash during replay

- **WHEN** VS Code crashes or window is closed during replay
- **THEN** `VSCodeNotFoundError` SHALL be raised
- **AND** clock-out SHALL occur in the `finally` block
- **AND** the session SHALL be marked as failed

#### Scenario: System crash protection

- **WHEN** the orchestrator process is killed (SIGKILL) or system crashes
- **THEN** the `atexit` handler SHALL attempt clock-out
- **AND** if clock-out fails, error SHALL be logged

#### Scenario: Watchdog process (optional)

- **WHEN** enabled in configuration
- **THEN** a watchdog process SHALL monitor the main process
- **AND** if the main process dies while clocked in, watchdog SHALL clock out

---

### Requirement: Polling Loop

The system SHALL poll for new sessions at configurable intervals.

#### Scenario: Configure poll interval

- **WHEN** `poll_interval` is set to 300 (seconds)
- **THEN** git pull SHALL occur every 5 minutes
- **AND** pending sessions SHALL be checked after each pull

#### Scenario: Poll on startup

- **WHEN** the orchestrator starts
- **THEN** an immediate git pull and session check SHALL occur
- **AND** pending sessions SHALL be processed before first wait

#### Scenario: Interruptible wait

- **WHEN** waiting for the poll interval
- **THEN** the wait SHALL be interruptible by signals
- **AND** `time.sleep()` SHALL be used with periodic checks

#### Scenario: Immediate trigger (optional)

- **WHEN** `SIGUSR1` is received
- **THEN** the current poll wait SHALL be interrupted
- **AND** an immediate git pull and session check SHALL occur

---

### Requirement: Logging

The system SHALL provide comprehensive logging for debugging and auditing.

Log events MUST include:
- Session start/complete/fail with timestamps
- Clock in/out events with contract details
- Git sync events
- Errors with full stack traces
- Signal handling events

#### Scenario: Log to file

- **WHEN** logging is configured
- **THEN** logs SHALL be written to the specified file (default: `session.log`)
- **AND** log rotation SHALL be supported (10MB max, 5 backups)

#### Scenario: Log format

- **WHEN** a log entry is written
- **THEN** the format SHALL be: `YYYY-MM-DD HH:MM:SS LEVEL [component] message`
- **AND** timestamps SHALL be in local time

#### Scenario: Audit trail

- **WHEN** clock in or clock out occurs
- **THEN** a log entry SHALL be written at INFO level
- **AND** the entry SHALL include contract ID and session ID

---

### Requirement: Configuration

The orchestrator SHALL accept configuration from YAML files.

Configuration options:
- `poll_interval` - Seconds between git pulls (default: 300)
- `git.remote` - Git remote name (default: "origin")
- `git.branch` - Git branch name (default: "main")
- `replay_dir` - Directory for session files (default: ".replay")
- `processed_file` - File tracking completed sessions (default: ".replay/.processed")
- `logging.file` - Log file path (default: "session.log")
- `logging.level` - Log level (default: "INFO")
- `watchdog.enabled` - Enable watchdog process (default: false)

#### Scenario: Load configuration

- **WHEN** the orchestrator starts
- **THEN** configuration SHALL be loaded from `config/default.yaml`
- **AND** environment-specific overrides MAY be applied

#### Scenario: Configuration validation

- **WHEN** configuration is loaded
- **THEN** required fields SHALL be validated
- **AND** invalid values SHALL raise `ConfigurationError`

#### Scenario: Runtime configuration reload

- **WHEN** `SIGHUP` is received
- **THEN** configuration SHALL be reloaded from file
- **AND** new settings SHALL take effect on next poll cycle

---

### Requirement: Daemon Mode

The system SHALL support running as a system daemon.

#### Scenario: Systemd service

- **WHEN** installed as a systemd service
- **THEN** the orchestrator SHALL run in foreground mode
- **AND** systemd SHALL manage start/stop/restart
- **AND** logs SHALL go to journald (in addition to file)

#### Scenario: Restart policy

- **WHEN** the orchestrator exits with non-zero code
- **THEN** systemd SHALL restart it after a delay
- **AND** the delay SHALL increase with consecutive failures

#### Scenario: Health check (optional)

- **WHEN** health monitoring is enabled
- **THEN** a status file SHALL be updated periodically
- **AND** systemd watchdog MAY be used for liveness checking

---

### Requirement: Error Recovery

The system SHALL recover gracefully from transient errors.

#### Scenario: Git network error

- **WHEN** git fetch fails due to network error
- **THEN** the error SHALL be logged
- **AND** the orchestrator SHALL continue with local sessions
- **AND** retry SHALL occur on next poll cycle

#### Scenario: Upwork error

- **WHEN** Upwork controller encounters an error
- **THEN** the session SHALL be aborted
- **AND** emergency clock-out SHALL be attempted
- **AND** the orchestrator SHALL continue with remaining sessions

#### Scenario: Consecutive failures

- **WHEN** multiple sessions fail consecutively (e.g., 3)
- **THEN** a critical error SHALL be logged
- **AND** the orchestrator MAY pause for an extended period
- **AND** alert mechanisms MAY be triggered (email, notification)
