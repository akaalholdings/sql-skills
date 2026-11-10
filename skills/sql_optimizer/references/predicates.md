# Predicates and SARGability

Detail for `SKILL.md`. Its hard rules apply here; nothing in this file relaxes them.

Each card is actionable only when its semantic preconditions hold. Record the listed MCP evidence before calling a measured result proven.

## Family 1: predicates and SARGability

- **Trigger:** a function, arithmetic expression, cast, or type conversion wraps an indexed/filter column, or the plan shows a residual predicate or scan.
- **Safe rewrite/action:** move the operation to the parameter/literal side; use a typed half-open range for a date/time bucket; align parameter and column types.
- **Preconditions:** the conversion is equivalent for all values, precision and collation are unchanged, and NULL/boundary behavior is preserved.
- **Counterexample/risk:** converting the parameter can change overflow, rounding, non-sargable collation behavior, or the matched datetime boundary; an implicit conversion may be intentional.
- **MCP evidence:** `explain_query`; actual plan predicate/residual details; `compare_plan_summaries`; type metadata; row estimates versus actual rows; logical reads and elapsed time by bucket.

## Concrete predicate rewrites

For a date bucket, prefer a typed half-open range over a function on the column. This preserves every time value in the day and gives an index on `OrderDate` a seekable boundary:

```sql
SELECT
    o.OrderId,
    o.OrderDate
FROM dbo.Orders AS o
WHERE o.OrderDate >= @Day
  AND o.OrderDate < DATEADD(day, 1, @Day);
```

Use this only when `@Day` is typed consistently with the contract and the upper-bound calculation cannot overflow. When some allowed values convert differently or overflow (the last date of the type, NULL), guard them: an IF / ELSE batch sends those values to the original predicate and every other value to the bare-column form. Do not replace an inclusive arbitrary timestamp range with this form. Lead with the half-open form, not an inclusive last-tick bound such as `<= '...23:59:59.9999999'`: the last tick depends on the column's precision and breaks when the type changes.

Keep the column bare when types can be aligned:

```sql
SELECT
    o.OrderId
FROM dbo.Orders AS o
WHERE o.CustomerId = @CustomerId;
```

Bind `@CustomerId` as the column’s SQL type. Do not repair a mismatched application parameter by converting `o.CustomerId` in the predicate. Likewise, move safe arithmetic to the constant side (`Amount >= @MinimumAmount`, not `Amount * 1.2 >= @Threshold`) only after checking decimal scale, rounding, overflow, and NULL behavior.

When the application sends a parameter of the wrong type (for example `nvarchar` against a `varchar` column), the primary fix is the parameter type in the application, with the exact binding the developer must write. When a CHECK constraint or the column type limits the values the column can hold, use it: a value the column cannot contain cannot match, so say that the type change returns the same rows instead of listing the case as a risk.

For prefix search, `Name LIKE @Prefix + N'%'` may be seekable under the active collation. A leading wildcard remains a contains search and must not be represented as a prefix range. Avoid `ISNULL(column, value)`, `COALESCE(column, value)`, CASE, scalar functions, or implicit type conversion around a search column unless no equivalent bare-column predicate exists.

## Scalar function in the select list or predicate

When `get_object_details` shows the body of a scalar function and the body is one deterministic expression over its arguments, write that expression in the query in place of the call, and aggregate before you apply it. State in the answer that the query now holds a copy of the rule, so a change to the function must be made in both places. When the body reads tables or is not visible, keep the call and reduce how often it runs: aggregate first, then call it once per group.
