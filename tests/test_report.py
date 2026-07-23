from dataclasses import replace
from datetime import UTC, datetime

from creator_breakout.models import AnalysisResult, Creator, Post, ScoredPost
from creator_breakout.report import to_csv, to_markdown


def result() -> AnalysisResult:
    creator = Creator(
        platform="x",
        uid="creator",
        handle="creator",
        name="Creator | Demo",
        homepage_url="https://x.com/creator",
        posts=(),
    )
    post = Post(
        id="1",
        title="A title | with a pipe\nand a newline",
        url="https://x.com/creator/status/1",
        published_at=datetime(2026, 1, 2, tzinfo=UTC),
        likes=300,
    )
    scored = ScoredPost(
        post=post, value=300, baseline=100, multiple=3, percentile=100, is_breakout=True
    )
    return AnalysisResult(
        creator=creator,
        metric="likes",
        metric_label="赞",
        baseline=100,
        sample_size=10,
        confidence="medium",
        scored=(scored,),
        breakouts=(scored,),
    )


def test_markdown_report_is_readable_and_escapes_table_content():
    output = to_markdown(result())

    assert "Creator \\| Demo" in output
    assert "A title \\| with a pipe and a newline" in output
    assert "3.00×" in output
    assert "TikHub API Key" not in output


def test_csv_report_contains_machine_readable_fields():
    output = to_csv(result())

    assert "is_breakout" in output
    assert "https://x.com/creator/status/1" in output
    assert "user-secret" not in output


def test_csv_report_neutralizes_spreadsheet_formulas():
    original = result()
    dangerous_post = replace(original.scored[0].post, title="=2+2")
    dangerous_score = replace(original.scored[0], post=dangerous_post)
    dangerous_result = replace(
        original,
        scored=(dangerous_score,),
        breakouts=(dangerous_score,),
    )

    output = to_csv(dangerous_result)

    assert "'=2+2" in output
    assert "\n=2+2," not in output


def test_markdown_report_escapes_untrusted_html_and_link_labels():
    original = result()
    dangerous_post = replace(original.scored[0].post, title="<script>[click]</script>")
    dangerous_score = replace(original.scored[0], post=dangerous_post)
    dangerous_result = replace(
        original,
        scored=(dangerous_score,),
        breakouts=(dangerous_score,),
    )

    output = to_markdown(dangerous_result)

    assert "<script>" not in output
    assert "\\[click\\]" in output
