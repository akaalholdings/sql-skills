# Joins, optional filters and relational shape

Detail for `SKILL.md`. Its hard rules apply here; nothing in this file relaxes them.

Each card is actionable only when its semantic preconditions hold. Record the listed MCP evidence before calling a measured result proven.

## Family 2: joins and relational shape

### Optional filters, OR branches, and LIKE

- **Trigger:** optional filters such as `(@p IS NULL OR col = @p)`, broad OR branches, CASE-wrapped filters, negation, or `LIKE` with a non-prefix wildcard.
- **Safe rewrite/action:** split genuinely distinct parameter states into explicit branches or separate statements; use a prefix range only for a known prefix search; keep an optional-filter branch when NULL means “all rows”.
- **Preconditions:** branch result multisets and order are identical, parameter types match, branches are disjoint or duplicate behavior is preserved, and the application can select the branch.
- **Counterexample/risk:** `UNION ALL` can duplicate rows; `LIKE '%x'` cannot become a prefix seek; dynamic SQL can change security, plan cache, or parameter semantics.
- **MCP evidence:** parameter buckets, Query Store history, `explain_query` for NULL/common/rare values, residual predicates, plan variants, and `compare_query_results` per branch/bucket.

When NULL means “no filter”, write one SELECT per parameter shape and let a batch choose the branch:

```sql
IF @CustomerId IS NULL
    SELECT o.OrderId, o.CustomerId
    FROM dbo.Orders AS o
    ORDER BY o.OrderId;
ELSE
    SELECT o.OrderId, o.CustomerId
    FROM dbo.Orders AS o
    WHERE o.CustomerId = @CustomerId
    ORDER BY o.OrderId;
```

Each branch compiles its own plan, and every branch keeps the baseline's outer ORDER BY. Do not combine overlapping branches with `UNION ALL`.

Choose the primary shape by the number of optional filters and the call rate:

- One or two optional filters: the IF / ELSE batch above.
- Three or more, or filters that combine freely: lead with parameterized dynamic SQL. Build the statement from a fixed list of predicates, append only the predicates whose parameter is supplied, pass every value as a parameter through `sp_executesql` with the full parameter list declared on every call, and never concatenate a value into the statement text. Each filter combination then gets its own cached plan. State the design notes with it: ownership chaining does not cover dynamic SQL, so the caller needs SELECT permission or the module must be signed or use `EXECUTE AS`; plan-cache growth is bounded by the number of filter combinations.
- Low call rate and an expensive execution: keep the catch-all statement and add `OPTION (RECOMPILE)`. State the cost: compile CPU per call times calls per second, next to the saving.
- Compatibility level 170 with Optional Parameter Plan Optimization on may already handle a single `(@p IS NULL OR col = @p)` predicate. Verify it in the plan; do not assume it.

Measure it as one candidate. The proof tools admit a read-only batch: optional DECLARE and SET of scalar variables, IF / ELSE over parameters and literals only, and per branch one SELECT or one `EXEC sys.sp_executesql` of a string literal with a parameter list; at most 16 branches. `explain_query` returns `branches`, one estimated plan per branch with its condition; with `analyze=true` it names the branch that ran in `summary.batch.executed_branch`. `compare_query_results` and `benchmark_tuning_candidate` take the single statement as the baseline and the batch as the candidate. Register one parameter case per branch and give the type of every parameter: a case set that never reaches a branch proves nothing about it. `get_tool_guide("branching_batch")` has the admitted grammar.

Do not add `OPTIMIZE FOR` hints to the branches: `OPTIMIZE FOR UNKNOWN` picked the worse index when it was measured. When a branch still takes the wrong index for a sniffed value, measure the cross case first, and deliver a hint only as an alternative with the case it makes worse.

### OR across two columns

`WHERE a = @x OR b = @x` cannot seek one index. Find the keys with one seek per column, then join back once:

```sql
SELECT TOP (50)
    t.TicketId,
    t.Title
FROM dbo.Tickets AS t
INNER JOIN
(
    SELECT t1.TicketId FROM dbo.Tickets AS t1 WHERE t1.OpenedByUserId = @UserId
    UNION
    SELECT t2.TicketId FROM dbo.Tickets AS t2 WHERE t2.AssignedToUserId = @UserId
) AS k
    ON k.TicketId = t.TicketId
ORDER BY t.TicketId;
```

`UNION` removes the row that matches both branches, so no row is returned twice; `UNION ALL` is right only when the branches cannot overlap. Each branch needs an index that leads on its column. The total-order proof follows this shape when the ORDER BY ends on the primary key.

### Joins, EXISTS, and fan-out

- **Trigger:** a join multiplies rows, a correlated subquery repeats work, or the query checks existence without selecting child columns.
- **Safe rewrite/action:** use `EXISTS`/`NOT EXISTS` only for a true semi/anti-join; pre-filter or pre-aggregate the many-side only when multiplicity and outer-join behavior stay the same; remove a provably unused join.
- **Preconditions:** join keys, NULL behavior, duplicate count, outer-join preservation, selected columns, and predicates are fully accounted for.
- **Counterexample/risk:** replacing JOIN with EXISTS removes fan-out; pre-aggregation can change NULL groups; a “redundant” join may enforce security or filter rows.
- **MCP evidence:** object/dependency metadata, join estimates versus actuals, fan-out rows, key lookups, `compare_query_results` with duplicate-aware comparison, and plan deltas.

If child rows are used only to test existence, a semi-join can avoid fan-out:

```sql
SELECT
    c.CustomerId,
    c.DisplayName
FROM dbo.Customers AS c
WHERE EXISTS
(
    SELECT 1
    FROM dbo.Orders AS o
    WHERE o.CustomerId = c.CustomerId
      AND o.Status = @Status
);
```

This is not equivalent when the original query returned one row per matching order. For `NOT EXISTS`, verify NULL semantics instead of mechanically replacing `NOT IN`. For outer joins, keep predicates on the nullable side in the correct `ON` or `WHERE` location; moving them can turn an outer join into an inner join.

Pre-aggregate the many-side only when the original result already had one row per parent:

```sql
WITH OrderTotals AS
(
    SELECT
        o.CustomerId,
        SUM(o.Amount) AS TotalAmount
    FROM dbo.Orders AS o
    WHERE o.OrderDate >= @FromDate
      AND o.OrderDate < @ToDate
    GROUP BY o.CustomerId
)
SELECT
    c.CustomerId,
    ot.TotalAmount
FROM dbo.Customers AS c
INNER JOIN OrderTotals AS ot
    ON ot.CustomerId = c.CustomerId;
```

Check empty groups, duplicate parents, decimal accumulation type, and predicates from other child tables. A CTE is syntax, not guaranteed materialization. If an expensive intermediate result is referenced repeatedly, test a temporary table only in an approved disposable execution context and include its populate cost, indexes, recompilation effect, and cleanup in the measurement.
