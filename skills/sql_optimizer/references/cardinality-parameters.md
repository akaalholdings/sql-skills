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

Do not prescribe `OPTION (RECOMPILE)`, `OPTIMIZE FOR`, `OPTIMIZE FOR UNKNOWN`, a Query Store hint, or forced parameterization by reflex:

- recompilation spends CPU and removes plan reuse; it can be appropriate only when execution savings dominate compile cost, so state both numbers: compile CPU per call times calls per second, against the saving per execution;
- a hint fits the values it was tuned on. Deliver `OPTION (RECOMPILE)`, `OPTIMIZE FOR`, or a join hint only as an alternative, and only with the measured numbers of the parameter pair it makes worse. When one value class is skewed, a branch per class is the lead; do not suggest `OPTIMIZE FOR UNKNOWN` for a catch-all predicate: measured, it picked the worse index;
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
