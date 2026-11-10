# Cardinality, parameters and statistics

Detail for `SKILL.md`. Its hard rules apply here; nothing in this file relaxes them.

Each card is actionable only when its semantic preconditions hold. Record the listed MCP evidence before calling a measured result proven.

## Family 4: cardinality, parameters, and statistics

- **Trigger:** estimated and actual rows diverge materially, a seek/lookup choice varies by value, statistics are stale, or common and rare values behave differently.
- **Safe rewrite/action:** correct parameter/literal types, make predicates estimable, refresh or create statistics only through an approved change path, and isolate a proven skew-sensitive branch.
- **Preconditions:** statistics/object metadata and parameter values are real, freshness is known, and one execution is not treated as a distribution.
- **Counterexample/risk:** `OPTIMIZE FOR UNKNOWN` can harm both common and rare values; a statistics update has write/concurrency cost; parameter “sniffing” is not proven from one plan.
- **MCP evidence:** Query Store history, statistics metadata, estimated/actual rows by operator, parameter buckets, plan fingerprints, resource pressure, and `compare_plan_summaries`.

### Parameter compilation and intelligent query processing

- **Trigger:** parameter-sensitive plans, optional-parameter optimization, memory-grant feedback, cardinality feedback, or plan variants appear in evidence.
- **Safe rewrite/action:** first make the predicate and parameter contract compatible with the feature; preserve a feature-compatible query, or test explicit branches only when the feature is absent/insufficient.
- **Preconditions:** database compatibility level, feature state, Query Store history, parameter distribution, and variant behavior are confirmed.
- **Counterexample/risk:** disabling a feedback feature or adding a hint can remove useful variants; a variant seen in one window may not represent current workload.
- **MCP evidence:** Query Store plan variants, compatibility/configuration evidence, parameter-sensitivity tools, memory-grant/row feedback, and non-overlapping bucket measurements.

Execute supplied parameters through typed `sp_executesql`, not local `DECLARE` variables, because local-variable compilation can change estimates and hide parameter sensitivity. Every parameter case carries one exact value and declared SQL type for every query parameter.

Test the plan cache, not only each value. `benchmark_tuning_candidate` with `cross_case={"compile_case": A, "run_case": B}` compiles the plan with case A and measures case B on it. Run it in both directions when two cases differ in selectivity; a candidate that regresses there is rejected. A `sniffed_parameter_differs` finding on an equality seek of a whole unique key is noise: that seek returns one row for any value.

A regressed case is final. `decision.by_metric` gives the verdict of every case on CPU, elapsed time, and logical reads from the same runs: read all three, not only the objective. A case that is worse than the original on CPU or logical reads, beyond noise, rejects the design as it is, also when the other cases are far faster. Add a branch that keeps the original statement for that case's parameter class (an index or view benchmark reports such a case as `unchanged_by_design`), or pick another design. Never explain a regression away, for example as an undercount in the original: a reviewer counts what was measured.

Do not prescribe `OPTION (RECOMPILE)`, `OPTIMIZE FOR`, `OPTIMIZE FOR UNKNOWN`, a Query Store hint, or forced parameterization by reflex:

- recompilation spends CPU and removes plan reuse; it can be appropriate only when execution savings dominate compile cost, so state both numbers: compile CPU per call times calls per second, against the saving per execution;
- a hint fits the values it was tuned on. Deliver `OPTION (RECOMPILE)`, `OPTIMIZE FOR`, or a join hint only as an alternative, and only with the measured numbers of the parameter pair it makes worse. When one value class is skewed, a branch per class is the lead; do not suggest `OPTIMIZE FOR UNKNOWN` for a catch-all predicate: measured, it picked the worse index. Two exceptions may be part of the lead, when every case was measured with the hint and none regressed: `OPTIMIZE FOR` on a key that the statement resolves itself (joins reference), and the finishing forms below;
- when the SQL cannot change or cannot be redeployed quickly, give the exact Query Store hint text as a no-redeploy fallback and route it to `sql-plan-enforcer`; do not set it from this skill;
- Query Store hints and forcing belong to `sql-plan-enforcer`, not this skill; workload-wide index review, overlap, consolidation, and removal belong to `sql-index-manager`, not this skill;
- Parameter Sensitive Plan optimization, Optional Parameter Plan Optimization, memory-grant feedback, cardinality feedback, batch mode, deferred compilation, and UDF inlining depend on compatibility level, database-scoped configuration, query shape, and observed runtime state.

Use `check_capabilities`, database configuration, Query Store variants, and actual plan evidence before crediting or disabling an intelligent-query-processing feature. A compatibility-level change affects the whole database and is never a single-query tuning experiment.

For Azure SQL Database, interpret the capability envelope with these concrete gates:

- compatibility level 140 enables the applicable adaptive-join, batch-mode memory-grant-feedback, and interleaved-execution families when their database-scoped configurations and query shapes also qualify;
- compatibility level 150 enables the applicable row-mode memory-grant feedback, batch mode on rowstore, table-variable deferred compilation, and scalar UDF inlining families;
- compatibility level 160 enables Parameter Sensitive Plan optimization and cardinality-estimation feedback when configured; persistent feedback features also require Query Store in `READ_WRITE`;
- compatibility level 170 enables Optional Parameter Plan Optimization for eligible optional predicates when its database-scoped configuration is on;
- DOP feedback is capability- and Query-Store-dependent and can remain off even at a qualifying compatibility level.

An applicable or enabled feature is not proof that this query used it. Require an observed dispatcher/variant, feedback state, plan shape, or Query Store evidence before attributing an improvement. If `check_capabilities` cannot verify Azure SQL Database PaaS, compatibility level, configuration, or Query Store state, mark the feature conclusion inconclusive.

## Plan-level finishing

After the design is chosen and measured, test each of these once, as a variant of the finalist. Each is measured on every case, never assumed, and the answer shows the hint or the batch in full.

- **Serial plan.** For a statement that already runs in under a second, test `OPTION (MAXDOP 1)`: a parallel plan can cost more CPU than it saves. Keep it only when CPU falls and no case regresses. The tools class `MAXDOP` as a plan-forcing hint: the numbers stand, and finalize lists `hinted_candidate` in `deployment_blockers`. Say that the hint is part of the measured statement.
- **Bounds computed once.** A bound that the statement derives for each table (the first and last key of a period): set it once in a variable in front of the statement, `DECLARE @FirstKey int = (SELECT MIN(...) ...)`, and filter each large table on the variables. The variables are not sniffed: check the estimates, and add `OPTIMIZE FOR` a typical period when they are wrong.
- **Probe before a parameter-sensitive join.** When the parameter decides the row count, a `TOP (n + 1)` probe counts the qualifying rows up to the limit, and an IF chooses the branch: nested loops up to n rows, a hash join above. Register a case on each side of the limit.

The proof tools take a variable set from a scalar subquery in front of one SELECT. When they refuse it in front of IF / ELSE, measure the probe batch under "Always finish" in `SKILL.md`, or give it as an alternative labelled not measured.
