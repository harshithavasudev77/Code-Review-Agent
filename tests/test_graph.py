import threading

import pytest

from code_review.graph import ReviewWorkflow, merge_findings
from code_review.llm import ProviderError
from code_review.models import AgentResult, AgentReview, HumanDecision, Role
from conftest import FakeLLM, successful_specialist


def test_real_graph_runs_specialists_concurrently_then_interrupts(request_snapshot):
    barrier = threading.Barrier(3, timeout=5)

    def parallel_specialist(role, request, llm):
        barrier.wait()
        return successful_specialist(role, request, llm)

    workflow = ReviewWorkflow(FakeLLM(), specialist=parallel_specialist)
    events = []
    report = workflow.run(request_snapshot, on_event=events.append)
    assert report.complete
    assert len(report.agents) == 3
    assert report.decision == "pending"
    assert workflow.graph.get_state(workflow.config(report.run_id)).next == ("human_review",)
    assert "Awaiting your review" in events
    decided = workflow.decide(report.run_id, HumanDecision(action="accepted", notes="Confirmed assessment."))
    assert decided.decision == "accepted"
    assert not decided.human_review_required
    assert len(workflow.graph.get_state(workflow.config(report.run_id)).values["results"]) == 3
    assert [e.node for e in workflow.trace(report.run_id)].count("human_review") == 1
    with pytest.raises(ValueError):
        workflow.decide(report.run_id, HumanDecision(action="accepted"))


def test_failed_specialist_does_not_appear_as_clean_review(request_snapshot):
    def partial(role, request, llm):
        if role == Role.SECURITY:
            return AgentResult(role=role, status="failed", error="Provider unavailable.")
        return successful_specialist(role, request, llm)
    workflow = ReviewWorkflow(FakeLLM(), specialist=partial)
    report = workflow.run(request_snapshot)
    assert not report.complete
    assert report.summary.startswith("Review incomplete:")
    assert any("security specialist failed" in s for s in report.limitations)
    decided = workflow.decide(report.run_id, HumanDecision(action="accepted"))
    assert decided.decision == "changes_requested"


def test_orchestrator_failure_preserves_findings_and_marks_incomplete(request_snapshot, finding):
    def specialist(role, request, llm):
        return AgentResult(role=role, status="completed", review=AgentReview(summary="Reviewed.", findings=[finding] if role == Role.BUGS else []))
    workflow = ReviewWorkflow(FakeLLM([ProviderError("Unavailable.")]), specialist=specialist)
    report = workflow.run(request_snapshot)
    assert len(report.findings) == 1
    assert not report.complete
    assert any("deterministic" in s for s in report.limitations)


def test_all_failed_skips_orchestrator(request_snapshot):
    llm = FakeLLM()
    workflow = ReviewWorkflow(llm, specialist=lambda role, *_: AgentResult(role=role, status="failed", error="Unavailable."))
    report = workflow.run(request_snapshot)
    assert not report.complete
    assert not llm.calls
    assert not report.findings


def test_separate_runs_keep_source_and_decisions_isolated(request_snapshot):
    workflow = ReviewWorkflow(FakeLLM(), specialist=successful_specialist)
    first = workflow.run(request_snapshot)
    second = workflow.run(request_snapshot.model_copy(update={"title": "Second review"}))
    workflow.decide(first.run_id, HumanDecision(action="changes_requested", notes="Add tests."))
    assert workflow.report(second.run_id).decision == "pending"
    assert workflow.report(first.run_id).reviewer_notes == "Add tests."


def test_deduplication_preserves_roles_and_caps_missing_test_severity(finding):
    bug = AgentResult(role=Role.BUGS, status="completed", review=AgentReview(summary="Bugs", findings=[finding]))
    security = AgentResult(role=Role.SECURITY, status="completed", review=AgentReview(summary="Security", findings=[finding.model_copy(update={"severity": "high"})]))
    tests = AgentResult(role=Role.TESTS, status="completed", review=AgentReview(summary="Tests", findings=[finding.model_copy(update={"severity": "critical"})]))
    result = merge_findings([bug, security, tests])
    assert len(result) == 2
    assert set(result[0].agents) == {Role.BUGS, Role.SECURITY}
    assert result[0].severity == "high"
    assert result[1].severity == "medium"
