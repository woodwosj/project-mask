# Input Backend Specification

## ADDED Requirements

### Requirement: Abstract Input Interface

The system SHALL provide an abstract `InputBackend` base class that defines the contract for input simulation implementations.

The interface SHALL include the following methods:
- `type_text(text: str, delay: float) -> None` - Type text character by character
- `key_press(key: str) -> None` - Press and release a single key
- `key_combo(*keys: str) -> None` - Press a key combination (e.g., Ctrl+S)
- `mouse_move(x: int, y: int) -> None` - Move mouse cursor to coordinates
- `mouse_click(button: str) -> None` - Click a mouse button

#### Scenario: Backend abstraction enables testing

- **WHEN** a controller class accepts an InputBackend instance via dependency injection
- **THEN** mock implementations can be substituted for unit testing without X11 display

#### Scenario: Backend interface is complete

- **WHEN** implementing a new backend (e.g., for Wayland)
- **THEN** all five interface methods MUST be implemented
- **AND** the backend MUST raise `NotImplementedError` for any unsupported operations

---

### Requirement: Xdotool Backend Implementation

The system SHALL provide an `XdotoolBackend` class that implements the `InputBackend` interface using the xdotool command-line tool.

The implementation MUST:
- Execute xdotool via subprocess for all operations
- Translate key names to xdotool format (e.g., "Return", "BackSpace", "ctrl", "alt", "shift")
- Support all printable ASCII characters
- Handle special characters that require shift modifier
- Raise `InputBackendError` when xdotool command fails

#### Scenario: Type plain text

- **WHEN** `type_text("Hello World", delay=0.05)` is called
- **THEN** xdotool SHALL type each character with approximately 50ms delay between keystrokes
- **AND** the text SHALL appear in the currently focused window

#### Scenario: Press special key

- **WHEN** `key_press("Return")` is called
- **THEN** xdotool SHALL execute `xdotool key Return`
- **AND** an Enter keypress SHALL be sent to the focused window

#### Scenario: Press key combination

- **WHEN** `key_combo("ctrl", "s")` is called
- **THEN** xdotool SHALL execute `xdotool key ctrl+s`
- **AND** the Ctrl+S keyboard shortcut SHALL be triggered

#### Scenario: Move mouse cursor

- **WHEN** `mouse_move(100, 200)` is called
- **THEN** xdotool SHALL execute `xdotool mousemove 100 200`
- **AND** the mouse cursor SHALL move to screen coordinates (100, 200)

#### Scenario: Click mouse button

- **WHEN** `mouse_click("left")` is called
- **THEN** xdotool SHALL execute `xdotool click 1`
- **AND** a left mouse click SHALL occur at the current cursor position

#### Scenario: Handle xdotool failure

- **WHEN** xdotool returns a non-zero exit code
- **THEN** `InputBackendError` SHALL be raised with the error message
- **AND** the error SHALL include the failed command for debugging

---

### Requirement: Display Server Detection

The system SHALL detect the current display server and validate compatibility before operation.

The detection MUST:
- Check the `XDG_SESSION_TYPE` environment variable
- Accept "x11" as a valid session type
- Reject "wayland" with a clear error message explaining the limitation
- Default to X11 if the environment variable is not set

#### Scenario: X11 session detected

- **WHEN** `XDG_SESSION_TYPE` is "x11"
- **THEN** `XdotoolBackend` SHALL initialize successfully
- **AND** all input operations SHALL be available

#### Scenario: Wayland session detected

- **WHEN** `XDG_SESSION_TYPE` is "wayland"
- **THEN** `XdotoolBackend` initialization SHALL raise `UnsupportedDisplayServerError`
- **AND** the error message SHALL explain that X11 is required for xdotool

#### Scenario: Unknown or missing session type

- **WHEN** `XDG_SESSION_TYPE` is not set or has an unknown value
- **THEN** the system SHALL log a warning
- **AND** the system SHALL attempt to use xdotool (assume X11)

---

### Requirement: Input Timing Configuration

The system SHALL support configurable timing parameters for input operations.

Configuration options MUST include:
- `key_press_delay` - Delay after each keypress (default: 12ms)
- `type_delay` - Base delay between characters when typing (default: 50ms)
- `mouse_move_delay` - Delay after mouse movement (default: 50ms)
- `click_delay` - Delay after mouse click (default: 100ms)

#### Scenario: Configure typing speed

- **WHEN** `XdotoolBackend(type_delay=0.02)` is instantiated
- **THEN** `type_text()` SHALL use 20ms base delay between characters

#### Scenario: Default timing works reliably

- **WHEN** using default timing values
- **THEN** input operations SHALL complete without race conditions
- **AND** target applications SHALL receive all input correctly

---

### Requirement: Thread Safety

The `InputBackend` implementations SHALL be thread-safe for concurrent access.

#### Scenario: Concurrent input operations

- **WHEN** multiple threads call input methods simultaneously
- **THEN** operations SHALL be serialized to prevent interleaved input
- **AND** each operation SHALL complete atomically

#### Scenario: Abort during operation

- **WHEN** an abort is requested while `type_text()` is executing
- **THEN** the current character MAY complete
- **AND** no additional characters SHALL be typed
