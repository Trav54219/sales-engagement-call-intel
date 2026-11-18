"""Export a Sequence as JSON shaped like a sales-engagement sequence payload.

MODELED, NOT CONNECTED: the layout (JSON:API-style data/attributes/relationships/included,
sequence -> sequenceSteps -> templates) imitates how products in this category describe
sequences. It is not validated against any vendor's real schema and no vendor API is called.
"""
from __future__ import annotations

from .sequence import Sequence

MODELED_NOTE = (
    "Modeled on the general shape of sales-engagement sequence payloads (Outreach/Salesloft style). "
    "Not the official schema; never sent to any vendor."
)


def to_payload(seq: Sequence) -> dict:
    included, step_refs = [], []
    for i, s in enumerate(seq.steps, start=1):
        tmpl_refs = []
        for v in s.variants:
            tid = f"tmpl-{s.id}-{v.name}"
            included.append({"type": "template", "id": tid, "attributes": {
                "name": f"{s.id} / {v.name}", "subject": v.subject, "bodyHtml": v.body,
                "abWeight": v.weight}})
            tmpl_refs.append({"type": "template", "id": tid})
        sid = f"step-{s.id}"
        included.append({"type": "sequenceStep", "id": sid, "attributes": {
            "order": i, "stepType": s.channel, "interval": s.delay_business_days,
            "intervalUnit": "business_days", "abTestingEnabled": len(s.variants) > 1},
            "relationships": {"templates": {"data": tmpl_refs}}})
        step_refs.append({"type": "sequenceStep", "id": sid})
    w = seq.window
    return {
        "meta": {"modeled": True, "note": MODELED_NOTE},
        "data": {
            "type": "sequence",
            "id": f"seq-{seq.name.lower().replace(' ', '-')}",
            "attributes": {
                "name": seq.name,
                "stopOnReply": True,
                "schedule": {"start": w.start.strftime("%H:%M"), "end": w.end.strftime("%H:%M"),
                             "days": sorted(w.days), "holidays": sorted(d.isoformat() for d in seq.holidays),
                             "timezoneBasis": "prospect"},
            },
            "relationships": {"sequenceSteps": {"data": step_refs}},
        },
        "included": included,
    }
