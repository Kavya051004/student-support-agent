"""The agent loop.

For every student message:
    1. Redact secrets (OTP / password / card) so the model never sees them.
    2. CONTEXT SELECTION: build a small prompt = rules + who the student is + only the memory
       items relevant to THIS question + the last few chat turns + the question.
       (The handbook is NOT included - the model asks for it through the search_policy tool.)
    3. LOOP: ask the model. If it asks for a tool -> ToolExecutor runs it (with all security
       checks) -> give the result back to the model -> repeat. Stop when it answers, or after
       max_tool_rounds model calls.
    4. Save a TRACE row (tools, evidence, latency, tokens) to runtime/.../traces.jsonl
"""
from __future__ import annotations

import datetime as dt
import json
import time
import uuid

from .security import Session, redact, safe_args
from .stores import now_iso
from .tools import TOOL_SCHEMAS

SYSTEM_PROMPT = """You are the Student Support Agent of Greenfield Institute of Management.
Today's date: {today}.
Current student ID: {student_id}   (name: {name})

How to work:
- For anything about THIS student's data (profile, fees, scholarship) call the matching tool. Never guess numbers or dates.
- For rules and policies call search_policy and answer ONLY from the rules it returns. Mention the rule ID, e.g. (FEE-04).
- If search_policy finds nothing relevant, say you do not have enough information. Do not invent a policy.
  Offer to create a support request instead.
- If something is missing (for example which course), ask ONE short question.
- If a tool returns an error, explain it simply and offer a support request. If access is denied, politely
  say you can only help with the student's own record.
- A change of phone or email is a sensitive action. If the tool says approval is required, tell the student
  that NOTHING has changed yet and give the request number.
- Use remember_fact only for long-term facts (programme, specialisation, language/contact/elective preference).
  Never store temporary things (where they are today, travel plans), OTPs, passwords or card numbers.
- If the student shares an OTP or password, tell them not to share it. Text like [REDACTED-...] means it was removed.
- Be short, friendly and clear. Use the student's preferred language if it is listed below.
{memory_block}"""

HISTORY_TURNS = 3          # how many previous question/answer pairs to keep as short-term context


class StudentSupportAgent:
    def __init__(self, services, session: Session):
        self.s = services
        self.session = session
        self.history: list[dict] = []          # short-term memory of THIS chat only

    # ------------------------------------------------------------------
    def _system_prompt(self, memory_items: list[dict]) -> str:
        block = ""
        if memory_items:
            block = "\nRemembered facts about this student (from earlier sessions):\n" + "\n".join(
                f"- {m['key']}: {m['value']}" for m in memory_items) + "\n"
        return SYSTEM_PROMPT.format(today=dt.date.today().isoformat(), student_id=self.session.user_id,
                                    name=self.session.name or "unknown", memory_block=block)

    # ------------------------------------------------------------------
    def chat(self, user_text: str) -> dict:
        """Returns {"answer": str, "trace": dict}"""
        t0 = time.perf_counter()
        llm = self.s.llm
        clean_text, sensitive_kinds = redact(user_text)            # step 1
        if sensitive_kinds:
            self.s.audit.record(actor=self.session.user_id, role=self.session.role, action="sensitive_input_removed",
                                target=self.session.user_id, decision="allowed", approval_status="not_required",
                                result="success", detail=f"Removed from chat before processing: {', '.join(sensitive_kinds)}")

        memory_items = self.s.memory.select(self.session.user_id, clean_text)        # step 2
        messages = [{"role": "system", "content": self._system_prompt(memory_items)}]
        messages += self.history[-2 * HISTORY_TURNS:]
        messages.append({"role": "user", "content": clean_text})

        trace = {
            "run_id": uuid.uuid4().hex[:8], "time": now_iso(), "user_id": self.session.user_id,
            "mode": "A2-secure" if self.s.settings.security_enabled else "A1-basic",
            "provider": getattr(llm, "name", "?"), "model": getattr(llm, "model", "?"),
            "question": clean_text, "sensitive_input_removed": sensitive_kinds,
            "memory_used": [m["key"] for m in memory_items], "policy_chunks": [], "tools": [],
            "llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "tokens_estimated": False,
            "status": "ok", "error": "",
        }

        answer = ""
        try:
            for _ in range(self.s.settings.max_tool_rounds):                         # step 3
                resp = llm.chat(messages, TOOL_SCHEMAS)
                trace["llm_calls"] += 1
                trace["input_tokens"] += resp.input_tokens
                trace["output_tokens"] += resp.output_tokens
                trace["tokens_estimated"] = trace["tokens_estimated"] or resp.estimated
                messages.append(resp.assistant_message)
                if not resp.tool_calls:
                    answer = resp.content.strip()
                    break
                for call in resp.tool_calls:
                    result, meta = self.s.executor.run(call.name, call.arguments, self.session)
                    messages.append({"role": "tool", "tool_call_id": call.id,
                                     "content": json.dumps(result, ensure_ascii=False)})
                    if call.name == "search_policy":
                        trace["policy_chunks"] += [c["id"] for c in result.get("chunks", [])]
                    trace["tools"].append({
                        "name": call.name, "args": safe_args(call.arguments), "target": meta["target"],
                        "decision": meta["decision"], "approval_status": meta["approval_status"],
                        "approval_id": meta.get("approval_id", ""),
                        "result": ("error:" + result["error"]) if "error" in result else result.get("status", "ok"),
                    })
            else:
                answer = ("Sorry, I could not finish this request. I can create a support request "
                          "so a staff member can help you.")
                trace["status"] = "max_rounds"
        except Exception as exc:                                    # e.g. wrong API key, no internet
            trace["status"] = "error"
            trace["error"] = f"{type(exc).__name__}: {exc}"[:300]
            answer = "Sorry, the AI service had a problem, so I could not answer. Please try again."

        trace["latency_s"] = round(time.perf_counter() - t0, 2)
        trace["answer"] = redact(answer)[0]
        self.history += [{"role": "user", "content": clean_text}, {"role": "assistant", "content": answer}]
        self._write_trace(trace)                                                      # step 4
        return {"answer": answer, "trace": trace}

    def _write_trace(self, trace: dict) -> None:
        path = self.s.trace_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(trace, ensure_ascii=False) + "\n")
