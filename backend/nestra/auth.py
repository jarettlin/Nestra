"""Who is calling: verifies Firebase ID tokens sent by the app.

Modes:
  none      no login; everyone shares one local home (uid "local"). Used for
            development and tests.
  firebase  every request must carry a Firebase ID token
            (`Authorization: Bearer <token>`, or an auth message on the WebSocket).
            With FIREBASE_AUTH_EMULATOR_HOST set, tokens from the local Auth
            emulator are accepted instead.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class UserInfo:
    uid: str
    email: str | None = None
    name: str | None = None


LOCAL_USER = UserInfo(uid="local", email=None, name=None)


class Authenticator(Protocol):
    mode: str

    def verify(self, token: str | None) -> UserInfo: ...


class NoAuth:
    mode = "none"

    def verify(self, token: str | None) -> UserInfo:
        return LOCAL_USER


def find_project_id(credentials_path: Path | None, explicit: str | None = None) -> str | None:
    """Project id from settings, the service-account file, or the repo's .firebaserc."""
    if explicit:
        return explicit
    if credentials_path and credentials_path.exists():
        project = json.loads(credentials_path.read_text()).get("project_id")
        if project:
            return project
    for env in ("GOOGLE_CLOUD_PROJECT", "GCLOUD_PROJECT"):
        if os.getenv(env):
            return os.environ[env]
    rc = Path(__file__).resolve().parents[2] / ".firebaserc"
    if rc.exists():
        return json.loads(rc.read_text()).get("projects", {}).get("default")
    return None


def firebase_app(credentials_path: Path | None, project_id: str | None):
    """The shared firebase_admin app, created on first use."""
    import firebase_admin
    from firebase_admin import credentials

    try:
        return firebase_admin.get_app()
    except ValueError:
        pass
    options = {"projectId": project_id} if project_id else None
    if credentials_path and credentials_path.exists():
        return firebase_admin.initialize_app(credentials.Certificate(str(credentials_path)), options)
    if not project_id:
        raise RuntimeError("Firebase project id unknown: set NESTRA_FIREBASE_PROJECT or add .firebaserc")
    # Without a key, Google's default credentials are looked up lazily. Verifying
    # sign-in tokens (and the emulators) only needs the project id; Firestore
    # needs a key, which require_credentials() checks.
    return firebase_admin.initialize_app(options=options)


def require_credentials(credentials_path: Path) -> None:
    if os.getenv("FIRESTORE_EMULATOR_HOST") or credentials_path.exists():
        return
    raise RuntimeError(
        f"Firestore storage needs a service-account key at {credentials_path}. In the Firebase console: "
        "Project settings → Service accounts → Generate new private key, then save the file there "
        "(it is git-ignored). Never commit or share it."
    )


class FirebaseAuth:
    mode = "firebase"

    def __init__(self, app) -> None:
        self._app = app

    def verify(self, token: str | None) -> UserInfo:
        from firebase_admin import auth

        if not token:
            raise AuthError("Sign in required")
        try:
            claims = auth.verify_id_token(token, app=self._app)
        except Exception as e:  # expired, revoked, malformed, wrong project...
            raise AuthError("Your session has expired. Please sign in again.") from e
        return UserInfo(uid=claims["uid"], email=claims.get("email"), name=claims.get("name"))
