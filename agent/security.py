"""Assignment 2 building blocks: sessions (who is signed in), sensitive-data detection,
audit log and the human approval queue.

IMPORTANT IDEA: all of these rules are normal Python code. They do not depend on the
AI model "behaving well". Even if the model is tricked, this code still says NO.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .stores import now_iso, read_json, write_json


@dataclass
class Session:
    user_id: str       # e.g. "S1001" or "STAFF01"  (set by login, never by the chat text)
    role: str          # "student" or "staff"
    name: str = ""


# ---------------------------------------------------------------------------
# Sensitive data detection (OTP, password, card, government id)
# ---------------------------------------------------------------------------
_OTP_CONTEXT = re.compile(r"\b(otp|one[- ]time|verification code|passcode)\b", re.I)
_PATTERNS = [
    ("password", re.compile(r"\b(password|passwd|pwd|pin|cvv)\b\s*(?:is|=|:|-)\s*(\S+)", re.I)),
    ("otp", re.compile(r"\b(otp|one[- ]time[- ](?:password|code)|verification code|passcode)\b"
                       r"\s*(?:is|was|=|:|-)?\s*(\d{4,8})\b", re.I)),
    ("card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("government_id", re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")),
]


def redact(text: str) -> tuple[str, list[str]]:
    """Replace sensitive values with [REDACTED-...]. Returns (clean_text, kinds_found)."""
    kinds: list[str] = []
    clean = text
    for kind, pattern in _PATTERNS:
        def _sub(m, kind=kind):
            if kind not in kinds:
                kinds.append(kind)
            if kind in ("password", "otp"):
                return f"{m.group(1)} is [REDACTED-{kind.upper()}]"
            return f"[REDACTED-{kind.upper()}]"
        clean = pattern.sub(_sub, clean)
    # "The OTP I received is 482913" -> number is not right next to the word OTP
    if _OTP_CONTEXT.search(clean):
        def _num(m):
            if "otp" not in kinds:
                kinds.append("otp")
            return "[REDACTED-OTP]"
        clean = re.sub(r"\b\d{4,8}\b", _num, clean)
    return clean, kinds


def detect_sensitive(text: str) -> list[str]:
    return redact(text)[1]


def mask(value: str) -> str:
    """Show only the last 3 characters, e.g. 9876501234 -> *******234 (used in audit log)."""
    value = str(value)
    return "*" * max(len(value) - 3, 0) + value[-3:]


def safe_args(args: dict) -> dict:
    """Arguments that are safe to write into trace/audit logs."""
    out = {}
    for k, v in args.items():
        if k == "new_value":
            out[k] = mask(v)
        elif isinstance(v, str):
            out[k] = redact(v)[0]
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Audit log: who asked for what, was it allowed, what happened
# ---------------------------------------------------------------------------
class AuditLog:
    def __init__(self, runtime_dir: Path, enabled: bool):
        self.path = runtime_dir / "audit.jsonl"
        self.enabled = enabled

    def record(self, *, actor: str, role: str, action: str, target: str,
               decision: str, approval_status: str, result: str,
               args: dict | None = None, detail: str = "") -> None:
        """decision: allowed | blocked | approval_required
           approval_status: not_required | pending | approved | rejected
           result: success | error:<code> | denied | not_executed | pending_approval"""
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "time": now_iso(), "actor": actor, "role": role, "action": action,
            "target_student": target, "decision": decision,
            "approval_status": approval_status, "result": result,
            "args": safe_args(args or {}), "detail": redact(detail)[0],
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read(self, session: Session) -> list[dict]:
        """Only staff may read the audit log (checked here, in code)."""
        if session.role != "staff":
            raise PermissionError("Only staff can read the audit log.")
        return self.read_unchecked()

    def read_unchecked(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# Approval queue (human in the loop)
# ---------------------------------------------------------------------------
class ApprovalStore:
    def __init__(self, runtime_dir: Path):
        self.path = runtime_dir / "approvals.json"

    def create(self, student_id: str, action: str, args: dict, requested_by: str) -> dict:
        items = read_json(self.path, [])
        rec = {
            "approval_id": f"AP-{len(items) + 1:04d}",
            "student_id": student_id, "action": action,
            "args": args,                       # full value needed so staff can see what to approve
            "requested_by": requested_by, "requested_at": now_iso(),
            "status": "pending", "decided_by": None, "decided_at": None,
            "note": "", "result": None,
        }
        items.append(rec)
        write_json(self.path, items)
        return rec

    def list(self, status: str | None = None, student_id: str | None = None) -> list[dict]:
        items = read_json(self.path, [])
        if status:
            items = [i for i in items if i["status"] == status]
        if student_id:
            items = [i for i in items if i["student_id"] == student_id]
        return items

    def get(self, approval_id: str) -> dict | None:
        return next((i for i in self.list() if i["approval_id"] == approval_id), None)

    def decide(self, approval_id: str, approver: Session, approve: bool, note: str = "") -> dict:
        if approver.role != "staff":
            raise PermissionError("Only staff can approve or reject requests.")
        items = read_json(self.path, [])
        for rec in items:
            if rec["approval_id"] == approval_id:
                if rec["status"] != "pending":
                    raise ValueError(f"{approval_id} is already {rec['status']}.")
                rec["status"] = "approved" if approve else "rejected"
                rec["decided_by"] = approver.user_id
                rec["decided_at"] = now_iso()
                rec["note"] = note
                write_json(self.path, items)
                return rec
        raise KeyError(approval_id)

    def set_result(self, approval_id: str, result: dict) -> dict:
        items = read_json(self.path, [])
        for rec in items:
            if rec["approval_id"] == approval_id:
                rec["result"] = result
                write_json(self.path, items)
                return rec
        raise KeyError(approval_id)
