"""Policy retrieval (the "R" in RAG) with NO extra libraries.

How it works (easy version):
  1. The handbook is split into small chunks - one rule per chunk (### FEE-04 ...).
  2. For a question we find which chunks share the most *important* words with it
     (rare words like "portal" count more than common words like "fee").
  3. We return only the best 1-3 chunks. If nothing is good enough we return an
     empty list, so the agent can honestly say "I do not have enough information".
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

STOPWORDS = set("""a an the is are was were be been am i me my we our you your it its to of in on at for from by with
and or but if then so do does did can could will would should may might shall this that these those there here what
which who whom how when where why not no yes please tell show give need want get got have has had about into as
any some also than too very just""".split())

SYNONYMS = {"paid": "pay", "failed": "fail", "failure": "fail", "fails": "fail", "failing": "fail",
            "down": "fail", "error": "fail", "dropped": "drop", "dropping": "drop",
            "withdraw": "withdraw", "withdrawal": "withdraw", "refunded": "refund",
            "scholarships": "scholarship", "instalments": "instalment", "installment": "instalment",
            "installments": "instalment", "emails": "email", "tuition": "tuition",
            "continue": "renew", "continued": "renew", "eligible": "criteria", "eligibility": "criteria",
            "semester": "term", "semesters": "term"}


def stem(word: str) -> str:
    word = SYNONYMS.get(word, word)
    for suffix in ("ment", "ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    if len(word) > 3 and word[-1] == word[-2]:      # dropp -> drop
        word = word[:-1]
    return SYNONYMS.get(word, word)


def tokenize(text: str) -> list[str]:
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 1]


class PolicyRetriever:
    MIN_SCORE = 0.55       # below this, the chunk is not relevant enough
    TOP_K = 3

    def __init__(self, handbook_path: Path):
        self.chunks = self._load_chunks(handbook_path)
        self.chunk_tokens = {c["id"]: set(tokenize(c["title"] + " " + c["text"])) for c in self.chunks}
        self.title_tokens = {c["id"]: set(tokenize(c["title"])) for c in self.chunks}
        n = len(self.chunks)
        df = Counter(t for toks in self.chunk_tokens.values() for t in toks)
        self.idf = {t: math.log((n + 1) / (d + 0.5)) + 1 for t, d in df.items()}
        self.unknown_idf = math.log(n + 1) + 1          # words that appear nowhere in the handbook

    @staticmethod
    def _load_chunks(path: Path) -> list[dict]:
        chunks = []
        for block in re.split(r"\n(?=### )", path.read_text(encoding="utf-8")):
            m = re.match(r"### (\S+) (.+)\n+(.*)", block.strip(), re.S)
            if m:
                chunks.append({"id": m.group(1), "title": m.group(2).strip(), "text": m.group(3).strip()})
        return chunks

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        q = set(tokenize(query))
        if not q:
            return []
        total = sum(self.idf.get(t, self.unknown_idf) for t in q)
        scored = []
        for c in self.chunks:
            matched = sum(self.idf[t] for t in q if t in self.chunk_tokens[c["id"]])
            in_title = sum(self.idf[t] for t in q if t in self.title_tokens[c["id"]])
            scored.append((min(1.0, (matched + 0.5 * in_title) / total), c))   # title match = small bonus
        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored or scored[0][0] < self.MIN_SCORE:
            return []
        best = scored[0][0]
        out = []
        for score, c in scored[: top_k or self.TOP_K]:
            if score >= self.MIN_SCORE and score >= 0.85 * best:
                out.append({"id": c["id"], "title": c["title"], "text": c["text"], "score": round(score, 2)})
        return out
