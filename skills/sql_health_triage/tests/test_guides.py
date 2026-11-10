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
    for phrase in ('First lines: the answer to the question asked', 'what to do now', 'Commit to one cause when the aligned evidence supports it', 'say that plainly and name the one check that would decide', 'the risk of acting, the risk of not acting, and how to undo it'):
        assert phrase in reader


def test_triage_starts_from_one_diagnosis_call_and_reads_it_in_order() -> None:
    # diagnose_database returns a conclusion, ranked stories, leads and scored
    # facts. The skill must read them in that order and follow the top story,
    # not walk every incident path.
    start = _flat(_section(TEXT, "## Start with one diagnosis"))
    assert "call `diagnose_database` first" in start
    order = [start.index(f"`{field}`") for field in ("conclusion", "stories", "leads", "facts", "verdict")]
    assert order == sorted(order)
    for phrase in (
        "a cause with a `confidence` below 1",
        "the facts that support it (`supporting_facts`)",
        "the checks that did not support it (`checked_not_supporting`)",
        "what would raise the confidence (`raise_confidence`)",
        "`next_tools` with ready arguments",
        "`basis` `verified` (read in this call) or `inferred` (derived or cumulative)",
        "A `not_observed` fact is a source that could not be read",
        "`partial` means a source was not read, so the result is not an all-clear",
        "Then run the `next_tools` of the top story, and only those",
    ):
        assert phrase in start, phrase


def test_client_answer_leads_with_the_top_story_and_its_confidence_in_plain_words() -> None:
    reader = _flat(_section(TEXT, "## Write for the reader"))
    for phrase in (
        "Lead with the top story and its confidence in plain words",
        '0.75 or more: "the evidence strongly supports"',
        '0.5 to 0.75: "the most likely cause is"',
        'below 0.5: "a possible cause, not established"',
        'never write "the cause is" without the qualifier',
        "the facts for the story and the checks against it",
        "whether it was read directly or inferred",
        "what would raise the confidence",
    ):
        assert phrase in reader, phrase


def test_a_lead_is_never_presented_as_a_cause() -> None:
    rules = _flat(_section(TEXT, "## Non-negotiable rules"))
    assert "Never present a lead as a cause" in rules
    start = _flat(_section(TEXT, "## Start with one diagnosis"))
    assert "A lead is not a cause" in start
    assert "`possible_causes` names the second fact that would make it one" in start
    reader = _flat(_section(TEXT, "## Write for the reader"))
    for phrase in (
        'A lead stays a lead: write "one observation, not corroborated"',
        "name the second fact that would confirm it",
        "attach no fix to a lead alone",
    ):
        assert phrase in reader, phrase
    outcome = _flat(_section(TEXT, "## Outcome contract"))
    assert "A lead alone is never `actionable`" in outcome


def test_triage_says_what_was_not_observed() -> None:
    rules = _flat(_section(TEXT, "## Non-negotiable rules"))
    assert "never present an unread source as an all-clear" in rules
    reader = _flat(_section(TEXT, "## Write for the reader"))
    for phrase in (
        "Say what was not observed",
        "every source that could not be read, why, and the statement a DBA can run",
        "An unread source is unknown, never healthy",
    ):
        assert phrase in reader, phrase
    output = _flat(_section(TEXT, "## Required output"))
    assert "**Not observed**" in output


def test_baseline_capacity_and_history_claims_follow_the_tool() -> None:
    section = _flat(_section(TEXT, "## Normal, capacity, and history"))
    for phrase in (
        "`get_database_baseline`",
        'Say "abnormal for this hour" only when the tool returns `judgement` `abnormal` with `band_kind` `hour_of_week` or `hour_of_day`',
        'With `band_kind` `flat`, say "above this database\'s usual level"',
        "`insufficient_history` or `too_few_executions` means you cannot say whether it is normal",
        "`assess_capacity`",
        "it reads no price, so state none",
        "`get_elastic_pool_pressure`",
        "`get_diagnostic_history`",
        "`category=coverage` lists them",
        "`precondition` means no recorder is configured for that question",
        'show the `remediation`, and never call it "nothing happened"',
        "Only `empty` from a recorder that covers the window is a true negative",
        "`get_deadlock_history` with `source=auto`",
        "`get_failed_executions`",
        "`analyze_application_patterns`",
        "`get_memory_pressure`",
        "`get_columnstore_health`",
    ):
        assert phrase in section, phrase


def test_translate_table_gives_plain_words_for_every_internal_term() -> None:
    # Client text that carries a status code or a tool name reads as a tool
    # log. Each internal term needs a plain-language replacement.
    section = _section(TEXT, "## Write for the reader")
    reader = _flat(section)
    for forbidden in ("tool names", "skill names", "internal field names", "status codes"):
        assert forbidden in reader
    assert "operator notes" in reader
    table = _rows(section)
    for term in ('`healthy`', '`actionable`', '`partial`', '`inconclusive`', '`precondition`', '`sql-optimizer`', '`sql-index-manager`', '`sql-plan-enforcer`'):
        plain = next(text for key, text in table.items() if term in key)
        assert plain and "`" not in plain and "_" not in plain, term


def test_triage_is_self_contained_and_read_only() -> None:
    assert TEXT.startswith("---\nname: sql-health-triage\n")
    assert 'metadata:\n  version: "1.1.0"' in TEXT
    assert "This skill is permanently read-only" in TEXT
    assert "Never call DDL, DML, unrestricted execution" in TEXT
    assert not re.search(r"https?://|[A-Za-z]+Guide\.md|/Users/", BUNDLE)


def test_triage_uses_exact_outcome_vocabulary() -> None:
    for state in ("healthy", "actionable", "partial", "inconclusive"):
        assert f"`{state}`" in TEXT
    assert "exactly one overall outcome" in TEXT


def test_incomplete_evidence_can_never_be_healthy() -> None:
    assert "Do not call an outcome healthy when any required evidence is unavailable" in TEXT
    assert "report `partial`" in TEXT
    assert "use partial or inconclusive, not healthy" in TEXT


def test_triage_quotes_numbers_with_unit_window_and_source() -> None:
    # The tools return scored facts; the skill only has to keep the number,
    # its bar and its window together and never mix windows.
    rules = _flat(_section(TEXT, "## Non-negotiable rules"))
    for phrase in (
        "Quote every number with its unit, its bar, its UTC window, and its source",
        "Evidence from different windows may support separate observations but is never combined as one causal comparison",
        "stable query identity",
    ):
        assert phrase in rules, phrase


def test_triage_uses_shared_cases_and_safe_handoffs() -> None:
    for tool in (
        "start_performance_case",
        "collect_performance_evidence",
        "get_performance_case",
    ):
        assert f"`{tool}`" in TEXT
    assert "case id is the durable handoff key" in TEXT
    assert "Do not copy raw SQL into local JSON" in TEXT


def test_deprecated_query_health_heuristics_are_absent() -> None:
    forbidden = (
        "fragment" + "ation",
        "page life " + "expectancy",
        "buffer cache " + "hit ratio",
    )
    lowered = TEXT.casefold()
    for phrase in forbidden:
        assert phrase not in lowered


def test_triage_reports_a_blocker_once_then_stops_retrying() -> None:
    # report_stuck writes a local backlog entry, so the read-only rule must name
    # it or the two rules contradict each other.
    rules = _flat(_section(TEXT, "## Non-negotiable rules"))
    assert "Call only read-only MCP tools, plus `report_stuck`" in rules
    assert "Never call DDL, DML, unrestricted execution" in rules
    for phrase in (
        "the same tool call fails the same way twice",
        "a required precondition cannot be met",
        "this skill's text contradicts what a tool returns",
        "call `report_stuck` once with `skill`, `skill_version` (this file's `metadata.version`), `last_tool`, `blocker_kind`",
        "no SQL, data values, or object, server, or database names",
        "If `report_stuck` is not in the tool list, skip it silently",
        "stop retrying that exact call, tell the user what is blocked, and give them the returned `incident_id`",
        "`failure_diagnostic.transient` is true (for example 40613, 40501, 49918) gets its normal retry first",
    ):
        assert phrase in rules


def test_runtime_gate_runs_before_any_case_or_evidence_tool() -> None:
    gate = _flat(_section(TEXT, "## Runtime contract gate"))
    calls = [gate.index(f"`{tool}`") for tool in (
        "check_runtime_status",
        "list_databases",
        "check_capabilities",
    )]
    assert calls == sorted(calls)
    for phrase in (
        "before any case or evidence tool",
        "Use only the database the user selects from the returned allowlist",
        "A server whose `profile` is null is valid",
        "that source cannot support an all-clear",
        "never authorize a write",
        "Use them only when the user asks",
        "keep the read-only behavior unchanged",
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


def test_blocking_path_reads_the_chain_and_true_lock_totals() -> None:
    # A head blocker that runs nothing holds an abandoned transaction: the fix
    # is the code path that left it open. The lock total, not the returned
    # row count, says how big the storm is.
    normalized = " ".join(TEXT.split())
    for phrase in (
        "`head_blocker_has_active_request` is false",
        "idle in an open transaction",
        "`total_locks` and `waiting_locks` are the database totals; `returned_locks` is only the rows shown",
        "`analyze_query_plan` with `session_id`",
    ):
        assert phrase in normalized
