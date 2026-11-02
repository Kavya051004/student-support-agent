"""Persistent memory (survives restarts / new chat sessions).

RULES (enforced in code, not by the AI):
  1. Only keys in ALLOWED_KEYS can be saved (profile facts and preferences).
  2. Anything that looks like an OTP / password / card number is refused.
  3. Words that mean "temporary" (today, tomorrow, right now ...) are refused.
Memory is stored per student: memory/<student_id>.json
"""
from __future__ import annotations

import re
from pathlib import Path

from .security import detect_sensitive
from .stores import now_iso, read_json, write_json

# key -> words in a question that make this memory item "relevant"
ALLOWED_KEYS: dict[str, set[str]] = {
    "programme": {"programme", "program", "course", "courses", "pgdm", "batch", "branch", "stream", "which"},
    "specialisation": {"specialisation", "specialization", "major", "stream", "track", "elective"},
    "preferred_language": set(),                       # style item -> always included
    "preferred_contact_method": {"contact", "call", "email", "phone", "reach", "notify", "message"},
    "preferred_elective": {"elective", "electives", "subject", "drop", "add", "change"},
}
ALWAYS_INCLUDE = {"preferred_language"}

_TEMPORARY = re.compile(
    r"\b(today|tomorrow|tonight|yesterday|right now|currently|at the|this week|this weekend|"
    r"next week|travel|travelling|traveling|library|hospital|sick|late today)\b", re.I)


class MemoryStore:
    def __init__(self, runtime_dir: Path):
        self.dir = runtime_dir / "memory"

    def _path(self, student_id: str) -> Path:
        return self.dir / f"{student_id}.json"

    def load(self, student_id: str) -> list[dict]:
        return read_json(self._path(student_id), [])

    def save(self, student_id: str, key: str, value: str) -> dict:
        """Returns {"saved": True, ...} or {"saved": False, "reason": ...}."""
        key = re.sub(r"[^a-z0-9_]+", "_", str(key).strip().lower()).strip("_")
        value = str(value).strip()
        if key not in ALLOWED_KEYS:
            return {"saved": False, "reason": f"'{key}' is not a long-term profile fact or preference. "
                    f"Allowed: {', '.join(ALLOWED_KEYS)}."}
        if not value or len(value) > 80:
            return {"saved": False, "reason": "Value is empty or too long."}
        if detect_sensitive(value):
            return {"saved": False, "reason": "Sensitive data (OTP/password/card/id) is never stored."}
        if _TEMPORARY.search(value):
            return {"saved": False, "reason": "That looks temporary, so it is not stored in long-term memory."}
        items = [i for i in self.load(student_id) if i["key"] != key]
        items.append({"key": key, "value": value, "saved_at": now_iso()})
        write_json(self._path(student_id), items)
        return {"saved": True, "key": key, "value": value}

    def select(self, student_id: str, question: str) -> list[dict]:
        """Context selection for memory: return only the items relevant to this question."""
        words = set(re.findall(r"[a-z0-9]+", question.lower()))
        chosen = []
        for item in self.load(student_id):
            triggers = ALLOWED_KEYS.get(item["key"], set())
            value_words = set(re.findall(r"[a-z0-9]+", item["value"].lower()))
            if (item["key"] in ALWAYS_INCLUDE or words & triggers
                    or (words & value_words - {"the", "of", "and", "in"})):
                chosen.append(item)
        return chosen
