# Client report and operator appendix

Detail for `SKILL.md`. Its hard rules apply here; nothing in this file relaxes them.

The answer follows the output contract in `SKILL.md`: recommendation first, plain language.

## Translate before you write

Sections 1 to 8 of the output contract never contain a tool name, a skill name, an internal field name, a status code, or a case, session, candidate, or evidence identifier. Object, column, and index names and Query Store query ids are the reader's language: use them. Replace each internal term before you write:

| Internal term | Write this |
| --- | --- |
| `deployment_ready` | proven and safe to deploy |
| `improved` | measured faster, with identical results |
| `equivalence_failed` | the rewrite changes the results |
| `performance_only` | faster, but not proven to return the same results |
| `tested_match` | the results matched on the tested cases; not proven for all inputs |
| `not_compared` | the results could not be compared; say why |
| `inconclusive` | the test could not decide; say what was missing |
| `cleanup_required` | a temporary test object may still exist; give the statement that removes it |
| `proof_contract_required` | results can differ on each run, so they cannot be compared automatically |
| `sql-plan-enforcer`, `sql-index-manager` | plan stabilization review, workload-wide index review |

A design under a declared precondition is written as: the same results while the property holds; verified on current data, not enforced. Give the DDL that enforces it. Never write "proven" or "safe to deploy" for it.

## When the engagement defines the report

When the engagement defines the report's sections, write those sections. Keep identifiers and tool notes out of the client report: put them in the last message, or in the notes file the engagement names.

## Operator appendix

The closing appendix of a measured run holds, also for failed work:

1. **Outcome and stopping reason.**
2. **Leaderboard:** candidate id and evidence id, the exact change, state, phase, parameter cases, executions, the returned medians, equivalence and proof scope, and cleanup status. Use `not collected` for missing values.
3. **Rejected experiments:** every slower, neutral, timed-out, refused, or non-equivalent attempt, with its reason.
4. **Measured outside the workflow:** each number that did not come from a benchmark tool, with the statements that produced it.
5. **Not measured:** when the time budget ended first, the design and the exact call that would measure it, with its arguments.
6. **Deployment handoff:** the smallest approved change, the exact rollback, and what to monitor.
7. **Evidence gaps:** untested cases, truncation, refused comparisons, shared resource noise, policy limits.

For `no_change`, say what was tried and why each attempt lost. Report the best static candidate separately; never call it a winner.
