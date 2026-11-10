# Evidence-governed learning loop

Detail for `SKILL.md`. Its boundaries apply here; nothing in this file relaxes them.

This loop is optional: run it only when the user asks for it. The learning tools take
four fingerprints from `check_runtime_status` as arguments: the process
`runtime_fingerprint` and the stable `runtime_compatibility_fingerprint`,
`tool_schema_fingerprint`, and `sanitized_config_fingerprint`. No other tool needs them.

## Recall

After the runtime and database gate in `SKILL.md` passes, call `recall_lessons` with
`skill=sql-plan-enforcer` and `skill_version=1.1.0`, the stable
`runtime_compatibility_fingerprint`, tool-schema and sanitized-config
fingerprints, and only supported optional
`query_fingerprint`, `tags`, and `database_name`. Never send raw SQL,
credentials, parameter values, result rows, or hidden reasoning.

## Decide, link, review

Lessons remain advisory only: they may rank review attention or expose risk, but
they never authorize preparation/apply, override ownership or policy, or weaken
verification, cleanup, rollback, equivalence, or the review-only default. Use evidence before
judgment. Once real evidence references exist and before a material control
judgment, call `record_decision` with the supported `DecisionRecordV1` fields:
`skill`, `skill_version`, `learning_key`, `subject_kind`,
`subject_fingerprint`, `consumed_evidence_refs`, `based_on_review_ids`, `tactic`,
`expected_result`, `confidence`, `uncertainty`, evaluator/runtime/schema/config
fingerprints, both runtime fingerprints, and applicable case/session/query
references. Record structured conclusions only; never store hidden reasoning.
Use `subject_kind=plan` and record a control or hold decision before
`prepare_plan_action`.

`prepare_plan_action` remains unlinked by the approved schema. Pass the
recorded decision id to `verify_plan_action`, `rollback_plan_action`, or a
resolved `resolve_handoff` call. Each terminal action returns
`terminal_link_id`; only then call `review_decision` as `OutcomeReviewV1` with that link in
`terminal_evidence_refs`, plus `observed_result`, `prediction_error`,
`counterexamples`, `next_observation`, and any correction. Never review
pending, partial, timed-out, stale, inferred, or unlinked results. A failed
prediction must include its correction and counterexample before considering
another control; the next decision cites the prior review through
`based_on_review_ids`. Propose a lesson only after review; the skill cannot
activate or approve it.

## Handoffs

Use the typed `HandoffV1` lifecycle for cross-skill work: `create_handoff` takes
`source_skill`, `target_skill`, redacted `objective`, immutable `evidence_refs`,
`constraints`, `gaps`, `acceptance_criteria`, and shared `case_id`/`session_id`;
`get_handoff` retrieves it; `resolve_handoff` requires an allowed action,
`expected_version`, the recorded `decision_id`, and terminal recipient evidence
or an explicit human decision when resolving. Handoffs never grant
authorization. If any learning or handoff tool is unavailable, malformed,
stale, incompatible, or remote-disabled, retain existing review-only behavior
unchanged. Do not create a substitute local ledger, install memory, or persist
raw SQL.

V1 index-manager routing is the exception to the typed handoff rule. Until a
public index evidence bridge and terminal-link contract exist, route work to
`sql-index-manager` in the report only; do not create a typed `HandoffV1` for
that target and do not relabel case, snapshot, review, or run ids as learning
evidence refs.
