import pytest

from creator_breakout.links import parse_creator_url


@pytest.mark.parametrize(
    ("url", "platform", "uid", "handle", "canonical"),
    [
        (
            "https://www.xiaohongshu.com/user/profile/abcDEF_123",
            "xiaohongshu",
            "abcDEF_123",
            "",
            "https://www.xiaohongshu.com/user/profile/abcDEF_123",
        ),
        (
            "https://www.douyin.com/user/MS4wLjABAAAA_test-123",
            "douyin",
            "MS4wLjABAAAA_test-123",
            "",
            "https://www.douyin.com/user/MS4wLjABAAAA_test-123",
        ),
        (
            "https://space.bilibili.com/123456",
            "bilibili",
            "123456",
            "",
            "https://space.bilibili.com/123456",
        ),
        (
            "https://www.tiktok.com/@OpenAI.creator",
            "tiktok",
            "",
            "OpenAI.creator",
            "https://www.tiktok.com/@OpenAI.creator",
        ),
        (
            "https://www.youtube.com/channel/UC1234567890_abcdef",
            "youtube",
            "UC1234567890_abcdef",
            "",
            "https://www.youtube.com/channel/UC1234567890_abcdef",
        ),
        (
            "https://youtube.com/@creator-name",
            "youtube",
            "",
            "creator-name",
            "https://www.youtube.com/@creator-name",
        ),
        (
            "https://twitter.com/Creator_Name/",
            "x",
            "creator_name",
            "creator_name",
            "https://x.com/creator_name",
        ),
    ],
)
def test_supported_creator_urls(url, platform, uid, handle, canonical):
    identity = parse_creator_url(url)

    assert identity.platform == platform
    assert identity.uid == uid
    assert identity.handle == handle
    assert identity.homepage_url == canonical


@pytest.mark.parametrize(
    "url",
    [
        "http://x.com/openai",
        "https://x.com/home",
        "https://x.com/openai/status/123",
        "https://youtu.be/abc",
        "https://www.youtube.com/watch?v=abc",
        "https://www.xiaohongshu.com/explore/abc",
        "https://user:password@x.com/openai",
        "https://x.com:8443/openai",
        "https://example.com/creator",
        "https://x.com/%6fpenai",
    ],
)
def test_rejects_non_profile_or_unsafe_urls(url):
    with pytest.raises(ValueError):
        parse_creator_url(url)
