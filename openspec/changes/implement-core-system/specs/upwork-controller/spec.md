# Upwork Controller Specification

## ADDED Requirements

### Requirement: Application Launch

The system SHALL launch and manage the Upwork time tracking interface.

The launcher MUST support two modes:
- `web` mode - Launch browser to Upwork time tracker URL
- `desktop` mode - Launch Upwork desktop application (if available on platform)

#### Scenario: Launch web mode

- **WHEN** `launch_upwork(mode="web")` is called
- **THEN** the configured browser (Firefox or Chromium) SHALL be launched
- **AND** the browser SHALL navigate to Upwork time tracker URL
- **AND** the system SHALL wait for the page to load

#### Scenario: Launch desktop mode

- **WHEN** `launch_upwork(mode="desktop")` is called on x86_64 platform
- **THEN** the Upwork desktop application SHALL be started
- **AND** the system SHALL wait for the application window to appear

#### Scenario: Desktop mode unavailable on ARM64

- **WHEN** `launch_upwork(mode="desktop")` is called on ARM64 platform
- **THEN** `UnsupportedPlatformError` SHALL be raised
- **AND** the error message SHALL recommend using web mode

#### Scenario: Check if Upwork is running

- **WHEN** `is_upwork_running()` is called
- **THEN** return `True` if the Upwork window/tab is detected
- **AND** return `False` otherwise

#### Scenario: Wait for ready state

- **WHEN** `wait_for_ready(timeout=30)` is called
- **THEN** the system SHALL wait for Upwork to be fully loaded
- **AND** return `True` if ready within timeout
- **AND** raise `UpworkTimeoutError` if timeout exceeded

---

### Requirement: Contract Selection

The system SHALL select the appropriate Upwork contract for time tracking.

#### Scenario: Select contract by name

- **WHEN** `select_contract("ClientName Project")` is called
- **THEN** the contract dropdown SHALL be opened
- **AND** the contract name SHALL be searched/typed
- **AND** the matching contract SHALL be selected

#### Scenario: Contract dropdown interaction (web mode)

- **WHEN** selecting a contract in web mode
- **THEN** the system SHALL click the contract selector element
- **AND** wait for the dropdown to appear
- **AND** type the contract name in the search field
- **AND** click the matching result

#### Scenario: Contract dropdown interaction (desktop mode)

- **WHEN** selecting a contract in desktop mode
- **THEN** the system SHALL click at the configured dropdown coordinates
- **AND** wait for the dropdown animation
- **AND** type the contract name
- **AND** press Enter to select

#### Scenario: Handle contract not found

- **WHEN** the specified contract is not found in the dropdown
- **THEN** `ContractNotFoundError` SHALL be raised
- **AND** the error message SHALL include the searched contract name

#### Scenario: Verify contract selection

- **WHEN** a contract is selected
- **THEN** `get_selected_contract()` SHALL return the contract name
- **AND** the name SHALL match the requested contract

---

### Requirement: Memo Setting

The system SHALL set the work memo/description for the time tracking session.

#### Scenario: Set memo text

- **WHEN** `set_memo("Implementing feature X")` is called
- **THEN** the memo input field SHALL be focused
- **AND** any existing text SHALL be cleared
- **AND** the new memo text SHALL be typed

#### Scenario: Clear existing memo

- **WHEN** setting a new memo
- **THEN** Ctrl+A SHALL be pressed to select all
- **AND** the new text SHALL be typed (replacing selection)

#### Scenario: Handle long memo

- **WHEN** the memo text exceeds Upwork's character limit
- **THEN** a warning SHALL be logged
- **AND** the memo SHALL be truncated to the limit

---

### Requirement: Time Tracking Control

The system SHALL control Upwork's clock in/out functionality.

#### Scenario: Clock in

- **WHEN** `clock_in()` is called
- **THEN** the Start/Play button SHALL be clicked
- **AND** the system SHALL wait for time tracking to begin
- **AND** `is_clocked_in()` SHALL return `True`

#### Scenario: Clock out

- **WHEN** `clock_out()` is called
- **THEN** the Stop/Pause button SHALL be clicked
- **AND** the system SHALL wait for time tracking to stop
- **AND** `is_clocked_in()` SHALL return `False`

#### Scenario: Verify clocked-in state

- **WHEN** `is_clocked_in()` is called
- **THEN** the system SHALL check the current tracking state
- **AND** return `True` if actively tracking time
- **AND** return `False` if not tracking

#### Scenario: Handle already clocked in

- **WHEN** `clock_in()` is called while already tracking
- **THEN** a warning SHALL be logged
- **AND** no action SHALL be taken
- **AND** `is_clocked_in()` SHALL still return `True`

#### Scenario: Handle already clocked out

- **WHEN** `clock_out()` is called while not tracking
- **THEN** a warning SHALL be logged
- **AND** no action SHALL be taken
- **AND** `is_clocked_in()` SHALL still return `False`

---

### Requirement: Full Session Workflow

The system SHALL provide a combined workflow for clock in with contract and memo.

#### Scenario: Start session

- **WHEN** `start_session(contract="ClientName", memo="Work description")` is called
- **THEN** the contract SHALL be selected first
- **AND** the memo SHALL be set
- **AND** clock in SHALL be triggered
- **AND** verification SHALL confirm all steps completed

#### Scenario: End session

- **WHEN** `end_session()` is called
- **THEN** clock out SHALL be triggered
- **AND** the system SHALL verify time tracking has stopped

---

### Requirement: UI Calibration

The system SHALL support calibration of UI element positions for different screen resolutions.

#### Scenario: Interactive calibration

- **WHEN** `UpworkCalibrator.run()` is executed
- **THEN** an interactive process SHALL guide the user
- **AND** prompts SHALL request clicking on each UI element:
  - Contract dropdown
  - Memo input field
  - Start/Stop button
- **AND** coordinates SHALL be recorded

#### Scenario: Save calibration

- **WHEN** calibration is complete
- **THEN** coordinates SHALL be saved to the config file
- **AND** the format SHALL include screen resolution for reference

#### Scenario: Load calibration

- **WHEN** `UpworkController` is initialized
- **THEN** calibration data SHALL be loaded from config
- **AND** coordinates SHALL be used for UI interactions

#### Scenario: Calibration mismatch warning

- **WHEN** current screen resolution differs from calibrated resolution
- **THEN** a warning SHALL be logged
- **AND** the user SHALL be prompted to recalibrate

---

### Requirement: Error Recovery

The system SHALL handle errors during Upwork interactions gracefully.

#### Scenario: Retry on click failure

- **WHEN** a UI click does not produce the expected result
- **THEN** the system MAY retry up to 3 times (configurable)
- **AND** delays between retries SHALL increase (100ms, 200ms, 400ms)

#### Scenario: Handle Upwork crash

- **WHEN** the Upwork window/tab is closed unexpectedly
- **THEN** `UpworkNotFoundError` SHALL be raised
- **AND** the caller SHALL handle emergency procedures

#### Scenario: Handle authentication loss

- **WHEN** Upwork session expires during operation
- **THEN** `UpworkAuthenticationError` SHALL be raised
- **AND** the error message SHALL indicate re-login is required

---

### Requirement: Configuration Options

The Upwork controller SHALL accept configuration for all parameters.

Configuration options MUST include:
- `mode` - "web" or "desktop" (default: "web")
- `browser` - Browser to use in web mode (default: "firefox")
- `url` - Upwork time tracker URL
- `click_delay` - Delay after clicks (default: 200ms)
- `typing_delay` - Delay between characters when typing (default: 50ms)
- `retry_count` - Number of retries on failure (default: 3)
- `ready_timeout` - Timeout waiting for app to be ready (default: 30s)
- `coordinates` - Calibrated UI element positions (nested object)

#### Scenario: Configure for web mode

- **WHEN** `UpworkController(config={"mode": "web", "browser": "chromium"})` is instantiated
- **THEN** web mode SHALL be used
- **AND** Chromium SHALL be the browser

#### Scenario: Configure custom coordinates

- **WHEN** `coordinates` config contains custom positions
- **THEN** those positions SHALL be used for UI interactions
- **AND** default coordinate detection SHALL be skipped
