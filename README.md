# SQL skills for Azure SQL Database

Four agent skills for performance work on Azure SQL Database. They are made to
be used with the [`azure-sql-mcp`](https://github.com/akaalholdings/azure-sql-mcp)
server, which gives the agent typed evidence and gated experiments.

| Skill | Use it for |
|---|---|
| `sql_optimizer` | Tune or rewrite one query, with measured proof when the policy allows it |
| `sql_health_triage` | Find the cause of slowness or an incident |
| `sql_index_manager` | Review the indexes of a workload |
| `sql_plan_enforcer` | Review and control plan choice through Query Store |

The skills work without the server for static analysis. In that mode they give
recommendations that are labelled as not measured.

## Install

Python 3.12 or newer. From the repository root:

```bash
python3 skills/install_all.py --dest "$HOME/.copilot/skills"
python3 skills/check_installed_parity.py --dest "$HOME/.copilot/skills"
```

On Windows:

```powershell
py -3.12 skills\install_all.py --dest "$env:USERPROFILE\.copilot\skills"
py -3.12 skills\check_installed_parity.py --dest "$env:USERPROFILE\.copilot\skills"
```

Reload the editor window after the install. Use another `--dest` for another
agent host. Full instructions, the MCP configuration and usage examples are in
[`skills/README.md`](skills/README.md).

## Versions

These skill versions go with `azure-sql-mcp` 3.0.0rc1: sql-optimizer 3.0.0,
sql-health-triage 1.1.0, sql-plan-enforcer 1.1.0, sql-index-manager 2.1.0.

## Test

```bash
python -m pip install pytest ruff
python -m pytest -q skills/sql_optimizer/tests skills/sql_plan_enforcer/tests skills/sql_health_triage/tests skills/sql_index_manager/tests skills/tests
python -m unittest discover -s scripts/tests -p 'test_*.py'
python -m ruff check skills scripts
python scripts/check_markdown_links.py
python scripts/check_retired_paths.py
python scripts/scan_content_secrets.py
```

## Known limits

- The skills are written for Azure SQL Database. They do not cover SQL Server
  on a virtual machine or Azure SQL Managed Instance.
- Measured tuning needs the `azure-sql-mcp` server and a database policy that
  allows it. Use a copy of a database, not production.

## Licence

MIT. See [`LICENSE`](LICENSE).
