import argparse
import ctypes
import json
import math
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import pygame
import vgamepad as vg

import tkinter as tk
from tkinter import ttk

CONFIG_PATH = "config.json"

RESET_DEFAULTS = {
  "rotation_speed_deg_per_sec": 180.0,
  "invert_rotation": True,
  "deadzone_left": 0.12,
  "deadzone_right": 0.1,
  "wrap_yaw": True,
  "invert_left_y": False,
  "invert_right_y": False,
  "output_smoothing": 0.0,
  "joystick_index": 0,
  "left_x_axis": 0,
  "left_y_axis": 1,
  "right_x_axis": 2,
  "right_y_axis": 3,
  "poll_hz": 240,
  "mouse_enabled": True,
  "mouse_speed_px_per_sec": 1200.0,
  "mouse_deadzone": 0.18,
  "mouse_accel": 1.35,
  "mouse_invert_y": False,
  "mouse_activation_mode": "always",
  "mouse_hold_key": "r3"
}


# ----------------------------
# Windows SendInput (mouse + keyboard)
# ----------------------------

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("union", INPUT_UNION),
    ]


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
KEYEVENTF_KEYUP = 0x0002

# Virtual-Key codes
VK_F8 = 0x77
VK_F11 = 0x7A
VK_F12 = 0x7B
VK_UP = 0x26
VK_DOWN = 0x28


def mouse_move_relative(dx: int, dy: int) -> None:
    if dx == 0 and dy == 0:
        return
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.union.mi = MOUSEINPUT(
        dx=dx,
        dy=dy,
        mouseData=0,
        dwFlags=MOUSEEVENTF_MOVE,
        time=0,
        dwExtraInfo=None,
    )
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _send_vk(vk: int, is_down: bool) -> None:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.union.ki = KEYBDINPUT(
        wVk=vk,
        wScan=0,
        dwFlags=0 if is_down else KEYEVENTF_KEYUP,
        time=0,
        dwExtraInfo=None,
    )
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def vk_key_down(vk: int) -> None:
    _send_vk(vk, True)


def vk_key_up(vk: int) -> None:
    _send_vk(vk, False)


def vk_tap(vk: int, tap_ms: int = 20) -> None:
    vk_key_down(vk)
    time.sleep(max(0.0, tap_ms / 1000.0))
    vk_key_up(vk)


# ----------------------------
# Config
# ----------------------------

@dataclass
class Config:
    rotation_speed_deg_per_sec: float = float(RESET_DEFAULTS["rotation_speed_deg_per_sec"])
    invert_rotation: bool = bool(RESET_DEFAULTS["invert_rotation"])

    deadzone_left: float = float(RESET_DEFAULTS["deadzone_left"])
    deadzone_right: float = float(RESET_DEFAULTS["deadzone_right"])

    wrap_yaw: bool = bool(RESET_DEFAULTS["wrap_yaw"])

    invert_left_y: bool = bool(RESET_DEFAULTS["invert_left_y"])
    invert_right_y: bool = bool(RESET_DEFAULTS["invert_right_y"])

    output_smoothing: float = float(RESET_DEFAULTS["output_smoothing"])

    joystick_index: int = int(RESET_DEFAULTS["joystick_index"])

    left_x_axis: int = int(RESET_DEFAULTS["left_x_axis"])
    left_y_axis: int = int(RESET_DEFAULTS["left_y_axis"])
    right_x_axis: int = int(RESET_DEFAULTS["right_x_axis"])
    right_y_axis: int = int(RESET_DEFAULTS["right_y_axis"])

    poll_hz: int = int(RESET_DEFAULTS["poll_hz"])

    mouse_enabled: bool = bool(RESET_DEFAULTS["mouse_enabled"])
    mouse_speed_px_per_sec: float = float(RESET_DEFAULTS["mouse_speed_px_per_sec"])
    mouse_deadzone: float = float(RESET_DEFAULTS["mouse_deadzone"])
    mouse_accel: float = float(RESET_DEFAULTS["mouse_accel"])
    mouse_invert_y: bool = bool(RESET_DEFAULTS["mouse_invert_y"])

    mouse_activation_mode: str = str(RESET_DEFAULTS["mouse_activation_mode"])
    mouse_hold_key: str = str(RESET_DEFAULTS["mouse_hold_key"])

    calibrated: bool = False
    calibration: Dict[str, Any] = field(default_factory=dict)


# ----------------------------
# Helpers
# ----------------------------

def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def apply_deadzone(x: float, y: float, dz: float) -> Tuple[float, float]:
    mag = math.hypot(x, y)
    if mag < dz or mag == 0.0:
        return 0.0, 0.0
    new_mag = (mag - dz) / (1.0 - dz)
    new_mag = clamp(new_mag, 0.0, 1.0)
    scale = new_mag / mag
    return x * scale, y * scale


def rotate_vec(x: float, y: float, ang_rad: float) -> Tuple[float, float]:
    ca = math.cos(ang_rad)
    sa = math.sin(ang_rad)
    return (x * ca - y * sa), (x * sa + y * ca)


def to_short_axis(v: float) -> int:
    v = clamp(v, -1.0, 1.0)
    return int(round(v * 32767.0))


def axis_to_trigger_0_255(v: float, mode: str) -> int:
    if mode == "minus1_to_1":
        t = (v + 1.0) * 0.5
    elif mode == "zero_to_1":
        t = v
    elif mode == "one_to_minus1":
        t = (1.0 - v) * 0.5
    else:
        t = (v + 1.0) * 0.5
    t = clamp(t, 0.0, 1.0)
    return int(round(t * 255.0))


def load_config(path: str) -> Config:
    if not os.path.exists(path):
        cfg = Config()
        save_config(path, cfg)
        return cfg
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return Config()

    cfg = Config()
    for k, v in data.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg


def save_config(path: str, cfg: Config) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg.__dict__, f, indent=2)


def list_joysticks():
    pygame.joystick.quit()
    pygame.joystick.init()
    count = pygame.joystick.get_count()
    print(f"Detected {count} joystick(s).")
    for i in range(count):
        j = pygame.joystick.Joystick(i)
        j.init()
        print(f"  [{i}] {j.get_name()} | axes={j.get_numaxes()} buttons={j.get_numbuttons()} hats={j.get_numhats()}")
        j.quit()
    pygame.joystick.quit()
    pygame.joystick.init()


def open_joystick(index: int) -> Optional[pygame.joystick.Joystick]:
    count = pygame.joystick.get_count()
    if count <= 0:
        return None
    if index < 0 or index >= count:
        print(f"joystick_index {index} is out of range (0..{count-1}).")
        return None
    j = pygame.joystick.Joystick(index)
    j.init()
    return j


def any_button_pressed(js: pygame.joystick.Joystick) -> bool:
    try:
        for i in range(js.get_numbuttons()):
            if js.get_button(i):
                return True
    except Exception:
        return True
    return False


def wait_for_buttons_released(js: pygame.joystick.Joystick):
    while True:
        pygame.event.pump()
        if not any_button_pressed(js):
            return
        time.sleep(0.01)


def detect_first_button_press(js: pygame.joystick.Joystick) -> int:
    while True:
        pygame.event.pump()
        for i in range(js.get_numbuttons()):
            try:
                if js.get_button(i):
                    return i
            except Exception:
                continue
        time.sleep(0.01)


def detect_hat_direction(js: pygame.joystick.Joystick) -> Tuple[int, int]:
    while True:
        pygame.event.pump()
        if js.get_numhats() <= 0:
            time.sleep(0.05)
            continue
        hx, hy = js.get_hat(0)
        if hx != 0 or hy != 0:
            return (hx, hy)
        time.sleep(0.01)


def detect_trigger_axis(js: pygame.joystick.Joystick, min_delta: float = 0.35) -> Tuple[int, str, float]:
    pygame.event.pump()
    rest = [js.get_axis(i) for i in range(js.get_numaxes())]
    while True:
        pygame.event.pump()
        cur = [js.get_axis(i) for i in range(js.get_numaxes())]
        deltas = [abs(cur[i] - rest[i]) for i in range(len(cur))]
        best_i = max(range(len(deltas)), key=lambda i: deltas[i]) if deltas else -1
        best_d = deltas[best_i] if best_i >= 0 else 0.0
        if best_i >= 0 and best_d >= min_delta:
            r = rest[best_i]
            if r <= -0.7:
                mode = "minus1_to_1"
            elif r >= 0.7:
                mode = "one_to_minus1"
            else:
                mode = "zero_to_1"
            return best_i, mode, r
        time.sleep(0.01)


def wait_for_axis_near(js: pygame.joystick.Joystick, axis_index: int, rest_value: float, eps: float = 0.15):
    while True:
        pygame.event.pump()
        try:
            v = js.get_axis(axis_index)
        except Exception:
            time.sleep(0.02)
            continue
        if abs(v - rest_value) <= eps and not any_button_pressed(js):
            return
        time.sleep(0.01)


def detect_axis_by_moving(js: pygame.joystick.Joystick, min_delta: float = 0.45) -> Tuple[int, int, float]:
    pygame.event.pump()
    rest = [js.get_axis(i) for i in range(js.get_numaxes())]
    while True:
        pygame.event.pump()
        cur = [js.get_axis(i) for i in range(js.get_numaxes())]
        deltas = [abs(cur[i] - rest[i]) for i in range(len(cur))]
        best_i = max(range(len(deltas)), key=lambda i: deltas[i]) if deltas else -1
        best_d = deltas[best_i] if best_i >= 0 else 0.0
        if best_i >= 0 and best_d >= min_delta:
            sign = 1 if (cur[best_i] - rest[best_i]) > 0 else -1
            return best_i, sign, rest[best_i]
        time.sleep(0.01)


def calibrate_sticks(js: pygame.joystick.Joystick, cfg: Config, cal: Dict[str, Any]) -> None:
    print("")
    print("Stick axis calibration (for cross-controller support).")
    print("When prompted, push and HOLD the stick direction until captured.")
    print("")

    wait_for_buttons_released(js)

    prompts = [
        ("lx", "Move LEFT stick fully LEFT and hold"),
        ("ly", "Move LEFT stick fully UP and hold"),
        ("rx", "Move RIGHT stick fully LEFT and hold"),
        ("ry", "Move RIGHT stick fully UP and hold"),
    ]

    stick_axes: Dict[str, Any] = {}

    for key, prompt in prompts:
        print(prompt)
        axis_i, sign, rest_val = detect_axis_by_moving(js)
        stick_axes[key] = {"axis": axis_i, "sign": sign, "rest": rest_val}
        print(f"Captured: axis {axis_i} (sign {sign})")
        print("Release...")
        wait_for_axis_near(js, axis_i, rest_val, eps=0.20)

    cfg.left_x_axis = int(stick_axes["lx"]["axis"])
    cfg.left_y_axis = int(stick_axes["ly"]["axis"])
    cfg.right_x_axis = int(stick_axes["rx"]["axis"])
    cfg.right_y_axis = int(stick_axes["ry"]["axis"])

    cfg.invert_left_y = True if int(stick_axes["ly"]["sign"]) > 0 else False
    cfg.invert_right_y = True if int(stick_axes["ry"]["sign"]) > 0 else False

    cal["stick_axes"] = stick_axes


def calibrate_controller(js: pygame.joystick.Joystick, cfg: Config) -> Config:
    print("")
    print("=== Controller Calibration ===")
    print("Follow the prompts. For each prompt:")
    print("1) Press the requested control.")
    print("2) Release it fully before the next prompt.")
    print("If you make a mistake, press Ctrl+C and rerun with --recalibrate.")
    print("")

    cal: Dict[str, Any] = {}
    cal["hat_index"] = 0 if js.get_numhats() > 0 else -1
    cal["dpad_mode"] = "hat" if js.get_numhats() > 0 else "buttons"

    print("Make sure no buttons are pressed...")
    wait_for_buttons_released(js)
    print("OK.")

    calibrate_sticks(js, cfg, cal)

    steps = [
        ("square_x", "Press SQUARE (PlayStation) / X (Xbox)"),
        ("cross_a", "Press CROSS (PlayStation) / A (Xbox)"),
        ("circle_b", "Press CIRCLE (PlayStation) / B (Xbox)"),
        ("triangle_y", "Press TRIANGLE (PlayStation) / Y (Xbox)"),

        ("dpad_up", "Press D-PAD UP"),
        ("dpad_left", "Press D-PAD LEFT"),
        ("dpad_down", "Press D-PAD DOWN"),
        ("dpad_right", "Press D-PAD RIGHT"),

        ("l1_lb", "Press L1 (PlayStation) / LB (Xbox)"),
        ("l2_lt", "Press and HOLD L2 (PlayStation) / LT (Xbox)"),
        ("r1_rb", "Press R1 (PlayStation) / RB (Xbox)"),
        ("r2_rt", "Press and HOLD R2 (PlayStation) / RT (Xbox)"),

        ("start", "Press START (PlayStation) / MENU (Xbox)"),
        ("select_back", "Press SELECT/SHARE (PlayStation) / BACK/VIEW (Xbox)"),

        ("l3", "Press L3 (Left stick click)"),
        ("r3", "Press R3 (Right stick click)"),
    ]

    button_keys = {
        "square_x", "cross_a", "circle_b", "triangle_y",
        "l1_lb", "r1_rb", "start", "select_back", "l3", "r3"
    }
    dpad_keys = {"dpad_up", "dpad_left", "dpad_down", "dpad_right"}
    trigger_keys = {"l2_lt", "r2_rt"}

    for key, prompt in steps:
        print("")
        print(prompt)

        wait_for_buttons_released(js)

        if key in button_keys:
            idx = detect_first_button_press(js)
            cal[key] = {"type": "button", "index": idx}
            print(f"Captured: button index {idx}")
            print("Release...")
            wait_for_buttons_released(js)

        elif key in dpad_keys:
            if cal["dpad_mode"] == "hat":
                hx, hy = detect_hat_direction(js)
                cal[key] = {"type": "hat_dir", "hat_index": cal["hat_index"], "hx": hx, "hy": hy}
                print(f"Captured: hat direction {hx},{hy}")
                while True:
                    pygame.event.pump()
                    hx2, hy2 = js.get_hat(int(cal["hat_index"]))
                    if hx2 == 0 and hy2 == 0 and not any_button_pressed(js):
                        break
                    time.sleep(0.01)
            else:
                idx = detect_first_button_press(js)
                cal[key] = {"type": "button", "index": idx}
                print(f"Captured: button index {idx}")
                print("Release...")
                wait_for_buttons_released(js)

        elif key in trigger_keys:
            axis_i, mode, rest_val = detect_trigger_axis(js)
            cal[key] = {"type": "axis", "index": axis_i, "mode": mode, "rest": rest_val}
            print(f"Captured: axis {axis_i} (mode {mode})")
            print("Release trigger...")
            wait_for_axis_near(js, axis_i, rest_val, eps=0.18)

        else:
            cal[key] = {"type": "none"}

    cfg.calibration = cal
    cfg.calibrated = True
    save_config(CONFIG_PATH, cfg)

    print("")
    print("Calibration saved to config.json.")
    print("")
    return cfg


def set_button(gamepad: vg.VX360Gamepad, vg_btn, pressed: bool):
    if pressed:
        gamepad.press_button(button=vg_btn)
    else:
        gamepad.release_button(button=vg_btn)


def read_cal_button(js: pygame.joystick.Joystick, cal: Dict[str, Any], key: str) -> bool:
    info = cal.get(key, {})
    if info.get("type") != "button":
        return False
    idx = int(info.get("index", -1))
    if idx < 0:
        return False
    try:
        return bool(js.get_button(idx))
    except Exception:
        return False


def read_cal_trigger(js: pygame.joystick.Joystick, cal: Dict[str, Any], key: str) -> int:
    info = cal.get(key, {})
    if info.get("type") != "axis":
        return 0
    ai = int(info.get("index", -1))
    mode = str(info.get("mode", "minus1_to_1"))
    if ai < 0:
        return 0
    try:
        return axis_to_trigger_0_255(js.get_axis(ai), mode)
    except Exception:
        return 0


# ----------------------------
# Shared state for realtime GUI edits
# ----------------------------

class SharedState:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.last_saved_cfg_json: Optional[str] = None

    def snapshot(self) -> Config:
        with self.lock:
            snap = Config()
            for k, v in self.cfg.__dict__.items():
                setattr(snap, k, v)
            return snap

    def update_and_save(self, **kwargs):
        with self.lock:
            for k, v in kwargs.items():
                if hasattr(self.cfg, k):
                    setattr(self.cfg, k, v)
            save_config(CONFIG_PATH, self.cfg)

    def maybe_reload_from_disk(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                txt = f.read()
        except Exception:
            return
        if txt == self.last_saved_cfg_json:
            return
        try:
            data = json.loads(txt)
        except Exception:
            return
        with self.lock:
            for k, v in data.items():
                if hasattr(self.cfg, k):
                    setattr(self.cfg, k, v)
        self.last_saved_cfg_json = txt

    def mark_saved(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                self.last_saved_cfg_json = f.read()
        except Exception:
            self.last_saved_cfg_json = None


# ----------------------------
# Controller worker thread
# ----------------------------

def controller_loop(state: SharedState, js: pygame.joystick.Joystick):
    gamepad = vg.VX360Gamepad()

    yaw_offset = 0.0
    out_lx = 0.0
    out_ly = 0.0

    mouse_rem_x = 0.0
    mouse_rem_y = 0.0

    last_time = time.perf_counter()
    last_disk_reload = 0.0

    prev_l3 = False

    # F8 combo (L1 + R3)
    f8_combo_armed = False

    # F12 combo (L1 + Start)
    f12_combo_armed = False

    # L1 + R1 + RightStickUp/Down repeater
    repeat_interval = 0.25
    ry_threshold = 0.65
    next_up_fire = 0.0
    next_down_fire = 0.0

    while not state.stop_event.is_set():
        now = time.perf_counter()
        dt = now - last_time
        last_time = now
        if dt <= 0.0:
            dt = 1e-6

        if now - last_disk_reload > 0.5:
            state.maybe_reload_from_disk()
            last_disk_reload = now

        cfg = state.snapshot()
        cal = cfg.calibration or {}

        pygame.event.pump()

        # Read stick axes
        try:
            lx = js.get_axis(cfg.left_x_axis)
            ly = js.get_axis(cfg.left_y_axis)
            rx = js.get_axis(cfg.right_x_axis)
            ry = js.get_axis(cfg.right_y_axis)
        except Exception:
            time.sleep(0.02)
            continue

        # Convert SDL Y (+down) to +up
        ly = -ly
        ry = -ry
        if cfg.invert_left_y:
            ly = -ly
        if cfg.invert_right_y:
            ry = -ry

        # Deadzones for gameplay stick output
        dlx, dly = apply_deadzone(lx, ly, cfg.deadzone_left)
        drx, dry = apply_deadzone(rx, ry, cfg.deadzone_right)

        # Integrate yaw from right stick X
        rot_dir = -1.0 if cfg.invert_rotation else 1.0
        speed_rad = cfg.rotation_speed_deg_per_sec * math.pi / 180.0
        yaw_offset += rot_dir * (drx * speed_rad * dt)

        if cfg.wrap_yaw:
            yaw_offset = (yaw_offset + math.pi) % (2.0 * math.pi) - math.pi

        # Rotate left stick
        rlx, rly = rotate_vec(dlx, dly, yaw_offset)

        # Optional smoothing
        s = clamp(cfg.output_smoothing, 0.0, 0.95)
        if s > 0.0:
            out_lx = out_lx * s + rlx * (1.0 - s)
            out_ly = out_ly * s + rly * (1.0 - s)
        else:
            out_lx, out_ly = rlx, rly

        # Output sticks to virtual controller
        gamepad.left_joystick(x_value=to_short_axis(out_lx), y_value=to_short_axis(out_ly))
        gamepad.right_joystick(x_value=to_short_axis(drx), y_value=to_short_axis(dry))

        # Buttons
        btn_bindings = [
            ("cross_a", vg.XUSB_BUTTON.XUSB_GAMEPAD_A),
            ("circle_b", vg.XUSB_BUTTON.XUSB_GAMEPAD_B),
            ("square_x", vg.XUSB_BUTTON.XUSB_GAMEPAD_X),
            ("triangle_y", vg.XUSB_BUTTON.XUSB_GAMEPAD_Y),
            ("l1_lb", vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER),
            ("r1_rb", vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER),
            ("select_back", vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK),
            ("start", vg.XUSB_BUTTON.XUSB_GAMEPAD_START),
            ("l3", vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB),
            ("r3", vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB),
        ]
        for cal_key, vg_btn in btn_bindings:
            set_button(gamepad, vg_btn, read_cal_button(js, cal, cal_key))

        # D-pad passthrough to virtual controller only
        dpad_mode = cal.get("dpad_mode", "hat")
        gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
        gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
        gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
        gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)

        if dpad_mode == "hat":
            hx, hy = 0, 0
            hat_index = int(cal.get("hat_index", 0)) if isinstance(cal.get("hat_index", 0), int) else 0
            try:
                if js.get_numhats() > 0 and hat_index >= 0:
                    hx, hy = js.get_hat(hat_index)
            except Exception:
                hx, hy = 0, 0
            if hy == 1:
                gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
            elif hy == -1:
                gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
            if hx == -1:
                gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
            elif hx == 1:
                gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)
        else:
            if read_cal_button(js, cal, "dpad_up"):
                gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
            if read_cal_button(js, cal, "dpad_down"):
                gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
            if read_cal_button(js, cal, "dpad_left"):
                gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
            if read_cal_button(js, cal, "dpad_right"):
                gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)

        # Triggers
        gamepad.left_trigger(value=read_cal_trigger(js, cal, "l2_lt"))
        gamepad.right_trigger(value=read_cal_trigger(js, cal, "r2_rt"))

        gamepad.update()

        # Extra keyboard bindings
        l1 = read_cal_button(js, cal, "l1_lb")
        r1 = read_cal_button(js, cal, "r1_rb")
        start = read_cal_button(js, cal, "start")
        r3 = read_cal_button(js, cal, "r3")

        # L1 + R3 -> F8 (R3 alone does nothing)
        combo_f8_now = l1 and r3
        if combo_f8_now and not f8_combo_armed:
            vk_tap(VK_F8)
            f8_combo_armed = True
        if not combo_f8_now:
            f8_combo_armed = False

        # L3 -> F11
        l3 = read_cal_button(js, cal, "l3")
        if l3 and not prev_l3:
            vk_tap(VK_F11)
        prev_l3 = l3

        # L1 + Start -> F12
        combo_f12_now = l1 and start
        if combo_f12_now and not f12_combo_armed:
            vk_tap(VK_F12)
            f12_combo_armed = True
        if not combo_f12_now:
            f12_combo_armed = False

        # L1 + R1 + right stick up/down => arrow key repeat every 0.25s
        if l1 and r1 and (abs(ry) >= ry_threshold):
            if ry >= ry_threshold:
                next_down_fire = 0.0
                if now >= next_up_fire:
                    vk_tap(VK_UP, tap_ms=10)
                    next_up_fire = now + repeat_interval
            elif ry <= -ry_threshold:
                next_up_fire = 0.0
                if now >= next_down_fire:
                    vk_tap(VK_DOWN, tap_ms=10)
                    next_down_fire = now + repeat_interval
        else:
            next_up_fire = 0.0
            next_down_fire = 0.0

        # Mouse from right stick
        if cfg.mouse_enabled:
            active = True
            if str(cfg.mouse_activation_mode).lower() == "hold":
                hold_key = str(cfg.mouse_hold_key)
                if hold_key == "l2_lt":
                    active = read_cal_trigger(js, cal, "l2_lt") > 8
                elif hold_key == "r2_rt":
                    active = read_cal_trigger(js, cal, "r2_rt") > 8
                else:
                    active = read_cal_button(js, cal, hold_key)

            if active:
                mx, my = apply_deadzone(rx, ry, cfg.mouse_deadzone)

                mag = math.hypot(mx, my)
                if mag > 0.0:
                    adj_mag = mag ** max(0.01, float(cfg.mouse_accel))
                    scale = adj_mag / mag
                    mx *= scale
                    my *= scale

                if cfg.mouse_invert_y:
                    my = -my

                mouse_dx = mx * float(cfg.mouse_speed_px_per_sec) * dt
                mouse_dy = -my * float(cfg.mouse_speed_px_per_sec) * dt

                mouse_rem_x += mouse_dx
                mouse_rem_y += mouse_dy

                send_dx = int(round(mouse_rem_x))
                send_dy = int(round(mouse_rem_y))

                mouse_rem_x -= send_dx
                mouse_rem_y -= send_dy

                mouse_move_relative(send_dx, send_dy)

        hz = max(30, int(cfg.poll_hz))
        time.sleep(1.0 / hz)


# ----------------------------
# GUI
# ----------------------------

def _float_or_keep(s: str, fallback: float) -> float:
    try:
        return float(s)
    except Exception:
        return fallback


def build_gui(state: "SharedState"):
    root = tk.Tk()
    root.title("Controller Cam Helper - Live Settings")
    root.minsize(520, 520)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure("TFrame", background="#111318")
    style.configure("Card.TFrame", background="#151822", relief="flat")
    style.configure("TLabel", background="#111318", foreground="#e6e6e6")
    style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"))
    style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground="#bdbdbd")
    style.configure("CardTitle.TLabel", font=("Segoe UI", 11, "bold"), background="#151822")
    style.configure("CardText.TLabel", font=("Segoe UI", 9), background="#151822", foreground="#cfcfcf")
    style.configure("TCheckbutton", background="#151822", foreground="#e6e6e6")
    style.configure("TButton", font=("Segoe UI", 9))
    style.configure("TScale", background="#151822")

    # Hover/active readability for widgets that highlight
    style.map(
        "TCheckbutton",
        foreground=[("active", "#000000"), ("pressed", "#000000")],
    )
    style.map(
        "TButton",
        foreground=[("active", "#000000"), ("pressed", "#000000")],
    )

    # Combobox: readable field + dropdown list
    style.configure(
        "TCombobox",
        foreground="#000000",
        fieldbackground="#ffffff",
        background="#ffffff",
        selectforeground="#000000",
        selectbackground="#cfe8ff",
    )
    style.map(
        "TCombobox",
        foreground=[("readonly", "#000000"), ("disabled", "#777777")],
        fieldbackground=[("readonly", "#ffffff"), ("disabled", "#e6e6e6")],
    )
    root.option_add("*TCombobox*Listbox.foreground", "#000000")
    root.option_add("*TCombobox*Listbox.background", "#ffffff")
    root.option_add("*TCombobox*Listbox.selectForeground", "#000000")
    root.option_add("*TCombobox*Listbox.selectBackground", "#cfe8ff")

    def on_close():
        state.stop_event.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    outer = ttk.Frame(root, padding=14, style="TFrame")
    outer.pack(fill="both", expand=True)

    title = ttk.Label(outer, text="Live Settings", style="Title.TLabel")
    title.pack(anchor="w")

    subtitle = ttk.Label(
        outer,
        text="Edits apply instantly to the running script and are saved to config.json.",
        style="Sub.TLabel",
    )
    subtitle.pack(anchor="w", pady=(2, 10))

    cfg0 = state.snapshot()

    def save_snapshot_mark():
        state.mark_saved()

    debounce = {"job": None}
    suspend = {"on": False}

    status_var = tk.StringVar(value="Saved")

    def queue_save(update_dict: Dict[str, Any]):
        if suspend["on"]:
            return

        def do_save():
            state.update_and_save(**update_dict)
            save_snapshot_mark()
            status_var.set("Saved")
            debounce["job"] = None

        status_var.set("Saving...")
        if debounce["job"] is not None:
            root.after_cancel(debounce["job"])
        debounce["job"] = root.after(120, do_save)

    gui_vars: Dict[str, Any] = {}

    def make_card(parent, title_text: str):
        card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        card.pack(fill="x", pady=8)
        lbl = ttk.Label(card, text=title_text, style="CardTitle.TLabel")
        lbl.pack(anchor="w", pady=(0, 8))
        return card

    def add_slider(card, label, field_name, from_, to_, step, fmt, as_int=False):
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=6)

        ttk.Label(row, text=label, style="CardText.TLabel").pack(side="left")

        val = getattr(cfg0, field_name)
        var = tk.DoubleVar(value=float(val))
        entry_var = tk.StringVar(value=fmt.format(val))

        entry = ttk.Entry(row, textvariable=entry_var, width=9)
        entry.pack(side="right", padx=(8, 0))

        def on_entry_commit(_evt=None):
            if suspend["on"]:
                return
            cur = state.snapshot()
            fallback = float(getattr(cur, field_name))
            newv = _float_or_keep(entry_var.get().strip(), fallback)
            newv = clamp(newv, float(from_), float(to_))
            if as_int:
                newv2 = int(round(newv))
                suspend["on"] = True
                var.set(float(newv2))
                entry_var.set(fmt.format(newv2))
                suspend["on"] = False
                queue_save({field_name: newv2})
            else:
                if step > 0:
                    newv = round(newv / step) * step
                    newv = clamp(newv, float(from_), float(to_))
                suspend["on"] = True
                var.set(float(newv))
                entry_var.set(fmt.format(newv))
                suspend["on"] = False
                queue_save({field_name: float(newv)})

        entry.bind("<Return>", on_entry_commit)
        entry.bind("<FocusOut>", on_entry_commit)

        scale = ttk.Scale(row, from_=from_, to=to_, variable=var)
        scale.pack(side="right", fill="x", expand=True, padx=(10, 10))

        def on_scale(_a=None, _b=None, _c=None):
            if suspend["on"]:
                return
            v = float(var.get())
            if as_int:
                v2 = int(round(v))
                entry_var.set(fmt.format(v2))
                queue_save({field_name: v2})
            else:
                if step > 0:
                    v = round(v / step) * step
                v = clamp(v, float(from_), float(to_))
                entry_var.set(fmt.format(v))
                queue_save({field_name: float(v)})

        var.trace_add("write", on_scale)

        gui_vars[field_name] = ("slider", var, entry_var, fmt, as_int, from_, to_, step)

    def add_check(card, label, field_name):
        cur = getattr(cfg0, field_name)
        var = tk.BooleanVar(value=bool(cur))

        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=5)

        chk = ttk.Checkbutton(row, text=label, variable=var)
        chk.pack(anchor="w")

        def on_toggle(*_):
            if suspend["on"]:
                return
            queue_save({field_name: bool(var.get())})

        var.trace_add("write", on_toggle)
        gui_vars[field_name] = ("check", var)

    def add_combo(card, label, field_name, values):
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=6)

        ttk.Label(row, text=label, style="CardText.TLabel").pack(side="left")

        cur = str(getattr(cfg0, field_name))
        var = tk.StringVar(value=cur if cur in values else values[0])

        cb = ttk.Combobox(row, values=values, textvariable=var, width=14, state="readonly")
        cb.pack(side="right")

        def on_change(_evt=None):
            if suspend["on"]:
                return
            queue_save({field_name: str(var.get())})

        cb.bind("<<ComboboxSelected>>", on_change)
        gui_vars[field_name] = ("combo", var, values)

    # Movement / rotation card
    card1 = make_card(outer, "Movement / Rotation")
    add_slider(card1, "Rotation speed (deg/sec)", "rotation_speed_deg_per_sec", 30, 720, 5, "{:.0f}")
    add_check(card1, "Invert rotation", "invert_rotation")
    add_check(card1, "Wrap yaw", "wrap_yaw")
    add_slider(card1, "Deadzone (left stick)", "deadzone_left", 0.00, 0.40, 0.01, "{:.2f}")
    add_slider(card1, "Deadzone (right stick)", "deadzone_right", 0.00, 0.40, 0.01, "{:.2f}")
    add_slider(card1, "Output smoothing", "output_smoothing", 0.00, 0.90, 0.01, "{:.2f}")
    add_slider(card1, "Poll rate (Hz)", "poll_hz", 30, 500, 5, "{:.0f}", as_int=True)

    # Mouse card
    card2 = make_card(outer, "Mouse From Right Stick")
    add_check(card2, "Mouse enabled", "mouse_enabled")
    add_slider(card2, "Mouse speed (px/sec)", "mouse_speed_px_per_sec", 100, 4000, 25, "{:.0f}")
    add_slider(card2, "Mouse deadzone", "mouse_deadzone", 0.00, 0.50, 0.01, "{:.2f}")
    add_slider(card2, "Mouse accel", "mouse_accel", 0.50, 3.00, 0.05, "{:.2f}")
    add_check(card2, "Invert mouse Y", "mouse_invert_y")
    add_combo(card2, "Mouse activation", "mouse_activation_mode", ["always", "hold"])
    add_combo(card2, "Hold key", "mouse_hold_key", ["r3", "l3", "l1_lb", "r1_rb", "l2_lt", "r2_rt", "start", "select_back"])

    # Footer
    footer = ttk.Frame(outer, style="TFrame")
    footer.pack(fill="x", pady=(10, 0))

    status = ttk.Label(footer, textvariable=status_var, style="Sub.TLabel")
    status.pack(side="left")

    def force_save():
        snap = state.snapshot()
        save_config(CONFIG_PATH, snap)
        state.mark_saved()
        status_var.set("Saved")

    def reset_to_defaults():
        cur = state.snapshot()
        update = dict(RESET_DEFAULTS)

        # Keep calibration info as-is so you do not have to recalibrate
        update["calibrated"] = bool(getattr(cur, "calibrated", False))
        update["calibration"] = dict(getattr(cur, "calibration", {}) or {})

        suspend["on"] = True
        try:
            state.update_and_save(**update)
            state.mark_saved()

            for k, v in RESET_DEFAULTS.items():
                if k not in gui_vars:
                    continue
                kind = gui_vars[k][0]
                if kind == "slider":
                    _, var, entry_var, fmt, as_int, from_, to_, step = gui_vars[k]
                    if as_int:
                        vv = int(round(float(v)))
                        var.set(float(vv))
                        entry_var.set(fmt.format(vv))
                    else:
                        vf = float(v)
                        var.set(vf)
                        entry_var.set(fmt.format(vf))
                elif kind == "check":
                    _, var = gui_vars[k]
                    var.set(bool(v))
                elif kind == "combo":
                    _, var, values = gui_vars[k]
                    sv = str(v)
                    var.set(sv if sv in values else values[0])

            status_var.set("Saved (reset to defaults)")
        finally:
            suspend["on"] = False

    btn_reset = ttk.Button(footer, text="Reset to Defaults", command=reset_to_defaults)
    btn_reset.pack(side="right", padx=(8, 0))

    btn_save = ttk.Button(footer, text="Save Now", command=force_save)
    btn_save.pack(side="right")

    def tick_status():
        state.maybe_reload_from_disk()
        root.after(500, tick_status)

    tick_status()

    # Auto-size to content (and only allow resize if clamped to screen)
    root.update_idletasks()
    req_w = root.winfo_reqwidth()
    req_h = root.winfo_reqheight()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    margin_w = 80
    margin_h = 120
    w = min(req_w, max(420, screen_w - margin_w))
    h = min(req_h, max(420, screen_h - margin_h))
    x = max(0, (screen_w - w) // 2)
    y = max(0, (screen_h - h) // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")
    fits = (req_w <= w) and (req_h <= h)
    root.resizable(not fits, not fits)

    return root


# ----------------------------
# Main
# ----------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recalibrate", action="store_true", help="Force calibration wizard")
    args = ap.parse_args()

    pygame.init()
    pygame.joystick.init()

    cfg = load_config(CONFIG_PATH)

    list_joysticks()
    js = open_joystick(cfg.joystick_index)
    if js is None:
        print("No joystick found by pygame. Check joy.cpl, reconnect controller, and rerun.")
        return

    print(f"Using joystick [{cfg.joystick_index}]: {js.get_name()}")

    if args.recalibrate or not cfg.calibrated:
        try:
            cfg = calibrate_controller(js, cfg)
        except KeyboardInterrupt:
            print("\nCalibration cancelled.")
            return

    state = SharedState(cfg)
    state.mark_saved()

    worker = threading.Thread(target=controller_loop, args=(state, js), daemon=True)
    worker.start()

    root = build_gui(state)
    try:
        root.mainloop()
    finally:
        state.stop_event.set()
        try:
            worker.join(timeout=1.0)
        except Exception:
            pass
        try:
            pygame.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
