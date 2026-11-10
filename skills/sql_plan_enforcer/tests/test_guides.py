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
    reader = _flat(_section(TEXT, "## Write for the reader"))
    for phrase in ('First lines: the decision (stabilize this plan, hold, roll back, or do nothing) and the expected effect', 'Commit to one control when the aligned evidence supports it', 'say that plainly and name the observation that would decide', 'the risk of acting, the risk of not acting, and the rollback (the exact prior state)'):
        assert phrase in reader


def test_translate_table_gives_plain_words_for_every_internal_term() -> None:
    # Client text that carries a status code or a tool name reads as a tool
    # log. Each internal term needs a plain-language replacement.
    section = _section(TEXT, "## Write for the reader")
    reader = _flat(section)
    for forbidden in ("tool names", "skill names", "internal field names", "status codes"):
        assert forbidden in reader
    assert "operator notes" in reader
    table = _rows(section)
    for term in ('prepared intent', '`keep`', '`rollback`', '`hold`', '`unknown`', '`ownership_review`', '`enforcer-review`'):
        plain = next(text for key, text in table.items() if term in key)
        assert plain and "`" not in plain and "_" not in plain, term


def test_enforcer_is_self_contained_and_mcp_owned() -> None:
    assert TEXT.startswith("---\nname: sql-plan-enforcer\n")
    assert 'metadata:\n  version: "1.1.0"' in TEXT
    assert "MCP prepared-intent lifecycle" in TEXT
    assert "MCP owns all durable intent state" in TEXT
    assert not re.search(r"https?://|[A-Za-z]+Guide\.md|/Users/", BUNDLE)


def test_direct_apply_paths_are_forbidden_and_tick_is_preview_only() -> None:
    assert "`plan_enforcer_tick` is permanently preview-only" in TEXT
    for tool in (
        "force_query_plan",
        "apply_plan_action",
        "unrestricted SQL",
    ):
        assert tool in TEXT
    assert "not valid apply paths" in TEXT


def test_prepared_intent_lifecycle_is_complete() -> None:
    for tool in (
        "prepare_plan_action",
        "apply_prepared_plan_action",
        "verify_plan_action",
        "rollback_plan_action",
    ):
        assert f"`{tool}`" in TEXT
    assert "observed -> reviewed -> prepared -> applied -> observing -> kept" in TEXT


def test_apply_is_fail_closed_and_idempotent() -> None:
    for phrase in (
        "local stdio `enforcer-apply`",
        "`AZURE_SQL_TOOL_GROUPS=core,performance,admin`",
        "unrestricted/apply posture",
        "evidence hash",
        "exact prior force/hint state",
        "database policy",
        "global kill switch",
        "idempotency key",
        "ownership is explicitly manual",
        "must not apply twice",
    ):
        assert phrase in TEXT


def test_verification_and_rollback_use_matching_evidence_and_exact_prior_state() -> None:
    for phrase in (
        "Pre and post windows must not overlap",
        "parameter buckets must match",
        "Insufficient evidence never means keep",
        "restores the exact pre-change state",
        "mark `unknown`",
    ):
        assert phrase in TEXT


def test_automatic_tuning_and_unknown_ownership_are_review_only() -> None:
    assert "Unknown or Automatic Tuning/engine ownership is review-only" in TEXT
    assert "do not prepare or apply an overlapping custom control" in TEXT


def test_blocker_is_reported_once_then_the_call_is_not_retried() -> None:
    # A blocked session leaves a redacted backlog entry instead of looping, but
    # a failover or busy error must still get its normal retry first.
    failures = _flat(_section(TEXT, "## Failure behavior"))
    assert "Apply timeout or uncertain response: reconcile through MCP; never retry blindly" in failures
    for phrase in (
        "the same tool call fails the same way twice",
        "a required precondition cannot be met",
        "this skill's text contradicts what a tool returns",
        "call `report_stuck` once with `skill`, `skill_version` (this file's `metadata.version`), `last_tool`, `blocker_kind`",
        "no SQL, data values, or object, server, or database names",
        "If `report_stuck` is not in the tool list, skip it silently",
        "stop retrying that exact call, tell the user what is blocked, and give them the returned `incident_id`",
        "`failure_diagnostic.transient` is true (for example 40613, 40501, 49918) gets its normal retry first",
        "`verification_failed` means a write was sent and its outcome is unknown",
        "never resubmit that apply or rollback",
    ):
        assert phrase in failures


def test_runtime_gate_runs_before_any_review_or_control_tool() -> None:
    gate = _flat(_section(TEXT, "## Runtime contract gate"))
    calls = [gate.index(f"`{tool}`") for tool in (
        "check_runtime_status",
        "list_databases",
        "check_capabilities",
    )]
    assert calls == sorted(calls)
    for phrase in (
        "before any review, preparation, verification, or rollback tool",
        "Use only the database the user selects from the returned allowlist",
        "Plan actions need the `enforcer-review` or `enforcer-apply` profile",
        "on any other server, including an unprofiled one, preparation is refused",
        "is a hard stop",
        "never authorize preparation or apply",
        "Use them only when the user asks",
        "keep the review-only behavior unchanged",
    ):
        assert phrase in gate
    # Fingerprints are arguments of the learning tools only.
    assert "_fingerprint" not in TEXT
    learning = _flat(REFERENCES["learning-loop.md"])
    for name in (
        "`runtime_fingerprint`",
        "`runtime_compatibility_fingerprint`",
        "`tool_schema_fingerprint`",
        "`sanitized_config_fingerprint`",
    ):
        assert name in learning, name


def test_prepare_reads_the_force_precheck_before_any_talk_of_apply() -> None:
    # A blocker rejects the intent. The skill must say why in the client's
    # terms and must not look for a way around it.
    prepare = _flat(_section(TEXT, "## 3. Prepare"))
    for phrase in (
        "`force_precheck`",
        "`status` is `block`, `warn`, or `pass`",
        "A blocker rejects the intent, so nothing is prepared",
        "`parameter_sensitive_query`",
        "one forced plan is wrong for part of the values",
        "`plan_belongs_to_another_query`",
        "`plan_not_run_recently` (not run for four days)",
        "`target_plan_not_found`",
        "`precheck_unavailable`",
        "Never retry a blocked force with another plan id to get past it",
        "A warning does not reject",
        "`psp_variant`",
        "`option_recompile`",
        "`temp_table_in_plan`",
        "`query_store_read_only`",
        "`prior_force_failures`",
        "Report every warning to the human before any apply",
    ):
        assert phrase in prepare, phrase


def test_guardrails_are_reported_and_never_worked_around() -> None:
    prepare = _flat(_section(TEXT, "## 3. Prepare"))
    for phrase in (
        "`guardrails`",
        "one force or hint action per query per day",
        "three per database per day",
        "a week after two failed actions on a query",
        "report `blocked_by` and `retry_after_utc` and wait",
        "never work around a guardrail with another intent or query id",
        "Unforce, clear hints, and rollback are never delayed",
    ):
        assert phrase in prepare, phrase
    apply = _flat(_section(TEXT, "## 4. Apply prepared action"))
    assert "`guardrail`" in apply
    assert "nothing was read or changed and the intent stays prepared" in apply


def test_production_apply_needs_a_token_that_only_a_human_passes_back() -> None:
    # The token exists so that a person, not the agent, confirms a production
    # change. An agent that guesses or echoes it defeats the control.
    apply = _flat(_section(TEXT, "## 4. Apply prepared action"))
    for phrase in (
        "production, which includes any environment label the server does not recognise as non-production",
        "`confirmation.confirmation_token`",
        "single-use",
        "expires after 15 minutes",
        "Never invent, guess, alter, or reuse a token",
        "never pass back a token in the same turn in which you showed it",
        "Tell the human exactly what to pass",
        "the intent id, the token, and their authorization reference",
        "pass it as `confirmation_token`",
        "If the token is refused or has expired, prepare the intent again",
        "never try another value",
    ):
        assert phrase in apply, phrase


def test_apply_failed_is_not_unknown_and_rollback_is_two_step_on_production() -> None:
    apply = _flat(_section(TEXT, "## 4. Apply prepared action"))
    for phrase in (
        "`apply_failed`",
        "the engine refused the action and the control state is unchanged",
        "the intent is back at prepared",
        "Report the reason, fix the cause, and apply again",
        "It is not the `unknown` state",
    ):
        assert phrase in apply, phrase
    rollback = _flat(_section(TEXT, "## 6. Roll back exactly"))
    for phrase in (
        "On a production database rollback takes two calls",
        "the first call, without a token, changes nothing and returns a rollback token",
        "call again with `confirmation_token`",
        "the same token rule as apply",
    ):
        assert phrase in rollback, phrase
