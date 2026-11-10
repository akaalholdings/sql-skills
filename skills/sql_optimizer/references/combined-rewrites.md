# Combined rewrites and rewrite-plus-index lineage

Detail for `SKILL.md`. Its hard rules apply here; nothing in this file relaxes them.

## Family 6: combined rewrites and rewrite-plus-index lineage

### Combined rewrite

- **Trigger:** two or more safe rewrite families interact.
- **Safe rewrite/action:** register a combined multi-family rewrite as `strategy=combined` with no parent lineage and benchmark it with `benchmark_tuning_candidate`.
- **Preconditions:** every combined rewrite preserves the frozen contract; measure its complete SQL as one candidate and do not add metrics from separate runs.
- **Counterexample/risk:** combined rewrites can hide which change caused a regression or alter fan-out, order, or NULL behavior.
- **MCP evidence:** candidate strategy, complete SQL fingerprint, per-case result/equivalence evidence, and plan deltas.

### Rewrite plus index

- **Trigger:** a rewrite wins only with its index, or a measured finalist remains worth testing with a temporary index.
- **Safe rewrite/action:** one call. Register the rewrite with `add_tuning_candidate`, `strategy=rewrite_plus_index`, and no `artifact_ref`. Then call `benchmark_index_candidate` with `phase=finalist`, the index set, `sql` as the original statement of the performance case, and the rewrite as `candidate_sql`: the baseline arms run the original without the indexes, the candidate arm runs the rewrite with them, and the tool compares the two results in one snapshot while the indexes exist. `get_tool_guide("rewrite_with_indexes")` has the detail.
- **Lineage:** to extend a rewrite already measured in this session, register `strategy=rewrite_plus_index` with `artifact_ref` exactly `candidate:<parent-id>`; it runs only through `benchmark_index_candidate` with `phase=finalist`. A parent that was `improved`, `neutral`, or `regressed` is accepted when its results matched the original for every parameter case; that run measures only what the index adds to the rewrite.
- **Preconditions:** the parent is in the same session and has finalist evidence with stable SQL/database/runtime fingerprints. A performance-only parent propagates `parent_equivalence=unproven`; an improving child remains `performance_only` and can never become proven, `improved`, or deploy-ready. Equivalence-failed, inconclusive, cleanup-required, or cross-session parents are ineligible.
- **Counterexample/risk:** a good rewrite plus a good index can duplicate work, change join order, or regress another bucket; lineage never upgrades index evidence into rewrite proof.
- **MCP evidence:** `get_tuning_session` lineage, parent/child evidence ids, per-case A-B-A deltas, equivalence scope, and sandbox cleanup state.

Do not open a second case or session for a rewrite with its index, and do not measure the rewrite alone first: the one call gives the combined gain as one measurement. Never open a performance case with the rewrite as its baseline, and never pass the rewrite as `sql`.
