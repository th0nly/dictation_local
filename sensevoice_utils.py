"""Shared helpers: log, history, clipboard and chimes.

Only text lengths are logged (history/sensevoice.log), never the dictated text.
The text itself is kept in history/history.jsonl. Both are capped; the limits
are in config.py.
"""

import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import threading
import time
import winsound
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

HISTORY_DIR = Path(__file__).with_name("history")
LOG_PATH = HISTORY_DIR / "sensevoice.log"
HISTORY_PATH = HISTORY_DIR / "history.jsonl"
HISTORY_MAX = config.HISTORY_MAX
LOG_MAX_LINES = config.LOG_MAX_LINES
SOUNDS_DIR = Path(__file__).with_name("sounds")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

user32.OpenClipboard.argtypes = [wt.HWND]
user32.OpenClipboard.restype = wt.BOOL
user32.CloseClipboard.restype = wt.BOOL
user32.EmptyClipboard.restype = wt.BOOL
user32.GetClipboardData.argtypes = [wt.UINT]
user32.GetClipboardData.restype = wt.HANDLE
user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
user32.SetClipboardData.restype = wt.HANDLE
user32.IsClipboardFormatAvailable.argtypes = [wt.UINT]
user32.IsClipboardFormatAvailable.restype = wt.BOOL
kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wt.HGLOBAL
kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
kernel32.GlobalLock.restype = wt.LPVOID
kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
kernel32.GlobalUnlock.restype = wt.BOOL
kernel32.GlobalFree.argtypes = [wt.HGLOBAL]
kernel32.GlobalFree.restype = wt.HGLOBAL
ERROR_ALREADY_EXISTS = 183


def append_capped(path, line, max_lines):
    """Append one line and keep only the newest max_lines lines.

    Appending is cheap and never loses old lines on a crash. When the file
    grows past the limit it is rewritten to a temp file and swapped in with
    os.replace, which is atomic, so the file is never half-written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # The file may have been saved by an editor without a final newline.
    if path.exists() and path.stat().st_size > 0:
        with path.open("rb") as f:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                line = "\n" + line
    with path.open("a", encoding="utf-8") as f:
        f.write(line)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if len(lines) > max_lines:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text("".join(lines[-max_lines:]), encoding="utf-8")
        os.replace(tmp, path)


_log_lock = threading.Lock()


def log(message):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n"
    with _log_lock:
        try:
            append_capped(LOG_PATH, line, LOG_MAX_LINES)
        except OSError:
            pass


def play_chime(kind):
    """Soft chime: kind "start" (low -> high) or "end" (high -> low)."""
    try:
        winsound.PlaySound(
            str(SOUNDS_DIR / f"{kind}.wav"), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
        )
    except RuntimeError:
        pass


_history_lock = threading.Lock()


def save_history(text, source):
    """Append one entry (JSON Lines); keep only the newest HISTORY_MAX."""
    entry = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "chars": len(text),
        "text": text,
    }
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with _history_lock:
        try:
            append_capped(HISTORY_PATH, line, HISTORY_MAX)
        except OSError as exc:
            log(f"history write failed {type(exc).__name__}: {exc}")


def _open_clipboard():
    for _ in range(50):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def read_clipboard_text():
    if not _open_clipboard():
        return None
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def write_clipboard_text(text):
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
    if not handle:
        return False
    ptr = kernel32.GlobalLock(handle)
    ctypes.memmove(ptr, data, size)
    kernel32.GlobalUnlock(handle)
    if not _open_clipboard():
        kernel32.GlobalFree(handle)
        return False
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        return True  # the clipboard owns the memory now
    finally:
        user32.CloseClipboard()
