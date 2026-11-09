"""/api/voice with a stand-in for Whisper (the real model is exercised manually)."""

from fastapi.testclient import TestClient

from nestra.main import Settings, create_app
from nestra.voice import Transcript, decode_audio


class FakeSpeech:
    loaded = True

    def __init__(self, text):
        self.text = text
        self.hints = []

    def transcribe(self, audio, *, hint=""):
        self.hints.append(hint)
        return Transcript(text=self.text, seconds=0.1)

    def preload_in_background(self):
        pass


def _client(tmp_path, speech):
    s = Settings(start_hour=14, time_scale=0, state_file=tmp_path / "home.json")
    return TestClient(create_app(settings=s, simulate=False, speech=speech))


def test_voice_command_runs_the_transcript(tmp_path):
    speech = FakeSpeech("Turn on the reading lamp.")
    with _client(tmp_path, speech) as client:
        r = client.post("/api/voice", files={"audio": ("cmd.webm", b"fake-audio", "audio/webm")})
        body = r.json()
        assert r.status_code == 200 and body["ok"]
        assert body["transcript"] == "Turn on the reading lamp."
        assert "Reading Lamp" in speech.hints[0]  # vocabulary hint includes device names
        assert client.get("/api/devices/living_reading_lamp").json()["on"]


def test_silence_is_handled(tmp_path):
    with _client(tmp_path, FakeSpeech("")) as client:
        body = client.post("/api/voice", files={"audio": ("a.webm", b"x", "audio/webm")}).json()
        assert not body["ok"] and "didn't catch" in body["reply"]


def test_empty_upload_rejected(tmp_path):
    with _client(tmp_path, FakeSpeech("hi")) as client:
        assert client.post("/api/voice", files={"audio": ("a.webm", b"", "audio/webm")}).status_code == 422


def test_decode_audio_handles_wav():
    import io
    import wave

    import numpy as np

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes((np.sin(np.linspace(0, 400, 8000)) * 10000).astype("<i2").tobytes())
    samples = decode_audio(buf.getvalue())
    assert samples.dtype == np.float32
    assert 15000 <= len(samples) <= 17000  # 1 s resampled to 16 kHz


def test_quiet_recordings_are_boosted_but_capped():
    import numpy as np

    from nestra.voice import MAX_GAIN, TARGET_PEAK, normalize

    quiet = np.array([0.0, 0.05, -0.1], dtype=np.float32)
    assert np.isclose(np.max(np.abs(normalize(quiet))), TARGET_PEAK)
    hiss = np.array([0.001, -0.001], dtype=np.float32)
    assert np.isclose(np.max(np.abs(normalize(hiss))), 0.001 * MAX_GAIN)
    loud = np.array([0.95, -0.5], dtype=np.float32)
    assert np.array_equal(normalize(loud), loud)
