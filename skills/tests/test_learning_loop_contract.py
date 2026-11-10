from __future__ import annotations

import pathlib
import re

from skills.tests.installed_bundles import read_installed_bundles

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BUNDLES = read_installed_bundles()
SKILLS = {
    "sql-health-triage": "sql_health_triage",
    "sql-optimizer": "sql_optimizer",
    "sql-plan-enforcer": "sql_plan_enforcer",
    "sql-index-manager": "sql_index_manager",
}
WRITE_LEARNING_SKILLS = {
    skill: bundle
    for skill, bundle in SKILLS.items()
    if skill != "sql-index-manager"
}


def _flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold())


def _core(bundle: str) -> str:
    return _flatten(BUNDLES[bundle][0])


def _reference(bundle: str, name: str) -> str:
    return _flatten(BUNDLES[bundle][1][name])


def _compact(bundle: str) -> str:
    """The whole installed bundle: the core first, then its references."""
    core, references = BUNDLES[bundle]
    return _flatten("\n".join((core, *references.values())))


def test_exact_skill_versions_are_published() -> None:
    expected = {
        "sql-health-triage": 'metadata: version: "1.1.0"',
        "sql-optimizer": 'metadata: version: "3.0.0"',
        "sql-plan-enforcer": 'metadata: version: "1.1.0"',
        "sql-index-manager": 'metadata: version: "2.1.0"',
    }
    for skill, phrase in expected.items():
        assert phrase in _core(SKILLS[skill]), skill


def test_every_skill_gates_database_and_runtime_before_recall() -> None:
    for skill, bundle in SKILLS.items():
        text = _compact(bundle)
        assert text.index("check_runtime_status") < text.index("recall_lessons"), skill
        assert text.index("list_databases") < text.index("recall_lessons"), skill
        assert text.index("check_capabilities") < text.index("recall_lessons"), skill
        for fingerprint in (
            "runtime_fingerprint",
            "runtime_compatibility_fingerprint",
            "tool_schema_fingerprint",
            "sanitized_config_fingerprint",
        ):
            assert fingerprint in text, (skill, fingerprint)
        assert "skill_version" in text, skill
        assert "raw sql" in text
        assert "hidden reasoning" in text
        recall_arguments = text.split("call `recall_lessons` with", 1)[1].split(
            "never send", 1
        )[0]
        assert "runtime_compatibility_fingerprint" in recall_arguments, skill
        assert "`runtime_fingerprint`" not in recall_arguments, skill


def test_learning_detail_is_routed_from_the_core_not_loaded_on_every_run() -> None:
    # The loop costs about 3 KB per skill. A run that never calls a learning
    # tool must not pay for it, but the core must still say it is advisory and
    # where the detail is before the first learning call.
    for skill, bundle in WRITE_LEARNING_SKILLS.items():
        core = _core(bundle)
        gate = core.split("## runtime contract gate", 1)[1]
        assert "advisory" in gate, skill
        assert "learning-loop" in gate, skill
        assert "before the first call" in gate, skill
        assert "unchanged" in gate, skill
        for detail in ("decisionrecordv1", "outcomereviewv1", "terminal_evidence_refs"):
            assert detail not in core, (skill, detail)
        assert "learning-loop.md" in BUNDLES[bundle][1], skill


def test_learning_order_is_evidence_decision_terminal_review_correction() -> None:
    required = (
        "record_decision",
        "decisionrecordv1",
        "decision_id",
        "subject_kind",
        "subject_fingerprint",
        "based_on_review_ids",
        "terminal",
        "terminal_link_id",
        "review_decision",
        "outcomereviewv1",
        "correction",
        "counterexample",
        "next_observation",
        "create_handoff",
        "get_handoff",
        "resolve_handoff",
        "handoffv1",
    )
    for skill, bundle in WRITE_LEARNING_SKILLS.items():
        text = _compact(bundle)
        for phrase in required:
            assert phrase in text, (skill, phrase)
        learning = _reference(bundle, "learning-loop.md")
        assert learning.startswith("# evidence-governed learning loop"), skill
        assert learning.index("call `recall_lessons` with") < learning.index("record_decision"), skill
        assert learning.index("record_decision") < learning.index("review_decision"), skill
        assert learning.index("review_decision") < learning.index("correction"), skill
        assert learning.index("counterexample") < learning.index("next_observation"), skill
        assert "evidence before" in learning, skill


def test_supported_decision_links_are_skill_specific() -> None:
    health = _compact(SKILLS["sql-health-triage"])
    optimizer = _compact(SKILLS["sql-optimizer"])
    plan = _compact(SKILLS["sql-plan-enforcer"])

    for tool in ("analyze_db_health", "collect_performance_evidence", "resolve_handoff"):
        assert tool in health
    for tool in (
        "benchmark_tuning_candidate",
        "benchmark_index_candidate",
        "finalize_tuning_session",
    ):
        assert tool in optimizer
    assert "prepare_plan_action` remains unlinked" in plan
    for tool in ("verify_plan_action", "rollback_plan_action", "resolve_handoff"):
        assert tool in plan
    assert "decision_id" in health and "decision_id" in optimizer and "decision_id" in plan

    index = _compact(SKILLS["sql-index-manager"])
    assert "review_workload_indexes" in index
    assert "recall-only" in index
    assert "no evidence id and no terminal link" in index

    for text in (health, optimizer, plan, index):
        assert "do not invent a decision_id" not in text
        assert "do not invent a decision_id parameter" not in text


def test_index_recommendation_ids_are_tracking_only() -> None:
    index = _compact(SKILLS["sql-index-manager"])
    assert (
        "recommendation ids, review ids, and query ids are tracking references, "
        "not learning evidence references"
    ) in index
    assert "evidence_ref" not in index
    for invented in (
        "prior_state_ref",
        "classification_ref",
        "blocker_ref",
        "validation_ref",
        "rollback_ref",
    ):
        assert invented not in index


def test_retired_index_portfolio_tool_names_are_absent() -> None:
    retired = (
        "get_index_portfolio_" + "snapshot",
        "capture_index_portfolio_" + "snapshot",
        "classify_index_" + "portfolio",
        "recheck_index_" + "portfolio",
    )
    roots = (REPO_ROOT / "README.md", REPO_ROOT / "skills", REPO_ROOT / "scripts", REPO_ROOT / "docs")
    paths = [path for root in roots for path in ([root] if root.is_file() else root.rglob("*"))]
    for path in paths:
        relative_parts = path.relative_to(REPO_ROOT).parts
        if (
            not path.is_file()
            or any(part.startswith(".") for part in relative_parts)
            or "__pycache__" in path.parts
            or path.suffix == ".pyc"
        ):
            continue
        text = path.read_text(encoding="utf-8")
        for name in retired:
            assert name not in text, f"{name} remains in {path}"


def test_learning_fallback_and_safety_boundaries_are_explicit() -> None:
    for skill, bundle in WRITE_LEARNING_SKILLS.items():
        text = _compact(bundle)
        for phrase in (
            "unavailable",
            "malformed",
            "stale",
            "incompatible",
            "remote-disabled",
            "unchanged",
            "advisory",
            "cannot activate",
            "local ledger",
            "install memory",
            "authorization",
            "equivalence",
            "cleanup",
            "verification",
            "rollback",
        ):
            assert phrase in text, (skill, phrase)
        assert "decision_id" in text, skill


def test_index_manager_is_recall_only_until_an_evidence_bridge_exists() -> None:
    index = _compact(SKILLS["sql-index-manager"])
    for phrase in (
        "recall-only",
        "future public mcp contract",
        "index evidence bridge",
        "no evidence id and no terminal link",
        "not learning evidence references",
        "never evidence",
        "without invoking learning or handoff tools",
    ):
        assert phrase in index, phrase

    forbidden = (
        "record_decision",
        "review_decision",
        "propose_lesson",
        "list_learning_candidates",
        "create_handoff",
        "get_handoff",
        "resolve_handoff",
    )
    for tool in forbidden:
        assert f"`{tool}`" in index
        assert re.search(rf"\b{tool}\s*\(", index) is None


def test_peer_routes_to_index_manager_are_report_only_in_v1() -> None:
    for skill, bundle in WRITE_LEARNING_SKILLS.items():
        text = _compact(bundle)
        assert (
            "v1 index-manager routing is the exception to the typed handoff rule"
            in text
        ), skill
        assert "do not create a typed `handoffv1` for that target" in text, skill
        assert (
            "do not relabel case, snapshot, review, or run ids as learning evidence refs"
            in text
        ), skill
