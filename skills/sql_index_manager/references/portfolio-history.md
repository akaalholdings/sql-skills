# Long-term portfolio history

Detail for `SKILL.md`. Its boundaries apply here; nothing in this file relaxes them.

## Optional: long-term portfolio history

When a DBA has installed the two `dbatools` index-history tables and enabled
`allow_index_history_write` in the local database policy, the portfolio tools
`capture_index_review_snapshot`, `review_index_portfolio`, and
`get_index_review` keep daily usage snapshots across counter resets. Use them
only to strengthen a removal decision over 35 days or more (longer for databases
with quarter-end or year-end jobs). They are not needed
for workload-driven design and require a database policy with `allow_read=true`.
`review_index_portfolio` returns a compact review: `state_counts`, the
`actionable_subjects` (create, consolidate and drop candidates with inert DDL
and rollback), `blockers` by code, and `omitted_subjects`. Call
`get_index_review` with `subject_ids` and read the subject's removal gate,
definition and protections before you recommend a drop or a consolidation; do
not ask for the full review of every index.
When one of them returns `result_status=precondition`, show its `remediation`
to a DBA and stop; never run it yourself.

Read `observation.history_status` before any advice from a portfolio review:

- `stale`: the newest capture is older than 48 hours, so the review holds no
  subject states. Capture a new snapshot and review again.
- `historical`: the review describes an old capture (`stale_hours` says how
  old). An index created or dropped since then is not in it. It is history, not
  a basis for a removal: capture a new snapshot and review again.

In the portfolio review, two unused indexes where one covers the other are
both removal candidates. Say that removing both leaves no index on those
leading keys, and apply the removal discipline in `SKILL.md` to each.
