"""Local CLI and reproducible live evaluations; no uploaded code is executed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ConfigurationError, load_settings
from .graph import ReviewWorkflow
from .llm import NebiusLLM
from .models import HumanDecision, ReviewRequest
from .reporting import write_report
from .samples import load_sample, sample_catalog
from .tools import load_source_paths


def evaluate(workflow: ReviewWorkflow, output: Path) -> dict:
    rows = []
    for sample in sample_catalog():
        print(f"Reviewing {sample['name']}…", flush=True)
        report = workflow.run(load_sample(sample["id"]))
        write_report(report, output / sample["id"])
        trace = [e.model_dump() for e in workflow.trace(report.run_id)]
        (output / f"{sample['id']}.trace.json").write_text(json.dumps(trace, indent=2) + "\n")
        rows.append({
            "sample": sample["id"], "origin": report.origin, "complete": report.complete,
            "decision": report.decision, "findings": len(report.findings),
            "severity_counts": {s: sum(f.severity.value == s for f in report.findings)
                                for s in ["critical", "high", "medium", "low", "info"]},
            "agents_completed": sum(a.status == "completed" for a in report.agents),
            "elapsed_seconds": report.elapsed_seconds, "llm_calls": report.llm_calls,
            "input_tokens": report.input_tokens, "output_tokens": report.output_tokens,
        })
        print(f"  {'Complete' if report.complete else 'INCOMPLETE'}: {len(report.findings)} findings, "
              f"{report.elapsed_seconds:.1f}s. Human review pending.", flush=True)
    summary = {
        "model": workflow.llm.settings.model, "samples_reviewed": len(rows),
        "complete_reviews": sum(r["complete"] for r in rows), "results": rows,
        "evaluation_scope": "Live end-to-end completion and citation validation, not ground-truth defect accuracy. No source tests were executed.",
    }
    (output / "evaluation.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = ["# Live evaluation: three real code samples", "", f"Model: `{summary['model']}`", "",
             summary["evaluation_scope"], "", "| Sample | Complete | Agents | Findings | Seconds |", "| --- | --- | --- | --- | --- |"]
    for row in rows:
        lines.append(f"| {row['sample']} | {row['complete']} | {row['agents_completed']}/3 | {row['findings']} | {row['elapsed_seconds']} |")
    lines += ["", "All saved reports are drafts pending a human decision. Upstream code is attributed in `examples/real_samples.json`.", ""]
    (output / "evaluation.md").write_text("\n".join(lines))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project 3E: LangGraph Code Review Agent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("samples", help="List the attributed real code samples")
    review = sub.add_parser("review", help="Review explicitly selected local code files")
    review.add_argument("files", nargs="+", type=Path)
    review.add_argument("--title", default="Code review")
    review.add_argument("--context", default="")
    review.add_argument("--output", type=Path, default=Path(".review-data/review"))
    evaluation = sub.add_parser("evaluate", help="Run live reviews of the three real samples")
    evaluation.add_argument("--output", type=Path, default=Path("reports"))
    decision = sub.add_parser("decide", help="Record your decision on an exported JSON draft")
    decision.add_argument("report", type=Path)
    decision.add_argument("--decision", choices=["accepted", "changes_requested"], required=True)
    decision.add_argument("--notes", default="")
    args = parser.parse_args(argv)
    workflow = None
    try:
        if args.command == "samples":
            for sample in sample_catalog():
                print(f"{sample['id']}: {sample['name']} ({sample['repo']} @ {sample['ref']})")
            return 0
        if args.command == "decide":
            from .models import ReviewReport
            report = ReviewReport.model_validate_json(args.report.read_text())
            approved = HumanDecision(action=args.decision, notes=args.notes)
            if report.decision != "pending":
                raise ValueError("This exported report already has a human decision.")
            if approved.action == "accepted" and not report.complete:
                raise ValueError("An incomplete review cannot be accepted. Run a new review.")
            report.decision, report.reviewer_notes = approved.action, approved.notes
            report.human_review_required = False
            write_report(report, args.report.with_suffix(""))
            print(f"Recorded decision: {report.decision}. Reviewed source was not modified.")
            return 0
        workflow = ReviewWorkflow(NebiusLLM(load_settings()))
        if args.command == "evaluate":
            return 0 if evaluate(workflow, args.output)["complete_reviews"] == 3 else 1
        request = ReviewRequest(title=args.title, files=load_source_paths(args.files), context=args.context)
        report = workflow.run(request, on_event=lambda e: print(e, flush=True))
        paths = write_report(report, args.output)
        print(f"Draft report: {paths[1]}; JSON: {paths[0]}")
        print(f"{len(report.findings)} findings. Human review pending.")
        return 0 if report.complete else 1
    except (ConfigurationError, ValueError, OSError):
        print("Could not complete the request. Check configuration, input files, and report validity.", file=sys.stderr)
        return 2
    finally:
        if workflow:
            workflow.close()


if __name__ == "__main__":
    raise SystemExit(main())
