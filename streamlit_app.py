"""Streamlit front end for Project 3E. Run with `streamlit run streamlit_app.py`."""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st
from pydantic import ValidationError

from code_review.config import PROJECT_ROOT, ConfigurationError, load_settings
from code_review.graph import ReviewWorkflow
from code_review.llm import NebiusLLM
from code_review.models import HumanDecision, ReviewReport, ReviewRequest, Role, Severity, SourceFile
from code_review.reporting import to_markdown
from code_review.samples import load_demo, load_sample, sample_catalog
from code_review.tools import SUPPORTED_SUFFIXES

st.set_page_config(page_title="Code Review Agent · Review Studio", page_icon="◈", layout="wide")

st.html("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stApp {font-family:'DM Sans',sans-serif;}
h1,h2,h3 {font-family:'Space Grotesk',sans-serif !important;letter-spacing:-.04em;}
.block-container {padding-top:2.6rem;max-width:1440px;padding-bottom:4rem;}
[data-testid="stSidebar"] {background:#111C34;}
[data-testid="stSidebar"] * {color:#E4EAFB;}
[data-testid="stSidebar"] [data-baseweb="radio"] {padding:8px 0;}
[data-testid="stSidebar"] .stButton button {background:#23314E;border:1px solid #3A4C6E;color:#E4EAFB;}
.brand {display:flex;align-items:center;gap:12px;font-size:21px;font-weight:700;letter-spacing:-.04em;}
.brandmark {background:#B9F27C;color:#111C34 !important;border-radius:12px;padding:8px 11px;font-size:25px;}
.sidebar-label {font-size:10px;letter-spacing:.18em;color:#8596B8 !important;font-weight:700;margin:28px 0 8px;}
.sidebar-note {font-size:12px;color:#9FADCA !important;line-height:1.6;}
.provider {border:1px solid #34435D;border-radius:12px;padding:14px;margin-top:10px;}
.provider strong {font-size:13px;}.provider p {font-size:11px;color:#9FADCA !important;margin:8px 0 0;overflow-wrap:anywhere;}
.eyebrow {font-size:11px;font-weight:700;letter-spacing:.16em;color:#64769B;margin-bottom:12px;}
.hero-title {font-family:'Space Grotesk',sans-serif;font-size:46px;font-weight:600;letter-spacing:-.06em;line-height:1.1;max-width:800px;margin:0 0 16px;color:#172340;}
.hero-title span {color:#315AF2;}
.hero-sub {font-size:15px;color:#6A7892;max-width:740px;line-height:1.7;margin-bottom:26px;}
.pill {display:inline-block;padding:5px 11px;border-radius:20px;background:#E9EEFF;color:#315AF2;font-size:10px;font-weight:700;letter-spacing:.04em;margin-right:6px;}
.agent-card {background:white;border:1px solid #E2E7F1;border-radius:14px;padding:18px 20px;min-height:130px;}
.agent-number {color:#8593AD;font-size:10px;letter-spacing:.12em;font-weight:700;}
.agent-title {font-family:'Space Grotesk',sans-serif;font-size:19px;font-weight:600;margin:9px 0 4px;letter-spacing:-.03em;}
.agent-desc {color:#6A7892;font-size:12px;line-height:1.6;}
.section-head {font-size:12px;font-weight:700;letter-spacing:.10em;color:#64769B;margin:26px 0 12px;}
.status-chip {display:inline-block;padding:7px 12px;border-radius:8px;background:#E9EEFF;color:#315AF2;font-size:11px;font-weight:700;letter-spacing:.05em;margin-bottom:12px;}
.finding-meta {font-size:12px;color:#75839E;margin:4px 0 14px;}
.empty-card {padding:36px;border:1px dashed #CDD6E8;border-radius:14px;text-align:center;color:#75839E;margin-top:24px;}
[data-testid="stMetric"] {background:white;border:1px solid #E2E7F1;padding:16px 20px;border-radius:12px;}
[data-testid="stMetricValue"] {font-family:'Space Grotesk',sans-serif;font-size:29px;}
.stButton button, .stDownloadButton button {border-radius:9px;}
div[data-testid="stExpander"] {background:white;border:1px solid #E2E7F1;border-radius:12px;}
.footer {color:#94A0B7;font-size:11px;margin-top:36px;border-top:1px solid #E2E7F1;padding-top:16px;}
@media(max-width:700px){.hero-title{font-size:34px;}.block-container{padding-top:1.5rem;}}
</style>
""")

ROLE_LABELS = {Role.BUGS: "Correctness", Role.SECURITY: "Security", Role.TESTS: "Test coverage"}


def hero(title: str, subtitle: str) -> None:
    st.html(f'<div class="eyebrow">PROJECT 3E / CODE REVIEW AGENT</div><div class="hero-title">{title}</div><div class="hero-sub">{subtitle}</div>')


def agent_cards() -> None:
    descriptions = [
        ("01 / BUGS & ANTI-PATTERNS", "Correctness", "Logic errors, edge cases, and the patterns that turn into bugs."),
        ("02 / VULNERABILITIES", "Security", "Input handling, access boundaries, and exploitable code paths."),
        ("03 / MISSING TESTS", "Test coverage", "Behavioral gaps, boundary conditions, and concrete test suggestions."),
    ]
    for column, (number, title, description) in zip(st.columns(3), descriptions):
        with column:
            st.html(f'<div class="agent-card"><div class="agent-number">{number}</div><div class="agent-title">{title}</div><div class="agent-desc">{description}</div></div>')


def remember(report: ReviewReport, request: ReviewRequest | None = None) -> None:
    st.session_state.active_report = report.model_dump(mode="json")
    history = [r for r in st.session_state.get("report_history", []) if r["run_id"] != report.run_id]
    st.session_state.report_history = [report.model_dump(mode="json"), *history][:5]
    if request:
        st.session_state.active_source = request.model_dump()


def render_report(report: ReviewReport, *, interactive: bool, prefix: str = "live") -> None:
    st.divider()
    label = "INCOMPLETE REVIEW" if not report.complete else {
        "pending": "DRAFT / AWAITING HUMAN REVIEW", "accepted": "REPORT ACCEPTED", "changes_requested": "CHANGES REQUESTED",
    }[report.decision]
    st.html(f'<div class="status-chip">{label}</div>')
    st.subheader(report.title)
    st.write(report.summary)
    st.caption(f"{report.provider} · {report.model} · {report.elapsed_seconds:.1f}s · {report.llm_calls} LLM requests · "
               f"{report.input_tokens + report.output_tokens:,} tokens")
    if not report.complete:
        st.warning("One or more review stages failed. Inspect the agent results and run a new review to finish.")
    cols = st.columns(5)
    for col, severity in zip(cols, Severity):
        col.metric(severity.value.capitalize(), sum(f.severity == severity for f in report.findings))
    findings_tab, agents_tab, trace_tab = st.tabs(["Prioritized findings", "Agent assessments", "Workflow & scope"])
    with findings_tab:
        filters = st.columns([1, 1])
        severity_filter = filters[0].multiselect(
            "Severity", [s.value for s in Severity], default=[s.value for s in Severity], key=f"{prefix}_severity"
        )
        role_filter = filters[1].multiselect(
            "Review lens", list(ROLE_LABELS.values()), default=list(ROLE_LABELS.values()), key=f"{prefix}_role"
        )
        visible = [f for f in report.findings if f.severity.value in severity_filter
                   and any(ROLE_LABELS[r] in role_filter for r in f.agents)]
        st.caption(f"Showing {len(visible)} of {len(report.findings)} findings · evidence checked against the submitted source")
        if not visible:
            st.info("No findings match this view." if report.findings else "No source-validated findings returned. Read the scope and completeness of this review.")
        for finding in visible:
            with st.expander(f"{finding.severity.value.upper()}  ·  {finding.id}  ·  {finding.title}", expanded=finding.severity in {Severity.CRITICAL, Severity.HIGH}):
                st.caption(f"{finding.file}:{finding.line_start}–{finding.line_end} · "
                           f"{', '.join(ROLE_LABELS[r] for r in finding.agents)} · {finding.confidence:.0%} confidence")
                st.write(finding.explanation)
                language = Path(finding.file).suffix.lstrip(".") or "text"
                st.code(finding.evidence, language=language, line_numbers=False)
                st.markdown("**Recommended change**")
                st.write(finding.recommendation)
                if finding.suggested_test:
                    st.markdown("**Test to add**")
                    st.write(finding.suggested_test)
    with agents_tab:
        for agent in report.agents:
            with st.container(border=True):
                st.markdown(f"**{ROLE_LABELS[agent.role]} · {agent.status.upper()}**")
                st.write(agent.review.summary if agent.review else agent.error)
                st.caption(f"{agent.elapsed_seconds:.1f}s · {agent.llm_calls} requests · "
                           f"Tools: {', '.join(agent.tool_calls) or 'none'}")
                if agent.review and agent.review.limitations:
                    for limit in agent.review.limitations:
                        st.caption("• " + limit)
    with trace_tab:
        workflow = st.session_state.get("workflow") if interactive else None
        if workflow:
            for e in workflow.trace(report.run_id):
                st.markdown(f"**{e.node.replace('_', ' ').title()}** — {e.message}")
        st.markdown("**Review scope**")
        for limit in report.limitations:
            st.write("• " + limit)
        st.dataframe(report.file_manifest, hide_index=True, width="stretch")
        st.caption("Source hashes identify the exact snapshot reviewed. Original source line numbers are preserved.")
    if interactive and report.human_review_required:
        st.markdown("### Your review decision")
        st.caption("Accept the assessment or record what needs another pass. Your source stays under your control.")
        notes = st.text_area("Reviewer notes", placeholder="Context, corrections, or follow-up work…", max_chars=2000, key=f"notes_{report.run_id}")
        accept_col, changes_col, _ = st.columns([1, 1, 2])
        action = None
        if accept_col.button("Accept report", type="primary", disabled=not report.complete, key=f"accept_{report.run_id}", width="stretch"):
            action = "accepted"
        if changes_col.button("Request changes", key=f"changes_{report.run_id}", width="stretch"):
            action = "changes_requested"
        if action:
            updated = st.session_state.workflow.decide(report.run_id, HumanDecision(action=action, notes=notes))
            remember(updated)
            st.rerun()
    elif report.reviewer_notes:
        st.markdown("**Reviewer notes**")
        st.write(report.reviewer_notes)
    st.markdown("**Next steps**")
    for step in report.next_steps:
        st.write("• " + step)
    downloads = st.columns([1, 1, 2])
    downloads[0].download_button("↓ Markdown report", to_markdown(report), file_name=f"review-{report.run_id[:8]}.md", mime="text/markdown", key=f"{prefix}_md", width="stretch")
    downloads[1].download_button("↓ JSON report", report.model_dump_json(indent=2), file_name=f"review-{report.run_id[:8]}.json", mime="application/json", key=f"{prefix}_json", width="stretch")


try:
    settings = load_settings()
    config_error = ""
except ConfigurationError as exc:
    settings, config_error = None, str(exc)

with st.sidebar:
    st.html('<div class="brand"><span class="brandmark">◈</span> Review Studio</div><p class="sidebar-note" style="margin-top:14px">A second set of eyes.<br>Three independent perspectives.</p>')
    st.html('<div class="sidebar-label">WORKSPACE</div>')
    page = st.radio("Navigation", ["Review workspace", "Sample reports", "How it works"], label_visibility="collapsed", key="navigation")
    st.html('<div class="sidebar-label">MODEL CONNECTION</div>')
    if settings:
        st.html(f'<div class="provider"><strong>● Nebius configured</strong><p>{html.escape(settings.model)}</p><p>{html.escape(settings.key_source)}</p></div>')
    else:
        st.caption(config_error)
    st.html('<div class="sidebar-label">THIS SESSION</div>')
    st.caption(f"{len(st.session_state.get('report_history', []))} recent reviews · session memory")
    if st.button("Reset workspace", width="stretch"):
        if st.session_state.get("workflow"):
            st.session_state.workflow.close()
        st.session_state.clear()
        st.rerun()
    st.html('<div class="sidebar-note" style="margin-top:40px">WEEK 03 / AGENTIC AI SYSTEMS<br>LangGraph × Streamlit × Nebius</div>')

if page == "Review workspace":
    hero('Good code starts with<br><span>a second look.</span>',
         'Put three specialist agents on your next change. Get a single, prioritized review with source evidence and a clear path forward.')
    agent_cards()
    st.html('<div class="section-head">01 / CHOOSE YOUR SOURCE</div>')
    mode = st.radio("Source", ["Sample library", "Paste code", "Upload files"], horizontal=True, label_visibility="collapsed", key="source_mode")
    request = None
    try:
        if mode == "Sample library":
            catalog = sample_catalog()
            choices = {s["name"]: s["id"] for s in catalog}
            choices["Checkout service · intentionally flawed demo"] = "demo"
            choice = st.selectbox("Code sample", list(choices), key="sample_choice")
            request = load_demo() if choices[choice] == "demo" else load_sample(choices[choice])
            st.caption(request.origin)
        elif mode == "Paste code":
            filename = st.text_input("Filename", value="review.py", max_chars=240, key="source_filename")
            content = st.text_area("Source code", height=270, placeholder="Paste the code you want reviewed…", key="source_code")
            if content.strip():
                if Path(filename).suffix.lower() not in SUPPORTED_SUFFIXES:
                    raise ValueError("Use a supported code extension, such as .py, .js, .ts, .java or .go.")
                request = ReviewRequest(title=f"Review of {filename}", files=[SourceFile(path=filename, content=content)])
        else:
            uploads = st.file_uploader("Source and test files", type=sorted(s.lstrip(".") for s in SUPPORTED_SUFFIXES), accept_multiple_files=True)
            st.caption("Up to 20 UTF-8 files and 100 KB total. Include related tests for a more useful testing review.")
            if uploads:
                if len(uploads) > 20 or sum(f.size for f in uploads) > 100_000:
                    raise ValueError("Select at most 20 files and 100 KB total.")
                request = ReviewRequest(title="Uploaded code review", files=[
                    SourceFile(path=f.name, content=f.getvalue().decode("utf-8")) for f in uploads
                ])
        if request and mode != "Paste code":
            with st.expander(f"Inspect source snapshot · {len(request.files)} files · {sum(f.line_count for f in request.files)} lines", expanded=False):
                selected_path = st.selectbox("Preview file", [f.path for f in request.files])
                selected = next(f for f in request.files if f.path == selected_path)
                st.code(selected.content, language=Path(selected.path).suffix.lstrip("."), line_numbers=True)
        context = st.text_area("Review context (optional)", placeholder="What changed? Any assumptions, risk areas, or behavior the reviewers should know about?", height=80, max_chars=3000, key="review_context")
        run_col, scope_col = st.columns([1, 3])
        run_clicked = run_col.button("Run code review →", type="primary", disabled=request is None or settings is None, width="stretch")
        scope_col.caption("Selected source is sent to Nebius. Reviews inspect code without executing it; measured test coverage is unavailable.")
        if config_error:
            st.info(config_error)
        if run_clicked and request and settings:
            if context.strip():
                request = request.model_copy(update={"context": (request.context + "\n" + context).strip()[:3000]})
            if "workflow" not in st.session_state:
                st.session_state.workflow = ReviewWorkflow(NebiusLLM(settings))
            with st.status("Reviewing your code with three specialists…", expanded=True) as status:
                st.write("Validated snapshot → parallel specialist reviews → prioritized report → your decision")
                report = st.session_state.workflow.run(request, on_event=lambda e: st.write(e))
                remember(report, request)
                status.update(label="Review ready for your decision" if report.complete else "Review returned with incomplete stages", state="complete" if report.complete else "error", expanded=False)
    except (ValueError, ValidationError, UnicodeError) as exc:
        # Pydantic error strings include input values. Never render them with source content.
        message = str(exc) if type(exc) is ValueError else "Check filenames, UTF-8 encoding, unique paths, and source size limits."
        st.error(message)
    except Exception:
        st.error("The review could not finish. Reset the workspace and retry, or inspect the CLI output for stage status.")
    if st.session_state.get("active_report"):
        render_report(ReviewReport.model_validate(st.session_state.active_report), interactive=True)
    else:
        st.html('<div class="empty-card">Your review will appear here.<br><small>Choose a sample or add your code to give the agents their first assignment.</small></div>')

elif page == "Sample reports":
    hero('A review you can <span>inspect.</span>', 'Explore live evaluations of three real open-source code samples, or revisit your recent session reviews.')
    available: dict[str, tuple[ReviewReport, bool]] = {}
    for data in st.session_state.get("report_history", []):
        r = ReviewReport.model_validate(data)
        available[f"Session · {r.title} · {r.run_id[:8]}"] = (r, True)
    for path in sorted((PROJECT_ROOT / "reports").glob("*.json")):
        try:
            r = ReviewReport.model_validate_json(path.read_text())
            available[f"Evaluation · {r.title}"] = (r, False)
        except (ValueError, OSError):
            continue
    if available:
        chosen = st.selectbox("Review report", list(available))
        r, live = available[chosen]
        if not live:
            st.caption("Saved evaluation draft. Run this sample in the review workspace to record an interactive decision.")
        render_report(r, interactive=live, prefix="library_" + r.run_id)
    else:
        st.info("No saved reports yet. Run a review or use `python -m code_review evaluate --output reports`.")

else:
    hero('Three agents.<br><span>One considered review.</span>', 'Independent analysis, explicit state, source-checked findings, and a human decision at the end.')
    agent_cards()
    st.html('<div class="section-head">THE ORCHESTRATION</div>')
    st.graphviz_chart('''digraph {
      graph [rankdir=LR, bgcolor="transparent", pad="0.3", nodesep="0.4"]
      node [shape=box, style="rounded,filled", fillcolor="#FFFFFF", color="#D7DFEF", fontname="Helvetica", fontsize=12, margin="0.2,0.15"]
      edge [color="#9CADD0", arrowsize=0.6]
      intake [label="Validate snapshot"]
      bugs [label="Correctness"]
      security [label="Security"]
      tests [label="Test coverage"]
      orchestrator [label="Combine & prioritize", fillcolor="#E9EEFF", color="#315AF2"]
      human [label="Your decision", fillcolor="#E8F5DC", color="#A9D483"]
      intake -> {bugs security tests}; {bugs security tests} -> orchestrator; orchestrator -> human
    }''')
    left, right = st.columns(2)
    with left:
        st.markdown("### Evidence before findings")
        st.write("Each agent inspects the submitted source using read-only tools, verifies line references, and returns a structured assessment. The orchestrator groups duplicates and keeps severity ordering consistent.")
        st.markdown("### Recovery is part of the workflow")
        st.write("Transient provider failures receive bounded retries. Invalid model output gets a repair attempt. Failed stages produce an incomplete report with explicit status.")
    with right:
        st.markdown("### You make the final call")
        st.write("LangGraph pauses at a human review step. Accept the report or request changes with feedback. Neither action edits, publishes, or merges source code.")
        st.markdown("### State stays in your session")
        st.write("Source snapshots, agent results, and decisions live in this browser session’s in-memory checkpointer. Download reports to keep them; a server restart or workspace reset clears session state.")
    st.markdown("### Real sample library")
    for sample in sample_catalog():
        with st.container(border=True):
            st.markdown(f"**{sample['name']}** · {sample['license']}")
            st.write(sample["description"])
            st.caption(f"{sample['repository_url']} @ {sample['ref']} · {len(sample['files'])} submitted files")

st.html('<div class="footer">REVIEW STUDIO / PROJECT 3E <span style="float:right">Source evidence. Specialist reasoning. Human judgment.</span></div>')
