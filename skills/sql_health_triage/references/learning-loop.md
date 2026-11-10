# Evidence-governed learning loop

Detail for `SKILL.md`. Its non-negotiable rules apply here; nothing in this file relaxes them.

This loop is optional: run it only when the user asks for it. The learning tools take
four fingerprints from `check_runtime_status` as arguments: the process
`runtime_fingerprint` and the stable `runtime_compatibility_fingerprint`,
`tool_schema_fingerprint`, and `sanitized_config_fingerprint`. No other tool needs them.

## Recall

After the runtime and database gate in `SKILL.md` passes, call `recall_lessons` with
`skill=sql-health-triage` and `skill_version=1.1.0`, the stable
`runtime_compatibility_fingerprint`, tool-schema and sanitized-config
fingerprints, and only supported optional identifiers:
`query_fingerprint`, `tags`, and `database_name`. Never send raw SQL,
credentials, parameter values, result rows, or hidden reasoning.

## Decide, link, review

Lessons remain advisory: they are optional, scoped, and inactive until local
maintainer approval. Recall may reorder read-only investigation or highlight
risk; it never authorizes a write or changes this skill's outcome contract.
Use evidence before judgment: after real evidence references exist and before
recording a material diagnosis or route, call `record_decision` with the
supported `DecisionRecordV1` fields (`skill`, `skill_version`, `learning_key`,
`subject_kind`, `subject_fingerprint`, `consumed_evidence_refs`,
`based_on_review_ids`, `tactic`, `expected_result`, `confidence`, `uncertainty`,
evaluator/runtime/schema/config fingerprints, both runtime fingerprints, and
applicable case/query references). Record concise structured conclusions and
predictions only; never store chain-of-thought. Record it only after evidence
exists and before the diagnosis or routing action.
Use `subject_kind=database` for a bounded database assessment and
`subject_kind=incident` for a routed incident.

The `record_decision` response supplies `decision_id`. Pass that id to a
supported later terminal action: `analyze_db_health`,
`collect_performance_evidence`, or a resolved `resolve_handoff` call. Each
terminal action must return `terminal_link_id`. Call `review_decision` only
after that returned link, using it in `terminal_evidence_refs` as an
`OutcomeReviewV1`; include
`counterexamples`, `next_observation`, `observed_result`, `prediction_error`,
and any correction. Never review pending, partial, timed-out, stale, inferred,
or unlinked results. The next decision cites the prior review through
`based_on_review_ids`. Propose a reusable lesson only after review; the skill
cannot activate or approve it.

## Handoffs

Replace prose-only owner transfers with the typed `HandoffV1` lifecycle: call
`create_handoff` with `source_skill`, `target_skill`, redacted `objective`,
immutable `evidence_refs`, `constraints`, `gaps`, `acceptance_criteria`, and
shared `case_id`/`session_id` where available; retrieve it with `get_handoff`;
resolve it with `resolve_handoff` using an allowed lifecycle action,
`expected_version`, the recorded `decision_id`, and terminal recipient
evidence or an explicit human decision when resolving. Resolution carries no
authorization. If learning or handoff tools are unavailable, malformed, stale,
incompatible, or remote-disabled, retain the existing read-only behavior
unchanged; do not create a substitute local ledger, install memory, or persist
raw SQL. Learning can never weaken policy, authorization, equivalence, cleanup,
verification, rollback, or this skill's scope.

V1 index-manager routing is the exception to the typed handoff rule. Until a
public index evidence bridge and terminal-link contract exist, route work to
`sql-index-manager` in the report only; do not create a typed `HandoffV1` for
that target and do not relabel case, snapshot, review, or run ids as learning
evidence refs.
