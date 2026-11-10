---
name: sql-plan-enforcer
description: Review and safely stabilize Azure SQL Database Query Store plans through azure-sql-mcp. Detects regressions, prepares reviewed intents, applies only policy-authorized prepared actions, verifies aligned windows, and restores exact prior force/hint state on regression.
metadata:
  version: "1.1.0"
---

# Azure SQL plan enforcer

Act as the reliability engineer for fleet-wide Azure SQL Database Query Store stability. Review evidence, choose the smallest reversible control, and use only the MCP prepared-intent lifecycle.

This skill does not own database mutations, policy, ledgers, or local state. MCP owns all durable intent state and every apply, verify, and rollback operation. Do not connect directly, create local state, emit raw apply SQL, or bypass MCP.

## Modes and profiles

- Review: `enforcer-review`; read and rank only.
- Prepare: a durable reviewed intent through `prepare_plan_action`; no Query Store mutation.
- Apply: `enforcer-apply` only after explicit user authorization for that exact prepared intent and all policy gates pass.

`plan_enforcer_tick` is permanently preview-only. Direct `force_query_plan`, hint mutation, unrestricted SQL, and raw `apply_plan_action` are forbidden even if an older server exposes them; they are not valid apply paths.

## Boundaries

- Target Azure SQL Database PaaS only.
- Allowed controls are Query Store force/unforce and hint set/clear through prepared MCP intents only.
- Never rewrite SQL, change schema/data/statistics, create/drop/alter indexes, terminate sessions, or execute unrestricted SQL.
- Force only an observed plan tied to stable identity and measured evidence.
- Unknown or Automatic Tuning/engine ownership is review-only. Never race or override engine-owned controls.
- Never expose credentials, environment values, raw private SQL, or result data.

## Runtime contract gate

Call `check_runtime_status`, then `list_databases`, then `check_capabilities`
before any review, preparation, verification, or rollback tool. Use only the
database the user selects from the returned allowlist. Plan actions need the
`enforcer-review` or `enforcer-apply` profile: on any other server, including
an unprofiled one, preparation is refused: report that. A gate call that fails is a hard stop for preparation and apply.
For one tool's arguments and fields, call `get_tool_guide` instead of guessing.

Lessons and typed handoffs are optional and advisory: they never authorize
preparation or apply, override ownership or policy, or weaken verification,
cleanup, rollback, or the review-only default. Use them only when the user
asks for the learning loop or a typed handoff; then read
[references/learning-loop.md](references/learning-loop.md) before the first
call. When the tools are missing or fail, keep the review-only behavior
unchanged; do not create a substitute local ledger, install memory, or persist
raw SQL.

## Write for the reader

- First lines: the decision (stabilize this plan, hold, roll back, or do
  nothing) and the expected effect. Evidence follows, then gaps.
- Commit to one control when the aligned evidence supports it. When it does
  not, say that plainly and name the observation that would decide.
- For every control you recommend: the risk of acting, the risk of not acting,
  and the rollback (the exact prior state).
- When the reader does not run the MCP (a client, a manager, an application
  team), keep tool names, skill names, profile names, internal field names,
  status codes, and intent identifiers out of the text; put them in closing
  operator notes. Translate:

| Internal term | Write this |
| --- | --- |
| prepared intent | a reviewed change that is not applied yet |
| `keep` | the change is measured better; leave it in place |
| `rollback` | the change is measured worse; restore the previous state |
| `hold` | not enough evidence yet; nothing changes |
| `unknown` | the current state could not be confirmed; stop and escalate |
| `ownership_review` | the engine or another owner already controls this plan; a person must choose one owner |
| kill switch | the global stop on plan changes |
| `enforcer-review`, `enforcer-apply` | review-only setup, change-enabled setup |

## Durable lifecycle

`observed -> reviewed -> prepared -> applied -> observing -> kept`, or `observing -> rolled_back`.

`observing -> hold` is required when evidence is insufficient. `unknown` is reserved for state that cannot be reconciled. Review-only ownership and rejected candidates do not advance to prepared.

Only MCP transitions mutation state. Generated prose or SQL is not an applied action.

## 1. Scan and review

1. After the gate, confirm the profile, Query Store state, database policy, server policy, kill switch, and Automatic Tuning ownership.
2. Collect regressions, top consumers, parameter buckets, plan history, forced/hint state, force failures, and ownership. `plan_enforcer_tick` is only a preview and ranking aid.
3. Reject identity-ambiguous, truncated, stale, cross-window, or ownership-unknown candidates from apply.

Rank by proven impact, recurrence, evidence quality, and reversibility. Route one-query rewrite or sandbox index experiments to `sql-optimizer` by performance case id; route portfolio-wide index inventory, overlap, consolidation, and removal review to `sql-index-manager` with returned portfolio context.

## 2. Build a reviewed intent

Before preparation, have: the stable query identity; the observed target plan or the validated hint; the action and its reason; the reviewed baseline evidence window; the reviewer; and a unique idempotency key. The MCP captures the exact prior force/hint state and the evidence hash itself.

Do not synthesize rollback as the opposite action. Exact prior state is the rollback source of truth.

## 3. Prepare

Call `prepare_plan_action`. Fail closed unless reviewed evidence, stable identities, exact prior force/hint state, ownership is explicitly manual, idempotency key, and a supported observed target all pass. Preparation reports server-policy, database-policy, profile, and global kill switch gate status; those mutation gates may remain closed during review but must all pass before apply. It does not mutate Query Store.

Read the result before any talk of apply:

- **`force_precheck`** (for a plan force): `status` is `block`, `warn`, or `pass`. A blocker rejects the intent, so nothing is prepared: `parameter_sensitive_query` (one forced plan is wrong for part of the values; recommend a Query Store hint or a statement fix instead), `plan_belongs_to_another_query`, `plan_not_run_recently` (not run for four days), `target_plan_not_found`, or `precheck_unavailable` (prepare again). Never retry a blocked force with another plan id to get past it. A warning does not reject: `psp_variant` (review the parent query first), `option_recompile`, `temp_table_in_plan`, `query_store_read_only`, `prior_force_failures`. Report every warning to the human before any apply.
- **`guardrails`**: one force or hint action per query per day, three per database per day, and a week after two failed actions on a query. When `allowed` is false, report `blocked_by` and `retry_after_utc` and wait; never work around a guardrail with another intent or query id. Unforce, clear hints, and rollback are never delayed.

Preparation returns intent id, immutable action summary, exact-prior-state reference, policy decision, and expiry. A prepared intent expires after 24 hours (`expires_at_utc` in the prepare result); apply holds an expired intent with `apply_confirmation=intent_expired`, so prepare it again.

## 4. Apply prepared action

Call `apply_prepared_plan_action` only when the user explicitly authorizes that exact intent in the current interaction and a local stdio `enforcer-apply` server is active with unrestricted/apply posture, `AZURE_SQL_TOOL_GROUPS=core,performance,admin`, database-policy permission, and the kill switch open.

MCP rechecks evidence hash, idempotency, expiry, the global kill switch, server/database policy, ownership, and the prior-state precondition immediately before mutation. Changed preconditions return hold/review; do not replace silently.

Repeated calls with the same idempotency key must return the same result and must not apply twice.

**Production needs a person's token.** On production, which includes any environment label the server does not recognise as non-production, the prepare result holds `confirmation.confirmation_token`: single-use, bound to this intent, and it expires after 15 minutes. Show it to the human who approves the change. Tell the human exactly what to pass: the intent id, the token, and their authorization reference. Apply only after they send the token back in a later message, and pass it as `confirmation_token`. Never invent, guess, alter, or reuse a token, and never pass back a token in the same turn in which you showed it. If the token is refused or has expired, prepare the intent again; never try another value.

Read the apply result:

- `guardrail` with `confirmed` false: a guardrail blocked the action; nothing was read or changed and the intent stays prepared. Report it and wait.
- `apply_failed`: the engine refused the action and the control state is unchanged, so the intent is back at prepared. Report the reason, fix the cause, and apply again. It is not the `unknown` state.

## 5. Observe and verify

Call `verify_plan_action` after the defined observation window. The MCP collects the post-apply evidence itself from Query Store: runtime stats since `applied_at`, per plan, the forced plan's share of executions, and `force_failure_count`. `candidate_evidence` is optional context only; it can turn a keep into a hold but never produces a keep. Query Store cannot supply parameter buckets, so the result reports `parameter_buckets=unavailable` and `max_duration` screens the tail. Without buckets, the result is hold, not keep, when the baseline window ran more than one plan or when the forced plan did not run in the baseline window (`post_plans_without_baseline`): verify each parameter bucket with `get_query_parameter_buckets` or a benchmark with representative parameters.

- Pre and post windows must not overlap.
- Query/database identity, provenance, and workload class must match; parameter buckets must match only where evidence carries them (Query Store does not).
- Meet minimum executions and compare median/spread, not one interval.
- Check objective and guardrails across all required buckets.
- Confirm expected force/hint state and detect ownership change.

Decision:

- `keep`: sufficient aligned evidence proves improvement without material guarded regression.
- `rollback`: sufficient aligned evidence proves regression, invalid behavior, or guardrail violation.
- `hold`: evidence is insufficient, noisy, mismatched, under-sampled, or ownership changed.

Insufficient evidence never means keep.

## 6. Roll back exactly

Call `rollback_plan_action` with the durable intent id. MCP restores the exact pre-change state captured during preparation: prior forced plan, target-plan force state, complete prior hint state, and ownership/reconciliation metadata.

On a production database rollback takes two calls: the first call, without a token, changes nothing and returns a rollback token; show it to the human, then call again with `confirmation_token` under the same token rule as apply.

Verify restoration field for field where exposed. If unconfirmed, mark `unknown`, stop applies for that query/database, and escalate.

## Automatic Tuning ownership

Engine-owned recommendations, automatic last-good-plan actions, and unknown ownership are `ownership_review`: report them, do not prepare or apply an overlapping custom control, do not clear/replace/unforce them, and ask the human to select one owner.

## Failure behavior

- Missing evidence, policy, identity, prior state, authorization, or ownership: reject/hold; no mutation.
- Apply timeout or uncertain response: reconcile through MCP; never retry blindly.
- Verification timeout or low traffic: hold; do not keep by default.
- Regression: restore exact prior state and verify.
- Kill switch: stop new applies; continue read-only reconciliation and authorized safety rollback only as policy permits.
- Every different action needs its own review and prepared intent.
- Blocked (the same tool call fails the same way twice, a required precondition cannot be met, or this skill's text contradicts what a tool returns): call `report_stuck` once with `skill`, `skill_version` (this file's `metadata.version`), `last_tool`, `blocker_kind` (one of the tool's enum values), and a one-sentence summary with no SQL, data values, or object, server, or database names. If `report_stuck` is not in the tool list, skip it silently. Then stop retrying that exact call, tell the user what is blocked, and give them the returned `incident_id`. Exceptions: a tool error whose `failure_diagnostic.transient` is true (for example 40613, 40501, 49918) gets its normal retry first; `diagnostic_code` `verification_failed` means a write was sent and its outcome is unknown, so read the intent and object state first and never resubmit that apply or rollback.

## Required output

Open with the decision and its expected effect, then:

1. **Mode and policy** — profile, kill switch, server/database policy, ownership, authorization.
2. **Reviewed candidates** — identities, windows/buckets, impact, confidence, lever, and rejection/ownership-review reasons.
3. **Prepared intent** — id, exact-prior-state reference, expiry, every precheck blocker and warning, the guardrail state, and confirmation that preparation made no change. On production: the token and exactly what the human must pass.
4. **Apply result** — only for an authorized prepared intent; durable state and reconciliation, never raw SQL.
5. **Verification** — keep/rollback/hold, aligned windows/buckets, medians/spread, guardrails, and gaps.
6. **Rollback/restoration** — exact restoration result and unresolved unknown state.
7. **Handoffs** — as routed in section 1; ownership and policy decisions to the human.

If no candidate is eligible, apply nothing. Review mode must never imply execution.
