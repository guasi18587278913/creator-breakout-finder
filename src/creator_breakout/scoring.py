"""Robust, creator-relative breakout scoring."""

from __future__ import annotations

import statistics

from .models import AnalysisResult, Confidence, Creator, Metric, Post, ScoredPost

BASELINE_WINDOW_POSTS = 30
MIN_BASELINE_POSTS = 5
BREAKOUT_MULTIPLE = 2.0
BREAKOUT_PERCENTILE = 90.0
MIN_LIKES = 20
MIN_VIEWS = 500
VIEW_PLATFORMS = {"bilibili", "youtube"}


class InsufficientSampleError(ValueError):
    """Raised when an account cannot support an honest personal baseline."""


def _published_sort_key(post: Post) -> float:
    return post.published_at.timestamp() if post.published_at is not None else float("-inf")


def _confidence(sample_size: int) -> Confidence:
    if sample_size >= 20:
        return "high"
    if sample_size >= 10:
        return "medium"
    return "low"


def analyze_creator(
    creator: Creator,
    *,
    window: int = BASELINE_WINDOW_POSTS,
    min_samples: int = MIN_BASELINE_POSTS,
) -> AnalysisResult:
    """Compare recent valid posts with the creator's own median performance.

    This is a retrospective snapshot analysis. It does not claim real-time velocity or
    causality because a one-off API read has no equal-age performance snapshots.
    """
    metric: Metric = "views" if creator.platform in VIEW_PLATFORMS else "likes"
    metric_label = "播放" if metric == "views" else "赞"
    floor = MIN_VIEWS if metric == "views" else MIN_LIKES
    ordered = sorted(creator.posts, key=_published_sort_key, reverse=True)
    recent = ordered[: max(1, int(window))]
    valid: list[tuple[Post, int]] = []
    for item in recent:
        raw_value = getattr(item, metric)
        if raw_value is None:
            continue
        value = int(raw_value)
        if value < 0:
            continue
        valid.append((item, value))

    required = max(1, int(min_samples))
    if len(valid) < required:
        raise InsufficientSampleError(
            f"至少需要 {required} 条带{metric_label}数据的作品，当前只有 {len(valid)} 条"
        )

    values = [value for _, value in valid]
    baseline = float(statistics.median(values))
    if baseline <= 0:
        raise InsufficientSampleError(f"账号{metric_label}基线为 0，暂时无法可靠判断爆款")

    scored: list[ScoredPost] = []
    sample_size = len(values)
    for item, value in valid:
        raw_multiple = value / baseline
        raw_percentile = sum(other <= value for other in values) / sample_size * 100
        multiple = round(raw_multiple, 2)
        percentile = round(raw_percentile, 1)
        is_breakout = (
            value >= floor
            and raw_multiple >= BREAKOUT_MULTIPLE
            and raw_percentile >= BREAKOUT_PERCENTILE
        )
        scored.append(
            ScoredPost(
                post=item,
                value=value,
                baseline=baseline,
                multiple=multiple,
                percentile=percentile,
                is_breakout=is_breakout,
            )
        )

    scored.sort(key=lambda item: (item.multiple, item.value, item.post.id), reverse=True)
    breakouts = tuple(item for item in scored if item.is_breakout)
    return AnalysisResult(
        creator=creator,
        metric=metric,
        metric_label=metric_label,
        baseline=baseline,
        sample_size=sample_size,
        confidence=_confidence(sample_size),
        scored=tuple(scored),
        breakouts=breakouts,
    )
