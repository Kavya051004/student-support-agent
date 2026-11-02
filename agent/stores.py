"""Simple file-based storage: students, support requests, password hashing."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import shutil
from pathlib import Path

from .config import DATA_DIR


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ---------- passwords (stored as salted hashes, never plain text) ----------
def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or os.urandom(8).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def check_password(password: str, stored: str) -> bool:
    salt = stored.split("$", 1)[0]
    return hmac.compare_digest(hash_password(password, salt), stored)


# ---------- students ----------
class StudentStore:
    """Works on a COPY of data/students.json inside the runtime folder,
    so your original dataset is never changed by the demo."""

    def __init__(self, runtime_dir: Path):
        runtime_dir.mkdir(parents=True, exist_ok=True)
        self.path = runtime_dir / "students.json"
        if not self.path.exists():
            shutil.copy(DATA_DIR / "students.json", self.path)

    def _all(self) -> list[dict]:
        return read_json(self.path, [])

    def get(self, student_id: str) -> dict | None:
        for s in self._all():
            if s["student_id"] == student_id:
                return s
        return None

    def update_field(self, student_id: str, field: str, value: str) -> None:
        students = self._all()
        for s in students:
            if s["student_id"] == student_id:
                s[field] = value
                write_json(self.path, students)
                return
        raise KeyError(student_id)

    def authenticate(self, user_id: str, password: str) -> dict | None:
        """Returns {user_id, name, role} if the password is right, else None."""
        user_id = user_id.strip().upper()
        for s in self._all():
            if s["student_id"] == user_id and check_password(password, s["password_hash"]):
                return {"user_id": user_id, "name": s["name"], "role": "student"}
        for st in read_json(DATA_DIR / "staff.json", []):
            if st["staff_id"] == user_id and check_password(password, st["password_hash"]):
                return {"user_id": user_id, "name": st["name"], "role": "staff"}
        return None

    def student_ids(self) -> list[str]:
        return [s["student_id"] for s in self._all()]


# ---------- support requests (tickets) ----------
class SupportRequestStore:
    def __init__(self, runtime_dir: Path):
        self.path = runtime_dir / "support_requests.json"

    def create(self, student_id: str, issue: str, category: str) -> dict:
        items = read_json(self.path, [])
        ticket = {
            "ticket_id": f"SR-{len(items) + 1:04d}",
            "student_id": student_id,
            "category": category,
            "issue": issue,
            "status": "Open",
            "created_at": now_iso(),
        }
        items.append(ticket)
        write_json(self.path, items)
        return ticket

    def list(self) -> list[dict]:
        return read_json(self.path, [])
