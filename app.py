"""Streamlit entrypoint for Creator Breakout Finder."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from creator_breakout.demo import load_demo_creator
from creator_breakout.links import parse_creator_url
from creator_breakout.providers.tikhub import MissingApiKey, TikHubClient, TikHubError
from creator_breakout.report import to_csv, to_markdown
from creator_breakout.scoring import InsufficientSampleError, analyze_creator

load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"), override=False)

PLATFORM_LABELS = {
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "bilibili": "B站",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "x": "X",
}
CONFIDENCE_LABELS = {"low": "低", "medium": "中", "high": "高"}


def _format_number(value: float | int | None) -> str:
    if value is None:
        return "—"
    numeric = float(value)
    return f"{int(numeric):,}" if numeric.is_integer() else f"{numeric:,.1f}"


def _fetch_and_analyze(url: str, use_demo: bool):
    if use_demo:
        return analyze_creator(load_demo_creator())
    identity = parse_creator_url(url)
    key = os.environ.get("TIKHUB_API_KEY", "").strip()
    with TikHubClient(key) as client:
        creator = client.fetch_creator(identity, max_posts=30)
    if not creator.posts:
        raise InsufficientSampleError("没有读取到这个账号的公开作品")
    return analyze_creator(creator)


st.set_page_config(
    page_title="Creator Breakout Finder",
    page_icon="↗",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .stApp { background: #f7f3e9; color: #19201b; }
      .block-container { max-width: 1120px; padding-top: 3.2rem; padding-bottom: 5rem; }
      h1, h2, h3 { letter-spacing: -0.03em; }
      h1 { font-size: clamp(2.7rem, 6vw, 5.4rem) !important; line-height: .95 !important; }
      [data-testid="stMetric"] { background: rgba(255,255,255,.62); border: 1px solid #d8d0bf;
        border-radius: 12px; padding: 1rem 1.1rem; }
      [data-testid="stForm"] { background: #fffdf7; border: 1px solid #cfc5b1;
        border-radius: 18px; padding: 1.2rem 1.35rem; }
      .eyebrow { color: #8d4c2d; font-size: .78rem; font-weight: 800; letter-spacing: .14em;
        text-transform: uppercase; }
      .lead { max-width: 760px; color: #586059; font-size: 1.12rem; line-height: 1.7; }
      .method { margin-top: 1.5rem; padding: 1rem 1.2rem; border-left: 3px solid #b15e37;
        background: rgba(255,255,255,.45); color: #505750; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="eyebrow">Creator intelligence · Open source</div>', unsafe_allow_html=True)
st.title("找到真正跑赢他自己的作品")
st.markdown(
    '<p class="lead">粘贴一个创作者主页，不拿他和全网大号硬比。'
    "工具会用这个账号自己的历史中位数建立基线，找出异常跑出的作品。</p>",
    unsafe_allow_html=True,
)

has_key = bool(os.environ.get("TIKHUB_API_KEY", "").strip())
if st.query_params.get("demo") == "1" and "analysis_result" not in st.session_state:
    st.session_state["analysis_result"] = analyze_creator(load_demo_creator())

with st.form("analysis-form"):
    url = st.text_input(
        "创作者主页链接",
        value="https://x.com/openai",
        placeholder="支持小红书、抖音、B站、TikTok、YouTube 和 X",
        help="只接受完整的 HTTPS 创作者主页，不接受作品链接或短链接。",
    )
    use_demo = st.checkbox(
        "使用虚构演示数据（不调用 TikHub）",
        value=not has_key,
        help="演示数据完全离线，不包含任何真实账号信息。",
    )
    submitted = st.form_submit_button("开始寻找异常作品", type="primary", width="stretch")

if submitted:
    try:
        with st.spinner("正在建立这个账号的历史基线…"):
            st.session_state["analysis_result"] = _fetch_and_analyze(url, use_demo)
        st.session_state.pop("analysis_error", None)
    except (ValueError, MissingApiKey, TikHubError, InsufficientSampleError) as error:
        st.session_state["analysis_error"] = str(error)
        st.session_state.pop("analysis_result", None)
    except Exception:
        st.session_state["analysis_error"] = (
            "分析失败，请稍后重试。为保护你的密钥，详细异常不会显示在页面上。"
        )
        st.session_state.pop("analysis_result", None)

if error_message := st.session_state.get("analysis_error"):
    st.error(error_message)

if not has_key:
    st.info("当前未读取到 TIKHUB_API_KEY。你可以先跑演示；真实分析需要把自己的 Key 写进本地 .env。")
else:
    st.caption(
        "已从本地环境读取 TikHub Key。Key 不会进入页面、报告或仓库。真实请求可能产生 TikHub 费用。"
    )

result = st.session_state.get("analysis_result")
if result is not None:
    creator = result.creator
    st.divider()
    heading = creator.name or creator.handle or creator.uid
    st.subheader(f"{heading} · {PLATFORM_LABELS.get(creator.platform, creator.platform)}")
    st.caption(f"样本主页：{creator.homepage_url}")

    metric_columns = st.columns(4)
    metric_columns[0].metric("有效样本", f"{result.sample_size} 条")
    metric_columns[1].metric("日常基线", f"{_format_number(result.baseline)} {result.metric_label}")
    metric_columns[2].metric("异常作品", f"{len(result.breakouts)} 条")
    metric_columns[3].metric("判断置信度", CONFIDENCE_LABELS[result.confidence])

    breakout_tab, sample_tab, method_tab = st.tabs(["异常作品", "全部样本", "判定方法"])
    with breakout_tab:
        if not result.breakouts:
            st.success("这批样本里没有作品同时越过三道门槛。没有异常，也是一条有用结论。")
        else:
            rows = [
                {
                    "作品": item.post.title,
                    f"当前{result.metric_label}": item.value,
                    "自身基线": item.baseline,
                    "基线倍数": item.multiple,
                    "历史分位": item.percentile / 100,
                    "原帖": item.post.url,
                }
                for item in result.breakouts
            ]
            st.dataframe(
                rows,
                hide_index=True,
                width="stretch",
                column_config={
                    "作品": st.column_config.TextColumn(width="large"),
                    f"当前{result.metric_label}": st.column_config.NumberColumn(format="localized"),
                    "自身基线": st.column_config.NumberColumn(format="localized"),
                    "基线倍数": st.column_config.NumberColumn(format="%.2f×"),
                    "历史分位": st.column_config.ProgressColumn(
                        min_value=0, max_value=1, format="percent"
                    ),
                    "原帖": st.column_config.LinkColumn(display_text="打开 ↗"),
                },
            )

        download_columns = st.columns(2)
        download_columns[0].download_button(
            "下载 Markdown 研究报告",
            data=to_markdown(result),
            file_name="creator-breakout-report.md",
            mime="text/markdown",
            width="stretch",
        )
        download_columns[1].download_button(
            "下载 CSV 全部样本",
            data=to_csv(result),
            file_name="creator-breakout-posts.csv",
            mime="text/csv",
            width="stretch",
        )

    with sample_tab:
        all_rows = [
            {
                "异常": "是" if item.is_breakout else "否",
                "作品": item.post.title,
                result.metric_label: item.value,
                "倍数": item.multiple,
                "分位": f"{item.percentile:.1f}%",
                "原帖": item.post.url,
            }
            for item in result.scored
        ]
        st.dataframe(
            all_rows,
            hide_index=True,
            width="stretch",
            column_config={
                "作品": st.column_config.TextColumn(width="large"),
                "原帖": st.column_config.LinkColumn(display_text="打开 ↗"),
            },
        )

    with method_tab:
        st.markdown(
            """
            1. 读取最近 30 条带有效指标的公开作品。
            2. 用中位数代表账号的日常水平，避免少量超级爆款拉高基线。
            3. 候选作品必须同时满足：达到基线 2 倍、进入历史前 10%、越过绝对量下限。
            4. YouTube 和 B站使用播放量，其余平台使用点赞量。

            这是一次性历史快照。它能发现异常表现，但不能证明爆款原因，也不等同于实时增长速度。
            """
        )

st.markdown(
    '<div class="method"><b>隐私边界</b><br>工具不保存账号数据，不内置作者的 TikHub Key，'
    "也不会把 Key 放进浏览器代码。开源用户必须使用自己的 Key。</div>",
    unsafe_allow_html=True,
)
