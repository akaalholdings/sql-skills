# Leads that are not B-tree changes

Detail for `SKILL.md`. Its boundaries apply here; nothing in this file relaxes them.

Each lead below is advice for a design or change review. None is a measured gain, and every statement in it is inert text.

## Columnstore

- **Protected (`columnstore_index_protected`).** Every columnstore index is listed as a `review_index`, also when it looks unused. Explain why: the analytic queries that need it often run only at period end, so usage counters and a short Query Store window do not prove non-use, and bringing it back means compressing the whole table again. A removal is a design decision with the owners of the reports, never a cleanup item.
- **A rowstore index on a columnstore table (`columnstore_selective_lookup`).** The review proposes one only for selective lookups: a scan that returns few rows and a small share of the table. Confidence is capped at medium. Say that the columnstore index keeps serving the scans and that every load now maintains one more index.
- **No B-tree for an analytic scan (`columnstore_scan_not_a_btree_candidate`).** Queries that read a large share of the table through the columnstore index are served well already. Do not add a seek index for them; route a slow scan to its plan findings (batch mode, segment elimination, predicate pushdown).
- **A columnstore design lead (`consider_columnstore_index`)** for a large rowstore table that is scanned and reduced by reporting queries. It has no DDL. Report its `conditions` with their measured values (rows, share of the table read, write churn, service objective), its `candidate_columns` and `excluded_columns`, and its `proof_set`. Its blocker `design_lead_requires_sandbox_proof` is exact: it must be proven on a non-production copy before anyone plans it.
- **Row-group maintenance (`columnstore_maintenance`).** The lead gives inert `REORGANIZE` or `REBUILD` text with its `cost` (space, log, and locks). Maintenance changes no definition, so there is no rollback. When the lead has no statement (`no_maintenance_statement_fixes_the_cause`), the cause is the load pattern (batch size, memory, or dictionary size): say that, and do not offer a rebuild as the fix. `get_columnstore_health` returns the row-group detail for one table.

## Partitioned tables

- **Removal is a review lead (`partitioned_index_removal_needs_switch_review`).** An unused, duplicate, or left-prefix index on a partition scheme is shown with the blocker `partition_switch_dependency`, a `removal_lead` block, and no DROP statement. State the reason: ALTER TABLE ... SWITCH needs matching indexes on both tables, so dropping the index on one side can fail the load or archive job. Then ask how the table is loaded and archived. If nothing switches, or once the staging and archive tables change too, the removal goes through change control.
- **New indexes** on a partitioned table carry `partitioning` (aligned with the table by default). When the supporting queries do not filter on the partitioning column, the recommendation adds a `non_aligned_alternative` with when it is better and what it breaks (partition switching). Present both; the choice belongs to the owner of the load process.

## Physical design (`physical_design_lead`)

Every one carries the blocker `design_lead_requires_change_review`.

- **Compression.** A large rowstore index stored uncompressed gets `estimate_statements`. Tell the DBA to run the estimate first; the lead proposes no rebuild. Compression costs CPU on writes and saves pages to read, cache, and back up.
- **Unique-constraint merge.** When a unique constraint and a covering twin index hold the same key, the lead gives `design_statements` and `rollback_statements` to keep one unique index. It gives no statements when a foreign key references the constraint.
- **Fill factor.** A change is proposed only from measured leaf allocations against leaf inserts: a lower fill factor where page splits are measured, a return to 100 where none are (`fill_factor_without_page_split_evidence`). Counters that could not be read give a gap, never a lead. The rebuild rewrites and logs the whole index: state that cost.
