# VS Code Controller Specification

## ADDED Requirements

### Requirement: Window Management

The system SHALL provide functions to find, focus, and verify VS Code windows.

The window management MUST:
- Locate VS Code windows by title pattern (configurable)
- Focus the VS Code window bringing it to the foreground
- Verify that VS Code is currently the active window
- Handle multiple VS Code windows by using the most recently focused

#### Scenario: Find VS Code window

- **WHEN** `find_vscode_window()` is called
- **THEN** the system SHALL search for windows matching the title pattern "Visual Studio Code"
- **AND** return the window identifier if found
- **AND** return `None` if no VS Code window exists

#### Scenario: Focus VS Code window

- **WHEN** `focus_window()` is called with a valid window identifier
- **THEN** VS Code SHALL become the active foreground window
- **AND** the system SHALL wait for focus to complete before returning

#### Scenario: Verify window focus

- **WHEN** `is_vscode_focused()` is called
- **THEN** return `True` if VS Code is the currently active window
- **AND** return `False` otherwise

#### Scenario: Handle missing VS Code

- **WHEN** `find_vscode_window()` returns `None`
- **THEN** operations requiring VS Code SHALL raise `VSCodeNotFoundError`
- **AND** the error message SHALL indicate VS Code must be running

---

### Requirement: File Navigation

The system SHALL provide functions to open files and navigate to specific lines in VS Code.

#### Scenario: Open file by path

- **WHEN** `open_file("/path/to/file.py")` is called
- **THEN** the system SHALL press Ctrl+P to open Quick Open
- **AND** wait for the dialog to appear (configurable delay, default 300ms)
- **AND** type the file path
- **AND** press Enter to open the file
- **AND** wait for the file to load

#### Scenario: Go to line number

- **WHEN** `goto_line(42)` is called
- **THEN** the system SHALL press Ctrl+G to open Go to Line dialog
- **AND** wait for the dialog to appear
- **AND** type the line number "42"
- **AND** press Enter to navigate
- **AND** the cursor SHALL be positioned at line 42

#### Scenario: Save current file

- **WHEN** `save_file()` is called
- **THEN** the system SHALL press Ctrl+S
- **AND** wait for the save operation to complete (configurable delay)

---

### Requirement: Human-Like Typing Simulation

The system SHALL simulate human-like typing behavior when entering code.

The typing simulation MUST include:
- Variable typing speed based on configured WPM
- Inter-character delays following a Gaussian distribution
- Bigram acceleration for common letter pairs
- Optional typo injection with correction
- Fatigue modeling (gradual slowdown over time)
- Thinking pauses at random intervals

#### Scenario: Type at target WPM

- **WHEN** `type_code("Hello World", wpm=80)` is called
- **THEN** the average typing speed SHALL approximate 80 words per minute
- **AND** individual character delays SHALL vary around the mean

#### Scenario: Gaussian timing distribution

- **WHEN** typing text at 60 WPM (base delay ~200ms per character)
- **THEN** actual delays SHALL follow a Gaussian distribution
- **AND** standard deviation SHALL be approximately 20% of the base delay
- **AND** delays SHALL be clamped to prevent negative or excessive values

#### Scenario: Bigram acceleration

- **WHEN** typing common letter pairs (th, he, in, er, an, on, or)
- **THEN** the delay between those characters SHALL be reduced by approximately 40%
- **AND** the effect SHALL simulate muscle memory for frequent combinations

#### Scenario: Inject typos with correction

- **WHEN** `type_code(text, typo_probability=0.02)` is called
- **THEN** approximately 2% of characters SHALL trigger a typo
- **AND** the typo SHALL be an adjacent key on QWERTY layout
- **AND** after a brief pause (100-300ms), backspace SHALL be pressed
- **AND** the correct character SHALL be typed

#### Scenario: Skip typo correction occasionally

- **WHEN** a typo is injected
- **THEN** with configurable probability (default 5%), the typo SHALL NOT be corrected
- **AND** the typo SHALL remain in the text to simulate human imperfection

#### Scenario: Fatigue modeling

- **WHEN** typing long text (> 500 characters)
- **THEN** typing speed SHALL gradually decrease
- **AND** the decrease SHALL be approximately 0.05% per character
- **AND** the effect SHALL simulate mental and physical fatigue

---

### Requirement: Thinking Pause Simulation

The system SHALL insert random "thinking" pauses during typing to simulate developer thought processes.

#### Scenario: Random thinking pause

- **WHEN** typing code with `thinking_pause_probability=0.10`
- **THEN** approximately 10% of characters SHALL trigger a thinking pause
- **AND** the pause duration SHALL be between 3 and 8 seconds (configurable)
- **AND** no input SHALL occur during the pause

#### Scenario: Pause at semantic boundaries

- **WHEN** the thinking pause feature is enabled
- **THEN** pauses SHOULD preferentially occur at:
  - End of lines
  - After punctuation (. , ; { } ( ))
  - Between words
- **AND** pauses SHOULD rarely occur mid-word

---

### Requirement: Line Operations

The system SHALL provide functions to manipulate lines of code in VS Code.

#### Scenario: Delete single line

- **WHEN** `delete_lines(15, 15)` is called
- **THEN** the cursor SHALL move to line 15
- **AND** Ctrl+Shift+K SHALL be pressed to delete the line
- **AND** the line SHALL be removed from the file

#### Scenario: Delete line range

- **WHEN** `delete_lines(10, 15)` is called
- **THEN** the cursor SHALL move to line 10
- **AND** lines 10 through 15 inclusive SHALL be selected
- **AND** the selected lines SHALL be deleted

#### Scenario: Select current line

- **WHEN** `select_line()` is called
- **THEN** Ctrl+L SHALL be pressed
- **AND** the entire current line SHALL be selected

---

### Requirement: Configuration Options

The VS Code controller SHALL accept configuration for all timing and behavior parameters.

Configuration options MUST include:
- `window_title_pattern` - Regex pattern for VS Code window (default: "Visual Studio Code")
- `quick_open_delay` - Delay after Ctrl+P before typing (default: 300ms)
- `goto_line_delay` - Delay after Ctrl+G before typing (default: 200ms)
- `save_delay` - Delay after Ctrl+S for save to complete (default: 500ms)
- `base_wpm` - Base typing speed in words per minute (default: 80)
- `wpm_variance` - Standard deviation as fraction of base (default: 0.2)
- `typo_probability` - Probability of typo per character (default: 0.02)
- `typo_correction_probability` - Probability of correcting typo (default: 0.95)
- `thinking_pause_probability` - Probability of thinking pause (default: 0.10)
- `thinking_pause_min` - Minimum pause duration in seconds (default: 3.0)
- `thinking_pause_max` - Maximum pause duration in seconds (default: 8.0)
- `fatigue_factor` - Speed decrease per character (default: 0.0005)

#### Scenario: Override default configuration

- **WHEN** `VSCodeController(config={"base_wpm": 120})` is instantiated
- **THEN** all typing operations SHALL use 120 WPM as the base speed
- **AND** other settings SHALL use their defaults

#### Scenario: Configuration validation

- **WHEN** invalid configuration values are provided (e.g., negative WPM)
- **THEN** `ConfigurationError` SHALL be raised
- **AND** the error message SHALL identify the invalid parameter
