"""Sign-in, per-user homes and Firestore storage (with an in-memory fake Firestore)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nestra.auth import AuthError, UserInfo
from nestra.main import Settings, create_app
from nestra.simulator import Home, SimClock
from nestra.simulator.home import ActivityEntry, DEFAULT_CONFIG
from nestra.store import FirestoreStore, StoreWriter


class FakeAuth:
    """Tokens "token-alice" / "token-bob" are valid; anything else is rejected."""

    mode = "firebase"

    def verify(self, token):
        if token and token.startswith("token-"):
            name = token.removeprefix("token-")
            return UserInfo(uid=f"uid-{name}", email=f"{name}@example.com")
        raise AuthError("Sign in required")


def _app(tmp_path, **settings):
    s = Settings(start_hour=14, time_scale=0, homes_dir=tmp_path / "homes", state_file=tmp_path / "local.json", **settings)
    return create_app(settings=s, simulate=False, authenticator=FakeAuth())


def _auth(name):
    return {"Authorization": f"Bearer token-{name}"}


def test_requests_without_sign_in_are_rejected(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        assert client.get("/api/home").status_code == 401
        assert client.get("/api/home", headers={"Authorization": "Bearer nope"}).status_code == 401
        assert client.get("/api/health").status_code == 200  # public


def test_each_user_gets_their_own_home(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        me = client.get("/api/me", headers=_auth("alice")).json()
        assert me["uid"] == "uid-alice" and me["email"] == "alice@example.com"

        # New users start with the usual rooms and devices, all off.
        home = client.get("/api/home", headers=_auth("alice")).json()
        rooms = {r["name"]: sorted(d["type"] for d in r["devices"]) for r in home["rooms"]}
        assert rooms == {
            "Living Room": ["ac", "fan", "light"],
            "Bedroom": ["ac", "fan", "light"],
            "Kitchen": ["fan", "light"],
        }
        assert not any(d["on"] for r in home["rooms"] for d in r["devices"])

        client.post("/api/devices", headers=_auth("alice"),
                    json={"type": "appliance", "name": "Bedside Speaker", "room_id": "bedroom", "kind": "speaker"})
        r = client.post("/api/command", headers=_auth("alice"), json={"text": "turn on the bedroom fan"})
        assert r.json()["ok"]

        bob = client.get("/api/home", headers=_auth("bob")).json()
        bob_bedroom = next(r for r in bob["rooms"] if r["id"] == "bedroom")
        assert all(d["name"] != "Bedside Speaker" for d in bob_bedroom["devices"]), "Bob must not see Alice's speaker"
        assert not any(d["on"] for d in bob_bedroom["devices"]), "Alice's command must not touch Bob's fan"

    # Saved per user.
    assert "Bedside Speaker" in (tmp_path / "homes" / "uid-alice.json").read_text()
    assert "Bedside Speaker" not in (tmp_path / "homes" / "uid-bob.json").read_text()


def test_websocket_requires_auth_message(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": "bad"})
            msg = ws.receive_json()
            assert msg["type"] == "error" and msg["data"]["code"] == 401

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": "token-alice"})
            snap = ws.receive_json()
            assert snap["type"] == "snapshot"
            assert snap["data"]["rooms"][0]["name"] == "Living Room"


# ------------------------------------------------------------- fake Firestore
class _Snap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _Doc:
    def __init__(self):
        self.data = None
        self.children: dict[str, _Collection] = {}

    def get(self):
        return _Snap(self.data)

    def set(self, data):
        self.data = dict(data)

    def collection(self, name):
        return self.children.setdefault(name, _Collection())


class _Collection:
    def __init__(self):
        self.docs: dict[str, _Doc] = {}
        self._desc = False
        self._limit = None

    def document(self, doc_id):
        return self.docs.setdefault(doc_id, _Doc())

    def order_by(self, field, direction=None):
        # Like real Firestore: sorting on the document id descending needs a custom index.
        self._desc = direction is not None and "DESC" in str(direction).upper()
        if field == "__name__" and self._desc:
            raise RuntimeError("400 The query requires an index")
        self._field = field
        return self

    def limit(self, n):
        self._limit = n
        return self

    def stream(self):
        docs = [d.data for d in self.docs.values() if d.data is not None]
        docs.sort(key=lambda d: d[self._field], reverse=self._desc)
        return [_Snap(d) for d in docs[: self._limit]]


class FakeFirestore:
    def __init__(self):
        self.root: dict[str, _Collection] = {}

    def collection(self, name):
        return self.root.setdefault(name, _Collection())


def test_firestore_store_round_trip():
    db = FakeFirestore()
    store = FirestoreStore(db, "uid-alice")
    assert store.load() is None

    home = Home.from_file(DEFAULT_CONFIG, clock=SimClock.at_hour(14))
    writer = StoreWriter(home, store)
    home.add_device("appliance", "Kettle", "kitchen", kind="kettle")
    home.update_device("living_air_circulator", {"speed": 30})
    home.log("Something happened", source="manual")
    writer.flush()

    saved = store.load()
    assert saved is not None
    assert any(d.name == "Kettle" for d in saved.devices)
    assert next(d for d in saved.devices if d.id == "living_air_circulator").speed == 30

    history = store.recent_activity(10)
    assert history[0].title == "Something happened"  # newest first

    # A restarted home continues the history and numbering.
    restored = Home(saved, clock=SimClock.at_hour(14))
    restored.restore_activity(history)
    entry = restored.log("After restart")
    assert entry.id > max(e.id for e in history)


def test_firestore_document_path():
    db = FakeFirestore()
    FirestoreStore(db, "uid-123").save(Home.from_file(DEFAULT_CONFIG).to_config())
    assert db.root["homes"].docs["uid-123"].data["name"] == "Nestra Demo Home"
    assert "updated_at" in db.root["homes"].docs["uid-123"].data


def test_activity_entry_ids_sort_in_firestore():
    db = FakeFirestore()
    store = FirestoreStore(db, "u")
    for i in (9, 10, 11):
        store.append_activity(ActivityEntry(id=i, time=f"2026-11-09T10:00:{i:02d}", title=f"e{i}"))
    assert [e.id for e in store.recent_activity(3)] == [11, 10, 9]


@pytest.mark.parametrize("value", ["none", "firebase"])
def test_health_reports_auth_mode(tmp_path, value):
    s = Settings(start_hour=14, time_scale=0, state_file=tmp_path / "x.json")
    auth = FakeAuth() if value == "firebase" else None
    with TestClient(create_app(settings=s, simulate=False, authenticator=auth)) as client:
        assert client.get("/api/health").json()["auth"] == value


def test_home_opens_even_if_history_fails(tmp_path):
    from nestra.sessions import SessionManager

    class BrokenHistory(FirestoreStore):
        def recent_activity(self, limit):
            raise RuntimeError("400 The query requires an index")

    db = FakeFirestore()
    FirestoreStore(db, "u").save(Home.from_file(DEFAULT_CONFIG).to_config())
    manager = SessionManager(clock=SimClock.at_hour(14), store_for=lambda uid: BrokenHistory(db, uid),
                             new_home=lambda uid: None)
    session = manager.get("u")
    assert session.home.devices  # loaded despite the history error
