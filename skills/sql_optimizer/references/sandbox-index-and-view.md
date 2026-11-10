# Test indexes, test indexed views, and view changes

Detail for `SKILL.md`. Its hard rules apply here; nothing in this file relaxes them.

## Test index

`benchmark_index_candidate` creates the index set under a lease, measures the query before, with, and after it, and drops every index on every path. `get_tool_guide("index_set_experiment")` has the argument notes.

Before the call, read `check_capabilities.local_tuning_policy`: `allow_benchmark` and `allow_test_indexes` must be true and `environment` must be a non-production label. The tool also needs the server to run the sandbox profile; on any other server, including an unprofiled one, it refuses. A refusal is handled by "Always finish" in `SKILL.md`: report it, then use the engagement's own permitted path if one exists.

- **Candidate.** Register it with `add_tuning_candidate`, `strategy=index`, and the unchanged case SQL. Design keys and includes from the plan (indexes reference), not from a missing-index hint.
- **One index or a set.** Pass `schema_name`, `table_name`, and `key_columns` for one index, or `indexes=[{table_name, key_columns, include_columns, filter_definition, is_unique, data_compression}, ...]` for 1 to 4 indexes, also on different tables. When the plan needs two indexes together, the set is the candidate: do not test them one at a time.
- **Columnstore.** An `indexes` entry with `kind: "nonclustered_columnstore"` builds a nonclustered columnstore test index; `key_columns` lists its columns, with no `include_columns`. The single-index form names the field `index_kind`.
- **Rewrite with its indexes.** Register the rewrite with `strategy=rewrite_plus_index` and no `artifact_ref`, keep `sql` as the original, and pass the rewrite as `candidate_sql`: one call measures the original without the indexes against the rewrite with them, and compares the results while the indexes exist.
- **Cases.** Pass every registered case in `parameter_cases`, in one call. A finalist needs all of them. `plan_reuse="first_case"` runs all cases on the plan that the first case compiled, in the order given: a shared-plan run, as a plan cache does, not a pairwise cross-case test.
- **Names.** The tool generates each name. `index_name_prefix` is optional and never refused: any text is accepted.
- **Compression.** `data_compression` is `NONE`, `ROW`, or `PAGE`. Pass `PAGE` for a new read-path index on a large table. One build: no second variant to compare ROW with PAGE, unless evidence shows a write-heavy table or the user asks.
- **Table with a clustered columnstore index.** The engine refuses an online index build only there. The tool then builds offline when the policy shows `allow_offline_test_index` true; writes to the table wait during the build, and `offline_build` in the result says so. A table with only a nonclustered columnstore index builds online.
- **Partitioned table.** `partition_aligned` is true by default: one B-tree per partition. False builds the index ON [PRIMARY] on a partitioned rowstore table: one ordered B-tree, which blocks partition SWITCH (`non_aligned_index_warning`).
- **Several variants.** `keep_for_session=true` leaves the built indexes or view in place for later calls of the session; `finalize_tuning_session` drops them.
- **Replacing an index.** `replaces` names the existing index that a one-index candidate would replace. The candidate arm is hinted, so the result is `hinted_evidence`: what the new index costs when used, never proof that the optimizer will choose it, and never deployment-ready.
- **Result.** Read `decision`, then `indexes` (`built`, `size_mb`, `index_depth`, `used_in_cases`) and `unused_indexes`. An index that no measured case used is not evidence: a faster run that ignored the index says nothing about it. Leave an unused index out of the recommendation and say that the smaller set was not measured alone.
- **Cleanup.** `lease.status` `cleanup_required`, or a refusal with `leftover_test_index` or `expired_index_cleanup_required`, means a test index may still exist. Give the user the returned rollback DDL, start no further test index in that database, and say so in the answer.
- **Scope of the proof.** With unchanged SQL the comparison shows stable results before, with, and after the index, not a rewrite proof. One query never justifies a production index alone: state the write cost and the size.

## Test indexed view

`benchmark_indexed_view_candidate` builds a leased test view `WITH SCHEMABINDING` and its unique clustered index, runs the candidate that reads the view `WITH (NOEXPAND)`, compares its results with the original, and drops the view on every path. `get_tool_guide("indexed_view_experiment")` has the detail.

1. **Gate.** `check_capabilities` must show `indexed_view_experiment.allowed` true; otherwise report its `blockers`. The first index of a view is built offline: writes to the base tables wait during the build.
2. **Preview.** Call the tool with `preview` true and `view_definition` (the SELECT body). It runs nothing and returns the view name, the findings, and the setup statements. View rules: two-part object names; `COUNT_BIG(*)` when the view aggregates, with or without `GROUP BY`; `SUM` over a nullable column must be `SUM(ISNULL(col, 0))`, and a NOT NULL column stays bare; `COUNT_BIG(col)` is accepted only beside `COUNT_BIG(*)`; no outer join, subquery, `DISTINCT`, `MIN`, `MAX`, `AVG`, or `UNION`.
3. **Candidate.** `add_tuning_candidate` with `strategy=rewrite_plus_index`, no `artifact_ref`, and the statement that reads the view `WITH (NOEXPAND)`. Convert the count back to the original type and compute an average from the sum and the count. A group with no rows is absent from the view: keep the original result for it.
4. **Measure once.** Call the tool with `sql` (the original), `candidate_sql`, `view_definition`, `view_name`, `clustered_index_key`, and `phase=finalist`. Read `decision`, `view.setup_statements` and `view.teardown_statements` (the exact DDL for the report), and `lease.status`.
5. **State the costs with the result.** Quote `view.write_overhead_warning` and `view.base_table_restrictions`. Every insert, update, and delete on a base table also maintains the view. While the view exists, `TRUNCATE TABLE`, `ALTER COLUMN`, and partition `SWITCH` on its base tables fail. Sessions that write to the base tables need the SET options that indexed views require, or their writes fail.
6. **When it is the wrong design.** A fact table loaded by partition switch or by truncate-and-load: an indexed view is wrong unless the load is changed. Say so in the recommendation and give the covering index or the columnstore index. Write-heavy base tables, or a definition that changes often: lead with the covering index. In every case give the covering index as the alternative. A view that is correct only under a data property with no constraint needs a declared precondition.

## View change

A view change affects every caller of the view. Rewrite the consumer query first. Only when the definition of an existing view is itself the candidate:

1. `prepare_view_change` is a read-only preview on any profile. It needs `mcp_contract.durable_view_change=1`.
2. Apply needs the sandbox profile, a non-production policy with `allow_view_apply=true`, and the server setting `AZURE_SQL_PERSIST_VIEW_SQL_STATE=true`. Prepare again in that sandbox process, review the returned dependencies, prior definition, apply SQL, and rollback SQL, then call `apply_prepared_view_change` and `verify_view_change`.
3. Call `rollback_view_change` immediately after validation and confirm the exact prior definition. If rollback cannot be confirmed, report `cleanup_required` with the change id and stop all sandbox changes.

A change to an existing view has no benchmark: it is a legality, dependency, and rollback exercise: do not register it as a measured candidate, and report its performance and equivalence as `not collected`. It stays recommendation-only. A tool error with `diagnostic_code` `verification_failed` means a write was sent and its outcome is unknown: read the change and the object state first, and never resubmit that apply or rollback.
