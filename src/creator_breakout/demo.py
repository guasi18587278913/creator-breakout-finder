"""Load the fictional offline account bundled with the open-source demo."""

from __future__ import annotations

import json
from datetime import datetime
from importlib.resources import files

from .models import Creator, Post


def _datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    return datetime.fromisoformat(text.replace("Z", "+00:00")) if text else None


def load_demo_creator() -> Creator:
    resource = files("creator_breakout").joinpath("data/sample_account.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    posts = tuple(
        Post(
            id=str(item["id"]),
            title=str(item["title"]),
            url=str(item["url"]),
            published_at=_datetime(item.get("published_at", "")),
            views=item.get("views"),
            likes=item.get("likes"),
            comments=item.get("comments"),
            shares=item.get("shares"),
            saves=item.get("saves"),
            author_name=str(payload["name"]),
            author_uid=str(payload["uid"]),
            author_handle=str(payload["handle"]),
            author_followers=payload.get("followers"),
        )
        for item in payload["posts"]
    )
    return Creator(
        platform=payload["platform"],
        uid=str(payload["uid"]),
        handle=str(payload["handle"]),
        name=str(payload["name"]),
        homepage_url=str(payload["homepage_url"]),
        followers=payload.get("followers"),
        posts=posts,
    )
