"""Terminal chat (no browser needed).

Examples:
    python chat_cli.py --mode a1 --student S1001            # Assignment 1: no login
    python chat_cli.py --mode a2                            # Assignment 2: asks user id + password
    python chat_cli.py --mode a2 --provider mock            # force the offline practice model
Type  quit  to leave.
"""
import argparse
import getpass

from agent.agent import StudentSupportAgent
from agent.config import get_settings
from agent.services import Services

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["a1", "a2"], default="a2")
parser.add_argument("--student", default="S1001", help="student id (a1 mode only)")
parser.add_argument("--provider", choices=["mock", "api"], default=None)
args = parser.parse_args()

svc = Services(get_settings(security_enabled=(args.mode == "a2"), provider=args.provider))
print(f"\nMode: {args.mode.upper()} | model: {svc.llm.name} ({getattr(svc.llm, 'model', '')})")

if args.mode == "a2":
    uid = input("User id (e.g. S1001): ").strip()
    pwd = getpass.getpass("Password: ")
    session = svc.login(uid, pwd)
    if not session:
        raise SystemExit("Login failed.")
    if session.role == "staff":
        print("Staff account: use the web app (streamlit run app.py) for the approval queue.")
        raise SystemExit
else:
    session = svc.open_session_no_auth(args.student.upper())

agent = StudentSupportAgent(svc, session)
print(f"Hello {session.name}! Ask me about fees, scholarships, courses or support requests.\n")
while True:
    q = input("You: ").strip()
    if q.lower() in ("quit", "exit", ""):
        break
    out = agent.chat(q)
    t = out["trace"]
    print(f"\nAgent: {out['answer']}")
    print(f"  [tools: {[x['name'] + ':' + x['decision'] for x in t['tools']] or 'none'} | "
          f"evidence: {t['policy_chunks'] + t['memory_used'] or 'none'} | {t['latency_s']}s | "
          f"tokens in/out: {t['input_tokens']}/{t['output_tokens']}]\n")
