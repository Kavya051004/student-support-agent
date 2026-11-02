"""The "brain" connectors.

  OpenAICompatLLM : a REAL model. Works with any OpenAI-compatible API (OpenAI, Google Gemini, Groq, ...)
                    -> reports true token usage. Use this for your final demo and evaluation numbers.
  MockLLM         : an offline, rule-based stand-in so you can practise and test without any key.
                    It is NOT an AI - its token numbers are only estimates. Do not submit mock numbers.
Both have the same method:  chat(messages, tools) -> LLMResponse
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall]
    input_tokens: int
    output_tokens: int
    assistant_message: dict          # the message to put back into the chat history
    estimated: bool = False          # True only for the mock model


def make_llm(settings):
    if settings.provider == "mock":
        return MockLLM()
    if not settings.api_key or not settings.model:
        raise RuntimeError("LLM_PROVIDER is 'api' but LLM_API_KEY or LLM_MODEL is missing. "
                           "Fill them in the .env file (see .env.example), or remove LLM_API_KEY to use the mock model.")
    return OpenAICompatLLM(settings.api_key, settings.base_url, settings.model)


# =============================================================================
# Real model
# =============================================================================
class OpenAICompatLLM:
    name = "api"

    def __init__(self, api_key: str, base_url: str, model: str):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("The 'openai' package is missing. Run:  pip install -r requirements.txt") from exc
        self.client = OpenAI(api_key=api_key, base_url=base_url or None)
        self.model = model

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        last_error = None
        for attempt in range(4):                       # free plans often rate-limit -> wait and retry
            try:
                resp = self.client.chat.completions.create(
                    model=self.model, messages=messages, tools=tools, tool_choice="auto", temperature=0)
                break
            except Exception as exc:
                last_error = exc
                code = getattr(exc, "status_code", None)
                retryable = code in (429, 500, 502, 503, 504) or type(exc).__name__ in (
                    "APITimeoutError", "APIConnectionError")
                if not retryable or attempt == 3:
                    raise
                time.sleep(2 * (2 ** attempt))
        else:                                          # pragma: no cover
            raise last_error

        msg = resp.choices[0].message
        calls, raw_calls = [], []
        for tc in (msg.tool_calls or []):
            call_id = tc.id or f"call_{uuid.uuid4().hex[:8]}"
            raw_args = tc.function.arguments or "{}"
            try:
                args = json.loads(raw_args)
                if not isinstance(args, dict):
                    args = {}
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(call_id, tc.function.name, args))
            raw_calls.append({"id": call_id, "type": "function",
                              "function": {"name": tc.function.name, "arguments": raw_args}})
        assistant = {"role": "assistant", "content": msg.content or ""}
        if raw_calls:
            assistant["tool_calls"] = raw_calls
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            content=msg.content or "", tool_calls=calls,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            assistant_message=assistant)


# =============================================================================
# Mock model (offline practice)
# =============================================================================
def _call(name: str, **args) -> ToolCall:
    return ToolCall(f"call_{uuid.uuid4().hex[:8]}", name, args)


class MockLLM:
    name = "mock"
    model = "mock-rule-based"

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        system = messages[0]["content"]
        me_match = re.search(r"Current student ID: (S\d{4})", system)
        me = me_match.group(1) if me_match else "S1001"
        last = messages[-1]
        if last["role"] == "tool":
            return self._reply(messages, content=self._compose(messages))
        text = last["content"]
        calls = self._plan(text, me)
        if calls:
            return self._reply(messages, calls=calls)
        return self._reply(messages, content=self._direct(text, system))

    # ---- helpers -----------------------------------------------------------
    @staticmethod
    def _reply(messages, content: str = "", calls: list[ToolCall] | None = None) -> LLMResponse:
        calls = calls or []
        assistant = {"role": "assistant", "content": content}
        if calls:
            assistant["tool_calls"] = [{"id": c.id, "type": "function",
                                        "function": {"name": c.name, "arguments": json.dumps(c.arguments)}} for c in calls]
        in_tok = len(json.dumps(messages)) // 4
        out_tok = max(1, len(content or json.dumps(assistant.get("tool_calls", []))) // 4)
        return LLMResponse(content, calls, in_tok, out_tok, assistant, estimated=True)

    # ---- decide which tools to call ---------------------------------------------
    def _plan(self, text: str, me: str) -> list[ToolCall]:
        t = text.lower()
        if "[redacted" in t:
            return []                                           # never act on sensitive values
        ids = re.findall(r"\bs\d{4}\b", t)
        target = ids[0].upper() if ids else me
        calls: list[ToolCall] = []

        # sensitive change of phone / email
        if re.search(r"\b(change|update|set|replace|modify)\b", t) and re.search(r"\b(phone|mobile|number|e-?mail)\b", t):
            field = "email" if re.search(r"e-?mail", t) else "phone"
            m = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text) if field == "email" else re.search(r"\b\d{10}\b", text)
            return [_call("update_contact_details", student_id=target, field=field, new_value=m.group(0))] if m else []

        # support request
        if re.search(r"\b(raise|create|open|file|log|register)\b.*\b(support request|ticket|complaint|request)\b", t):
            issue = text.split(":", 1)[1].strip() if ":" in text else text
            cat = ("Fees" if re.search(r"fee|receipt|payment|pay", t) else
                   "Scholarship" if "scholar" in t else
                   "Academic" if re.search(r"course|elective|exam|grade", t) else "Other")
            return [_call("create_support_request", student_id=me, issue=issue, category=cat)]

        # remember long-term facts
        if re.search(r"programme|program|pgdm|mba", t):
            m = re.search(r"(?:my (?:programme|program) is|i(?: am|'m) (?:in|doing|enrolled in|studying))\s+(?:the\s+)?(.+?)"
                          r"(?:\s+(?:programme|program))?\s*(?:[.,!;]|\band\b|$)", text, re.I)
            if m:
                calls.append(_call("remember_fact", key="programme", value=m.group(1).strip()))
        m = re.search(r"\bprefer(?:s|red)?\s+(?:replies|answers|responses|messages)?\s*in\s+(\w+)", text, re.I)
        if m:
            calls.append(_call("remember_fact", key="preferred_language", value=m.group(1)))
        if calls:
            return calls

        # casual / temporary statements -> just chat, do not search or save anything
        if re.search(r"\b(remember that|note that|fyi|i(?: am|'m) (?:at|travelling|traveling|going))\b", t):
            return []

        if re.search(r"which (programme|program)|what(?:'s| is) my (programme|program)", t):
            return []                                           # answered from remembered facts

        # vague request -> ask a question instead of guessing
        if re.fullmatch(r"(i want to |can i |please )?change my (course|elective|subject)s?\.?", t.strip()):
            return []

        # private data (own or someone else's - the SECURITY layer decides what is allowed)
        wants_fee, wants_sch = "fee" in t, "scholar" in t
        policy_words = re.search(r"portal|late fee|refund|instal|can i pay|next working day|deadline|fail|receipt|"
                                 r"payment mode|waiver|renew|eligib|criteria|maintain|cgpa|appeal|disburs|continue|"
                                 r"rule|policy|paid out|payout|pay out", t)
        if wants_fee and (re.search(r"\b(my|status|balance|outstanding|how much|due amount)\b", t) or ids) \
                and not re.search(r"portal|late fee|refund|instal|can i pay|next working day|receipt", t):
            calls.append(_call("get_fee_status", student_id=target))
        if wants_sch and (re.search(r"\b(my|status|do i have|am i)\b", t) or ids):
            calls.append(_call("get_scholarship_status", student_id=target))
        if ids and not calls:
            calls.append(_call("get_student_record", student_id=target))
        if re.search(r"\b(my|own)\b.{0,20}\b(record|details|profile)\b|\bmy (email|phone)\b", t) and not calls:
            calls.append(_call("get_student_record", student_id=target))

        # policy questions
        academics = re.search(r"drop|elective|specialis|attendance|credit|core course|course change", t)
        if (policy_words and (wants_fee or wants_sch)) or academics or (not calls and not ids):
            query = text
            if re.search(r"renew|eligib|continue", t) and wants_sch:
                query = "scholarship renewal criteria CGPA attendance"
            calls.append(_call("search_policy", query=query))
        return calls

    # ---- answer without tools ------------------------------------------------------
    def _direct(self, text: str, system: str) -> str:
        t = text.lower()
        if "[redacted" in t:
            return ("Please do not share OTPs or passwords with anyone - not even me. I have not saved it. "
                    "Student Services staff will never ask for it. How else can I help?")
        if re.search(r"which (programme|program)|what(?:'s| is) my (programme|program)", t):
            m = re.search(r"- programme: (.+)", system)
            if m:
                return f"You are in {m.group(1).strip()} (this is from the profile you told me earlier)."
            return "I do not have your programme saved yet. Which programme are you in?"
        if re.fullmatch(r"(i want to |can i |please )?change my (course|elective|subject)s?\.?", t.strip()):
            return "Sure - which course or elective do you want to change, and what do you want to change it to?"
        if re.search(r"\b(change|update)\b", t) and re.search(r"phone|mobile|email|e-mail", t):
            return "What is the new phone number (10 digits) or email address you want to register?"
        return ("I noted that for this chat only. I save just long-term facts such as your programme or "
                "language preference. How can I help with fees, scholarships, courses or support requests?")

    # ---- write the final answer from tool results --------------------------------
    def _compose(self, messages: list[dict]) -> str:
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
        names = {}
        for m in messages[last_user:]:
            for tc in m.get("tool_calls", []) or []:
                names[tc["id"]] = tc["function"]["name"]
        parts = []
        for m in messages[last_user:]:
            if m["role"] != "tool":
                continue
            res = json.loads(m["content"])
            parts.append(self._describe(names.get(m["tool_call_id"], "?"), res))
        return "\n\n".join(parts)

    @staticmethod
    def _describe(tool: str, r: dict) -> str:
        if "error" in r:
            code = r["error"]
            return {
                "access_denied": "Sorry, I cannot show or change another student's private information. "
                                 "I can only help with your own record.",
                "student_not_found": "I could not find a student with that ID. Please check the ID and try again.",
                "fee_record_unavailable": "I am unable to get your fee record right now - it is not available in the system. "
                                          "I can create a support request so the Accounts Office can check it. Shall I?",
                "memory_rejected": "I did not save that - I keep only long-term facts like your programme or language "
                                   "preference, never temporary or sensitive details.",
                "invalid_value": f"That value does not look valid. {r.get('message', '')}",
            }.get(code, f"Something went wrong ({code}). I can raise a support request if you like.")
        if tool == "get_fee_status":
            due = f" Next due date: {r['next_due_date']}." if r.get("next_due_date") else ""
            return (f"Your fee status is {r['status']}. Total fee Rs {r['total_fee']:,}, paid Rs {r['paid']:,}, "
                    f"amount due Rs {r['due_amount']:,}.{due}")
        if tool == "get_scholarship_status":
            if not r.get("has_scholarship"):
                return "You do not have a scholarship on record."
            return (f"Your scholarship: {r['name']} ({r['percent']}%), status {r['status']}. "
                    f"Next review: {r['next_review']}.")
        if tool == "get_student_record":
            return (f"{r['name']} ({r['student_id']}) - {r['programme']}, batch {r['batch']}. "
                    f"Email {r['email']}, phone {r['phone']}.")
        if tool == "search_policy":
            if not r.get("chunks"):
                return ("I do not have enough information in the student handbook to answer that, and I do not want "
                        "to guess. Would you like me to create a support request so the right office can reply?")
            lines = [f"According to the student handbook ({c['id']} - {c['title']}): {c['text']}" for c in r["chunks"][:2]]
            return "\n\n".join(lines)
        if tool == "create_support_request":
            return (f"I have created support request {r['ticket_id']} (category: {r['category']}). "
                    "It will be acknowledged within 1 working day.")
        if tool == "remember_fact":
            return f"Got it - I have saved your {r['key'].replace('_', ' ')}: {r['value']}."
        if tool == "update_contact_details":
            if r.get("status") == "approval_required":
                return (f"This change needs staff approval, so I have NOT changed anything yet. "
                        f"Your request number is {r['approval_id']}. Student Services will review it.")
            return f"Done - your {r['field']} has been updated."
        return json.dumps(r)
