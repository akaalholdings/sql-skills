# Aggregation, windowing, ordering and row goals

Detail for `SKILL.md`. Its hard rules apply here; nothing in this file relaxes them.

Each card is actionable only when its semantic preconditions hold. Record the listed MCP evidence before calling a measured result proven.

## Family 3: aggregation, windowing, ordering, and row goals

- **Trigger:** repeated sorts/scans, late aggregation, `ROW_NUMBER`, `TOP`, `OFFSET/FETCH`, or a top-per-group pattern dominates the plan.
- **Safe rewrite/action:** aggregate before a one-to-many join when proven safe; use a partitioned window with an explicit tie rule; use keyset pagination only when the caller has a stable unique continuation key; remove redundant DISTINCT/grouping.
- **Preconditions:** grouping keys, window frame, ties, page boundary, total-count behavior, and output order are contractual and preserved.
- **Counterexample/risk:** `TOP (1)` without a unique order is nondeterministic; keyset pagination is not equivalent to arbitrary OFFSET; moving an aggregate across an outer join changes empty-group results.
- **MCP evidence:** actual row counts, sort/aggregate operators, memory grants, spill warnings, ordering metadata, per-bucket equivalence, and `compare_plan_summaries`.

For top-per-group work, make ties deterministic:

```sql
WITH RankedOrders AS
(
    SELECT
        o.CustomerId,
        o.OrderId,
        o.OrderDate,
        ROW_NUMBER() OVER
        (
            PARTITION BY o.CustomerId
            ORDER BY o.OrderDate DESC, o.OrderId DESC
        ) AS row_number
    FROM dbo.Orders AS o
)
SELECT
    CustomerId,
    OrderId,
    OrderDate
FROM RankedOrders
WHERE row_number = 1;
```

The unique tie-breaker is part of the result contract. Do not add it if the business rule intentionally returns all ties.

Choose the top-per-group shape by how much of the table each shape reads:

- A small driving set of groups (a parent table or a filtered key list) and an index on (group key, order key): lead with `CROSS APPLY (SELECT TOP (n) ... ORDER BY ...)` from the parent, one seek per group, and make the index part of the fix. Use `TOP (n) WITH TIES` when the contract returns every tied row.
- Most of the table is read anyway, or there is no parent to drive from: one pass with `ROW_NUMBER()`, or `RANK()` or `MAX(...) OVER (PARTITION BY ...)` when ties must stay.

For one aggregate per parent row over most parents, lead with one set-based pass: aggregate the child table once with `GROUP BY`, then join it back. Use `LEFT JOIN` when parents without children must stay, and keep the original result for them: NULL for `SUM`, 0 for `COUNT`, and the same result type. A correlated subquery or `APPLY` per parent repeats the child access for every parent and relies on the optimizer to decorrelate it. Keep the `APPLY` form only when few parents are read and an index supports each seek.

For deep `OFFSET` paging over wide rows, page a narrow key set first (the ordering index plus the key) in a derived table, join back on the primary key for the wide columns, and repeat the `ORDER BY` on the outer query. The total-order proof follows the derived table, so this rewrite is provable when the ORDER BY ends on the primary key. Test keyset continuation on the complete unique sort key; it is not a drop-in replacement for arbitrary page-number access. `DISTINCT` is not a generic join-fan-out repair: remove it only after proving uniqueness without it.

### Aggregates over a columnstore index

Inside an aggregate that a columnstore scan can compute itself, keep `SUM` and `COUNT` on the bare column. A `CONVERT` or other expression inside the aggregate stops aggregate pushdown: every row leaves the scan. Measured once on a 22 million row table: about 630 ms CPU with the conversion inside the `SUM`, 262 ms with it outside. Sum the narrow type per group and convert the group sums outside. That form raises an overflow error where the original did not, when one group's sum passes the limit of the narrow type: state that bound per group. Aggregate the fact by its keys before the dimension joins.

### Row goals, sorts, and spills

- **Trigger:** a row goal, large sort, memory-grant warning, tempdb spill, or parallel exchange is visible in the plan.
- **Safe rewrite/action:** make required order and tie-breakers explicit; narrow only contract-approved projections; align filtering and ordering keys; remove work only when the result contract permits it.
- **Preconditions:** no arbitrary TOP/ORDER BY is introduced, order semantics remain exact, and memory/resource changes are measured under representative concurrency.
- **Counterexample/risk:** a smaller first page can regress later pages; eliminating a sort can change order; a spill can be a shared memory-pressure symptom rather than a query-shape defect.
- **MCP evidence:** actual plan row goals, sort keys, spills, memory grants, worker/parallelism details, elapsed/CPU/logical reads, resource history, waits, and concurrent blocking.

### UDFs, APPLY, and intermediate work

- A scalar UDF can hide row-by-row CPU. Confirm whether scalar UDF inlining is supported, enabled, and actually used before rewriting it. Inline the logic manually only when exception, NULL, collation, data-access, and nondeterministic behavior remain identical.
- `CROSS APPLY` and `OUTER APPLY` are useful for correlated top-N or reusable expressions, but they do not guarantee one execution. Inspect actual executions and row counts on the inner side.
- A temporary table can improve cardinality between phases but adds writes, tempdb use, statistics, and compilation boundaries. Include all phases in the benchmark.
- Table variables, multi-statement table-valued functions, and opaque predicates can hide cardinality. Treat modern deferred compilation or interleaved execution as capability-dependent, not assumed.
