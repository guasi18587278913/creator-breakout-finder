"""Human- and machine-readable analysis exports."""

from __future__ import annotations

import csv
import html
import io
from urllib.parse import urlsplit

from .models import AnalysisResult, ScoredPost

_CONFIDENCE_LABELS = {"low": "低", "medium": "中", "high": "高"}


def _cell(value: object) -> str:
    text = html.escape(" ".join(str(value or "").split()), quote=False)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("[", "\\[").replace(
        "]", "\\]"
    )


def _safe_url(value: object) -> str:
    text = str(value or "").strip()
    if len(text) > 2048 or any(ord(char) < 32 or ord(char) == 127 for char in text):
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return ""
    return text.replace("<", "%3C").replace(">", "%3E").replace(" ", "%20")


def _csv_cell(value: object) -> str:
    text = str(value or "")
    candidate = text.lstrip(" \t\r\n")
    if text[:1] in {"\t", "\r"} or candidate.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _date(item: ScoredPost) -> str:
    return item.post.published_at.date().isoformat() if item.post.published_at else "未知"


def _number(value: float | int) -> str:
    numeric = float(value)
    return f"{int(numeric):,}" if numeric.is_integer() else f"{numeric:,.1f}"


def to_markdown(result: AnalysisResult) -> str:
    creator = result.creator
    lines = [
        f"# {_cell(creator.name)} 的高表现作品报告",
        "",
        f"- 主页：{_cell(creator.homepage_url)}",
        f"- 平台：{_cell(creator.platform)}",
        f"- 有效样本：{result.sample_size} 条",
        f"- 平时每条：{_number(result.baseline)} {result.metric_label}",
        f"- 置信度：{_CONFIDENCE_LABELS[result.confidence]}",
        f"- 明显高于平时：{len(result.breakouts)} 条",
        "",
        "## 明显高于平时的作品",
        "",
    ]
    if not result.breakouts:
        lines.append("本次样本中没有找到明显高于账号平时水平的作品。")
    else:
        lines.extend(
            [
                f"| 日期 | 作品 | 本条{result.metric_label} | 平时每条 | 高出平时 | 账号内排名 |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in result.breakouts:
            title = _cell(item.post.title)
            safe_url = _safe_url(item.post.url)
            link = f"[{title}](<{safe_url}>)" if safe_url else title
            lines.append(
                f"| {_date(item)} | {link} | {_number(item.value)} | "
                f"{_number(item.baseline)} | {item.multiple:.2f}× | {item.percentile:.1f}% |"
            )
    lines.extend(
        [
            "",
            "## 判定方法",
            "",
            "读取最近 30 条带有效指标的作品，用中位数估算账号平时每条的表现。候选作品必须"
            "达到平时 2 倍、进入样本前 10%，并通过最低数据门槛。YouTube 与 B站使用播放量，"
            "其余平台使用点赞量。",
            "",
            "> 这是一次性历史快照，只说明作品数据明显高于平时，不代表因果，"
            "也不等同于实时增长速度。",
        ]
    )
    return "\n".join(lines) + "\n"


def to_csv(result: AnalysisResult) -> str:
    buffer = io.StringIO(newline="")
    fieldnames = [
        "post_id",
        "published_at",
        "title",
        "url",
        "metric",
        "value",
        "baseline",
        "multiple",
        "percentile",
        "is_breakout",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for item in result.scored:
        writer.writerow(
            {
                "post_id": _csv_cell(item.post.id),
                "published_at": _csv_cell(
                    item.post.published_at.isoformat() if item.post.published_at else ""
                ),
                "title": _csv_cell(item.post.title),
                "url": _csv_cell(_safe_url(item.post.url)),
                "metric": result.metric,
                "value": item.value,
                "baseline": item.baseline,
                "multiple": item.multiple,
                "percentile": item.percentile,
                "is_breakout": str(item.is_breakout).lower(),
            }
        )
    return buffer.getvalue()
