import httpx
import pytest

from creator_breakout.links import parse_creator_url
from creator_breakout.providers.tikhub import MissingApiKey, TikHubClient, parse_posts


@pytest.mark.parametrize(
    ("platform", "payload", "expected"),
    [
        (
            "douyin",
            {
                "data": {
                    "aweme_list": [
                        {
                            "aweme_id": "d1",
                            "desc": "抖音作品",
                            "create_time": 1710000000,
                            "statistics": {"digg_count": 42, "play_count": 900},
                            "author": {"nickname": "作者"},
                        }
                    ]
                }
            },
            ("d1", "抖音作品", 42, 900),
        ),
        (
            "tiktok",
            {
                "data": {
                    "aweme_list": [
                        {
                            "aweme_id": "t1",
                            "desc": "TikTok post",
                            "create_time": 1710000000,
                            "statistics": {"digg_count": 55, "play_count": 1200},
                            "author": {"unique_id": "creator"},
                        }
                    ]
                }
            },
            ("t1", "TikTok post", 55, 1200),
        ),
        (
            "xiaohongshu",
            {
                "data": {
                    "data": {
                        "notes": [
                            {
                                "id": "x1",
                                "title": "小红书笔记",
                                "create_time": 1710000000,
                                "liked_count": "88",
                                "user": {"nickname": "作者"},
                            }
                        ]
                    }
                }
            },
            ("x1", "小红书笔记", 88, None),
        ),
        (
            "bilibili",
            {
                "data": {
                    "data": {
                        "list": {
                            "vlist": [
                                {
                                    "bvid": "BV1",
                                    "title": "B站视频",
                                    "created": 1710000000,
                                    "play": 3200,
                                    "video_review": 12,
                                }
                            ]
                        },
                        "page": {"pn": 1, "ps": 30, "count": 1},
                    }
                }
            },
            ("BV1", "B站视频", None, 3200),
        ),
        (
            "x",
            {
                "data": {
                    "timeline": [
                        {
                            "tweet_id": "tw1",
                            "text": "X post",
                            "created_at": "Tue Jun 10 18:23:39 +0000 2025",
                            "favorites": 99,
                            "views": "1.2K",
                            "author": {"screen_name": "creator"},
                        }
                    ]
                }
            },
            ("tw1", "X post", 99, 1200),
        ),
        (
            "youtube",
            {
                "data": {
                    "videos": [
                        {
                            "video_id": "yt1",
                            "title": "YouTube video",
                            "number_of_views": "8.5K",
                            "published_time": "2 weeks ago",
                            "channel_id": "UC123",
                        }
                    ]
                }
            },
            ("yt1", "YouTube video", None, 8500),
        ),
    ],
)
def test_platform_payloads_are_normalized(platform, payload, expected):
    posts, _, _ = parse_posts(platform, payload)

    assert len(posts) == 1
    item = posts[0]
    assert (item.id, item.title, item.likes, item.views) == expected


def test_client_requires_the_users_own_key():
    with pytest.raises(MissingApiKey):
        TikHubClient("")


def test_client_sends_bearer_key_only_in_request_header():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "data": {
                    "timeline": [{"tweet_id": "1", "text": "hello", "favorites": 10, "views": 100}]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    client = TikHubClient("user-secret", http_client=http_client)

    result = client.fetch_creator(parse_creator_url("https://x.com/openai"), max_posts=30)

    assert captured["authorization"] == "Bearer user-secret"
    assert result.posts[0].id == "1"
    assert "user-secret" not in repr(result)


def test_missing_metric_stays_unknown_instead_of_becoming_zero():
    posts, _, _ = parse_posts(
        "x",
        {"data": {"timeline": [{"tweet_id": "1", "text": "missing likes"}]}},
    )

    assert posts[0].likes is None


def test_x_retweets_are_not_treated_as_the_creators_own_work():
    posts, _, _ = parse_posts(
        "x",
        {
            "data": {
                "timeline": [
                    {
                        "tweet_id": "wrapper",
                        "text": "RT",
                        "retweeted_tweet": {
                            "tweet_id": "someone-elses-post",
                            "text": "viral post",
                            "favorites": 99999,
                        },
                    },
                    {"tweet_id": "own-post", "text": "original", "favorites": 30},
                ]
            }
        },
    )

    assert [post.id for post in posts] == ["own-post"]


def test_provider_share_url_cannot_replace_the_canonical_post_url():
    posts, _, _ = parse_posts(
        "douyin",
        {
            "data": {
                "aweme_list": [
                    {
                        "aweme_id": "d1",
                        "desc": "post",
                        "share_url": "javascript:alert(1)",
                        "statistics": {"digg_count": 30},
                    }
                ]
            }
        },
    )

    assert posts[0].url == "https://www.douyin.com/video/d1"


def test_xiaohongshu_uses_the_verified_user_notes_endpoint():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["user_id"] = request.url.params.get("user_id")
        return httpx.Response(200, json={"data": {"data": {"notes": []}}})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = TikHubClient("user-secret", http_client=http_client)
    client.fetch_creator(
        parse_creator_url("https://www.xiaohongshu.com/user/profile/abcDEF_123")
    )

    assert captured == {
        "path": "/api/v1/xiaohongshu/app/get_user_notes",
        "user_id": "abcDEF_123",
    }


def test_youtube_uses_the_verified_channel_videos_endpoint():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["channel_id"] = request.url.params.get("channel_id")
        return httpx.Response(200, json={"data": {"videos": []}})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = TikHubClient("user-secret", http_client=http_client)
    client.fetch_creator(
        parse_creator_url("https://www.youtube.com/channel/UC1234567890_abcdef")
    )

    assert captured == {
        "path": "/api/v1/youtube/web/get_channel_videos",
        "channel_id": "UC1234567890_abcdef",
    }


def test_client_refuses_to_send_a_key_to_an_untrusted_base_url():
    with pytest.raises(ValueError, match="TikHub 官方"):
        TikHubClient("user-secret", base_url="https://example.com")
