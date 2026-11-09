"""Speech-to-text with Whisper (faster-whisper), running locally on this machine.

Audio never leaves the computer. The model downloads once on first use
(about 145 MB for "base.en") and is cached by Hugging Face.

Whisper gets a hint listing the home's rooms and devices, so it spells
"Aircond" or "Ceiling Fan" the way the command parser expects.
"""

from __future__ import annotations

import io
import logging
import os
import threading
import time
from dataclasses import dataclass

from .simulator import Home

log = logging.getLogger("nestra.voice")

# tiny.en (fastest) < base.en < small.en (most accurate, ~460 MB). ".en" models are English-only and faster.
DEFAULT_MODEL = os.getenv("NESTRA_WHISPER_MODEL", "base.en")


@dataclass
class Transcript:
    text: str
    seconds: float  # how long transcription took
    language: str | None = None


class SpeechToText:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self):
        """Load (and on first run download) the model. Safe to call from several threads."""
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                started = time.perf_counter()
                self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
                log.info("Whisper %s ready in %.1fs", self.model_name, time.perf_counter() - started)
            return self._model

    def preload_in_background(self) -> None:
        threading.Thread(target=self._safe_load, name="whisper-load", daemon=True).start()

    def _safe_load(self) -> None:
        try:
            self.load()
        except Exception:
            log.exception("Could not load Whisper model %s", self.model_name)

    def transcribe(self, audio: bytes, *, hint: str = "") -> Transcript:
        model = self.load()
        started = time.perf_counter()
        segments, info = model.transcribe(
            decode_audio(audio),
            beam_size=1,
            vad_filter=True,  # skip silence before/after speaking
            condition_on_previous_text=False,
            initial_prompt=hint or None,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        return Transcript(text=text, seconds=time.perf_counter() - started, language=getattr(info, "language", None))


SAMPLE_RATE = 16000  # what Whisper expects


def decode_audio(data: bytes):
    """Any common recording format (webm/opus, ogg, mp4/aac, wav...) -> 16 kHz mono float32 samples.

    Done here rather than by faster-whisper so it keeps working across PyAV versions.
    """
    import av
    import numpy as np

    chunks = []
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    with av.open(io.BytesIO(data), mode="r") as container:
        stream = next(s for s in container.streams if s.type == "audio")
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):  # flush
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return normalize(np.concatenate(chunks).astype(np.float32) / 32768.0)


TARGET_PEAK = 0.9
MAX_GAIN = 20.0  # up to +26 dB, so speech from across the room is loud enough for Whisper


def normalize(samples):
    """Boost quiet recordings (speaking from further away) to a steady level.

    Gain is capped so a recording of near-silence doesn't turn into loud noise.
    """
    import numpy as np

    if samples.size == 0:
        return samples
    peak = float(np.max(np.abs(samples)))
    if peak <= 0:
        return samples
    gain = min(TARGET_PEAK / peak, MAX_GAIN)
    if gain <= 1:
        return samples
    return np.clip(samples * gain, -1.0, 1.0).astype(np.float32)


def vocabulary_hint(home: Home) -> str:
    """A short prompt that nudges Whisper toward this home's words."""
    rooms = ", ".join(r.name for r in home.rooms.values())
    devices = ", ".join(sorted({d.name for d in home.devices.values()}))
    return (
        f"Smart home commands for Nestra. Rooms: {rooms}. Devices: {devices}. "
        "Turn on the aircond, set the fan to low, make it comfortable, a bit cooler."
    )
