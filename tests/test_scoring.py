from datetime import UTC, datetime, timedelta

import pytest

from creator_breakout.models import Creator, Post
from creator_breakout.scoring import InsufficientSampleError, analyze_creator


def post(index: int, *, likes=None, views=None) -> Post:
    return Post(
        id=str(index),
        title=f"作品 {index}",
        url=f"https://example.com/{index}",
        published_at=datetime.now(UTC) - timedelta(days=index + 7),
        likes=likes,
        views=views,
    )


def creator(platform: str, posts: list[Post]) -> Creator:
    return Creator(
        platform=platform,
        uid="creator-1",
        handle="creator",
        name="示例创作者",
        homepage_url="https://example.com/creator",
        posts=tuple(posts),
    )


def test_likes_platform_uses_recent_median_and_marks_real_outliers():
    posts = [
        post(i, likes=value)
        for i, value in enumerate([500, 320, 140, 120, 110, 100, 100, 95, 90, 85])
    ]

    result = analyze_creator(creator("x", posts))

    assert result.metric == "likes"
    assert result.baseline == 105
    assert [item.post.id for item in result.breakouts] == ["0", "1"]
    assert result.breakouts[0].multiple == pytest.approx(4.76, abs=0.01)
    assert result.breakouts[0].percentile == 100


def test_video_platform_uses_views():
    posts = [
        post(i, views=value)
        for i, value in enumerate([9000, 3500, 1200, 1100, 1000, 950, 900, 850, 800, 750])
    ]

    result = analyze_creator(creator("youtube", posts))

    assert result.metric == "views"
    assert result.baseline == 975
    assert [item.post.id for item in result.breakouts] == ["0", "1"]


def test_absolute_floor_blocks_tiny_false_positive():
    posts = [post(i, likes=value) for i, value in enumerate([10, 4, 3, 2, 2, 2, 1, 1, 1, 1])]

    result = analyze_creator(creator("xiaohongshu", posts))

    assert result.breakouts == ()
    assert result.scored[0].multiple == 5
    assert result.scored[0].is_breakout is False


def test_rounding_cannot_promote_a_post_below_two_times_baseline():
    posts = [post(i, likes=value) for i, value in enumerate([1999, *([1000] * 9)])]

    result = analyze_creator(creator("x", posts))

    assert result.scored[0].multiple == 2
    assert result.scored[0].is_breakout is False
    assert result.breakouts == ()


def test_missing_metrics_are_ignored_but_zero_is_a_real_sample():
    posts = [post(i, likes=value) for i, value in enumerate([300, 100, 100, 100, 100, None, None])]

    result = analyze_creator(creator("douyin", posts))

    assert result.sample_size == 5
    assert result.baseline == 100
    assert result.breakouts[0].post.id == "0"


def test_requires_five_valid_samples():
    posts = [post(i, likes=value) for i, value in enumerate([300, 100, 100, None, None])]

    with pytest.raises(InsufficientSampleError, match="至少需要 5 条"):
        analyze_creator(creator("x", posts))


def test_zero_baseline_is_reported_as_insufficient():
    posts = [post(i, likes=0) for i in range(10)]

    with pytest.raises(InsufficientSampleError, match="基线为 0"):
        analyze_creator(creator("x", posts))


@pytest.mark.parametrize(("count", "confidence"), [(5, "low"), (10, "medium"), (20, "high")])
def test_confidence_reflects_sample_size(count, confidence):
    posts = [post(i, likes=100 + i) for i in range(count)]

    assert analyze_creator(creator("x", posts)).confidence == confidence
