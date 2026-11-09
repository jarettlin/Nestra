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


def test_wake_phrase_variants():
    from nestra.wake import split_wake

    for text, command in [
        ("Hi Nestra, turn on the fan.", "turn on the fan."),
        ("Hey, Nestra. Make it cooler", "Make it cooler"),
        ("Hi Nestor turn off the lights", "turn off the lights"),
        ("Hinestra, dim the lights", "dim the lights"),
        ("Hi, Ness tra.", ""),
        ("Nestra, close the blinds", "close the blinds"),
        ("Okay Nestra", ""),
    ]:
        w = split_wake(text)
        assert w.heard and w.command == command, text
    for text in ["Turn on the fan", "Hi mom, how are you", "That's extra", "I like Nestor", "Pass the remote", ""]:
        assert not split_wake(text).heard, text


def test_hands_free_ignores_speech_without_wake_phrase(tmp_path):
    with _client(tmp_path, FakeSpeech("Turn off the reading lamp.")) as client:
        before = client.get("/api/devices/living_reading_lamp").json()["on"]
        body = client.post("/api/voice", data={"wake": "true"}, files={"audio": ("a.wav", b"x", "audio/wav")}).json()
        assert body["woke"] is False and "transcript" not in body
        assert client.get("/api/devices/living_reading_lamp").json()["on"] == before
        assert len(client.get("/api/activity").json()) <= 1  # nothing logged


def test_hands_free_wake_then_command(tmp_path):
    with _client(tmp_path, FakeSpeech("Hi Nestra.")) as client:
        body = client.post("/api/voice", data={"wake": "true"}, files={"audio": ("a.wav", b"x", "audio/wav")}).json()
        assert body["woke"] and body["listen"] and body["reply"]
    speech = FakeSpeech("Hey Nestra, turn off the reading lamp")
    with _client(tmp_path, speech) as client:
        body = client.post("/api/voice", data={"wake": "true"}, files={"audio": ("a.wav", b"x", "audio/wav")}).json()
        assert body["woke"] and body["ok"] and body["command"] == "turn off the reading lamp"
        assert not client.get("/api/devices/living_reading_lamp").json()["on"]


def test_conversation_needs_no_wake_phrase_and_ends_on_thanks(tmp_path):
    speech = FakeSpeech("turn off the reading lamp")
    with _client(tmp_path, speech) as client:
        form = {"wake": "true", "conversation": "true"}
        body = client.post("/api/voice", data=form, files={"audio": ("a.wav", b"x", "audio/wav")}).json()
        assert body["ok"] and not body.get("end")
        assert not client.get("/api/devices/living_reading_lamp").json()["on"]
        for bye in ["Thank you.", "No, that's all.", "That's it, thanks", "Nothing else", "I'm good", "Okay thanks Nestra"]:
            speech.text = bye
            body = client.post("/api/voice", data=form, files={"audio": ("a.wav", b"x", "audio/wav")}).json()
            assert body["end"] and body["reply"], bye


def test_goodbye_detection():
    from nestra.replies import is_goodbye

    for text in ["thanks", "Thank you so much", "that's all", "No thanks", "Nope, that's it.", "goodbye", "never mind", "ok thanks", "alright that is all"]:
        assert is_goodbye(text), text
    for text in ["turn off the lights", "thanks, now turn off the fan", "all lights off", "stop the fan"]:
        assert not is_goodbye(text), text


def test_friendly_replies_vary_but_keep_the_facts():
    from nestra.replies import friendly

    seen = set()
    for _ in range(40):
        reply = friendly({"ok": True, "reply": "Main Light turned on."}, follow_up=True)["reply"]
        assert "Main Light" in reply and "on" in reply
        seen.add(reply)
    assert len(seen) > 5
    failed = {"ok": False, "reply": "Which room?"}
    assert friendly(failed)["reply"] == "Which room?"


def test_answering_nestras_questions_by_voice(tmp_path):
    speech = FakeSpeech("the bedroom")
    with _client(tmp_path, speech) as client:
        form = {"conversation": "true", "previous": "turn on the light"}
        body = client.post("/api/voice", data=form, files={"audio": ("a.wav", b"x", "audio/wav")}).json()
        assert body["ok"] and "Ceiling Light" in body["reply"], body  # the bedroom's light
        speech.text = "yes please"
        form = {"conversation": "true", "previous": "unlock the front door"}
        body = client.post("/api/voice", data=form, files={"audio": ("a.wav", b"x", "audio/wav")}).json()
        assert body["ok"] and not client.get("/api/devices/front_door").json()["locked"]
        speech.text = "no"
        form = {"conversation": "true", "previous": "turn on the bedroom fan"}
        body = client.post("/api/voice", data=form, files={"audio": ("a.wav", b"x", "audio/wav")}).json()
        assert body["ok"] and "changes" not in body  # declined: nothing run
