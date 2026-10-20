"""Microphone recording + local speech-to-text with SenseVoice (sherpa-onnx).

Everything runs on this PC: no network, no account, no usage limits.
The model is loaded once in the background at startup and stays in memory.
"""

import os
import sys
import threading

import numpy as np
import sherpa_onnx
import sounddevice as sd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

SAMPLE_RATE = 16000  # what SenseVoice expects
HERE = os.path.dirname(os.path.abspath(__file__))


class Engine:
    """SenseVoice recognizer, loaded in a background thread (~1 s)."""

    def __init__(self):
        self._recognizer = None
        self._error = None
        self._loaded = threading.Event()
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            model_dir = os.path.join(HERE, config.MODEL_DIR)
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=os.path.join(model_dir, "model.int8.onnx"),
                tokens=os.path.join(model_dir, "tokens.txt"),
                num_threads=config.NUM_THREADS,
                language=config.LANGUAGE,
                use_itn=True,  # punctuation, and "九点" -> "9点"
            )
        except Exception as exc:  # reported on first use
            self._error = exc
        self._loaded.set()

    def transcribe(self, audio):
        self._loaded.wait()
        if self._error is not None:
            raise RuntimeError(f"model failed to load: {self._error}")
        stream = self._recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, audio)
        self._recognizer.decode_stream(stream)
        return stream.result.text.strip()


class Recorder:
    """Records the default microphone only between start() and stop()."""

    def __init__(self):
        self._stream = None
        self._chunks = []
        self._energy = 0.0  # sum of squared samples since the indicator last looked
        self._count = 0
        self._devices_lock = threading.Lock()

    @property
    def recording(self):
        return self._stream is not None

    def start(self):
        self._chunks = []
        self._energy, self._count = 0.0, 0
        with self._devices_lock:
            try:
                self._open()
            except Exception:
                # Mic unplugged/replugged or PC woke from sleep: the device
                # list PortAudio read at startup is stale. Re-read it once.
                self._refresh_devices()
                self._open()

    def _open(self):
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=self._on_audio)
        stream.start()
        self._stream = stream

    @staticmethod
    def _refresh_devices():
        sd._terminate()
        sd._initialize()

    def _on_audio(self, indata, frames, time_info, status):
        block = indata[:, 0].copy()
        self._chunks.append(block)
        self._energy += float(np.dot(block, block))
        self._count += len(block)

    def take_level(self):
        """Average loudness (RMS) since the last call, for the indicator's waveform.

        An average over the whole ~50 ms, not the loudest 10 ms block, so a
        short click or knock does not shoot the bar to full height."""
        energy, count = self._energy, self._count
        self._energy, self._count = 0.0, 0
        return (energy / count) ** 0.5 if count else 0.0

    def stop(self):
        """Stops recording and returns the audio (float32, 16 kHz, mono)."""
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
            # Re-read the device list in the background (~150 ms), so a newly
            # plugged-in mic or a changed default mic is used next time.
            threading.Thread(target=self._refresh_in_background, daemon=True).start()
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._chunks)

    def _refresh_in_background(self):
        with self._devices_lock:
            if self._stream is None:
                self._refresh_devices()
