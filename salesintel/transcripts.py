"""Call-transcript analysis: talk ratio, questions, objections, next steps, topics, scorecard.

All detection is keyword/regex heuristics, deliberately transparent. It is not ML.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

TURN_RE = re.compile(r"^\[(\d+):(\d{2})-(\d+):(\d{2})\]\s*(REP|PROSPECT)\s*:\s*(.+)$")

OBJECTION_RULES = {
    "price": r"too expensive|over budget|no budget|budget is|pricey|can'?t afford|that'?s a lot",
    "timing": r"not the right time|not right now|next quarter|next year|too busy|after the (?:audit|holidays|migration)|maybe later",
    "competitor": r"already (?:use|using|have|work with)|current (?:vendor|provider|tool)|we use \w+",
    "authority": r"run it by|my (?:boss|vp|cfo|director)|not my decision|sign.?off|procurement",
    "need": r"don'?t need|no need|not a priority|works fine",
}
TOPIC_RULES = {
    "pricing": r"price|pricing|cost|budget|discount|contract",
    "integration": r"integrat|crm|api|salesforce|hubspot|sync",
    "security": r"security|soc ?2|compliance|sso|encrypt",
    "onboarding": r"onboard|implementation|rollout|training|go.?live",
    "reporting": r"report|dashboard|analytics|forecast",
}
NEXT_STEP_RE = re.compile(
    r"schedule|book|set up|send (?:over|you)|follow up|calendar invite|demo (?:on|next)|let'?s (?:talk|meet|reconnect)|"
    r"next (?:monday|tuesday|wednesday|thursday|friday|week)", re.I)
DATE_RE = re.compile(
    r"monday|tuesday|wednesday|thursday|friday|tomorrow|next week|\b\d{1,2}(?::\d{2})?\s?(?:am|pm)\b|\b\d{1,2}/\d{1,2}\b", re.I)


@dataclass(frozen=True)
class Turn:
    start: int
    end: int
    role: str  # REP | PROSPECT
    text: str

    @property
    def seconds(self) -> int:
        return max(0, self.end - self.start)


@dataclass
class Call:
    id: str
    rep: str
    turns: list
    meta: dict = field(default_factory=dict)


def parse_transcript(text: str, call_id: str = "call") -> Call:
    meta, turns = {}, []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            k, _, v = line[1:].partition(":")
            meta[k.strip().lower()] = v.strip()
            continue
        m = TURN_RE.match(line)
        if not m:
            raise ValueError(f"unparseable line: {line!r}")
        s = int(m[1]) * 60 + int(m[2])
        e = int(m[3]) * 60 + int(m[4])
        if e < s:
            raise ValueError(f"end before start: {line!r}")
        turns.append(Turn(s, e, m[5], m[6].strip()))
    return Call(id=call_id, rep=meta.get("rep", "unknown"), turns=turns, meta=meta)


def load_dir(path) -> list:
    return [parse_transcript(p.read_text(), p.stem) for p in sorted(Path(path).glob("*.txt"))]


def analyze(call: Call) -> dict:
    rep = [t for t in call.turns if t.role == "REP"]
    pro = [t for t in call.turns if t.role == "PROSPECT"]
    rep_s, pro_s = sum(t.seconds for t in rep), sum(t.seconds for t in pro)
    talk = rep_s + pro_s
    duration = (max(t.end for t in call.turns) - min(t.start for t in call.turns)) if call.turns else 0
    questions = sum(t.text.count("?") for t in rep)

    objections = []
    for i, t in enumerate(call.turns):
        if t.role != "PROSPECT":
            continue
        tags = [k for k, rx in OBJECTION_RULES.items() if re.search(rx, t.text, re.I)]
        if tags:
            nxt = call.turns[i + 1] if i + 1 < len(call.turns) else None
            objections.append({
                "at": t.start, "tags": tags, "text": t.text,
                "rep_followed_with_question": bool(nxt and nxt.role == "REP" and "?" in nxt.text),
            })

    next_steps = []
    for t in call.turns:
        if NEXT_STEP_RE.search(t.text):
            next_steps.append({"at": t.start, "by": t.role.lower(), "text": t.text,
                               "has_date": bool(DATE_RE.search(t.text))})

    topics = {}
    for k, rx in TOPIC_RULES.items():
        hit = [t for t in call.turns if re.search(rx, t.text, re.I)]
        if hit:
            topics[k] = {"turns": len(hit), "seconds": sum(t.seconds for t in hit)}

    a = {
        "call_id": call.id,
        "rep": call.rep,
        "duration_s": duration,
        "talk_ratio_rep": round(rep_s / talk, 3) if talk else 0.0,
        "talk_ratio_prospect": round(pro_s / talk, 3) if talk else 0.0,
        "rep_questions": questions,
        "questions_per_min": round(questions / (duration / 60), 2) if duration else 0.0,
        "longest_rep_monologue_s": max((t.seconds for t in rep), default=0),
        "objections": objections,
        "next_steps": next_steps,
        "topics": topics,
    }
    a["score"] = score(a)
    return a


def score(a: dict) -> dict:
    """0-100, heuristic weights (arbitrary, documented): talk 30, questions 25, next step 25, objections 20."""
    r = a["talk_ratio_rep"]
    dist = 0.35 - r if r < 0.35 else (r - 0.55 if r > 0.55 else 0.0)
    talk = 30 * max(0.0, 1 - dist / 0.2)
    q = 25 * min(1.0, a["questions_per_min"] / 0.8)
    ns = a["next_steps"]
    nxt = 25 if any(n["has_date"] for n in ns) else (10 if ns else 0)
    obs = a["objections"]
    obj = 20.0 if not obs else 20 * sum(o["rep_followed_with_question"] for o in obs) / len(obs)
    parts = {"talk_ratio": round(talk, 1), "questions": round(q, 1), "next_step": nxt, "objection_handling": round(obj, 1)}
    return {"total": round(sum(parts.values()), 1), "parts": parts}


def rep_scorecard(analyses: list) -> dict:
    by: dict = {}
    for a in analyses:
        by.setdefault(a["rep"], []).append(a)
    out = {}
    for rep, items in by.items():
        n = len(items)
        out[rep] = {
            "calls": n,
            "avg_score": round(sum(i["score"]["total"] for i in items) / n, 1),
            "avg_talk_ratio_rep": round(sum(i["talk_ratio_rep"] for i in items) / n, 3),
            "avg_questions_per_min": round(sum(i["questions_per_min"] for i in items) / n, 2),
            "calls_with_dated_next_step": sum(any(s["has_date"] for s in i["next_steps"]) for i in items),
            "objection_tags": sorted({t for i in items for o in i["objections"] for t in o["tags"]}),
        }
    return out
