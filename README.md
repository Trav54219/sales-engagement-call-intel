# sales-engagement-call-intel

Two small Python modules (standard library only) that model the core of two tool categories:

1. **Sales engagement** (Outreach / Salesloft style): a sequence engine.
2. **Conversation intelligence** (Gong style): a call-transcript analyzer and rep scorecard.

> **Not connected to any vendor.** Nothing here calls Outreach, Salesloft, Gong or any other API.
> The JSON export imitates the general shape of a sequence payload; it is not validated against a real schema.

> **All data is synthetic.** The three transcripts in `data/transcripts/` were written for this repo, with fictional people and companies. No real calls, customers or results.

## Sequence engine (`salesintel/sequence.py`, `calendar.py`)

- Steps with a delay in **business days** (weekends and a holiday list skipped)
- **Send windows** (default Mon-Fri 09:00-17:00) evaluated in each prospect's own timezone
- **Stop on reply**; bounce and unsubscribe also stop. A later reply never overrides a stop.
- **Per-step A/B variants** with weights; assignment is a deterministic hash of prospect+step, so reruns agree
- `variant_report()` gives raw sent/replied counts per step and variant (no significance testing)

## Call analyzer (`salesintel/transcripts.py`)

Per call: talk-to-listen ratio, rep question count and rate, longest rep monologue, objection tags (price, timing, competitor, authority, need) and whether the rep followed with a question, next-step detection (with whether a day/time was named), topic tracking (turns and seconds), and a 0-100 score. `rep_scorecard` averages by rep.

Detection is plain regex and keyword rules, not ML. The score weights (talk 30, questions 25, next step 25, objection handling 20) are my own arbitrary heuristic, not an industry benchmark.

Transcript format: `[mm:ss-mm:ss] REP|PROSPECT: text`, with `# rep: name` headers.

## Run

```
python -m pip install pytest
python -m pytest
python -m salesintel analyze data/transcripts
python -m salesintel export-sequence
```

## What is verified

- `pytest`: unit tests for business-day math, window rules, timezone scheduling, stop-on-reply, bounce/unsubscribe, variant determinism and weighting, transcript metrics on a hand-computed example, and export structure.
- Verified means "tests pass on synthetic input". Detector accuracy on real calls and compatibility with any real product payload are **not** tested.

## Limits

No persistence, no actual sending, no calendar holidays beyond a list you supply, no speech-to-text, and variant stats make no statistical claims.
