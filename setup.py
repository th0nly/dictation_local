"""One-time setup on a (new) Windows PC. Run:  python setup.py

1. Creates .venv in this folder and installs requirements.txt
   (sherpa-onnx, numpy, sounddevice; about 120 MB).
2. Downloads the SenseVoice int8 model (about 230 MB) into models/.
3. Generates the start/end sounds if missing.
4. Stops an older copy of the program and starts it.
5. Optionally sets up autostart at login.

Safe to run again: finished steps are skipped.
Options: --yes (no questions, no autostart), --autostart (also autostart).
"""

import os
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config  # noqa: E402
import make_sounds  # noqa: E402

VENV_PYTHON = HERE / ".venv" / "Scripts" / "python.exe"
MODEL_DIR = HERE / config.MODEL_DIR
MODEL_URL = (
    "https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
    "/resolve/main/{name}"
)
MODEL_FILES = {"model.int8.onnx": 239233841, "tokens.txt": 315894}  # name -> bytes


def make_venv():
    if not VENV_PYTHON.exists():
        print("[..] creating .venv")
        subprocess.run([sys.executable, "-m", "venv", str(HERE / ".venv")], check=True)
    print("[..] installing packages (first time: about 1 minute)")
    subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
    subprocess.run(
        [str(VENV_PYTHON), "-m", "pip", "install", "-q", "-r", str(HERE / "requirements.txt")], check=True
    )
    print("[ok] .venv ready")


def download_model():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name, size in MODEL_FILES.items():
        target = MODEL_DIR / name
        if target.exists() and target.stat().st_size == size:
            continue
        print(f"[..] downloading {name} ({size / 2**20:.0f} MB)")
        tmp = target.with_name(name + ".part")

        def progress(blocks, block_size, total):
            done = min(blocks * block_size, total) if total > 0 else blocks * block_size
            print(f"\r     {done / 2**20:6.0f} / {size / 2**20:.0f} MB", end="", flush=True)

        urllib.request.urlretrieve(MODEL_URL.format(name=name), tmp, progress)
        print()
        if tmp.stat().st_size != size:
            tmp.unlink()
            sys.exit(f"{name}: download incomplete, run setup.py again.")
        os.replace(tmp, target)
    print("[ok] SenseVoice model ready")


def make_chimes():
    sounds = HERE / "sounds"
    if not (sounds / "start.wav").exists() or not (sounds / "end.wav").exists():
        sounds.mkdir(exist_ok=True)
        make_sounds.chime(sounds / "start.wav", [880.0, 1318.5])
        make_sounds.chime(sounds / "end.wav", [1318.5, 880.0])
    print("[ok] sounds ready")


def restart_program():
    subprocess.run(["cmd", "/c", str(HERE / "stop_sensevoice.cmd")], capture_output=True)
    # No inherited handles, so setup.py itself can exit while the program runs.
    subprocess.run(
        ["cmd", "/c", str(HERE / "start_sensevoice.cmd")],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    print(f"[ok] program started; tap {config.HOTKEY_LABEL} to dictate")


def main():
    assume_yes = "--yes" in sys.argv
    make_venv()
    download_model()
    make_chimes()
    restart_program()
    if "--autostart" in sys.argv or (
        not assume_yes and input("Start automatically at login? (y/n) ").strip().lower().startswith("y")
    ):
        subprocess.run(["cmd", "/c", str(HERE / "install_autostart.cmd")], input="\n", text=True)


if __name__ == "__main__":
    main()
