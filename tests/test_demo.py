from creator_breakout.demo import load_demo_creator
from creator_breakout.scoring import analyze_creator


def test_demo_is_fictional_and_produces_three_clear_breakouts():
    creator = load_demo_creator()
    result = analyze_creator(creator)

    assert "虚构数据" in creator.name
    assert len(creator.posts) == 20
    assert len(result.breakouts) == 3
    assert result.breakouts[0].post.id == "20"
