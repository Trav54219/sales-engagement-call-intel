import json

from salesintel.demo import demo_sequence
from salesintel.export import to_payload


def test_payload_shape_and_modeled_label():
    p = to_payload(demo_sequence())
    json.dumps(p)  # serializable
    assert p["meta"]["modeled"] is True
    assert p["data"]["type"] == "sequence"
    assert p["data"]["attributes"]["stopOnReply"] is True
    refs = p["data"]["relationships"]["sequenceSteps"]["data"]
    ids = {i["id"] for i in p["included"]}
    assert len(refs) == 4 and all(r["id"] in ids for r in refs)
    steps = [i for i in p["included"] if i["type"] == "sequenceStep"]
    assert [s["attributes"]["order"] for s in steps] == [1, 2, 3, 4]
    assert steps[0]["attributes"]["abTestingEnabled"] is True
    assert steps[1]["attributes"]["abTestingEnabled"] is False
    assert steps[2]["attributes"]["intervalUnit"] == "business_days"
    for s in steps:
        for t in s["relationships"]["templates"]["data"]:
            assert t["id"] in ids
