"""The agent's tools + the ToolExecutor that guards them.

The AI model only *asks* to use a tool. ToolExecutor.run() is normal Python code that decides
whether the call is really allowed (Assignment 2). The order inside run() is the whole story:

    1. Is it a known tool?
    2. Whose data is it about?  (target student)
    3. [secure mode] Is the signed-in user the owner of that data?  If not -> BLOCKED
    4. [secure mode] Is it a sensitive action?  If yes -> save as PENDING approval, do NOT execute
    5. Otherwise run the tool, then write an audit record
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .security import Session, safe_args

if TYPE_CHECKING:
    from .services import Services


# ---------------------------------------------------------------------------
# Tool descriptions shown to the AI model (OpenAI "function calling" format)
# ---------------------------------------------------------------------------
def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required}}}


_SID = {"type": "string", "description": "Student ID such as S1001. For 'my ...' questions use the current student's ID."}

TOOL_SCHEMAS = [
    _fn("get_student_record", "Get a student's profile: name, programme, batch, email, phone.",
        {"student_id": _SID}, ["student_id"]),
    _fn("get_fee_status", "Get a student's fee status: total fee, paid, amount due, next due date, status.",
        {"student_id": _SID}, ["student_id"]),
    _fn("get_scholarship_status", "Get a student's scholarship name, percentage, status and next review date.",
        {"student_id": _SID}, ["student_id"]),
    _fn("search_policy", "Search the student handbook for rules about fees, scholarships, courses, "
        "support requests and privacy. Returns only the most relevant rules (with IDs).",
        {"query": {"type": "string", "description": "A short search query describing the rule needed."}}, ["query"]),
    _fn("create_support_request", "Create a support request (ticket) for the student.",
        {"student_id": _SID,
         "issue": {"type": "string", "description": "Short description of the problem."},
         "category": {"type": "string", "enum": ["Fees", "Scholarship", "Academic", "IT/Portal", "Other"]}},
        ["student_id", "issue", "category"]),
    _fn("remember_fact", "Save ONE long-term fact about the current student (programme, specialisation, "
        "preferred_language, preferred_contact_method, preferred_elective). "
        "Never use for temporary things, OTPs, passwords or other sensitive data.",
        {"key": {"type": "string", "enum": ["programme", "specialisation", "preferred_language",
                                            "preferred_contact_method", "preferred_elective"]},
         "value": {"type": "string"}}, ["key", "value"]),
    _fn("update_contact_details", "Request a change of the student's registered phone number or email. "
        "This is a SENSITIVE action and may need staff approval.",
        {"student_id": _SID, "field": {"type": "string", "enum": ["phone", "email"]},
         "new_value": {"type": "string"}}, ["student_id", "field", "new_value"]),
]

TOOLS_WITH_STUDENT_DATA = {"get_student_record", "get_fee_status", "get_scholarship_status",
                           "create_support_request", "update_contact_details"}
SENSITIVE_TOOLS = {"update_contact_details"}          # need approval in secure mode
NOT_AUDITED = {"search_policy"}                       # public handbook text, nothing private


# ---------------------------------------------------------------------------
# Validation helper (used before asking for approval AND again before executing)
# ---------------------------------------------------------------------------
def validate_contact_update(field: str, value: str) -> str | None:
    """Returns an error message, or None if the new value looks valid."""
    value = str(value).strip()
    if field == "phone" and not re.fullmatch(r"\d{10}", value):
        return "Phone number must be exactly 10 digits."
    if field == "email" and not re.fullmatch(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", value):
        return "Email address does not look valid."
    if field not in ("phone", "email"):
        return "Only phone or email can be changed."
    return None


class ToolExecutor:
    def __init__(self, services: "Services"):
        self.s = services

    # ------------------------------------------------------------------
    def run(self, name: str, args: dict, session: Session) -> tuple[dict, dict]:
        """Returns (result_for_the_model, meta_for_the_trace)."""
        args = dict(args or {})
        secure = self.s.settings.security_enabled
        meta = {"tool": name, "decision": "allowed", "approval_status": "not_required", "target": session.user_id}

        func = getattr(self, f"_tool_{name}", None)
        if func is None:
            meta["decision"] = "error"
            return {"error": "unknown_tool", "message": f"No tool called {name}."}, meta

        # --- 2. whose data is this about? -------------------------------------------
        if name in TOOLS_WITH_STUDENT_DATA:
            target = str(args.get("student_id") or session.user_id).strip().upper()
            args["student_id"] = target
        else:
            target = session.user_id
        meta["target"] = target

        if secure and name != "search_policy":
            # --- 3. AUTHORIZATION (plain code, not an AI instruction) -----------------
            if session.role != "student" or (name in TOOLS_WITH_STUDENT_DATA and target != session.user_id):
                meta["decision"] = "blocked"
                self._audit(session, name, target, "blocked", "not_required", "denied", args,
                            "Signed-in user is not the owner of this record.")
                return {"error": "access_denied",
                        "message": "You can only access your own student record."}, meta

            # --- 4. SENSITIVE ACTION -> human approval, do NOT execute ----------------
            if name in SENSITIVE_TOOLS:
                problem = validate_contact_update(args.get("field", ""), args.get("new_value", ""))
                if problem:
                    self._audit(session, name, target, "allowed", "not_required", "error:invalid_value", args, problem)
                    return {"error": "invalid_value", "message": problem}, meta
                rec = self.s.approvals.create(target, name, args, requested_by=session.user_id)
                meta["decision"] = "approval_required"
                meta["approval_status"] = "pending"
                meta["approval_id"] = rec["approval_id"]
                self._audit(session, name, target, "approval_required", "pending", "pending_approval", args,
                            f"Approval {rec['approval_id']} created. Nothing was changed.")
                return {"status": "approval_required", "approval_id": rec["approval_id"],
                        "message": "This change needs staff approval. It has NOT been applied yet."}, meta

        # --- 5. run the tool ---------------------------------------------------------
        try:
            result = func(args, session)
        except Exception as exc:                       # a tool must never crash the agent
            result = {"error": "tool_failed", "message": f"The tool failed: {type(exc).__name__}"}
        if secure and name not in NOT_AUDITED:
            outcome = "success" if "error" not in result else f"error:{result['error']}"
            self._audit(session, name, target, "allowed", "not_required", outcome, args)
        return result, meta

    # ------------------------------------------------------------------
    def _audit(self, session, action, target, decision, approval_status, result, args, detail=""):
        self.s.audit.record(actor=session.user_id, role=session.role, action=action, target=target,
                            decision=decision, approval_status=approval_status, result=result,
                            args=args, detail=detail)

    # ------------------------------ the tools ---------------------------------------
    def _tool_get_student_record(self, a, session):
        s = self.s.students.get(a["student_id"])
        if not s:
            return {"error": "student_not_found", "message": f"No student with ID {a['student_id']}."}
        return {k: s[k] for k in ("student_id", "name", "programme", "batch", "email", "phone")}

    def _tool_get_fee_status(self, a, session):
        s = self.s.students.get(a["student_id"])
        if not s:
            return {"error": "student_not_found", "message": f"No student with ID {a['student_id']}."}
        if not s.get("fee"):
            return {"error": "fee_record_unavailable", "message": "The fee record is not available in the system."}
        return {"student_id": s["student_id"], **s["fee"]}

    def _tool_get_scholarship_status(self, a, session):
        s = self.s.students.get(a["student_id"])
        if not s:
            return {"error": "student_not_found", "message": f"No student with ID {a['student_id']}."}
        if not s.get("scholarship"):
            return {"student_id": s["student_id"], "has_scholarship": False}
        return {"student_id": s["student_id"], "has_scholarship": True, **s["scholarship"]}

    def _tool_search_policy(self, a, session):
        chunks = self.s.retriever.search(str(a.get("query", "")))
        if not chunks:
            return {"chunks": [], "message": "No relevant rule found in the handbook."}
        return {"chunks": chunks}

    def _tool_create_support_request(self, a, session):
        if not self.s.students.get(a["student_id"]):
            return {"error": "student_not_found", "message": f"No student with ID {a['student_id']}."}
        category = a.get("category") if a.get("category") in ("Fees", "Scholarship", "Academic", "IT/Portal", "Other") else "Other"
        t = self.s.requests.create(a["student_id"], str(a.get("issue", "")), category)
        return {"ticket_id": t["ticket_id"], "category": t["category"], "status": t["status"]}

    def _tool_remember_fact(self, a, session):
        # memory always belongs to the signed-in student - the model cannot choose whose memory to write
        res = self.s.memory.save(session.user_id, a.get("key", ""), a.get("value", ""))
        if not res["saved"]:
            return {"error": "memory_rejected", "message": res["reason"]}
        return {"saved": True, "key": res["key"], "value": res["value"]}

    def _tool_update_contact_details(self, a, session):
        """Runs directly only in Assignment-1 mode. In secure mode it is reached ONLY via approval."""
        problem = validate_contact_update(a.get("field", ""), a.get("new_value", ""))
        if problem:
            return {"error": "invalid_value", "message": problem}
        if not self.s.students.get(a["student_id"]):
            return {"error": "student_not_found", "message": f"No student with ID {a['student_id']}."}
        self.s.students.update_field(a["student_id"], a["field"], str(a["new_value"]).strip())
        return {"status": "updated", "field": a["field"]}


def apply_approved_action(services: "Services", record: dict) -> dict:
    """Executes a sensitive action AFTER staff approval. Refuses if the status is not 'approved'."""
    if record.get("status") != "approved":
        raise PermissionError("Action can only run after approval.")
    if record["action"] == "update_contact_details":
        a = record["args"]
        return ToolExecutor(services)._tool_update_contact_details(a, Session(record["requested_by"], "student"))
    return {"error": "unknown_action"}
