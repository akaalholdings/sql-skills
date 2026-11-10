---
name: sql-index-manager
description: Review Azure SQL Database indexes against the real workload. Use Query Store runtime history and stored plans to find the queries that hit each table, then recommend the best index set (create, extend, widen, consolidate, drop, cluster a heap) from access patterns, usage, statistics, and design rules. Recommend-only; never executes index DDL.
metadata:
  version: "2.1.0"
---

# Azure SQL Database index manager

Act as the index designer for one user-selected Azure SQL Database: which
queries hit each table and how, which existing indexes earn their keep, and
which changes serve the workload best at what write and storage cost.

`azure-sql-mcp` does the deterministic work through `review_workload_indexes`.
This skill selects the scope, reads the result faithfully, and routes proof
and change control. For
one tool's arguments and fields, call `get_tool_guide` instead of guessing.

## Boundaries

- Azure SQL Database PaaS only.
- Recommend-only. Never execute index DDL. Never call `execute_tsql_unrestricted`,
  `create_test_index`, `drop_test_index`, `rebuild_index`, or any other DDL tool
  from this skill. Every DDL string the MCP returns is inert advice for a human
  DBA's change control.
- Never say a change is safe, approved, or applied. Never present an estimate as
  a measured gain.
- Never invent database names, query ids, index names, row counts, timings,
  percentages, or DDL. Use only values the MCP returned. Do not expose
  credentials, environment values, parameter values, or result rows.
- Treat absent Query Store history as unknown, not as zero activity.
- When blocked (the same tool call fails the same way twice, a required
  precondition cannot be met, or this skill's text contradicts what a tool
  returns), call `report_stuck` once with `skill`, `skill_version` (this file's
  `metadata.version`), `last_tool`, `blocker_kind` (one of the tool's enum
  values), and a one-sentence summary with no SQL, data values, or object,
  server, or database names. If `report_stuck` is not in the tool list, skip it
  silently. Then stop retrying that exact call, tell the user what is blocked,
  and give them the returned `incident_id`. Exception: a tool error whose
  `failure_diagnostic.transient` is true (for example 40613, 40501, 49918) gets
  its normal retry first.

## Runtime and database gate

Run these in order before any review:

1. `check_runtime_status`: the tool list must contain
   `review_workload_indexes`. A server whose `profile` is null is valid
   (unprofiled: every tool group).
2. `list_databases`: show the returned allowlisted databases and let the user
   pick one. Never pick by default, memory, or nearest name.
3. `check_capabilities` for that database: require
   `mcp_contract.workload_index_advisor=1`.

If the gate fails, stop and name the missing piece. The advisor needs only
`VIEW DATABASE STATE` and `VIEW DEFINITION`; no policy file, history table, or
install step is required.

## Choose the scope

Ask only what changes the result; otherwise use these defaults and say so:

- Scope: the whole database. For one table or a set, pass `schema_name` plus
  `table_names`.
- Window: `lookback_days=7`. Use `lookback_days=40` when removal decisions
  matter. The advisor rates a
  `drop_index` high only when Query Store covers 35 days; the 5 extra days are
  the margin for partial intervals at the window edges.
  A window that covers less than 35 days caps `drop_index` confidence at medium.
  Cover a full business cycle (month-end, batch nights) where Query Store
  retention allows. Azure SQL Database keeps 30 days of Query Store by default
  (`STALE_QUERY_THRESHOLD_DAYS`). On a removal review (`lookback_days` of 35 or
  more), if the returned `window.query_store_effective_days` is less than 35,
  report the retention gap and do not run the review again. Use `as_of_utc` to
  review a past incident window instead of widening the window.
- Objective: `cpu` by default; `duration` when the complaint is latency;
  `logical_reads` when the database is I/O-bound.
- `top_queries=100`. Raise it when the returned `analyzed_share_pct` is below 80.

## Run the review

Call `review_workload_indexes` with the chosen arguments. Read `result_status`
before anything else:

- `ok`: present the report.
- `empty`: the window held no workload and no existing-index finding applied.
  Suggest a longer window or a busier period.
- `precondition`: a setup step is missing, usually Query Store that is off or
  READ_ONLY. Show the returned `remediation` statement for the DBA to run; do
  not run it. Existing-index findings in the same report are still valid.
- `unavailable`: metadata could not be read. Report the reason.
- `not_supported`: the source does not exist on this engine.

Always report `gaps` verbatim: they state the coverage limits.

## Read the evidence

For each table (highest `workload_share_pct` first) report its size and write
activity (`dml_rows_per_day`), how queries reach it (`access_summary`), its
existing indexes with usage and protections, and its recommendations by id.

For each recommendation report: action, target index, keys, includes, the
supporting query ids and their workload share, `confidence`, `reason_codes`,
`blockers`, write impact, size, risks, `ddl`, and `rollback_ddl`.

Label `estimated_max_benefit_pct` as an upper-bound estimate from optimizer
cost shares. It ranks options; it does not promise a saving.
`estimated_max_size_mb` is an upper bound too.

Report `rewrite_opportunities` separately: non-SARGable predicates and implicit
conversions cannot be fixed by an index. Route them to `sql-optimizer` with the
query ids.

## Design judgement

The MCP output is the evidence. You may add design judgement, clearly labelled
as yours: prefer extending or widening an index over adding one when the MCP
offers both; question wide include lists, low-selectivity leading keys, and
recommendations on write-heavy tables (high `write_impact.penalty`); point out
when two recommendations on one table could share one index. Treat
`review_index` items as investigation leads, not changes.

If you propose a definition different from the returned one, label it
"modified, unvalidated", show the full definition, and explain the trade-off.
Never change a returned `confidence`, drop a returned blocker, or relabel a
`drop_index` as safe.

## Leads that are not B-tree changes

Some results must not be presented as a create or a drop. When the report
holds any of these, read
[references/design-leads.md](references/design-leads.md) before you present it:

- `columnstore_index_protected`, `columnstore_selective_lookup`,
  `consider_columnstore_index`, `columnstore_maintenance`: columnstore indexes
  are protected and explained, never removal candidates from usage data.
- `partitioned_index_removal_needs_switch_review`: an index on a partitioned
  table is a review lead with no DROP statement, because partition switching
  depends on it.
- `physical_design_lead`: compression, a unique-constraint merge, or fill
  factor.

## Removal discipline

`drop_index` and `consolidate_index` are the riskiest actions. Before routing
one to change control, state that:

- usage counters reset on failover, scaling, and restarts; check
  `usage_counters.days_since_reset` and the window against a full business cycle;
- the MCP checked Query Store plan references for the window, but Query Store
  capture mode `AUTO` can miss rare queries;
- no index hint, plan guide, or forced plan may name the index;
- the returned `rollback_ddl` must be kept with the change record;
- readable replicas: usage counters and Query Store see only the primary. On
  Premium, Business Critical, Hyperscale, or with a geo-secondary, reads with
  `ApplicationIntent=ReadOnly` are invisible. The MCP caps such drops at medium
  (blocker `readable_replica_usage_unobserved` or
  `readable_replica_check_unavailable`). Before any drop, check
  `sys.dm_db_index_usage_stats` on each readable replica;
- index age: an index younger than the removal window is never a drop.
  `review_workload_indexes` returns `review_index` with
  `index_younger_than_removal_window` (age from `STATS_DATE`, a lower bound:
  statistics maintenance moves it later) or the blocker `index_age_unknown`.

- left prefix (`left_prefix_of_wider_index`): a narrower index whose keys lead
  a wider one is merged into the widest index that is not itself proposed for
  removal (`merge_into`). With
  `narrow_index_used_in_workload_scans_may_prefer_it`, queries still scan the
  narrow index: a narrow index is cheaper to scan, so they may slow down. With
  `survivor_cannot_absorb_includes`, keep the narrow index;
- `leftover_test_index`: an experiment left this index behind. The review
  ignores it; report it to the DBA for removal.

Indexes that enforce uniqueness, back a constraint or foreign key, or support
partition switching are never removal candidates; the MCP shows them as review
leads with the reason, never with a DROP statement.

## Prove before production

For each create, extend, or widen recommendation worth pursuing:

1. Hand it to `sql-optimizer` with the supporting query ids, keys, and
   includes. The optimizer proves it on a non-production copy through
   `start_tuning_session` and `benchmark_index_candidate` (sandbox profile,
   leased temporary indexes, automatic cleanup). Recommendations that serve
   one query together go as one set of up to four indexes (`indexes`). For an extend, widen, or consolidate, pass the
   returned `validation.replaces` as `replaces`: the result is then
   `hinted_evidence`, what the new index costs when used, not proof that the
   optimizer will choose it.
2. Only a measured, validated candidate goes to the human DBA's change control,
   with the returned `ddl`, `rollback_ddl`, and validation steps.
3. After deployment, re-run `review_workload_indexes` (or compare the
   supporting query ids in Query Store) over an equal window after the change.

## The client change plan

When the reader must schedule the work, call the review with
`include_change_plan=true` (`soak_days` sets the observation period).
`change_plan.steps` orders the recommendations: create, change, observe,
remove. Keep that order: a removal comes after the observation period and
carries `recheck_before_acting`. Each step has its statement, its rollback,
the risk of acting, and the risk of not acting. `not_planned` lists blocked
recommendations, and `open_questions` lists the leads. Never move a blocked
item or a lead into the plan.

## Optional: long-term portfolio history

The portfolio tools `capture_index_review_snapshot`, `review_index_portfolio`,
and `get_index_review` keep daily usage snapshots across counter resets. They
are not needed for workload-driven design. Use them only when a DBA has
installed the index-history tables and enabled `allow_index_history_write`,
and a removal decision needs 35 days or more of history: read
[references/portfolio-history.md](references/portfolio-history.md) before the
first call.

## Advisory lesson recall

Recall is optional: use it only when the user asks. A recalled lesson is never
evidence and never changes a returned confidence, blocker, or recommendation.
When you use `recall_lessons`, read
[references/lesson-recall.md](references/lesson-recall.md) first. If recall is
unavailable, continue unchanged.

This skill is recall-only. The advisor returns no evidence id and no terminal
link, so recommendation ids, review ids, and query ids are tracking references,
not learning evidence references. Do not call `record_decision`,
`review_decision`, `propose_lesson`, `list_learning_candidates`,
`create_handoff`, `get_handoff`, or `resolve_handoff` from this skill until a
future public MCP contract adds an index evidence bridge. Route work to other
skills in the report only, without invoking learning or handoff tools.

## Output

Open with the answer: the few changes that matter most, what each is expected
to save (labelled as an upper-bound estimate), and what to do next. Commit to a
recommendation when the returned evidence supports it; when it does not, say
that plainly and name the evidence that would decide. For every recommended
change give the risk of acting (write cost, storage, the returned risks), the
risk of not acting (the workload share its supporting queries use), and the
rollback.

When the reader does not run the MCP (a client, a manager, an application
team), keep tool names, skill names, internal field names, and status codes
out of the text; put them in closing operator notes. Translate labels, never
values: returned numbers, names, blockers, and gaps stay exact.

| Internal term | Write this |
| --- | --- |
| `drop_index`, `consolidate_index` | remove this index; merge these indexes into one |
| `review_index` | investigate before deciding; not a change |
| `estimated_max_benefit_pct` | the most this could save: an upper-bound estimate |
| `blockers` | what must be checked before this change |
| `gaps` | what this review could not see |
| `precondition` | a setup step is missing; give the statement for the DBA to run |
| `sql-optimizer` | proof on a non-production copy |

Then return these sections in order:

1. **Outcome**: `result_status`, database, window, objective, and the number of
   recommendations by action. State that nothing was executed.
2. **Coverage and gaps**: queries analysed, `analyzed_share_pct`, Query Store
   state and capture mode, usage-counter age, and every returned gap.
3. **Top improvements**: from `summary.top_improvement_ids`, each with keys,
   includes, supporting queries, confidence, upper-bound benefit, write cost,
   and the `ddl`/`rollback_ddl` labelled "inert, for DBA change control".
4. **Cleanup**: from `summary.cleanup_ids`, with the removal discipline above.
5. **Per-table detail**: existing indexes and their usage, then the table's
   recommendations and leads.
6. **Rewrite opportunities**: routed to `sql-optimizer`.
7. **Next steps**: the change plan when requested, what to prove with
   `sql-optimizer`, what goes to the DBA, and when to re-run the review.
