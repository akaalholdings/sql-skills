# Indexes

Detail for `SKILL.md`. Its hard rules apply here; nothing in this file relaxes them.

## Family 5: indexes

- **Trigger:** a proven predicate, join, or order is uncovered, a lookup is material, or existing indexes overlap while writes are costly.
- **Safe rewrite/action:** compare existing keys and includes first (`get_object_details` returns them, with filters); extend or widen an index before adding one; test the smallest covering or key-order change.
- **Preconditions:** exact data types, filter truth domain, write workload, uniqueness, partitioning, and compression are read from MCP metadata.
- **Counterexample/risk:** a filtered index misses parameter values; missing-index suggestions are leads, not proof; `is_unused=null` means unknown coverage, and a successful per-query `missing_index_count=0` means no optimizer hint for that plan, not proof that no index could help. Top-level recommendations may also be empty because emitted hints were filtered against existing indexes. Never infer a safe production drop from one query.
- **MCP evidence:** plan lookup and scan findings, usage and write impact, benchmark results for every parameter case, missing-index provenance, and lease state.

## Design

Design the index from the plan. Key: the equality columns, then the ORDER BY columns in the query's order and direction. A range column goes last; when the query needs no order, it follows the equality columns. INCLUDE the other columns the query reads, so the index covers: an INCLUDE cannot seek or give order. When an existing index has the same leading keys, extend or widen it instead of adding one, and pass `replaces` to the benchmark.

`get_object_details` returns keys, included columns, index filters, and `max_length` in bytes. It does not return collation, partitioning, foreign-key trust, or SET options: read those with one catalog query.

Call `review_workload_indexes(schema_name, table_names, query_ids, objective)` only when the table already has two or more nonclustered indexes and you hold the Query Store query id of the tuned query. Its use is to extend an existing index instead of adding one. Pass `query_ids` with that id and set `objective` to the case objective (`duration` for `elapsed_time`). Read `requested_queries` first: it says how many recommendations serve the tuned query (`serves_requested_query`). Recommendations from other queries are left out unless you pass `include_other_recommendations`. When it reports none, keep your own design and say that the workload review did not propose it.

## What a quick design misses

- **Compression.** PAGE is the default for a new read-path nonclustered index on a large table. Build once. Test a ROW or uncompressed variant only when evidence shows a write-heavy table (PAGE costs CPU on every write) or the user asks.
- **Depth.** A seek costs one read per B-tree level. Read `index_depth` and `size_mb` in the benchmark result and report the depth and size of the one you recommend.
- **Used or not.** Verify that the candidate plan used the test index (`used_in_cases`). A faster run that ignored it is not evidence for the index.
- **Cost.** Count write amplification, storage, and log generation on a write-heavy table, and the other queries on the table. A statement that already runs in a few milliseconds and a few dozen reads gets no new index and no indexed view on a large fact table: saving milliseconds per call needs the call volume and a write cost justified with numbers.
- **Table with a columnstore index.** There a rowstore index helps only a selective lookup; the columnstore serves the scan. On a table with a clustered columnstore index the engine refuses an online build, so the index is built offline; with only a nonclustered columnstore index it builds online. On a partitioned table with a clustered columnstore index it must be partition-aligned: leave the ON clause out.
- **Partitioned rowstore table, `TOP` with `ORDER BY` on a column that is not the partition column.** An aligned index is one B-tree per partition, so the order must be merged across partitions. A non-aligned index (`partition_aligned` false) is one ordered B-tree. It blocks partition SWITCH: give that warning with the DDL, and recommend it only when the table is not loaded or aged out by switch.
- **Rowstore fact table scanned for aggregates.** Lead with a nonclustered columnstore index on the key and measure columns the query family reads, not with B-tree indexes. Keep `SUM` and `COUNT` on bare columns (aggregation-ordering reference). State the cost: every write also maintains the columnstore index, and a table takes only one. `get_tool_guide("columnstore")` has the detail.
- **Filtered and computed-column options** need a filter that is true for every parameter value, deterministic expressions, and a write-cost review.
- **Indexed view.** An indexed view is a setup change with write cost: measure it (sandbox reference), and give the covering index as the alternative.

## Columnstore options and forbidden designs

- **Ordered columnstore.** For a nonclustered columnstore test index (`kind: "nonclustered_columnstore"`), give `order_columns` when the query filters a range of one column, for example a date. The rows are sorted on build, so segment elimination skips most row groups. The order columns must be in the index column list. Sorting makes the build slower.
- **Archive compression.** `data_compression: "COLUMNSTORE_ARCHIVE"` reads fewer pages and costs more CPU to decompress. Use it for cold, read-mostly data and measure both CPU and reads before you recommend it.
- **Indexed views forbidden.** When `check_capabilities` returns `indexed_view_experiment.designs_forbidden: true`, or the brief says the client does not use indexed views, do not propose or test one. Go to the next design for the shape: a columnstore index for a fact scan and aggregate, a covering index with a set-based rewrite for the rest. Say once that the faster design exists and why it is not offered.
