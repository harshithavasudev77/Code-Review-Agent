"""Portable, clearly labeled draft and human-reviewed reports."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ReviewReport, Severity


def to_markdown(report: ReviewReport) -> str:
    counts = {s.value: sum(f.severity == s for f in report.findings) for s in Severity}
    lines = [
        f"# {report.title}", "", f"**Decision:** {report.decision}",
        f"**Review complete:** {'yes' if report.complete else 'no — review is incomplete'}",
        f"**Human review required:** {'yes' if report.human_review_required else 'no'}",
        f"**Provider / model:** {report.provider} / `{report.model}`",
        f"**Run:** `{report.run_id}` · {report.created_at}",
        f"**Source:** {report.origin}",
        f"**Elapsed:** {report.elapsed_seconds:.1f}s · **LLM requests:** {report.llm_calls} · "
        f"**Tokens:** {report.input_tokens:,} input / {report.output_tokens:,} output", "",
        "## Assessment", "", report.summary, "",
        " · ".join(f"{k}: {v}" for k, v in counts.items()), "", "## Prioritized findings", "",
    ]
    if not report.findings:
        lines.append("No source-validated findings were returned. See completeness and limitations before interpreting this result.")
    for finding in report.findings:
        lines += [
            f"### {finding.id} · {finding.severity.value.upper()} · {finding.title}", "",
            f"`{finding.file}:{finding.line_start}-{finding.line_end}` · "
            f"Agents: {', '.join(r.value for r in finding.agents)} · Confidence: {finding.confidence:.0%}", "",
            finding.explanation, "", "**Source evidence**", "", "````text", finding.evidence,
            "````", "", f"**Recommendation:** {finding.recommendation}", "",
        ]
        if finding.suggested_test:
            lines += [f"**Suggested test:** {finding.suggested_test}", ""]
    lines += ["## Next steps", "", *[f"- {step}" for step in report.next_steps], "", "## Specialist results", ""]
    for result in report.agents:
        lines += [
            f"- **{result.role.value} — {result.status}:** "
            + (result.review.summary if result.review else result.error)
        ]
    lines += ["", "## Limitations", "", *[f"- {limit}" for limit in report.limitations], "", "## Source manifest", ""]
    for file in report.file_manifest:
        lines += [f"- `{file['path']}`: {file['lines']} lines; SHA-256 `{file['sha256']}`"]
    if report.reviewer_notes:
        lines += ["", "## Reviewer notes", "", report.reviewer_notes]
    return "\n".join(lines) + "\n"


def write_report(report: ReviewReport, output_stem: Path) -> tuple[Path, Path]:
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    json_path = output_stem.with_suffix(".json")
    markdown_path = output_stem.with_suffix(".md")
    json_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(to_markdown(report), encoding="utf-8")
    return json_path, markdown_path
