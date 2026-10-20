"""Generate the soft chime used for dictation start and finish."""
import math
import struct
import wave
from pathlib import Path

RATE = 44100


def chime(path, freqs, note_ms=110, gap_ms=20, volume=0.18):
    samples = []
    for f in freqs:
        n = int(RATE * note_ms / 1000)
        for i in range(n):
            t = i / RATE
            attack = min(1.0, i / (RATE * 0.008))  # 8 ms fade-in, no click
            decay = math.exp(-t * 28)              # soft bell-like tail
            tone = math.sin(2 * math.pi * f * t) + 0.25 * math.sin(2 * math.pi * 2 * f * t)
            samples.append(volume * attack * decay * tone / 1.25)
        samples.extend([0.0] * int(RATE * gap_ms / 1000))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in samples))


if __name__ == "__main__":
    out = Path(__file__).with_name("sounds")
    out.mkdir(exist_ok=True)
    chime(out / "start.wav", [880.0, 1318.5])  # low -> high: recording started
    chime(out / "end.wav", [1318.5, 880.0])    # high -> low: text delivered
    print("written", out / "start.wav", out / "end.wav")
