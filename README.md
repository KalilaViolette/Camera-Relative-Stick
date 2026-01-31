# Camera Relative Stick (pygame)

This project fixes a common problem in games that were designed for a fixed/top-down camera, but are being played with a modded 3rd-person / free camera.

In these games, the game still interprets **left stick movement** relative to the original camera orientation (ex: "up" always means "north"), even if your modded camera is pointing somewhere else. The result is that pushing forward on the stick often moves your character in a direction that does not match what the camera shows.

**Goal:** make controller movement feel camera-relative again by dynamically rotating the left stick output based on how you rotate the camera.

---

## What it does (high level)

- Reads your **real controller** using `pygame`.
- Creates a **virtual Xbox 360 controller** using `vgamepad`.
- Integrates a yaw offset from the **right stick X** (camera rotation input).
- Rotates the **left stick** vector by that yaw offset so "forward" stays aligned with your camera direction.
- (Optional) moves the **mouse cursor** using the right stick.
- Provides a **calibration wizard** so it works across different controller models and button layouts.
- Provides a **live GUI** to edit settings in real time and saves them instantly to `config.json`.

---

## Features (full list)

### Core movement/camera features
- Camera-relative movement: left stick is rotated by a continuously integrated yaw offset.
- Adjustable rotation speed (deg/sec) to match your camera rotation sensitivity.
- Optional rotation direction invert (in case your game/mod rotates opposite of expectation).
- Optional yaw wrapping (keeps yaw within -pi..pi range).
- Independent deadzones for left and right sticks.
- Optional output smoothing (can reduce jitter, but may add slight input lag).
- High poll rate support (adjustable Hz).

### Mouse from right stick
- Optional mouse movement controlled by right stick.
- Adjustable mouse speed (pixels/sec).
- Adjustable mouse deadzone (separate from stick deadzones).
- Adjustable mouse acceleration curve for more usable center precision.
- Optional invert mouse Y.
- Mouse activation modes:
  - `always`
  - `hold` (hold a selected controller input to enable mouse movement)

### Controller compatibility + calibration
- First-run calibration wizard that records:
  - Face buttons (Square/Cross/Circle/Triangle or X/A/B/Y)
  - D-pad (hat-based or button-based, depending on controller)
  - Bumpers and triggers
  - Start / Select (Menu / View)
  - L3 / R3 clicks
  - Stick axis mapping for LX/LY/RX/RY (cross-controller support)
- Calibration saved in `config.json` and reused automatically.
- Manual re-calibration supported via command line flag or config.

### Extra hotkeys / macros (built-in)
These send keyboard input using Windows `SendInput`:

- **L1 + R3** -> taps **F8**
- **L3** -> taps **F11**
- **L1 + Start** -> taps **F12**
- **L1 + R1 + Right Stick Up** -> taps **Arrow Up** every 0.25s while held
- **L1 + R1 + Right Stick Down** -> taps **Arrow Down** every 0.25s while held

### Live GUI
- Clean GUI with appropriate widgets (sliders/toggles/dropdowns).
- Changes apply instantly while the script is running.
- Automatically saves changes to `config.json`.
- Includes a **Reset to Defaults** button that resets only the editable settings (keeps calibration data so you do not need to re-calibrate).

---

## Project files

Your folder should look like this:

- `camera_relative_stick_pygame.py`  
  The main program (virtual controller + mouse + hotkeys + GUI + calibration).

- `config.json`  
  Stores your settings and your controller calibration.

- `install.bat`  
  Installs Python (if needed), installs dependencies, and verifies imports.

- `run.bat`  
  Runs the main script normally.

- `calibrate.bat`  
  Runs the calibration wizard (`--recalibrate`).

---

## Setup and usage (recommended order)

### 1) Install dependencies
Run:
- `install.bat`

This will:
- Check for Python (and install it if missing via winget)
- Install required packages (`pygame`, `vgamepad`)
- Verify the imports

If the virtual controller does not appear, you may also need ViGEmBus installed (used by `vgamepad`).

### 2) First time calibration
Run:
- `calibrate.bat`

Follow the prompts carefully:
- Press the requested button/control
- Release it fully before continuing
- The script saves mappings into `config.json`

### 3) Run normally
Run:
- `run.bat`

The GUI will open and you can tune settings in real time.

---

## Config file (config.json)

This file is automatically created/updated. You can edit it manually, but it is intended to be controlled via the GUI.

### Main settings

- `rotation_speed_deg_per_sec`
  How fast yaw accumulates from right-stick X. If the camera turns faster than your movement rotation, increase this.

- `invert_rotation`
  Flips yaw direction. Use this if turning the camera left makes movement rotate the wrong way.

- `deadzone_left`
  Deadzone applied to left stick input before rotation.

- `deadzone_right`
  Deadzone applied to right stick input used for yaw integration (and virtual right stick output).

- `wrap_yaw`
  Keeps yaw offset bounded in a stable range (recommended true).

- `invert_left_y`
  Inverts the left stick Y axis (usually determined automatically during calibration).

- `invert_right_y`
  Inverts the right stick Y axis (usually determined automatically during calibration).

- `output_smoothing`
  Smooths rotated left-stick output (0.0 = off). Higher = smoother but adds latency.

- `joystick_index`
  Which controller `pygame` should use if multiple are connected (0 is the first).

- `left_x_axis`, `left_y_axis`, `right_x_axis`, `right_y_axis`
  Axis indices for the sticks. These are normally set by calibration.

- `poll_hz`
  Loop update frequency. Higher values feel more responsive but use more CPU.

### Mouse settings

- `mouse_enabled`
  Enables right-stick mouse movement.

- `mouse_speed_px_per_sec`
  Cursor speed at full stick deflection.

- `mouse_deadzone`
  Deadzone for mouse movement (separate from `deadzone_right`).

- `mouse_accel`
  Acceleration curve (1.0 = linear). Higher values make the center gentler and edges faster.

- `mouse_invert_y`
  Inverts mouse Y.

- `mouse_activation_mode`
  `always` or `hold`.

- `mouse_hold_key`
  Which calibrated control enables mouse movement when `mouse_activation_mode` is `hold`.

### Calibration settings

- `calibrated`
  True if calibration has been completed.

- `calibration`
  Saved mappings for:
  - stick axes and their direction/rest values
  - face buttons
  - bumpers/triggers
  - start/select
  - L3/R3
  - dpad mode (hat vs button)

Do not edit the calibration section unless you know exactly what you are doing. Use `calibrate.bat` instead.

---

## Important warning: camera/player can desync

This system assumes that:
- Your camera rotation input (right stick / mouse movement) always corresponds to actual camera yaw changes
- The game is always in a state where the camera and movement logic behave normally

However, there are situations that can cause the yaw tracking to drift out of sync, such as:
- Ladders or climbing states
- Cutscenes / scripted moments
- UI menus that still accept right stick input but do not rotate the camera normally
- Forced camera snaps / camera resets
- Any state where camera rotation is constrained, slowed, or disabled

### How to resync
If movement starts feeling "off" (forward drifts to the side/backwards):
1. Walk forward slowly.
2. Use your mouse to gently rotate the camera until walking forward matches the camera-forward direction again.

Once realigned, movement should feel correct again.

---

## Notes
- Many games will detect both your physical controller and the virtual controller. Configure your game/Steam Input so it uses the virtual controller if needed.
- This project sends virtual controller input and simulated keyboard/mouse input. Use responsibly and follow the rules of the game you use it with.

---
