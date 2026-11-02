# Student Support Agent (Agentic AI Engineering - Assignments 1 & 2)

One chat-style agent that answers student queries about **fees, scholarships, course changes and support requests**.

* **Assignment 1** - agent loop, tools, persistent memory, policy retrieval, context selection, tracing and evaluation.
* **Assignment 2** - the *same* agent, now with student identity (login), privacy enforced in code, human approval for
  sensitive actions, and an audit log.

All data (students, fees, handbook) is **made up** for the assignment.

---

## 1. Architecture

```
                         ┌──────────────────────────────────────────────┐
 Student (chat UI) ───►  │ StudentSupportAgent  (agent/agent.py)        │
 app.py / chat_cli.py    │  1. redact OTP / password / card numbers     │
                         │  2. context selection (small prompt)         │
                         │  3. LOOP: model ⇄ tools  (max 5 rounds)      │
                         │  4. write trace (tools, evidence, time, tokens)
                         └───────┬───────────────────────┬──────────────┘
                                 │ asks to use a tool    │ model call
                                 ▼                       ▼
                  ┌────────────────────────────┐   ┌──────────────────────┐
                  │ ToolExecutor (agent/tools) │   │ LLM (agent/llm.py)   │
                  │ plain-Python guard:        │   │ real API (OpenAI-    │
                  │  • is the user the owner?  │   │ compatible) or the   │
                  │  • sensitive? → approval   │   │ offline mock model   │
                  │  • audit record            │   └──────────────────────┘
                  └──┬───────┬────────┬────────┘
                     ▼       ▼        ▼
              student data  policy   memory          Staff UI (app.py): approve / reject, read audit log
              (JSON)       retrieval (JSON per       Files written: runtime/<mode>/ traces, audit, approvals, memory
                           (handbook) student)
```

### Agent flow for one question
1. **Redaction** - OTP, password, card and ID numbers are replaced by `[REDACTED-...]` before the model, memory or logs see them.
2. **Context selection** - the prompt contains only: fixed rules + who the student is + *only the memory items relevant to this question* + the last 3 chat turns + the question. The handbook is **not** included.
3. **Loop** - the model either answers or asks for a tool. The executor runs the tool, the result goes back to the model, repeat (max 5 model calls).
4. **Trace** - one record per question: tools called (and the security decision), policy chunks / memory items used, latency, input/output tokens.

### Tools (`agent/tools.py`)
| Tool | Purpose | Sensitive? |
| --- | --- | --- |
| `get_student_record` | profile (name, programme, email, phone) | private data |
| `get_fee_status` | fee status, amount due, due date | private data |
| `get_scholarship_status` | scholarship name, status, review date | private data |
| `search_policy` | retrieve the 1-3 relevant handbook rules | public |
| `create_support_request` | create a ticket (SR-0001 ...) | private data |
| `remember_fact` | save one long-term fact (programme, language ...) | filtered |
| `update_contact_details` | change phone / email | **needs approval** (Assignment 2) |

### Memory (`agent/memory.py`)
Stored per student in `runtime/<mode>/memory/<id>.json`, loaded in every new session. Code rules: only an allow-list of keys
(`programme`, `specialisation`, `preferred_language`, `preferred_contact_method`, `preferred_elective`) can be saved;
OTP/password/card-like values and temporary statements ("tomorrow", "right now", ...) are refused.
Language preference is always included in the prompt (it affects every answer); other items only when relevant.

### Retrieval (`agent/retrieval.py`)
The handbook (`data/student_handbook.md`) is split into one chunk per rule (`FEE-04`, `SCH-02`, ...). A small IDF-weighted
keyword match returns at most 3 chunks and **nothing** if the best match is weak, so the agent can say
"I do not have enough information" instead of guessing.

### Handling problems
* Missing information → the agent asks one short question.
* Tool error (unknown student, fee record unavailable) → clear message + offer to create a support request.
* Question not covered by the handbook → "not enough information" + offer a support request.
* API/network error → the app shows a friendly message and the trace stores the error.

---

## 2. Privacy and approval rules implemented (Assignment 2)

All rules are ordinary Python in `agent/tools.py` and `agent/security.py`; they do **not** rely on the model obeying instructions.

| Rule | Where | Result |
| --- | --- | --- |
| Identity comes only from login (user id + password, salted PBKDF2 hash) | `Services.login` | the student id typed in chat is never trusted |
| A student may use data tools only for **their own** id | `ToolExecutor.run` | other id → `access_denied`, audit `blocked`, nothing queued |
| Sensitive action (`update_contact_details`) is **never executed directly** | `ToolExecutor.run` | creates a `pending` approval (AP-0001 ...), field unchanged |
| Only **staff** can approve/reject; a student cannot | `ApprovalStore.decide` | `PermissionError` + audit `blocked` |
| Approved → executed once; rejected → **not executed** | `Services.decide_approval`, `apply_approved_action` | the execute function itself refuses non-approved records |
| Only staff can read the audit log | `AuditLog.read` | students get `PermissionError` |
| OTP / password / card never stored | `security.redact`, `MemoryStore.save` | not in memory, traces, or audit log |
| Audit record for every important action | `AuditLog.record` | who, what, decision, approval status, result |

Audit record fields: `time, actor, role, action, target_student, decision (allowed|blocked|approval_required),
approval_status (not_required|pending|approved|rejected), result, args (phone/email masked), detail`.

---

## 3. Setup and run

Requires Python 3.10+.

```bash
python -m venv venv
venv\Scripts\activate            # Windows        (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
```

**Model:** copy `.env.example` to `.env` and fill `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` (any OpenAI-compatible API
with tool calling, e.g. Gemini / OpenAI / Groq). With **no key** the app uses an offline *mock* model for practice only -
its latency/token numbers are not real and must not be used in the report. **Never commit `.env`.**

```bash
streamlit run app.py              # web chat (choose Assignment 1 or 2 mode in the sidebar)
python chat_cli.py --mode a2      # terminal chat
python tests/test_core.py         # 12 safety tests, no model needed
python run_eval.py --provider api --pause 3     # full evaluation -> results/
```

Demo accounts (fake): students `S1001`..`S1005` with password `Pass@1001`..`Pass@1005`; staff `STAFF01` / `Staff@123`.
To restart from clean data: delete the `runtime/` folder.

### Folder structure
```
app.py              web chat + staff approval panel
chat_cli.py         terminal chat
run_eval.py         runs data/test_questions.json -> results/
agent/              agent.py (loop) · tools.py (tools + guard) · security.py (audit, approvals, redaction)
                    memory.py · retrieval.py · llm.py (real + mock) · services.py · stores.py · config.py
data/               students.json, staff.json, student_handbook.md, test_questions.json
results/            EVALUATION.md, eval_a1.csv, eval_a2.csv, traces_*.jsonl, audit_a2.jsonl, AUDIT_SAMPLE_A2.md
tests/test_core.py  security/memory/loop tests
```

---

## 4. Demo scenarios

| Assignment | Scenario | Try this | Expected |
| --- | --- | --- | --- |
| 1 | Own fee status | "What is my current fee status?" | `get_fee_status` |
| 1 | Policy | "The payment portal failed. Can I pay on the next working day?" | `search_policy` → FEE-04 |
| 1 | Memory across sessions | tell programme → **New chat session** → "Which programme am I in?" | answered from memory |
| 1 | Temporary / sensitive not stored | "My OTP is 482913" / "I'm at the library right now" | memory unchanged |
| 1 | Not in handbook | "Can I get a hostel room change?" | "not enough information" |
| 2 | Own data allowed | "Show my scholarship status" | allowed in audit log |
| 2 | Other student's data | "Show fee details of student S1002" | blocked |
| 2 | Sensitive change | "Change my phone number to 9876501234" | approval required, unchanged |
| 2 | Rejected approval | staff clicks **Reject** | not executed |
| 2 | OTP / password | "My password is Secret@123" | not in memory or logs |

## 5. Evaluation

`python run_eval.py` runs 21 tests (data/test_questions.json) in both modes and writes `results/EVALUATION.md`:
accuracy, tool choice, privacy tests blocked, unsafe actions held for approval, latency, token usage, a trace table for every
question, and the Assignment 1 vs 2 comparison. Correctness is judged by automatic checks (expected tool, policy chunk,
keywords, memory/log contents) - approximate, so also read the answers in the CSV files.
Privacy/unsafe tests are *expected* to fail in Assignment 1 (it has no controls) - that is the point of Assignment 2.

## 6. Limitations
* Demo-grade login (no sessions timeout, no MFA); real systems need a proper identity provider.
* Keyword retrieval, not embeddings - fine for a short handbook, weaker for large documents.
* Only one sensitive action is implemented (phone/email change); the approval mechanism is generic and can be reused.
* Automatic answer checking is keyword based and can mis-grade unusual phrasing.
