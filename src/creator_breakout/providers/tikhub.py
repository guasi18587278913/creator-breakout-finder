"""Minimal BYOK TikHub adapter for supported creator homepages."""

from __future__ import annotations

import datetime as dt
import math
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

import httpx

from ..models import Creator, CreatorIdentity, Platform, Post

DEFAULT_BASE_URL = "https://api.tikhub.io"


class TikHubError(RuntimeError):
    """A provider request or response could not be completed safely."""


class MissingApiKey(TikHubError):
    """The user did not configure their own TikHub key."""


@dataclass(frozen=True, slots=True)
class Endpoint:
    path: str
    identity_param: str
    cursor_param: str = ""


_POST_ENDPOINTS: dict[Platform, Endpoint] = {
    "douyin": Endpoint("/api/v1/douyin/web/fetch_user_post_videos", "sec_user_id", "max_cursor"),
    "xiaohongshu": Endpoint(
        "/api/v1/xiaohongshu/app/get_user_notes", "user_id", "cursor"
    ),
    "bilibili": Endpoint("/api/v1/bilibili/web/fetch_user_post_videos", "uid", "pn"),
    "tiktok": Endpoint("/api/v1/tiktok/app/v3/fetch_user_post_videos", "sec_user_id", "max_cursor"),
    "youtube": Endpoint(
        "/api/v1/youtube/web/get_channel_videos", "channel_id", "continuation_token"
    ),
    "x": Endpoint("/api/v1/twitter/web/fetch_user_post_tweet", "screen_name", "cursor"),
}


def _get(value: Any, *path: str, default=None):
    current = value
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def _optional_number(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        amount = float(value)
        suffix = ""
    else:
        text = str(value).strip().replace(",", "")
        match = re.match(r"^(\d+(?:\.\d+)?)\s*(万|亿|[KMBW])?", text, flags=re.I)
        if not match:
            return None
        try:
            amount = float(match.group(1))
        except ValueError:
            return None
        suffix = (match.group(2) or "").upper()
    if not math.isfinite(amount) or amount < 0:
        return None
    multiplier = {
        "K": 1_000,
        "M": 1_000_000,
        "B": 1_000_000_000,
        "W": 10_000,
        "万": 10_000,
        "亿": 100_000_000,
    }.get(suffix, 1)
    return int(amount * multiplier)


def _number(value: Any) -> int:
    return _optional_number(value) or 0


def _timestamp(value: Any) -> dt.datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) or str(value).isdigit():
        raw = float(value)
        if raw > 100_000_000_000:
            raw /= 1000
        try:
            return dt.datetime.fromtimestamp(raw, tz=dt.UTC)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    try:
        return dt.datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y").astimezone(dt.UTC)
    except ValueError:
        pass
    match = re.search(r"(\d+)\s*(minute|hour|day|week|month|year)s?\s+ago", text, re.I)
    if match:
        amount = int(match.group(1))
        seconds = {
            "minute": 60,
            "hour": 3600,
            "day": 86_400,
            "week": 604_800,
            "month": 2_592_000,
            "year": 31_536_000,
        }[match.group(2).lower()]
        return dt.datetime.now(dt.UTC) - dt.timedelta(seconds=amount * seconds)
    return None


def _stats(source: Any) -> dict[str, int | None]:
    if not isinstance(source, dict):
        source = {}

    def first(*keys: str) -> int | None:
        for key in keys:
            if key in source and source.get(key) is not None:
                value = _optional_number(source.get(key))
                if value is not None:
                    return value
        return None

    return {
        "views": first(
            "play_count", "playCount", "view", "view_count", "number_of_views", "play", "views"
        ),
        "likes": first(
            "digg_count",
            "diggCount",
            "liked_count",
            "like",
            "likeNum",
            "likes",
            "like_count",
            "favorites",
        ),
        "comments": first(
            "comment_count",
            "commentCount",
            "reply",
            "comment",
            "comments_count",
            "video_review",
            "replies",
        ),
        "shares": first("share_count", "shareCount", "share", "shared_count", "retweets"),
        "saves": first(
            "collect_count",
            "collectCount",
            "favorite",
            "collected_count",
            "favorites_count",
            "bookmarks",
        ),
    }


def _post(
    *,
    post_id: Any,
    title: Any,
    url: str,
    published_at: Any,
    stats: dict[str, int | None],
    author: dict[str, Any] | None = None,
) -> Post:
    author = author or {}
    followers = author.get("followers")
    if followers is None:
        followers = author.get("follower_count")
    return Post(
        id=str(post_id or "").strip(),
        title=re.sub(r"\s+", " ", str(title or "")).strip()[:4000] or "（无标题）",
        url=str(url or "").strip(),
        published_at=_timestamp(published_at),
        views=stats["views"],
        likes=stats["likes"],
        comments=stats["comments"],
        shares=stats["shares"],
        saves=stats["saves"],
        author_name=str(author.get("name") or author.get("nickname") or "").strip(),
        author_uid=str(author.get("uid") or author.get("sec_uid") or "").strip(),
        author_handle=str(
            author.get("handle") or author.get("unique_id") or author.get("screen_name") or ""
        ).strip(),
        author_followers=_optional_number(followers),
    )


def _aweme(platform: Platform, item: dict[str, Any]) -> Post:
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    post_id = item.get("aweme_id") or item.get("id")
    handle = author.get("unique_id") or "_"
    safe_post_id = quote(str(post_id or ""), safe="")
    if platform == "douyin":
        fallback = f"https://www.douyin.com/video/{safe_post_id}"
    else:
        safe_handle = quote(str(handle), safe="._")
        fallback = f"https://www.tiktok.com/@{safe_handle}/video/{safe_post_id}"
    return _post(
        post_id=post_id,
        title=item.get("desc") or item.get("title"),
        url=fallback,
        published_at=item.get("create_time") or item.get("createTime"),
        stats=_stats(item.get("statistics") or item.get("stats") or item),
        author={
            "name": author.get("nickname"),
            "uid": author.get("sec_uid"),
            "handle": handle,
            "followers": author.get("follower_count"),
        },
    )


def parse_posts(platform: Platform, payload: dict[str, Any]) -> tuple[list[Post], str, bool]:
    """Normalize one TikHub user-post response without retaining the raw payload."""
    posts: list[Post] = []
    cursor = ""
    has_more = False

    if platform in {"douyin", "tiktok"}:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        posts = [
            _aweme(platform, item)
            for item in data.get("aweme_list") or []
            if isinstance(item, dict)
        ]
        cursor = str(data.get("max_cursor") or "")
        has_more = bool(data.get("has_more"))

    elif platform == "xiaohongshu":
        data = _get(payload, "data", "data", default={}) or {}
        notes = data.get("notes") if isinstance(data, dict) else []
        if not isinstance(notes, list):
            notes = []
        for note in notes or []:
            if not isinstance(note, dict) or not note.get("id"):
                continue
            note_id = str(note["id"])
            token = str(note.get("xsec_token") or "")
            url = f"https://www.xiaohongshu.com/explore/{quote(note_id, safe='')}"
            if token:
                url += "?" + urlencode({"xsec_token": token, "xsec_source": "pc_user"})
            user = note.get("user") if isinstance(note.get("user"), dict) else {}
            posts.append(
                _post(
                    post_id=note_id,
                    title=note.get("title") or note.get("display_title") or note.get("desc"),
                    url=url,
                    published_at=note.get("create_time") or note.get("time"),
                    stats=_stats(note),
                    author={
                        "name": user.get("nickname"),
                        "uid": user.get("userid") or user.get("user_id"),
                    },
                )
            )
        cursor = str((notes[-1].get("cursor") if notes else "") or "")
        has_more = bool(data.get("has_more")) if isinstance(data, dict) else False

    elif platform == "bilibili":
        data = _get(payload, "data", "data", default={}) or {}
        listing = data.get("list") if isinstance(data, dict) else {}
        items = listing.get("vlist") if isinstance(listing, dict) else []
        for item in items or []:
            if not isinstance(item, dict) or not (item.get("bvid") or item.get("aid")):
                continue
            post_id = item.get("bvid") or item.get("aid")
            owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
            posts.append(
                _post(
                    post_id=post_id,
                    title=re.sub(r"<[^>]+>", "", str(item.get("title") or "")),
                    url=f"https://www.bilibili.com/video/{quote(str(post_id), safe='')}",
                    published_at=item.get("pubdate") or item.get("created") or item.get("senddate"),
                    stats=_stats(item.get("stat") or item),
                    author={
                        "name": owner.get("name") or item.get("author"),
                        "uid": owner.get("mid") or item.get("mid"),
                    },
                )
            )
        page = (
            data.get("page")
            if isinstance(data, dict) and isinstance(data.get("page"), dict)
            else {}
        )
        current_page = _number(page.get("pn")) or 1
        page_size = _number(page.get("ps")) or 30
        total = _number(page.get("count"))
        cursor = str(current_page + 1)
        has_more = current_page * page_size < total

    elif platform == "x":
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        for wrapper in data.get("timeline") or []:
            if not isinstance(wrapper, dict):
                continue
            if isinstance(wrapper.get("retweeted_tweet"), dict):
                continue
            item = wrapper
            post_id = item.get("tweet_id") or item.get("id")
            if not post_id:
                continue
            author = item.get("author") if isinstance(item.get("author"), dict) else {}
            if not author and isinstance(wrapper.get("author"), dict):
                author = wrapper["author"]
            handle = author.get("screen_name") or wrapper.get("screen_name") or "_"
            safe_handle = quote(str(handle), safe="_")
            safe_post_id = quote(str(post_id), safe="")
            posts.append(
                _post(
                    post_id=post_id,
                    title=item.get("text") or item.get("full_text"),
                    url=f"https://x.com/{safe_handle}/status/{safe_post_id}",
                    published_at=item.get("created_at"),
                    stats=_stats(item),
                    author={
                        "name": author.get("name"),
                        "handle": handle,
                        "uid": handle,
                        "followers": author.get("followers_count"),
                    },
                )
            )
        cursor = str(data.get("next_cursor") or data.get("cursor") or "")
        has_more = bool(data.get("has_more") or cursor)

    elif platform == "youtube":
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        channel = data.get("channel") if isinstance(data.get("channel"), dict) else {}
        for video in data.get("videos") or []:
            if not isinstance(video, dict) or not video.get("video_id"):
                continue
            video_id = str(video["video_id"])
            posts.append(
                _post(
                    post_id=video_id,
                    title=video.get("title"),
                    url="https://www.youtube.com/watch?" + urlencode({"v": video_id}),
                    published_at=video.get("published_time"),
                    stats=_stats(video),
                    author={
                        "name": video.get("author") or channel.get("name"),
                        "uid": video.get("channel_id") or channel.get("id"),
                    },
                )
            )
        cursor = str(data.get("continuation_token") or "")
        has_more = bool(cursor)

    return ([item for item in posts if item.id], cursor, has_more)


class TikHubClient:
    """Fetch one account with the caller's key. Keys are never persisted or logged."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        http_client: httpx.Client | None = None,
        timeout: float = 30,
    ) -> None:
        key = str(api_key or "").strip()
        if not key:
            raise MissingApiKey("请在本地 .env 中配置你自己的 TIKHUB_API_KEY")
        try:
            parsed_base = urlsplit(str(base_url or "").strip())
            base_port = parsed_base.port
        except ValueError as error:
            raise ValueError("API 地址必须是 TikHub 官方 HTTPS 地址") from error
        if (
            parsed_base.scheme != "https"
            or (parsed_base.hostname or "").lower().rstrip(".") != "api.tikhub.io"
            or parsed_base.username
            or parsed_base.password
            or base_port not in (None, 443)
            or parsed_base.path not in ("", "/")
            or parsed_base.query
            or parsed_base.fragment
        ):
            raise ValueError("API 地址必须是 TikHub 官方 HTTPS 地址")
        self._api_key = key
        self._base_url = DEFAULT_BASE_URL
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout, follow_redirects=False)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()

    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        last_status = 0
        for attempt in range(3):
            try:
                response = self._client.get(
                    self._base_url + path,
                    params=params,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
            except httpx.RequestError as error:
                if attempt == 2:
                    raise TikHubError("TikHub 网络请求失败，请稍后重试") from error
                time.sleep(2**attempt)
                continue
            last_status = response.status_code
            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError as error:
                    raise TikHubError("TikHub 返回了无法解析的数据") from error
                if not isinstance(payload, dict):
                    raise TikHubError("TikHub 返回的数据结构不正确")
                return payload
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(2**attempt)
                continue
            if response.status_code == 401:
                raise TikHubError("TikHub 鉴权失败，请检查你自己的 API Key")
            if response.status_code == 402:
                raise TikHubError("TikHub 余额不足，请充值后重试")
            raise TikHubError(f"TikHub 请求失败（HTTP {response.status_code}）")
        raise TikHubError(f"TikHub 请求失败（HTTP {last_status or '网络错误'}）")

    def _resolve(self, identity: CreatorIdentity) -> CreatorIdentity:
        if identity.uid:
            return identity
        if identity.platform == "youtube":
            payload = self._request(
                "/api/v1/youtube/web/get_channel_id", {"channel_name": identity.handle}
            )
            uid = str(_get(payload, "data", "channel_id", default="") or "")
            if not re.fullmatch(r"UC[A-Za-z0-9_-]{10,80}", uid):
                raise TikHubError("没有解析出这个 YouTube 频道")
            return CreatorIdentity("youtube", uid, identity.handle, identity.homepage_url)
        if identity.platform == "tiktok":
            payload = self._request(
                "/api/v1/tiktok/app/v3/fetch_video_search_result",
                {"keyword": identity.handle},
            )
            wanted = identity.handle.casefold()
            for wrapper in _get(payload, "data", "search_item_list", default=[]) or []:
                author = _get(wrapper, "aweme_info", "author", default={}) or {}
                if str(author.get("unique_id") or "").casefold() == wanted and author.get(
                    "sec_uid"
                ):
                    uid = str(author["sec_uid"])
                    return CreatorIdentity("tiktok", uid, identity.handle, identity.homepage_url)
            raise TikHubError("没有找到完全匹配的 TikTok 用户名")
        raise TikHubError("这个主页缺少可读取的账号标识")

    def fetch_creator(self, identity: CreatorIdentity, *, max_posts: int = 30) -> Creator:
        resolved = self._resolve(identity)
        endpoint = _POST_ENDPOINTS[resolved.platform]
        reference = resolved.uid or resolved.handle
        limit = max(5, min(int(max_posts), 100))
        posts: list[Post] = []
        seen: set[str] = set()
        cursor = ""

        for _page in range(5):
            params: dict[str, Any] = {
                endpoint.identity_param: reference,
                "count": min(30, limit - len(posts)),
            }
            if endpoint.cursor_param == "pn":
                params[endpoint.cursor_param] = int(cursor or 1)
            elif endpoint.cursor_param and cursor:
                params[endpoint.cursor_param] = cursor
            payload = self._request(endpoint.path, params)
            page_posts, next_cursor, has_more = parse_posts(resolved.platform, payload)
            added = 0
            for item in page_posts:
                if item.id in seen:
                    continue
                seen.add(item.id)
                posts.append(item)
                added += 1
                if len(posts) >= limit:
                    break
            if len(posts) >= limit or not has_more or not next_cursor or added == 0:
                break
            cursor = next_cursor

        first = posts[0] if posts else None
        return Creator(
            platform=resolved.platform,
            uid=resolved.uid,
            handle=resolved.handle or (first.author_handle if first else ""),
            name=(first.author_name if first else "") or resolved.handle or resolved.uid,
            homepage_url=resolved.homepage_url,
            followers=first.author_followers if first else None,
            posts=tuple(posts),
        )
