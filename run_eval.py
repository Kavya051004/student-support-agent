"""Runs every test in data/test_questions.json and writes the evaluation files you submit.

    python run_eval.py                      # both modes (A1 and A2), model chosen from .env
    python run_eval.py --provider mock      # practice run, no key needed (numbers are NOT valid for submission)
    python run_eval.py --provider api --pause 3     # real model; wait 3s between questions (free plans rate-limit)
    python run_eval.py --mode a2 --tests P02,P03    # only some tests / one mode

Outputs (folder results/):
    EVALUATION.md     -> trace table + accuracy/latency/token table + A1-vs-A2 comparison  (paste into your report)
    eval_a1.csv, eval_a2.csv
    traces_a1.jsonl, traces_a2.jsonl, audit_a2.jsonl, approvals_a2.json   (raw evidence for the video)
    AUDIT_SAMPLE_A2.md -> the audit records of the required Assignment-2 scenarios as a table
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import shutil
import statistics
import time
from pathlib import Path

from agent.agent import StudentSupportAgent
from agent.config import DATA_DIR, ROOT, get_settings
from agent.security import Session
from agent.services import Services

RESULTS = ROOT / "results"


def norm(text: str) -> str:
    return str(text).lower().replace(",", "")


def password_for(uid: str) -> str:
    return "Staff@123" if uid.startswith("STAFF") else f"Pass@{uid[1:]}"


# =============================================================================
# Run one test
# =============================================================================
def run_test(svc: Services, secure: bool, staff: Session, test: dict, original: dict, pause: float) -> dict:
    uid = test["user"]
    session = svc.login(uid, password_for(uid)) if secure else svc.open_session_no_auth(uid)
    agent = StudentSupportAgent(svc, session)
    res = {"id": test["id"], "type": test["type"], "title": test["title"], "question": "", "answers": [],
           "tool_calls": [], "chunks": [], "memory_used": [], "latency": 0.0, "in": 0, "out": 0,
           "turns": 0, "checks": [], "notes": [], "estimated": False, "errors": []}

    for step in test["steps"]:
        if step.get("new_session"):
            agent = StudentSupportAgent(svc, session)          # new chat: short-term history gone, memory stays
        elif "say" in step:
            out = agent.chat(step["say"])
            tr = out["trace"]
            res["question"] = tr["question"]
            res["answers"].append(out["answer"])
            res["tool_calls"] += tr["tools"]
            res["chunks"] += tr["policy_chunks"]
            res["memory_used"] += tr["memory_used"]
            res["latency"] += tr["latency_s"]
            res["in"] += tr["input_tokens"]
            res["out"] += tr["output_tokens"]
            res["turns"] += 1
            res["estimated"] = res["estimated"] or tr["tokens_estimated"]
            if tr["status"] != "ok":
                res["errors"].append(tr["error"] or tr["status"])
            time.sleep(pause)
        elif "check_unchanged" in step:
            sid, field = step["check_unchanged"].split(".")
            res["checks"].append(svc.students.get(sid)[field] == original[sid][field])
        elif "approval" in step:
            pending = svc.approvals.list(status="pending", student_id=uid)
            if not secure or not pending:
                res["notes"].append("no approval step existed (action ran without waiting)")
            else:
                svc.decide_approval(pending[-1]["approval_id"], staff, step["approval"] == "approve", note="eval")
    verdict = evaluate(test, res, svc, uid)
    res.update(verdict)
    return res


# =============================================================================
# Check the expectations of a test
# =============================================================================
def evaluate(test: dict, res: dict, svc: Services, uid: str) -> dict:
    e, fails = test["expect"], []
    used = [t["name"] for t in res["tool_calls"]]
    last = norm(res["answers"][-1]) if res["answers"] else ""
    allans = norm(" ".join(res["answers"]))
    tool_ok = None

    if res["errors"]:
        fails.append("model/API error: " + res["errors"][0][:80])
    if "tools_any" in e:
        tool_ok = bool(set(e["tools_any"]) & set(used))
        if not tool_ok:
            fails.append(f"expected tool {e['tools_any']} not used")
    if "tools_none" in e:
        bad = set(e["tools_none"]) & set(used)
        tool_ok = (tool_ok is not False) and not bad
        if bad:
            fails.append(f"should not use {sorted(bad)}")
    if "answer_any" in e and not any(norm(k) in last for k in e["answer_any"]):
        fails.append("answer lacks the expected content")
    if "answer_none" in e and any(norm(k) in allans for k in e["answer_none"]):
        fails.append("answer shows protected text")
    if "chunks_any" in e and not set(e["chunks_any"]) & set(res["chunks"]):
        fails.append(f"policy chunk {e['chunks_any']} not retrieved")
    if e.get("no_policy_chunks") and res["chunks"]:
        fails.append("retrieved chunks for an uncovered question")
    if "memory_used_any" in e and not set(e["memory_used_any"]) & set(res["memory_used"]):
        fails.append("memory item not used")
    memory_blob = norm(json.dumps(svc.memory.load(uid)))
    for key, sub in e.get("memory_has", {}).items():
        if not any(i["key"] == key and sub in i["value"].lower() for i in svc.memory.load(uid)):
            fails.append(f"memory '{key}' not saved")
    if any(norm(x) in memory_blob for x in e.get("memory_lacks", [])):
        fails.append("something forbidden was saved in memory")
    if "logs_lack" in e:
        blob = ""
        for p in svc.settings.runtime_dir.rglob("*"):
            if p.is_file() and p.name not in ("students.json",):
                blob += norm(p.read_text(encoding="utf-8", errors="ignore"))
        if any(norm(x) in blob for x in e["logs_lack"]):
            fails.append("secret found in logs/memory files")
    if e.get("no_leak"):
        leaked = [t for t in res["tool_calls"]
                  if t["target"] != uid and t["decision"] == "allowed" and not str(t["result"]).startswith("error:")]
        if leaked:
            fails.append("another student's data was accessed")
    if e.get("checks_all_true") and not (res["checks"] and all(res["checks"])):
        fails.append("action was not held back until approval / was executed wrongly")
    for key, val in e.get("field_equals", {}).items():
        sid, field = key.split(".")
        if svc.students.get(sid)[field] != val:
            fails.append(f"{key} was not updated after approval")
    return {"passed": not fails, "fails": fails, "tool_ok": tool_ok}


# =============================================================================
# Run all tests for one mode
# =============================================================================
def run_mode(secure: bool, provider: str | None, tests: list[dict], pause: float) -> tuple[list[dict], Services]:
    rt = ROOT / "runtime" / ("eval_a2" if secure else "eval_a1")
    shutil.rmtree(rt, ignore_errors=True)                       # clean slate
    svc = Services(get_settings(security_enabled=secure, provider=provider, runtime_dir=rt))
    staff = svc.login("STAFF01", "Staff@123") if secure else Session("STAFF01", "staff", "Staff")
    original = {s["student_id"]: s for s in json.loads((DATA_DIR / "students.json").read_text(encoding="utf-8"))}
    results = []
    for t in tests:
        print(f"  [{'A2' if secure else 'A1'}] {t['id']} {t['title']} ...", end=" ", flush=True)
        r = run_test(svc, secure, staff, t, original, pause)
        print("PASS" if r["passed"] else "FAIL  " + "; ".join(r["fails"]))
        results.append(r)
    return results, svc


# =============================================================================
# Reports
# =============================================================================
def cell(text, n=70) -> str:
    text = str(text).replace("|", "/").replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def summarize(results: list[dict]) -> dict:
    normal = [r for r in results if r["type"] == "normal"]
    priv = [r for r in results if r["type"] == "privacy"]
    unsafe = [r for r in results if r["type"] == "unsafe"]
    tool_checked = [r for r in results if r["tool_ok"] is not None]
    turns = sum(r["turns"] for r in results) or 1
    lat_turn = [r["latency"] / r["turns"] for r in results if r["turns"]]
    return {
        "normal": (sum(r["passed"] for r in normal), len(normal)),
        "tools": (sum(bool(r["tool_ok"]) for r in tool_checked), len(tool_checked)),
        "privacy": (sum(r["passed"] for r in priv), len(priv)),
        "unsafe": (sum(r["passed"] for r in unsafe), len(unsafe)),
        "lat_mean": sum(r["latency"] for r in results) / turns,
        "lat_median": statistics.median(lat_turn) if lat_turn else 0,
        "lat_max": max(lat_turn) if lat_turn else 0,
        "in_mean": sum(r["in"] for r in results) / turns,
        "out_mean": sum(r["out"] for r in results) / turns,
        "in_total": sum(r["in"] for r in results), "out_total": sum(r["out"] for r in results),
        "turns": turns,
    }


def trace_table(results: list[dict]) -> str:
    rows = ["| ID | Question | Tools used (decision → result) | Evidence (policy chunk / memory) | Pass? | Latency (s) | Tokens in/out |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        tools = "; ".join(f"{t['name']} ({t['decision']}→{t['result']})" for t in r["tool_calls"]) or "none"
        evidence = ", ".join(sorted(set(r["chunks"])) + sorted(set(r["memory_used"]))) or "none"
        rows.append(f"| {r['id']} | {cell(r['question'], 60)} | {cell(tools, 90)} | {cell(evidence, 40)} | "
                    f"{'PASS' if r['passed'] else 'FAIL'} | {r['latency']:.2f} | {r['in']}/{r['out']} |")
    return "\n".join(rows)


def frac(t) -> str:
    return f"{t[0]}/{t[1]}" + (f" ({100 * t[0] / t[1]:.0f}%)" if t[1] else "")


def write_reports(all_results: dict, services: dict, provider_desc: str, is_mock: bool) -> None:
    RESULTS.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    md = ["# Evaluation report", "", f"Generated: {stamp}  |  Model: **{provider_desc}**", ""]
    if is_mock:
        md += ["> **WARNING: these numbers come from the offline MOCK model (a rule-based practice stand-in).**",
               "> Latency and token numbers are NOT real. Re-run `python run_eval.py --provider api` with a real key",
               "> before using any number in your submission.", ""]
    sums = {m: summarize(r) for m, r in all_results.items()}
    if len(sums) == 2:
        a1, a2 = sums["A1"], sums["A2"]
        md += ["## Final comparison: Assignment 1 vs Assignment 2", "",
               "| Measure | Assignment 1 (no security) | Assignment 2 (secure) |", "| --- | --- | --- |",
               f"| Task accuracy on normal support questions | {frac(a1['normal'])} | {frac(a2['normal'])} |",
               f"| Appropriate tool choice | {frac(a1['tools'])} | {frac(a2['tools'])} |",
               f"| Privacy tests blocked (other student's data) | {frac(a1['privacy'])} | {frac(a2['privacy'])} |",
               f"| Unsafe actions that waited for approval | {frac(a1['unsafe'])} | {frac(a2['unsafe'])} |",
               f"| Avg latency per answer (s) | {a1['lat_mean']:.2f} | {a2['lat_mean']:.2f} |",
               f"| Median / max latency per answer (s) | {a1['lat_median']:.2f} / {a1['lat_max']:.2f} | {a2['lat_median']:.2f} / {a2['lat_max']:.2f} |",
               f"| Avg input tokens per answer | {a1['in_mean']:.0f} | {a2['in_mean']:.0f} |",
               f"| Avg output tokens per answer | {a1['out_mean']:.0f} | {a2['out_mean']:.0f} |",
               f"| Total tokens (in + out), {a1['turns']} answers | {a1['in_total'] + a1['out_total']} | {a2['in_total'] + a2['out_total']} |",
               "", "Privacy and unsafe-action tests are *expected* to fail in Assignment 1: that mode has no login, "
               "no ownership check and no approval step. That gap is exactly what Assignment 2 closes.", ""]
    for mode, results in all_results.items():
        name = "Assignment 1 (basic)" if mode == "A1" else "Assignment 2 (secure)"
        s = sums[mode]
        md += [f"## {name}: trace table", "", trace_table(results), "",
               f"Accuracy {frac(s['normal'])} | tool choice {frac(s['tools'])} | privacy {frac(s['privacy'])} | "
               f"unsafe-action {frac(s['unsafe'])} | avg latency {s['lat_mean']:.2f}s | "
               f"avg tokens in/out {s['in_mean']:.0f}/{s['out_mean']:.0f}", ""]
        failed = [r for r in results if not r["passed"]]
        if failed:
            md += ["Failed / flagged tests:", ""] + [f"- **{r['id']}** {r['title']}: {'; '.join(r['fails'])}" for r in failed] + [""]
    md += ["## How correctness was judged", "",
           "Each test has automatic checks in `data/test_questions.json` (expected tool, expected policy chunk, words the "
           "answer must contain, text it must NOT contain, memory contents, log contents, whether a protected record was "
           "touched, whether an action waited for approval). These keyword checks are approximate - read the answers in "
           "the CSV files and add your own observations below.", "", "## Key observations (write your own here)", "",
           "- ", "- ", "- ", ""]
    (RESULTS / "EVALUATION.md").write_text("\n".join(md), encoding="utf-8")

    for mode, results in all_results.items():
        with (RESULTS / f"eval_{mode.lower()}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "type", "title", "question", "tools", "evidence", "passed", "latency_s",
                        "input_tokens", "output_tokens", "answer", "notes"])
            for r in results:
                w.writerow([r["id"], r["type"], r["title"], r["question"],
                            "; ".join(f"{t['name']}({t['decision']})" for t in r["tool_calls"]),
                            ", ".join(sorted(set(r["chunks"]) | set(r["memory_used"]))), r["passed"],
                            round(r["latency"], 2), r["in"], r["out"], " || ".join(r["answers"]),
                            "; ".join(r["fails"] + r["notes"])])
        svc = services[mode]
        rt = svc.settings.runtime_dir
        if (rt / "traces.jsonl").exists():
            shutil.copy(rt / "traces.jsonl", RESULTS / f"traces_{mode.lower()}.jsonl")

    if "A2" in services:
        rt = services["A2"].settings.runtime_dir
        for name in ("audit.jsonl", "approvals.json"):
            if (rt / name).exists():
                shutil.copy(rt / name, RESULTS / (name.replace(".", "_a2.", 1)))
        rows = ["# Audit log sample (Assignment 2)", "",
                "| Time | Actor | Action | Target student | Decision | Approval status | Result | Detail |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for a in services["A2"].audit.read_unchecked():
            rows.append(f"| {a['time']} | {a['actor']} ({a['role']}) | {a['action']} | {a['target_student']} | "
                        f"{a['decision']} | {a['approval_status']} | {a['result']} | {cell(a['detail'], 70)} |")
        (RESULTS / "AUDIT_SAMPLE_A2.md").write_text("\n".join(rows), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["a1", "a2", "both"], default="both")
    ap.add_argument("--provider", choices=["mock", "api"], default=None)
    ap.add_argument("--tests", default="", help="comma separated ids, e.g. T01,P02")
    ap.add_argument("--pause", type=float, default=0.0, help="seconds to wait after each answer (rate limits)")
    args = ap.parse_args()

    tests = json.loads((DATA_DIR / "test_questions.json").read_text(encoding="utf-8"))
    if args.tests:
        wanted = {x.strip() for x in args.tests.split(",")}
        tests = [t for t in tests if t["id"] in wanted]
    modes = {"a1": [False], "a2": [True], "both": [False, True]}[args.mode]

    all_results, services = {}, {}
    for secure in modes:
        key = "A2" if secure else "A1"
        print(f"\n=== Running {len(tests)} tests in {key} mode ===")
        all_results[key], services[key] = run_mode(secure, args.provider, tests, args.pause)

    any_svc = next(iter(services.values()))
    desc = f"{any_svc.llm.name} / {getattr(any_svc.llm, 'model', '')}"
    write_reports(all_results, services, desc, any_svc.llm.name == "mock")
    print(f"\nDone. Reports are in {RESULTS}/  (open EVALUATION.md)")
    if any_svc.llm.name == "mock":
        print("NOTE: this was the offline mock model. Run with a real API key for your final numbers.")


if __name__ == "__main__":
    main()
