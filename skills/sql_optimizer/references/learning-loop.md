# Evidence-governed learning loop

Detail for `SKILL.md`. Its hard rules apply here; nothing in this file relaxes them.

This loop is optional and outside the tuning path: run it only when the user asks for
it. When its tools are missing or fail, continue the tuning work unchanged. The learning
tools take four fingerprints from `check_runtime_status` as arguments: the process
`runtime_fingerprint` and the stable `runtime_compatibility_fingerprint`,
`tool_schema_fingerprint`, and `sanitized_config_fingerprint`. No tuning tool needs them.

## Recall

The learning plane is advisory only: it may reorder exploration or highlight a
risk, but it never authorizes execution, changes equivalence, or overrides
policy, cleanup, verification, rollback, or the candidate state machine. Do not
recall until the runtime contract gate in `SKILL.md` has passed. Then call
`recall_lessons` with `skill=sql-optimizer` and `skill_version=3.0.0`, the stable
`runtime_compatibility_fingerprint`,
`tool_schema_fingerprint`, and `sanitized_config_fingerprint`, plus only
supported optional `query_fingerprint`, `tags`, and `database_name`. Never send
raw SQL, credentials, parameter values, result rows, or hidden reasoning. A
missing, malformed, stale, incompatible, or remote-disabled recall falls back
to this skill's existing static/rewrite-first workflow unchanged.

## Decide, link, review

Use evidence before judgment. Once real evidence references have been consumed
and before a material measured candidate decision, call `record_decision` with
the supported `DecisionRecordV1` fields: `skill`, `skill_version`,
`learning_key`, `subject_kind`, `subject_fingerprint`,
`consumed_evidence_refs`, `based_on_review_ids`, `tactic`, `expected_result`,
`confidence`, `uncertainty`, evaluator/runtime/schema/config fingerprints, both
runtime fingerprints, and the applicable case/session/candidate/query
references. `expected_result` and `uncertainty` take one sentence or an object; free text
must not hold SQL statements. Record structured predictions and conclusions, never
chain-of-thought. Use `subject_kind=query` for rewrite, index, and final
selection decisions. Record one decision before each material benchmark and before
final selection; the response supplies its `decision_id`.

Pass each decision id to the corresponding supported terminal action:
`benchmark_tuning_candidate`, `benchmark_index_candidate`, or
`finalize_tuning_session`. Each returns `terminal_link_id`. Only then call
`review_decision` as `OutcomeReviewV1` with that returned id in
`terminal_evidence_refs`, plus `observed_result`, `prediction_error`,
`counterexamples`, `next_observation`, and any correction. Never review pending, partial, stale, inferred, or unlinked
results. Review a timeout only when MCP returned it as a durable terminal classification with a
`terminal_link_id`; otherwise it remains unreviewable. A losing prediction must record its
correction and counterexample before generating the next candidate; that next decision cites the
prior review through `based_on_review_ids`. Propose a lesson only after review; the skill cannot
activate or approve it.

## Handoffs

Use the typed `HandoffV1` lifecycle for cross-skill work: `create_handoff` takes
`source_skill`, `target_skill`, redacted `objective`, immutable `evidence_refs`,
`constraints`, `gaps`, `acceptance_criteria`, and shared `case_id`/`session_id`;
`get_handoff` retrieves it; `resolve_handoff` requires an allowed action,
`expected_version`, the recorded `decision_id`, and terminal recipient evidence
or an explicit human decision when resolving. Handoffs never grant
authorization. If any learning or handoff tool is unavailable, malformed,
stale, incompatible, or remote-disabled, retain existing static behavior, do
not create a substitute local ledger, install memory, or persist raw SQL. V1 index-manager routing is the exception to the typed handoff rule: until a public index evidence bridge and terminal-link contract exist, route work to `sql-index-manager` in the report only; do not create a typed `HandoffV1` for that target and do not relabel case, snapshot, review, or run ids as learning evidence refs.
