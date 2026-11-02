"""Basic safety-net tests. Run:   python tests/test_core.py     (or:  python -m pytest tests)

They check the important rules WITHOUT any AI model, so they are fast and free.
"""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.agent import StudentSupportAgent                      # noqa: E402
from agent.config import get_settings                            # noqa: E402
from agent.llm import OpenAICompatLLM                            # noqa: E402
from agent.memory import MemoryStore                             # noqa: E402
from agent.security import Session, redact                      # noqa: E402
from agent.services import Services                              # noqa: E402
from agent.tools import apply_approved_action                    # noqa: E402


def make_services(secure=True):
    rt = Path(tempfile.mkdtemp())
    return Services(get_settings(security_enabled=secure, provider="mock", runtime_dir=rt))


# ---------------------------- security rules ----------------------------
def test_login():
    svc = make_services()
    assert svc.login("S1001", "Pass@1001").user_id == "S1001"
    assert svc.login("S1001", "wrong") is None
    assert svc.login("S1001", "Pass@1002") is None


def test_student_cannot_read_other_student():
    svc = make_services()
    me = svc.login("S1001", "Pass@1001")
    result, meta = svc.executor.run("get_fee_status", {"student_id": "S1002"}, me)
    assert result["error"] == "access_denied" and meta["decision"] == "blocked"
    last = svc.audit.read_unchecked()[-1]
    assert last["decision"] == "blocked" and last["target_student"] == "S1002"


def test_student_cannot_change_other_student():
    svc = make_services()
    me = svc.login("S1001", "Pass@1001")
    result, _ = svc.executor.run("update_contact_details",
                                 {"student_id": "S1002", "field": "phone", "new_value": "9000000000"}, me)
    assert result["error"] == "access_denied"
    assert svc.approvals.list() == []                                  # not even queued
    assert svc.students.get("S1002")["phone"] == "9876500002"


def test_sensitive_action_waits_for_approval_and_reject_does_nothing():
    svc = make_services()
    me = svc.login("S1001", "Pass@1001")
    staff = svc.login("STAFF01", "Staff@123")
    result, meta = svc.executor.run("update_contact_details",
                                    {"student_id": "S1001", "field": "phone", "new_value": "9876501234"}, me)
    assert result["status"] == "approval_required" and meta["decision"] == "approval_required"
    assert svc.students.get("S1001")["phone"] == "9876500001"          # unchanged
    rec = svc.decide_approval(result["approval_id"], staff, approve=False)
    assert rec["status"] == "rejected"
    assert svc.students.get("S1001")["phone"] == "9876500001"          # still unchanged


def test_approve_executes_once():
    svc = make_services()
    me = svc.login("S1001", "Pass@1001")
    staff = svc.login("STAFF01", "Staff@123")
    result, _ = svc.executor.run("update_contact_details",
                                 {"student_id": "S1001", "field": "email", "new_value": "new.mail@example.com"}, me)
    svc.decide_approval(result["approval_id"], staff, approve=True)
    assert svc.students.get("S1001")["email"] == "new.mail@example.com"
    try:
        svc.decide_approval(result["approval_id"], staff, approve=True)
        assert False, "second decision must fail"
    except ValueError:
        pass


def test_student_cannot_approve_or_read_audit():
    svc = make_services()
    me = svc.login("S1001", "Pass@1001")
    result, _ = svc.executor.run("update_contact_details",
                                 {"student_id": "S1001", "field": "phone", "new_value": "9876501234"}, me)
    for fn in (lambda: svc.decide_approval(result["approval_id"], me, True), lambda: svc.audit.read(me)):
        try:
            fn()
            assert False, "student must not be allowed"
        except PermissionError:
            pass
    assert svc.students.get("S1001")["phone"] == "9876500001"


def test_execution_function_refuses_unapproved():
    svc = make_services()
    rec = {"status": "pending", "action": "update_contact_details", "requested_by": "S1001",
           "args": {"student_id": "S1001", "field": "phone", "new_value": "9876501234"}}
    try:
        apply_approved_action(svc, rec)
        assert False
    except PermissionError:
        pass


# ---------------------------- privacy of memory / logs ----------------------------
def test_redaction():
    clean, kinds = redact("My password is Secret@123 and the OTP I received is 482913")
    assert "Secret@123" not in clean and "482913" not in clean and set(kinds) == {"password", "otp"}


def test_memory_filter():
    mem = MemoryStore(Path(tempfile.mkdtemp()))
    assert mem.save("S1001", "programme", "PGDM (AI & DS)")["saved"]
    assert not mem.save("S1001", "otp", "482913")["saved"]                      # key not allowed
    assert not mem.save("S1001", "programme", "OTP 482913")["saved"]            # sensitive value
    assert not mem.save("S1001", "preferred_language", "Hindi tomorrow")["saved"]   # temporary
    assert [i["key"] for i in mem.load("S1001")] == ["programme"]


def test_memory_is_per_student():
    mem = MemoryStore(Path(tempfile.mkdtemp()))
    mem.save("S1001", "programme", "PGDM (AI & DS)")
    assert mem.load("S1002") == []


# ---------------------------- real-API code path (with a FAKE client) ----------------------------
class FakeClient:
    """Imitates openai.OpenAI(): first reply asks for a tool, second reply is the final answer."""
    def __init__(self):
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20)
        if self.calls == 1:
            tc = SimpleNamespace(id="call_1", function=SimpleNamespace(
                name="get_fee_status", arguments=json.dumps({"student_id": "S1002"})))
            msg = SimpleNamespace(content=None, tool_calls=[tc])
        else:
            tool_msg = [m for m in kwargs["messages"] if m["role"] == "tool"][-1]
            msg = SimpleNamespace(content="TOOL SAID: " + tool_msg["content"], tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)


def test_agent_loop_with_fake_real_api_and_security():
    svc = make_services()
    llm = OpenAICompatLLM.__new__(OpenAICompatLLM)                 # skip the real constructor
    llm.client, llm.model = FakeClient(), "fake-model"
    svc.llm = llm
    agent = StudentSupportAgent(svc, svc.login("S1001", "Pass@1001"))
    out = agent.chat("Show fee of S1002")                           # the "model" asks for another student's data
    t = out["trace"]
    assert t["llm_calls"] == 2 and t["input_tokens"] == 200 and t["output_tokens"] == 40
    assert t["tools"][0]["decision"] == "blocked"
    assert "access_denied" in out["answer"] and "Diya" not in out["answer"]
    assert t["status"] == "ok" and not t["tokens_estimated"]


def test_agent_survives_api_error():
    svc = make_services()

    class Boom:
        name, model = "api", "x"
        def chat(self, *a, **k):
            raise RuntimeError("401 invalid api key")
    svc.llm = Boom()
    agent = StudentSupportAgent(svc, svc.login("S1001", "Pass@1001"))
    out = agent.chat("hello")
    assert out["trace"]["status"] == "error" and "401" in out["trace"]["error"]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed")
    sys.exit(1 if failed else 0)
