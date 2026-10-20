"""Typeless-style global dictation on Windows, powered by local SenseVoice.

Tap Right Alt anywhere to start dictating, tap it again to stop. The text is
typed (pasted) where your cursor is and also left on the clipboard. Esc
cancels a recording. Right Alt used together with another key works as usual.

How it works:
  * A low-level keyboard hook spots a lone tap of Right Alt.
  * First tap: start recording the microphone (sensevoice_engine.Recorder).
  * A small status bar (sensevoice_overlay.Overlay) shows recording/transcribing.
  * Second tap: stop, transcribe locally with SenseVoice (sensevoice_engine.
    Engine), put the text on the clipboard and press Ctrl+V for you.
"""

import ctypes
import ctypes.wintypes as wt
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sensevoice_utils as helpers  # noqa: E402
import config  # noqa: E402
from sensevoice_utils import log, play_chime  # noqa: E402
from sensevoice_engine import SAMPLE_RATE, Engine, Recorder  # noqa: E402
from sensevoice_overlay import Overlay  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# The key you tap: see config.py.
HOTKEY_VK = config.HOTKEY_VK
HOTKEY_LABEL = config.HOTKEY_LABEL

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
# Unassigned key sent right after Right Alt goes down, so a lone Alt tap does
# not open the window's menu bar (same idea as AutoHotkey's MenuMaskKey).
MENU_MASK_VK = 0xE8
# Tags our own injected keys so the hook ignores them.
OWN_INPUT_TAG = 0x434F4458
VK_LCONTROL = 0xA2
VK_ESCAPE = 0x1B
VK_V = 0x56
ALTGR_FAKE_CTRL_SCAN = 0x21D
MODIFIER_VKS = (0x10, 0x11, 0x12, 0x5B, 0x5C)  # Shift, Ctrl, Alt, LWin, RWin
MIN_AUDIO_SECONDS = 0.3  # shorter recordings are treated as accidental taps


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wt.DWORD),
        ("scanCode", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HHOOK
user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.keybd_event.argtypes = [wt.BYTE, wt.BYTE, wt.DWORD, ctypes.c_size_t]
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short


def send_key(vk, flags=0, scan=0):
    user32.keybd_event(vk, scan, flags, OWN_INPUT_TAG)


def wait_for_modifiers_released(timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in MODIFIER_VKS):
            return
        time.sleep(0.01)


def paste():
    """Press Ctrl+V in the focused window."""
    wait_for_modifiers_released()
    send_key(VK_LCONTROL)
    send_key(VK_V)
    send_key(VK_V, KEYEVENTF_KEYUP)
    send_key(VK_LCONTROL, KEYEVENTF_KEYUP)


class Toggle:
    """Idle -> recording -> (transcribing) -> idle."""

    def __init__(self):
        self.engine = Engine()
        self.recorder = Recorder()
        self.overlay = Overlay(self.recorder.take_level)
        self.lock = threading.Lock()
        self.busy = False  # transcribing the previous recording
        self.session = 0  # counts recordings, so an old auto-stop timer does nothing

    def press(self):
        with self.lock:
            if self.recorder.recording:
                audio = self.recorder.stop()
                log("stop")
                self.overlay.transcribing()
                self.busy = True
                threading.Thread(target=self._finish, args=(audio,), daemon=True).start()
                return
            if self.busy:
                log("ignored tap: still transcribing")
                return
            try:
                self.recorder.start()
            except Exception as exc:
                log(f"microphone error {type(exc).__name__}: {exc}")
                return
            self.session += 1
            timer = threading.Timer(config.MAX_RECORD_SECONDS, self._auto_stop, args=(self.session,))
            timer.daemon = True
            timer.start()
            self.overlay.recording()
            play_chime("start")
            log("start")

    def _auto_stop(self, session):
        if self.session == session and self.recorder.recording:
            log(f"auto stop after {config.MAX_RECORD_SECONDS}s")
            self.press()

    def cancel(self):
        """Esc while recording. Returns True if a recording was cancelled.

        Called from the keyboard hook, so it never waits for the lock."""
        if not self.recorder.recording or not self.lock.acquire(blocking=False):
            return False
        try:
            if not self.recorder.recording:
                return False
            self.recorder.stop()
            self.overlay.hide()
            log("cancel")
            return True
        finally:
            self.lock.release()

    def _finish(self, audio):
        try:
            seconds = len(audio) / SAMPLE_RATE
            if seconds < MIN_AUDIO_SECONDS:
                log(f"too short ({seconds:.2f}s), skipped")
                return
            started = time.monotonic()
            text = self.engine.transcribe(audio)
            took = time.monotonic() - started
            if not text:
                peak = float(abs(audio).max())
                log(f"no speech ({seconds:.1f}s audio, peak {peak:.3f})")  # peak ~0: mic muted?
                return
            log(f"transcribed audio={seconds:.1f}s took={took:.2f}s chars={len(text)}")
            helpers.save_history(text, "sensevoice")
            if helpers.write_clipboard_text(text):
                paste()
                play_chime("end")
            else:
                log("clipboard busy, text only saved to history")
        except Exception as exc:
            log(f"transcribe error {type(exc).__name__}: {exc}")
        finally:
            self.overlay.hide()
            self.busy = False


class LoneTapDetector:
    """Fires when the hotkey is pressed and released with no other key between."""

    def __init__(self, on_tap, on_escape):
        self.on_tap = on_tap
        self.on_escape = on_escape
        self.hotkey_down = False
        self.other_key_pressed = False

    def handle(self, msg, kb):
        """Returns True to swallow the event.

        The first Right Alt press is replaced by our own Alt down + mask key, sent
        together so their order is fixed: the window sees Alt down -> mask key
        -> (real) Alt up and never opens its menu bar. The real Alt release is
        always passed on, so no program can think Alt is stuck.
        """
        if kb.dwExtraInfo == OWN_INPUT_TAG:
            return False
        is_down = msg in (WM_KEYDOWN, WM_SYSKEYDOWN)
        is_up = msg in (WM_KEYUP, WM_SYSKEYUP)
        if kb.vkCode == HOTKEY_VK:
            if is_down and not self.hotkey_down:  # ignore auto-repeat
                self.hotkey_down = True
                self.other_key_pressed = False
                send_key(HOTKEY_VK, KEYEVENTF_EXTENDEDKEY, kb.scanCode)
                send_key(MENU_MASK_VK)
                send_key(MENU_MASK_VK, KEYEVENTF_KEYUP)
                return True
            if is_up and self.hotkey_down:
                self.hotkey_down = False
                if not self.other_key_pressed:
                    threading.Thread(target=self.on_tap, daemon=True).start()
            return False
        if kb.vkCode == VK_ESCAPE and is_down and self.on_escape():
            return True  # Esc only cancels the recording; the window never sees it
        if is_down and self.hotkey_down:
            # AltGr layouts send a fake Left Ctrl with Right Alt; not a real key.
            if not (kb.vkCode == VK_LCONTROL and kb.scanCode == ALTGR_FAKE_CTRL_SCAN):
                self.other_key_pressed = True
        return False


def hotkey_loop():
    toggle = Toggle()
    detector = LoneTapDetector(toggle.press, toggle.cancel)

    @HOOKPROC
    def hook(n_code, w_param, l_param):
        if n_code == 0:
            kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            try:
                if detector.handle(w_param, kb):
                    return 1
            except Exception as exc:  # never break the keyboard
                log(f"hook error {type(exc).__name__}: {exc}")
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    hook_handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, hook, kernel32.GetModuleHandleW(None), 0)
    if not hook_handle:
        log(f"could not install keyboard hook (error {ctypes.get_last_error()})")
        return 1
    log(f"listening on {HOTKEY_LABEL} (SenseVoice)")
    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return 0


def main():
    kernel32.CreateMutexW(None, False, "Local\\sensevoice_hotkey")
    if ctypes.get_last_error() == helpers.ERROR_ALREADY_EXISTS:
        print("already running")
        return 0
    return hotkey_loop()


if __name__ == "__main__":
    sys.exit(main())
