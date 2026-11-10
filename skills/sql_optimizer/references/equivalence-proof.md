# Equivalence proof with the MCP

Detail for `SKILL.md`. Its hard rules apply here; nothing in this file relaxes them.

## Rewrite comparison

`benchmark_tuning_candidate` finalists and `compare_query_results` run baseline and candidate in one snapshot-consistent comparison: complete results within `AZURE_SQL_COMPARISON_ROW_LIMIT`, the same shape and types, values, NULLs, and duplicate multiplicity. Omit `compare_order`: the MCP resolves it from the outer ORDER BY, and an outer ORDER BY is always order-compared; without one it compares duplicate-aware multisets, never sets. `compare_query_results` takes `parameter_case`, or the short form `parameter_values` with `parameter_types`, the same spellings as `explain_query`; never pass both. It also takes up to 4 `parameter_cases` in one call. `max_seconds` caps the comparison (default 120): a capped run returns `timed_out` with the arm that was running. Pass `estimated_seconds` when you know the statement time; a comparison that cannot fit is not started.

- A rewrite that drops or changes the baseline outer ORDER BY keys gets the risk `order_contract_changed` and is capped at `performance_only`. A new alias or a derived table that carries the same columns is not a change.
- `order_only_mismatch` means the same rows in a different order: inconclusive, not a semantic change.
- Screening defers the comparison, so an unproven screen cannot win. Any rewrite mismatch is `equivalence_failed` and cannot win.
- Every comparison carries `ordered_rows_match`, `multiset_match`, `tested_match`, and `caveats`. A `tested_match` on the measured cases is enough to recommend a design when the report states the scope (tested on the listed cases, not proven for all inputs) and each caveat. Never discard a faster measured design because its scope is a snapshot test and not a proof; say which scope it has.
- `not_compared` means that the results are unstable by construction (a clock, a row-volatile function, `TABLESAMPLE`, an unordered row limit, an isolation hint) or that the run stopped: say which.
- `proof_scope` says what the equality rests on. A match on the tested cases alone is a test result; `deployment_ready` also needs the `logical_preconditions` that `finalize_tuning_session` verified in the catalog.

## Row limits and total order

A query with `TOP` or `OFFSET/FETCH` is comparable only when its ORDER BY is a verified unique total order, backed by a constraint or unique index. The proof follows derived tables, CTEs, and set operations: a plain derived table or CTE is flattened to its base tables, a `UNION`, `INTERSECT`, `EXCEPT`, or `SELECT DISTINCT` is one source keyed by all of its columns, and a join back on the primary key carries the key across. So "page the keys, then join back" and "UNION of key seeks, then join back" are provable when the ORDER BY ends on the key.

When `check_equivalence_preflight` or a comparison still returns `classification=proof_contract_required` with `row_limit_total_order_unproven`:

1. Read `total_order_gaps`. Each entry names the tie (which rows can swap places) and the `tiebreaker` that removes it, with `tiebreaker_columns`.
2. Name that tie in the answer: the original can return tied rows in a different order on each run.
3. When the caller's contract allows it, append the tiebreaker to the ORDER BY of both forms and compare those: an exact deterministic recast. Report the original and the recast together, and never alter the measured SQL when the result says `performance_sql_must_remain_unchanged=true`. A recast can change the plan: when the baseline takes over 10 seconds, skip the recast and go to step 4.
4. Otherwise run `compare_query_results` on the tested cases. Under a gap that a comparison can settle (possible ties, a row limit with ties, a `UNION ALL` rewrite, a changed ORDER BY) it still runs and returns `proof_scope` `snapshot_test`: a test on today's data that lists what is not settled. Report it as tested, never as proven. Only when it cannot run, compare by hand and label that "compared by hand, not proven by the tool". The candidate stays `performance_only`.

The same gate applies to an order-sensitive window expression whose ORDER BY lacks a verified unique total order, and to a `UNION ALL` in a derived table, which can return the same row twice. A `UNION ALL` form therefore gets a `snapshot_test`, not a proof: do not retry it for a better verdict. When the proof matters, prove the `UNION` form and say which form was proven and which was tested.

## Preconditions the statement handles

Finalize no longer demands NOT NULL for a column that the statement itself tests for NULL. A precondition that the rewrite handles in its own text is listed in `handled_by_statement`. One that holds unless the statement handles NULL is listed in `conditional_preconditions`: it never blocks and never counts as verified, so the scope stays a snapshot match. Do not pass either as a `logical_preconditions` entry.

## Declared precondition

A design that is correct only under a data property with no constraint (a key is unique, validity ranges do not overlap and leave no gap) is not proven equivalent. It may be the recommendation when all of these hold:

1. The answer states the property as a declared precondition, in one sentence.
2. You verified it on the whole table with a query you ran through the MCP and show: a count of duplicates, overlaps, or gaps that returns zero. No sample and no `TOP`.
3. The answer labels it "verified on current data, not enforced", and says that the results are wrong if the property breaks.
4. The answer gives the constraint or unique index DDL that would enforce it. When no single constraint can express the property (ranges that must not overlap), give the nearest enforceable DDL and the check query to run after each load, and say which part stays unenforced.
5. The answer does not call the change deployment-ready until the catalog enforces the property.

Do not pass a declared precondition in `logical_preconditions`: the catalog check refutes it. Finalize without it; `deployment_ready` stays false, which is correct. A property that nobody verified stays under the strict rule: a rewrite that is correct only for today's data is not equivalent.

## Volatile queries

`GETDATE` or another current-time function, `NEWID`, unseeded or nondeterministically seeded `RAND`, and non-repeatable `TABLESAMPLE` also return `proof_contract_required`. A literal `RAND` seed is allowed. Keep a promising proof-required candidate in the performance workload; skip only the impossible comparison. Do not use `prove_equivalence=false` as a proof bypass. A performance-only finalist needs evidence-backed, nonzero executions and a measured improvement; report equivalence as `not proven` and deployment as `not ready`, and select it only through `finalize_tuning_session` with `selection_scope=performance_only`.

Preflight reads `STRING_SPLIT` and user table-valued functions in FROM, JOIN, or APPLY. A function body it cannot read is reported as an unresolved or encrypted dependency, and the proof is then incomplete.

## Index stability

An index benchmark runs unchanged SQL across A-B-A phases separated by DDL, so it cannot claim a same-snapshot rewrite proof. It requires stable, complete result fingerprints before, during, and after the index, plus proof that the candidate plan used the expected index. Data movement between phases makes the index result inconclusive.

Runtime speed, plan similarity, result counts, and any other proxy must never be used to overclaim semantic proof.

## Branching candidates and extra runs

- A case whose executed branch is the unchanged original comes back as `unchanged_by_design` with `executed_branch`. It is not a failure and does not need a separate comparison.
- A further run on a finalist (another parameter order, a shared plan): pass `measurement_only: true`. It can lower the verdict, never raise it.
