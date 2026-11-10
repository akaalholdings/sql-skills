from __future__ import annotations

import importlib.util
import pathlib
import re
import tempfile

SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
CORE_CEILING_BYTES = 14 * 1024


def _installed_bundle() -> tuple[str, dict[str, str]]:
    """Install the bundle and read it back, so every test sees what a host gets."""
    spec = importlib.util.spec_from_file_location(
        f"{SKILL_DIR.name}_install", SKILL_DIR / "install.py"
    )
    assert spec is not None and spec.loader is not None
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    with tempfile.TemporaryDirectory() as root:
        destination = installer.install(pathlib.Path(root) / "skills")
        core = (destination / "SKILL.md").read_text(encoding="utf-8")
        references = {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted((destination / "references").glob("*.md"))
        }
    return core, references


TEXT, REFERENCES = _installed_bundle()
BUNDLE = "\n".join((TEXT, *REFERENCES.values()))


def _flat(text: str) -> str:
    return " ".join(text.split())


def _section(text: str, heading: str) -> str:
    """Return one `## heading` section, up to the next `## ` heading."""
    return text.split(f"\n{heading}", 1)[1].split("\n## ", 1)[0]


def _rows(section: str) -> dict[str, str]:
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in section.splitlines()
        if line.startswith("|") and not set(line) <= set("|- ")
    ]
    return {row[0]: row[1] for row in rows[1:]}


def test_core_stays_under_its_size_ceiling() -> None:
    # Every run pays for the core. Detail that only some runs need belongs in
    # a reference, which costs nothing until its condition holds.
    assert len(TEXT.encode("utf-8")) <= CORE_CEILING_BYTES
    for name, text in REFERENCES.items():
        assert len(text.encode("utf-8")) <= CORE_CEILING_BYTES, name


def test_every_reference_is_routed_by_a_condition_and_every_route_resolves() -> None:
    # An unrouted reference is never read. A route to a missing file sends the
    # agent to look for guidance that was never installed.
    flat = _flat(TEXT)
    assert set(re.findall(r"references/([a-z-]+\.md)", TEXT)) == set(REFERENCES)
    for name, text in REFERENCES.items():
        route = flat.split(f"(references/{name})", 1)
        assert len(route) == 2, name
        condition = route[0].rsplit(". ", 1)[-1]
        assert re.search(r"\b(when|only when|before)\b", condition, re.IGNORECASE), name
        assert "nothing in this file relaxes them" in text, name


def test_report_leads_with_the_answer_and_states_both_risks_and_the_undo() -> None:
    # Both consult exams marked the skill down for burying the decision and
    # for leaving out what happens when nobody acts.
    reader = _flat(_section(TEXT, "## Output"))
    for phrase in ('Open with the answer: the few changes that matter most', 'labelled as an upper-bound estimate', 'Commit to a recommendation when the returned evidence supports it', 'say that plainly and name the evidence that would decide', 'the risk of acting (write cost, storage, the returned risks), the risk of not acting', 'and the rollback', 'Translate labels, never values'):
        assert phrase in reader


def test_translate_table_gives_plain_words_for_every_internal_term() -> None:
    # Client text that carries a status code or a tool name reads as a tool
    # log. Each internal term needs a plain-language replacement.
    section = _section(TEXT, "## Output")
    reader = _flat(section)
    for forbidden in ("tool names", "skill names", "internal field names", "status codes"):
        assert forbidden in reader
    assert "operator notes" in reader
    table = _rows(section)
    for term in ('`drop_index`', '`review_index`', '`estimated_max_benefit_pct`', '`blockers`', '`gaps`', '`precondition`', '`sql-optimizer`'):
        plain = next(text for key, text in table.items() if term in key)
        assert plain and "`" not in plain and "_" not in plain, term


NORMALIZED = " ".join(TEXT.casefold().split())
PUBLIC_README = (SKILL_DIR.parent / "README.md").read_text(encoding="utf-8")
PUBLIC_NORMALIZED = " ".join(PUBLIC_README.casefold().split())


def _position(term: str) -> int:
    return NORMALIZED.index(term.casefold())


def test_frontmatter_names_a_workload_driven_recommend_only_skill() -> None:
    assert TEXT.startswith("---\nname: sql-index-manager\n")
    assert 'metadata:\n  version: "2.1.0"' in TEXT
    description = TEXT.split("description:", 1)[1].split("\n", 1)[0].casefold()
    assert "query store" in description
    assert "recommend-only" in description
    assert "never executes index ddl" in description
    assert not re.search(r"https?://|/Users/", BUNDLE)
    assert " ".join(("safe", "to", "drop")) not in _flat(BUNDLE).casefold()  # noqa: FLY002


def test_runtime_gate_runs_before_the_review_in_order() -> None:
    ordered = (
        "check_runtime_status",
        "list_databases",
        "let the user pick one",
        "check_capabilities",
        "mcp_contract.workload_index_advisor=1",
        "call `review_workload_indexes`",
    )
    positions = [_position(term) for term in ordered]
    assert positions == sorted(positions)
    gate = NORMALIZED.split("## runtime and database gate", 1)[1].split("## ", 1)[0]
    assert "a server whose `profile` is null is valid" in gate
    # Fingerprints are arguments of lesson recall only, and a version test in
    # prose goes stale: the contract flag is the gate.
    assert "_fingerprint" not in TEXT
    assert "2.4.0" not in TEXT
    assert re.search(r"(MCP|server) older than", _flat(BUNDLE)) is None


def test_columnstore_indexes_are_protected_and_explained() -> None:
    # A columnstore index used only at period end looks unused. Its removal is
    # a design decision, and bringing it back recompresses the whole table.
    core = NORMALIZED.split("## leads that are not b-tree changes", 1)[1].split("## ", 1)[0]
    for phrase in (
        "must not be presented as a create or a drop",
        "(references/design-leads.md) before you present it",
        "`columnstore_index_protected`",
        "columnstore indexes are protected and explained, never removal candidates from usage data",
    ):
        assert phrase in core, phrase
    leads = _flat(REFERENCES["design-leads.md"])
    for phrase in (
        "`columnstore_index_protected`",
        "usage counters and a short Query Store window do not prove non-use",
        "bringing it back means compressing the whole table again",
        "`columnstore_selective_lookup`",
        "only for selective lookups",
        "the columnstore index keeps serving the scans",
        "`columnstore_scan_not_a_btree_candidate`",
        "`consider_columnstore_index`",
        "a large rowstore table that is scanned and reduced",
        "It has no DDL",
        "`conditions` with their measured values",
        "`columnstore_maintenance`",
        "there is no rollback",
        "the cause is the load pattern",
        "`get_columnstore_health`",
    ):
        assert phrase in leads, phrase


def test_partitioned_tables_are_review_leads_with_the_switch_reason() -> None:
    core = NORMALIZED.split("## leads that are not b-tree changes", 1)[1].split("## ", 1)[0]
    assert "`partitioned_index_removal_needs_switch_review`" in core
    assert "a review lead with no drop statement, because partition switching depends on it" in core
    leads = _flat(REFERENCES["design-leads.md"])
    for phrase in (
        "`partition_switch_dependency`",
        "ALTER TABLE ... SWITCH needs matching indexes on both tables",
        "ask how the table is loaded and archived",
        "`partitioning`",
        "`non_aligned_alternative`",
    ):
        assert phrase in leads, phrase


def test_physical_design_leads_carry_evidence_and_no_rebuild() -> None:
    core = NORMALIZED.split("## leads that are not b-tree changes", 1)[1].split("## ", 1)[0]
    assert "`physical_design_lead`" in core
    leads = _flat(REFERENCES["design-leads.md"])
    for phrase in (
        "`estimate_statements`",
        "run the estimate first; the lead proposes no rebuild",
        "a unique constraint and a covering twin index hold the same key",
        "`design_statements` and `rollback_statements`",
        "A change is proposed only from measured leaf allocations against leaf inserts",
        "Counters that could not be read give a gap, never a lead",
        "`design_lead_requires_change_review`",
    ):
        assert phrase in leads, phrase


def test_change_plan_orders_create_change_observe_remove() -> None:
    plan = NORMALIZED.split("## the client change plan", 1)[1].split("## ", 1)[0]
    for phrase in (
        "`include_change_plan=true`",
        "`soak_days`",
        "`change_plan.steps`",
        "create, change, observe, remove",
        "keep that order",
        "`recheck_before_acting`",
        "the risk of acting, and the risk of not acting",
        "`not_planned`",
        "`open_questions`",
        "never move a blocked item or a lead into the plan",
    ):
        assert phrase in plan, phrase


def test_proof_hands_index_sets_and_replaces_to_the_optimizer() -> None:
    proof = NORMALIZED.split("## prove before production", 1)[1].split("## ", 1)[0]
    for phrase in (
        "one set of up to four indexes (`indexes`)",
        "`validation.replaces`",
        "as `replaces`",
        "`hinted_evidence`",
        "not proof that the optimizer will choose it",
    ):
        assert phrase in proof, phrase


def test_removal_discipline_covers_left_prefix_and_stale_reviews() -> None:
    removal = NORMALIZED.split("## removal discipline", 1)[1].split("## prove before production", 1)[0]
    for phrase in (
        "`left_prefix_of_wider_index`",
        "merged into the widest index that is not itself proposed for removal (`merge_into`)",
        "`narrow_index_used_in_workload_scans_may_prefer_it`",
        "a narrow index is cheaper to scan, so they may slow down",
        "with `survivor_cannot_absorb_includes`, keep the narrow index",
        "`leftover_test_index`",
    ):
        assert phrase in removal, phrase
    history = _flat(REFERENCES["portfolio-history.md"])
    for phrase in (
        "`observation.history_status`",
        "`stale`",
        "`historical`",
        "`stale_hours`",
        "is history, not a basis for a removal",
        "capture a new snapshot and review again",
        "two unused indexes where one covers the other are both removal candidates",
    ):
        assert phrase in history, phrase


def test_the_advisor_needs_no_install_step_or_policy_file() -> None:
    for phrase in (
        "view database state",
        "view definition",
        "no policy file, history table, or install step is required",
    ):
        assert phrase in NORMALIZED


def test_every_result_status_has_explicit_handling() -> None:
    for status in ("`ok`", "`empty`", "`precondition`", "`unavailable`", "`not_supported`"):
        assert status in TEXT
    # Remediation is shown to the DBA, never executed by the skill.
    assert "show the returned `remediation` statement for the dba to run; do not run it" in NORMALIZED
    assert "report `gaps` verbatim" in NORMALIZED


def test_scope_defaults_and_past_windows_are_explicit() -> None:
    for phrase in ("`schema_name`", "`table_names`", "`lookback_days=7`", "`as_of_utc`", "`top_queries=100`"):
        assert phrase in TEXT
    assert "full business cycle" in NORMALIZED
    assert "`analyzed_share_pct` is below 80" in NORMALIZED


def test_removal_window_reaches_high_confidence_drops() -> None:
    # The MCP rates a drop_index high only when Query Store covers 35 days, and
    # it measures coverage from interval edges, so a lookback of exactly 35 can
    # come back as 34.95 days and cap every drop at medium. Ask for a margin.
    window = NORMALIZED.split("- window:", 1)[1].split("- objective:", 1)[0]
    assert "use `lookback_days=40` when removal decisions matter" in window
    assert "`lookback_days=35`" not in window
    assert "caps `drop_index` confidence at medium" in window
    assert "14–30" not in window
    # Azure SQL Database keeps 30 days of Query Store by default, so a longer
    # lookback cannot help; report the gap instead of repeating the review.
    # The stop rule must use the 35-day gate, not the lookback: with a 40-day
    # lookback, 38 effective days still gives high confidence and is no gap.
    assert "`stale_query_threshold_days`" in window
    assert "`window.query_store_effective_days` is less than 35" in window
    assert "less than the lookback" not in window
    assert "report the retention gap" in window
    # The default 7-day review always returns about 7 effective days. The stop
    # rule applies only to a removal review, or every default run would stop.
    assert "on a removal review (`lookback_days` of 35 or more)" in window


def test_skill_never_executes_ddl_or_calls_ddl_tools() -> None:
    assert "recommend-only. never execute index ddl" in NORMALIZED
    for tool in ("execute_tsql_unrestricted", "create_test_index", "drop_test_index", "rebuild_index"):
        assert f"`{tool}`" in TEXT
        assert re.search(rf"\b{tool}\s*\(", BUNDLE) is None
    assert "inert advice for a human dba's change control" in NORMALIZED
    assert "never say a change is safe, approved, or applied" in NORMALIZED


def test_estimates_are_labelled_as_upper_bounds_not_promises() -> None:
    assert "`estimated_max_benefit_pct` as an upper-bound estimate" in NORMALIZED
    assert "does not promise a saving" in NORMALIZED
    assert "`estimated_max_size_mb`" in TEXT
    assert "never invent database names, query ids, index names, row counts, timings" in NORMALIZED


def test_proof_and_rewrites_route_to_the_optimizer() -> None:
    proof = NORMALIZED.split("## prove before production", 1)[1]
    for phrase in ("`sql-optimizer`", "`start_tuning_session`", "`benchmark_index_candidate`", "non-production copy"):
        assert phrase in proof
    assert "only a measured, validated candidate goes to the human dba's change control" in proof
    assert "non-sargable predicates and implicit conversions cannot be fixed by an index" in NORMALIZED


def test_removal_discipline_covers_counter_resets_capture_mode_and_rollback() -> None:
    removal = NORMALIZED.split("## removal discipline", 1)[1].split("## prove before production", 1)[0]
    for phrase in (
        "usage counters reset on failover",
        "`usage_counters.days_since_reset`",
        "capture mode `auto` can miss rare queries",
        "no index hint, plan guide, or forced plan",
        "`rollback_ddl` must be kept",
        "never removal candidates",
    ):
        assert phrase in removal


def test_design_judgement_is_labelled_and_cannot_override_evidence() -> None:
    assert '"modified, unvalidated"' in NORMALIZED
    assert "never change a returned `confidence`, drop a returned blocker" in NORMALIZED


def test_portfolio_history_tools_are_optional_and_policy_gated() -> None:
    # The core says the tools are optional and when to read the reference.
    section = NORMALIZED.split("## optional: long-term portfolio history", 1)[1].split("##", 1)[0]
    for tool in ("capture_index_review_snapshot", "review_index_portfolio", "get_index_review"):
        assert f"`{tool}`" in section
    assert "not needed for workload-driven design" in section
    assert "`allow_index_history_write`" in section
    assert "(references/portfolio-history.md) before the first call" in section
    history = _flat(REFERENCES["portfolio-history.md"])
    assert "require a database policy with `allow_read=true`" in history
    assert "show its `remediation` to a DBA and stop; never run it yourself" in history


def test_output_sections_are_ordered() -> None:
    ordered = (
        "**outcome**",
        "**coverage and gaps**",
        "**top improvements**",
        "**cleanup**",
        "**per-table detail**",
        "**rewrite opportunities**",
        "**next steps**",
    )
    positions = [_position(term) for term in ordered]
    assert positions == sorted(positions)
    assert '"inert, for dba change control"' in NORMALIZED


def test_public_readme_describes_the_workload_driven_flow() -> None:
    for phrase in (
        "review_workload_indexes",
        "sql-index-manager",
        "recommend-only",
    ):
        assert phrase in PUBLIC_NORMALIZED
    assert "seven" not in PUBLIC_NORMALIZED.split("sql-index-manager", 1)[1].split("\n", 1)[0]


def test_blocker_is_reported_once_then_the_call_is_not_retried() -> None:
    # A blocked session leaves a redacted backlog entry instead of looping, but
    # a failover or busy error must still get its normal retry first.
    boundaries = NORMALIZED.split("## boundaries", 1)[1].split("## ", 1)[0]
    for phrase in (
        "the same tool call fails the same way twice",
        "a required precondition cannot be met",
        "this skill's text contradicts what a tool returns",
        "call `report_stuck` once with `skill`, `skill_version` (this file's `metadata.version`), `last_tool`, `blocker_kind`",
        "no sql, data values, or object, server, or database names",
        "if `report_stuck` is not in the tool list, skip it silently",
        "stop retrying that exact call, tell the user what is blocked, and give them the returned `incident_id`",
        "`failure_diagnostic.transient` is true (for example 40613, 40501, 49918) gets its normal retry first",
    ):
        assert phrase in boundaries


def test_portfolio_review_reads_the_gate_of_a_candidate_before_advice() -> None:
    # The review is compact: it lists candidates and counts the rest. The
    # evidence behind one drop is a separate read of that subject.
    history = _flat(REFERENCES["portfolio-history.md"])
    for phrase in (
        "`actionable_subjects`",
        "`get_index_review` with `subject_ids`",
        "before you recommend a drop or a consolidation",
        "`omitted_subjects`",
    ):
        assert phrase in history


def test_lesson_recall_stays_recall_only_in_the_core() -> None:
    # The recall call is optional detail. The ban on learning writes and
    # handoffs is a boundary, so it stays in the file every run reads.
    recall = NORMALIZED.split("## advisory lesson recall", 1)[1].split("## ", 1)[0]
    assert "this skill is recall-only" in recall
    assert "never changes a returned confidence, blocker, or recommendation" in recall
    assert "(references/lesson-recall.md) first" in recall
    for tool in ("record_decision", "review_decision", "create_handoff", "resolve_handoff"):
        assert f"`{tool}`" in recall
    call = _flat(REFERENCES["lesson-recall.md"])
    assert "recall_lessons(skill=sql-index-manager, skill_version=2.1.0," in call
    assert "Do not pass the process `runtime_fingerprint`" in call
