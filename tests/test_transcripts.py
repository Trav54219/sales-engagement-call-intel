from pathlib import Path

import pytest

from salesintel.transcripts import analyze, load_dir, parse_transcript, rep_scorecard

SMALL = """\
# rep: Rep X
[00:00-00:30] REP: What brings you here today? Anything urgent?
[00:30-01:30] PROSPECT: Honestly our budget is tight and the price worries me.
[01:30-02:00] REP: What number would feel reasonable?
[02:00-03:00] PROSPECT: I need to run it by my VP first.
[03:00-03:20] REP: Understood.
[03:20-04:00] PROSPECT: Let's schedule a call Friday at 3pm.
"""


def test_parse_and_talk_ratio_exact():
    a = analyze(parse_transcript(SMALL, "c"))
    # rep: 30+30+20 = 80s ; prospect: 60+60+40 = 160s
    assert a["talk_ratio_rep"] == pytest.approx(0.333, abs=1e-3)
    assert a["talk_ratio_prospect"] == pytest.approx(0.667, abs=1e-3)
    assert a["duration_s"] == 240
    assert a["rep_questions"] == 3
    assert a["questions_per_min"] == 0.75
    assert a["longest_rep_monologue_s"] == 30


def test_objection_tags_and_followup():
    a = analyze(parse_transcript(SMALL, "c"))
    tags = [o["tags"] for o in a["objections"]]
    assert tags == [["price"], ["authority"]]
    assert a["objections"][0]["rep_followed_with_question"] is True
    assert a["objections"][1]["rep_followed_with_question"] is False


def test_next_step_detection_with_date():
    a = analyze(parse_transcript(SMALL, "c"))
    assert len(a["next_steps"]) == 1
    assert a["next_steps"][0]["has_date"] is True
    assert a["next_steps"][0]["by"] == "prospect"


def test_topics_tracked_with_seconds():
    a = analyze(parse_transcript(SMALL, "c"))
    assert a["topics"]["pricing"] == {"turns": 1, "seconds": 60}  # only the prospect budget/price turn


def test_no_next_step_scores_zero_for_that_part():
    txt = "# rep: R\n[00:00-00:30] REP: Hello there?\n[00:30-01:00] PROSPECT: Hi.\n"
    a = analyze(parse_transcript(txt))
    assert a["next_steps"] == []
    assert a["score"]["parts"]["next_step"] == 0


def test_bad_line_raises():
    with pytest.raises(ValueError):
        parse_transcript("[00:00-00:10] SOMEONE: hi")
    with pytest.raises(ValueError):
        parse_transcript("[00:20-00:10] REP: hi")


def test_synthetic_files_load_and_separate_good_from_bad():
    data = Path(__file__).parent.parent / "data" / "transcripts"
    res = {a["call_id"]: a for a in map(analyze, load_dir(data))}
    assert set(res) == {"call_01", "call_02", "call_03"}
    # call_02 is a deliberate rep monologue: rep dominates, almost no questions
    assert res["call_02"]["talk_ratio_rep"] > 0.8
    assert res["call_02"]["rep_questions"] == 0
    assert res["call_01"]["score"]["total"] > res["call_02"]["score"]["total"]
    assert {"competitor", "timing"} <= {t for o in res["call_02"]["objections"] for t in o["tags"]}
    assert any(n["has_date"] for n in res["call_03"]["next_steps"])


def test_scorecard_groups_by_rep():
    data = Path(__file__).parent.parent / "data" / "transcripts"
    sc = rep_scorecard([analyze(c) for c in load_dir(data)])
    assert sc["Rep A"]["calls"] == 2 and sc["Rep B"]["calls"] == 1
    assert sc["Rep A"]["avg_score"] > sc["Rep B"]["avg_score"]
