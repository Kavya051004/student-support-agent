"""Services = one object that holds every store (students, memory, audit, ...) for one mode."""
from __future__ import annotations

from .config import DATA_DIR, Settings
from .llm import make_llm
from .memory import MemoryStore
from .retrieval import PolicyRetriever
from .security import ApprovalStore, AuditLog, Session
from .stores import StudentStore, SupportRequestStore
from .tools import ToolExecutor, apply_approved_action


class Services:
    def __init__(self, settings: Settings):
        self.settings = settings
        rt = settings.runtime_dir
        rt.mkdir(parents=True, exist_ok=True)
        self.students = StudentStore(rt)
        self.requests = SupportRequestStore(rt)
        self.memory = MemoryStore(rt)
        self.retriever = PolicyRetriever(DATA_DIR / "student_handbook.md")
        self.audit = AuditLog(rt, enabled=settings.security_enabled)
        self.approvals = ApprovalStore(rt)
        self.llm = make_llm(settings)
        self.executor = ToolExecutor(self)
        self.trace_path = rt / "traces.jsonl"

    # ---- who is using the app --------------------------------------------------
    def login(self, user_id: str, password: str) -> Session | None:
        """Assignment 2: password login. Every attempt is written to the audit log."""
        user = self.students.authenticate(user_id, password)
        uid = user_id.strip().upper()
        if not user:
            self.audit.record(actor=uid or "unknown", role="unknown", action="login", target=uid,
                              decision="blocked", approval_status="not_required", result="denied",
                              detail="Wrong user id or password.")
            return None
        self.audit.record(actor=uid, role=user["role"], action="login", target=uid, decision="allowed",
                          approval_status="not_required", result="success")
        return Session(user["user_id"], user["role"], user["name"])

    def open_session_no_auth(self, student_id: str) -> Session:
        """Assignment 1: no login - we simply pretend this student is chatting."""
        s = self.students.get(student_id)
        return Session(student_id, "student", s["name"] if s else student_id)

    # ---- human approval ----------------------------------------------------------
    def decide_approval(self, approval_id: str, approver: Session, approve: bool, note: str = "") -> dict:
        """Staff approves or rejects. Only an APPROVED request is executed."""
        existing = self.approvals.get(approval_id)
        try:
            rec = self.approvals.decide(approval_id, approver, approve, note)
        except PermissionError as exc:
            self.audit.record(actor=approver.user_id, role=approver.role, action="decide_approval",
                              target=existing["student_id"] if existing else "?", decision="blocked",
                              approval_status="pending", result="denied", detail=str(exc))
            raise
        if rec["status"] == "approved":
            result = apply_approved_action(self, rec)
            rec = self.approvals.set_result(approval_id, result)
            outcome = "success" if "error" not in result else f"error:{result['error']}"
            self.audit.record(actor=approver.user_id, role="staff", action=rec["action"], target=rec["student_id"],
                              decision="allowed", approval_status="approved", result=outcome,
                              args=rec["args"], detail=f"Approved {approval_id}; requested by {rec['requested_by']}.")
        else:
            self.audit.record(actor=approver.user_id, role="staff", action=rec["action"], target=rec["student_id"],
                              decision="allowed", approval_status="rejected", result="not_executed",
                              args=rec["args"], detail=f"Rejected {approval_id}; requested by {rec['requested_by']}.")
        return rec
