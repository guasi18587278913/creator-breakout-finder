"""Small, provider-neutral data models used by the app and exporters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Platform = Literal["xiaohongshu", "douyin", "bilibili", "tiktok", "youtube", "x"]
Metric = Literal["likes", "views"]
Confidence = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class CreatorIdentity:
    platform: Platform
    uid: str
    handle: str
    homepage_url: str


@dataclass(frozen=True, slots=True)
class Post:
    id: str
    title: str
    url: str
    published_at: datetime | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    saves: int | None = None
    author_name: str = ""
    author_uid: str = ""
    author_handle: str = ""
    author_followers: int | None = None


@dataclass(frozen=True, slots=True)
class Creator:
    platform: Platform
    uid: str
    handle: str
    name: str
    homepage_url: str
    posts: tuple[Post, ...]
    followers: int | None = None


@dataclass(frozen=True, slots=True)
class ScoredPost:
    post: Post
    value: int
    baseline: float
    multiple: float
    percentile: float
    is_breakout: bool


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    creator: Creator
    metric: Metric
    metric_label: str
    baseline: float
    sample_size: int
    confidence: Confidence
    scored: tuple[ScoredPost, ...]
    breakouts: tuple[ScoredPost, ...]
