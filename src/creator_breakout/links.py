"""Strict creator-homepage URL recognition.

Only known HTTPS profile shapes are accepted. Work URLs, short links, credentials,
custom ports and encoded paths are rejected before any provider request is made.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from .models import CreatorIdentity

_X_RESERVED = {
    "about",
    "account",
    "compose",
    "download",
    "explore",
    "hashtag",
    "home",
    "i",
    "intent",
    "jobs",
    "login",
    "messages",
    "notifications",
    "privacy",
    "search",
    "settings",
    "share",
    "signup",
    "tos",
}

_SUPPORTED_HOSTS = {
    "douyin.com",
    "www.douyin.com",
    "xiaohongshu.com",
    "www.xiaohongshu.com",
    "space.bilibili.com",
    "tiktok.com",
    "www.tiktok.com",
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
}


def _parse_https_url(value: str):
    text = str(value or "").strip()
    if not text or len(text) > 2048 or any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ValueError("主页链接为空或包含不安全字符")
    try:
        parsed = urlsplit(text)
    except ValueError as error:
        raise ValueError("主页链接格式不正确") from error
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
        raise ValueError("请粘贴以 https:// 开头的公开主页链接")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("主页链接端口不合法") from error
    if port not in (None, 443):
        raise ValueError("主页链接不能包含自定义端口")
    if host not in _SUPPORTED_HOSTS:
        raise ValueError("当前支持小红书、抖音、B站、TikTok、YouTube 和 X")
    if "\\" in text or "%" in parsed.path or "//" in parsed.path:
        raise ValueError("主页链接路径不安全")
    return parsed, host


def parse_creator_url(value: str) -> CreatorIdentity:
    """Parse one full creator homepage into a canonical provider identity."""
    parsed, host = _parse_https_url(value)
    segments = [segment for segment in parsed.path.rstrip("/").split("/") if segment]

    if host in {"xiaohongshu.com", "www.xiaohongshu.com"}:
        if len(segments) == 3 and segments[:2] == ["user", "profile"]:
            uid = segments[2]
            if re.fullmatch(r"[A-Za-z0-9_-]{6,80}", uid):
                return CreatorIdentity(
                    "xiaohongshu",
                    uid,
                    "",
                    f"https://www.xiaohongshu.com/user/profile/{uid}",
                )

    elif host in {"douyin.com", "www.douyin.com"}:
        if len(segments) == 2 and segments[0] == "user":
            uid = segments[1]
            if re.fullmatch(r"[A-Za-z0-9_-]{6,160}", uid):
                return CreatorIdentity("douyin", uid, "", f"https://www.douyin.com/user/{uid}")

    elif host == "space.bilibili.com":
        if len(segments) == 1 and re.fullmatch(r"\d{1,20}", segments[0]):
            uid = segments[0]
            return CreatorIdentity("bilibili", uid, "", f"https://space.bilibili.com/{uid}")

    elif host in {"tiktok.com", "www.tiktok.com"}:
        if len(segments) == 1 and re.fullmatch(r"@[A-Za-z0-9._]{2,24}", segments[0]):
            handle = segments[0][1:]
            return CreatorIdentity("tiktok", "", handle, f"https://www.tiktok.com/@{handle}")

    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if len(segments) == 2 and segments[0] == "channel":
            uid = segments[1]
            if re.fullmatch(r"UC[A-Za-z0-9_-]{10,80}", uid):
                return CreatorIdentity("youtube", uid, "", f"https://www.youtube.com/channel/{uid}")
        if len(segments) == 1 and re.fullmatch(r"@[A-Za-z0-9._-]{2,100}", segments[0]):
            handle = segments[0][1:]
            return CreatorIdentity("youtube", "", handle, f"https://www.youtube.com/@{handle}")
        if (
            len(segments) == 2
            and segments[0] in {"c", "user"}
            and re.fullmatch(r"[A-Za-z0-9._-]{2,100}", segments[1])
        ):
            handle = segments[1]
            return CreatorIdentity(
                "youtube", "", handle, f"https://www.youtube.com/{segments[0]}/{handle}"
            )

    elif (
        host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}
        and len(segments) == 1
        and re.fullmatch(r"[A-Za-z0-9_]{1,15}", segments[0])
    ):
        handle = segments[0].casefold()
        if handle in _X_RESERVED:
            raise ValueError("这不是创作者主页")
        return CreatorIdentity("x", handle, handle, f"https://x.com/{handle}")

    raise ValueError("这不是可识别的创作者主页，请不要粘贴作品、搜索或功能页链接")
