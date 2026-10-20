"""Small status bar at the bottom of the screen: "● ▁▃▆▃▁ 0:03" / "transcribing".

While recording, the bars scroll from right to left and follow the microphone
loudness: tall when you speak, flat when you are silent.

It never takes focus (WS_EX_NOACTIVATE) and mouse clicks pass through it
(WS_EX_TRANSPARENT), so typing and the final paste still go to the window you
were using. It runs its own Tk thread; other threads talk to it via a queue.
"""

import ctypes
import ctypes.wintypes as wt
import math
import queue
import threading
import time
import tkinter as tk

import config

user32 = ctypes.WinDLL("user32", use_last_error=True)

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
MONITOR_DEFAULTTONEAREST = 2
ALPHA = 0.93
HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

BG = "#202124"
FG = "#e8eaed"
RED = "#ff5c5c"
BLUE = "#8ab4f8"

BARS = 18  # waveform bars, newest on the right
TICK_RECORDING_MS = 50
TICK_IDLE_MS = 100


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_long]
user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
user32.MonitorFromPoint.restype = wt.HMONITOR
user32.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]


def _work_area_under_cursor():
    pt = wt.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    user32.GetMonitorInfoW(user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST), ctypes.byref(info))
    return info.rcWork


def _bar_height(rms):
    """Loudness -> 0..1. See WAVE_* in config.py."""
    db = 20 * math.log10(rms + 1e-9)
    x = min(max((db - config.WAVE_SILENCE_DB) / (config.WAVE_LOUD_DB - config.WAVE_SILENCE_DB), 0.0), 1.0)
    return x ** config.WAVE_CURVE


class Overlay:
    def __init__(self, level_source=None):
        """level_source: called while recording, returns the loudness (RMS)."""
        self._level_source = level_source or (lambda: 0.0)
        self._queue = queue.Queue()
        self._ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(5)

    # Thread-safe API ---------------------------------------------------
    def recording(self):
        self._queue.put("recording")

    def transcribing(self):
        self._queue.put("transcribing")

    def hide(self):
        self._queue.put("hide")

    # Tk thread ---------------------------------------------------------
    def _run(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on HiDPI
        except (AttributeError, OSError):
            pass
        root = tk.Tk()
        self._root = root
        root.overrideredirect(True)
        root.configure(bg=BG)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.0)  # hidden = fully transparent
        scale = root.winfo_fpixels("1i") / 96
        self._size = (int(190 * scale), int(38 * scale))
        font = ("Microsoft YaHei UI", 11)
        frame = tk.Frame(root, bg=BG, padx=int(14 * scale))
        frame.pack(expand=True)
        self._dot = tk.Label(frame, text="●", fg=RED, bg=BG, font=font)
        self._dot.pack(side="left")
        # Waveform: BARS rounded bars, redrawn in place on every tick.
        self._bar_w, self._bar_gap = max(2, int(3 * scale)), max(1, int(2 * scale))
        self._wave_h = int(22 * scale)
        wave_w = BARS * (self._bar_w + self._bar_gap) - self._bar_gap
        self._wave = tk.Canvas(frame, width=wave_w, height=self._wave_h, bg=BG, highlightthickness=0)
        self._wave_pad = (int(8 * scale), int(8 * scale))
        self._wave.pack(side="left", padx=self._wave_pad)
        self._bars = [
            self._wave.create_line(0, 0, 0, 0, width=self._bar_w, capstyle="round", fill=FG)
            for _ in range(BARS)
        ]
        self._levels = [0.0] * BARS
        self._text = tk.Label(frame, text="", fg=FG, bg=BG, font=font)
        self._text.pack(side="left")
        root.geometry(f"{self._size[0]}x{self._size[1]}+0+0")
        root.update_idletasks()
        hwnd = int(root.wm_frame(), 16)
        self._hwnd = hwnd
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        self._state = "hide"
        self._started = 0.0
        self._ready.set()
        root.after(50, self._tick)
        root.mainloop()

    def _show(self):
        area = _work_area_under_cursor()
        w, h = self._size
        x = area.left + (area.right - area.left - w) // 2
        y = area.bottom - h - int(60 * w / 170)
        # Move with the Win32 call (Tk ignores geometry for this window) and
        # never activate it.
        user32.SetWindowPos(self._hwnd, HWND_TOPMOST, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)
        self._root.attributes("-alpha", ALPHA)

    def _draw_wave(self):
        mid = self._wave_h / 2
        # half the round cap sticks out at each end, so keep it inside the canvas
        reach = (self._wave_h - self._bar_w) / 2
        for i, (bar, level) in enumerate(zip(self._bars, self._levels)):
            x = i * (self._bar_w + self._bar_gap) + self._bar_w / 2
            half = max(reach * level, 0.5)  # silent = a small dot
            self._wave.coords(bar, x, mid - half, x, mid + half)

    def _tick(self):
        try:
            while True:
                state = self._queue.get_nowait()
                if state == "recording":
                    self._started = time.monotonic()
                    self._levels = [0.0] * BARS
                    self._level_source()  # drop anything left from before
                    self._draw_wave()
                    self._dot.configure(fg=RED)
                    self._wave.pack(side="left", padx=self._wave_pad, before=self._text)
                    self._show()
                elif state == "transcribing":
                    self._dot.configure(fg=BLUE)
                    self._wave.pack_forget()
                    self._text.configure(text="  识别中…")
                else:
                    self._root.attributes("-alpha", 0.0)
                self._state = state
        except queue.Empty:
            pass
        if self._state == "recording":
            seconds = int(time.monotonic() - self._started)
            self._text.configure(text=f"{seconds // 60}:{seconds % 60:02d}")
            # gentle blink so it reads as "live"
            self._dot.configure(fg=RED if int(time.monotonic() * 2) % 2 == 0 else "#a33")
            self._levels = self._levels[1:] + [_bar_height(self._level_source())]
            self._draw_wave()
        self._root.after(TICK_RECORDING_MS if self._state == "recording" else TICK_IDLE_MS, self._tick)
