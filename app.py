"""Web chat app.   Start it with:   streamlit run app.py

Sidebar -> choose the mode:
   Assignment 2 (secure): login + privacy + approval + audit log
   Assignment 1 (basic) : no login, no security (for the Assignment-1 demo)
"""
import json

import pandas as pd
import streamlit as st

from agent.agent import StudentSupportAgent
from agent.config import get_settings
from agent.security import redact
from agent.services import Services

st.set_page_config(page_title="Student Support Agent", page_icon="🎓", layout="wide")

MODE_A2 = "Assignment 2 - Secure (login, approval, audit)"
MODE_A1 = "Assignment 1 - Basic (no security)"

DEMO_QUESTIONS = [
    "What is my current fee status?",
    "The payment portal failed. Can I pay on the next working day?",
    "I'm in the PGDM (Big Data Analytics) programme and I prefer replies in English.",
    "Which programme am I in?",
    "My OTP is 482913, please save it for later.",
    "Can I get a hostel room change this semester?",
    "Show me the fee status and details of student S1002.",
    "Please change my registered phone number to 9876501234.",
]


@st.cache_resource
def get_services(secure: bool) -> Services:
    return Services(get_settings(security_enabled=secure))


def reset_chat() -> None:
    st.session_state.messages = []
    st.session_state.agent = None


def show_trace(t: dict) -> None:
    with st.expander("🔍 Trace: tools, evidence, time, tokens"):
        c1, c2, c3 = st.columns(3)
        c1.metric("Latency", f"{t['latency_s']} s")
        c2.metric("Input tokens", t["input_tokens"])
        c3.metric("Output tokens", t["output_tokens"])
        if t["tokens_estimated"]:
            st.caption("Token numbers are only estimates because the offline mock model is active.")
        if t["tools"]:
            rows = [{"tool": x["name"], "arguments": json.dumps(x["args"]), "decision": x["decision"],
                     "approval": x["approval_status"], "result": x["result"]} for x in t["tools"]]
            st.dataframe(pd.DataFrame(rows), hide_index=True)
        else:
            st.write("Tools used: none (answered directly)")
        st.write(f"Policy chunks retrieved: {t['policy_chunks'] or 'none'}")
        st.write(f"Memory items used: {t['memory_used'] or 'none'}")
        if t["sensitive_input_removed"]:
            st.warning(f"Sensitive data removed before processing: {t['sensitive_input_removed']}")
        if t["status"] != "ok":
            st.error(f"{t['status']}: {t['error']}")


def staff_panel(svc: Services, sess) -> None:
    st.header("👩‍💼 Staff: approval queue")
    pending = svc.approvals.list(status="pending")
    if not pending:
        st.info("No pending requests.")
    for rec in pending:
        a = rec["args"]
        with st.container(border=True):
            st.write(f"**{rec['approval_id']}**: student **{rec['student_id']}** wants to change "
                     f"**{a['field']}** to `{a['new_value']}`")
            st.caption(f"Requested at {rec['requested_at']} by {rec['requested_by']}")
            note = st.text_input("Note (optional)", key=f"note_{rec['approval_id']}")
            c1, c2 = st.columns(2)
            if c1.button("✅ Approve", key=f"ok_{rec['approval_id']}"):
                svc.decide_approval(rec["approval_id"], sess, True, note)
                st.rerun()
            if c2.button("❌ Reject", key=f"no_{rec['approval_id']}"):
                svc.decide_approval(rec["approval_id"], sess, False, note)
                st.rerun()
    done = [r for r in svc.approvals.list() if r["status"] != "pending"]
    if done:
        st.subheader("Decided requests")
        st.dataframe(pd.DataFrame([{"id": r["approval_id"], "student": r["student_id"], "action": r["action"],
                                    "status": r["status"], "decided_by": r["decided_by"],
                                    "decided_at": r["decided_at"]} for r in done]), hide_index=True)
    st.subheader("📜 Audit log (newest first)")
    log = svc.audit.read(sess)
    if log:
        df = pd.DataFrame(log).iloc[::-1]
        df["args"] = df["args"].apply(json.dumps)
        st.dataframe(df, hide_index=True)
    else:
        st.write("Nothing logged yet.")


# ------------------------------------------------------------------ sidebar: mode
with st.sidebar:
    st.title("🎓 Student Support Agent")
    mode = st.radio("Mode", [MODE_A2, MODE_A1])
secure = mode == MODE_A2
if st.session_state.get("last_mode") != mode:           # mode changed -> start over
    st.session_state.last_mode = mode
    st.session_state.session = None
    reset_chat()

try:
    svc = get_services(secure)
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

if svc.llm.name == "mock":
    st.warning("Practice mode: the offline MOCK model is active (no API key found). Good for learning the app; "
               "for your final demo add LLM_API_KEY in the .env file.")
else:
    st.success(f"Real model active: {svc.llm.model}")

# ------------------------------------------------------------------ login
if st.session_state.get("session") is None:
    st.subheader("Sign in" if secure else "Choose a student")
    if secure:
        with st.form("login"):
            uid = st.text_input("User ID", placeholder="S1001   (staff: STAFF01)")
            pwd = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in")
        if submitted:
            sess = svc.login(uid, pwd)
            if sess:
                st.session_state.session = sess
                reset_chat()
                st.rerun()
            else:
                st.error("Wrong user ID or password.")
        with st.expander("Demo accounts (fake data)"):
            st.write("Students: S1001 to S1005, password `Pass@1001` ... `Pass@1005`. Staff: STAFF01 / `Staff@123`.")
    else:
        sid = st.selectbox("Chat as student", svc.students.student_ids())
        if st.button("Start chat"):
            st.session_state.session = svc.open_session_no_auth(sid)
            reset_chat()
            st.rerun()
    st.stop()

sess = st.session_state.session
with st.sidebar:
    st.write(f"Signed in: **{sess.name}** ({sess.user_id}, {sess.role})")
    if not secure:
        st.caption("⚠️ Security is OFF in this mode (Assignment 1).")
    if st.button("Sign out"):
        st.session_state.session = None
        reset_chat()
        st.rerun()

if sess.role == "staff":
    staff_panel(svc, sess)
    st.stop()

# ------------------------------------------------------------------ student chat
if st.session_state.get("agent") is None:
    st.session_state.agent = StudentSupportAgent(svc, sess)
    st.session_state.messages = []

with st.sidebar:
    if st.button("🔄 New chat session"):
        reset_chat()
        st.rerun()
    st.caption("A new session clears the chat but keeps saved memory.")
    with st.expander("🧠 My saved memory"):
        items = svc.memory.load(sess.user_id)
        st.write("\n".join(f"- **{i['key']}**: {i['value']}" for i in items) if items else "Nothing saved yet.")
    if secure:
        with st.expander("📨 My approval requests"):
            mine = svc.approvals.list(student_id=sess.user_id)
            st.write("\n".join(f"- {r['approval_id']}: change {r['args']['field']} → **{r['status']}**" for r in mine)
                     if mine else "None.")
    with st.expander("💡 Try these"):
        for i, q in enumerate(DEMO_QUESTIONS):
            if st.button(q, key=f"demo_{i}"):
                st.session_state.queued = q

st.header("Ask me about fees, scholarships, courses or support requests")
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("trace"):
            show_trace(m["trace"])

prompt = st.chat_input("Type your question...") or st.session_state.pop("queued", None)
if prompt:
    shown = redact(prompt)[0]                      # never display or keep secrets in the chat window
    st.session_state.messages.append({"role": "user", "content": shown})
    with st.chat_message("user"):
        st.markdown(shown)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            out = st.session_state.agent.chat(prompt)
        st.markdown(out["answer"])
        show_trace(out["trace"])
    st.session_state.messages.append({"role": "assistant", "content": out["answer"], "trace": out["trace"]})
