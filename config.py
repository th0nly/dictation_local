"""Settings you may want to change. Restart the program after editing
(run stop_sensevoice.cmd, then start_sensevoice.cmd; see getting-started/项目说明.md)."""

# The key you tap to start/stop dictation. 0xA5 = Right Alt.
# Other single keys: 0xA3 = Right Ctrl, 0xA1 = Right Shift, 0x7C = F13.
HOTKEY_VK = 0xA5
HOTKEY_LABEL = "Right Alt"

# SenseVoice model folder (relative to this project) and how it runs.
MODEL_DIR = "models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
NUM_THREADS = 4       # CPU threads used while transcribing
LANGUAGE = "auto"     # "auto", "zh", "en", "ja", "ko" or "yue"

# A recording stops by itself after this many seconds (in case you forget it).
MAX_RECORD_SECONDS = 300

# Waveform in the indicator bar (display only, does not affect recognition).
# Loudness in dBFS: 0 = the loudest the mic can record, more negative = quieter.
# At or below WAVE_SILENCE_DB the bars are flat dots (set it a few dB above your
# room noise, which was about -42 dB when measured); at WAVE_LOUD_DB or louder
# they are full height. A wider gap = more steps between far and close.
WAVE_SILENCE_DB = -38.0
WAVE_LOUD_DB = -10.0
# > 1 makes quiet sounds smaller while loud ones stay tall (more contrast).
WAVE_CURVE = 1.6

# history/history.jsonl keeps only the newest N dictations.
HISTORY_MAX = 200

# history/sensevoice.log keeps only the newest N lines.
LOG_MAX_LINES = 500
