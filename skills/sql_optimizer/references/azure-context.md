# Azure SQL Database operating context

Detail for `SKILL.md`. Its hard rules apply here; nothing in this file relaxes them.

- **Trigger:** CPU, data IO, log IO, workers, memory grants, throttling, waits, blocking, deadlocks, or concurrent load coincides with the query regression.
- **Safe rewrite/action:** reduce query work only after separating shared pressure; adjust the test window or hand off an estate/resource issue to triage; do not claim a query fix from a quieter sample.
- **Preconditions:** Azure SQL service tier/compute model, collection window, concurrency, isolation, workload overlap, and replica/read-scale destination are known.
- **Counterexample/risk:** scaling or killing sessions is outside this skill; a faster isolated run can be worse under concurrency; resource evidence may be partial.
- **MCP evidence:** `collect_performance_evidence`, Query Store/resource history, waits, blocking/open transactions, worker/memory/IO limits, and availability/truncation/provenance fields.

Interpret the query inside its Azure SQL Database limits:

- compare CPU, data I/O, log write, workers/sessions, memory, storage, and governance percentages with the database’s actual objective and collection window;
- in an elastic pool, separate database pressure from shared pool pressure;
- in serverless, exclude resume/cold-cache effects or label them as part of the workload requirement;
- in Hyperscale or read scale-out, record the replica and data-access path because cache and remote-page behavior can change measurements;
- check blocking, lock waits, snapshot/version-store behavior, memory grants, and concurrent workload before blaming the plan;
- verify Query Store state, capture mode, retention, and interval coverage; absent history is not zero activity;
- detect Automatic Tuning ownership and do not silently compete with automatic force-plan or index actions;
- use database-scoped configuration and supported Query Store controls. Do not recommend instance trace flags, SQL Server service changes, or instance tempdb file layout for Azure SQL Database.
