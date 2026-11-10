from __future__ import annotations

import ast
import json
import os
import pathlib
import re

import pytest

from skills.tests.installed_bundles import read_installed_bundles

BUNDLES = read_installed_bundles()
PIN = pathlib.Path(__file__).resolve().parent / "mcp_contract_tools.json"
CONTRACT = json.loads(PIN.read_text(encoding="utf-8"))
ALL_TOOLS = frozenset(CONTRACT["tools"])
ALWAYS_AVAILABLE = frozenset(CONTRACT["always_available"])
PARAMETERS: dict[str, list[str]] = CONTRACT.get("parameters", {})

# What the skills rely on in the 3.0 server. A rename in the server must fail
# here, not in front of a client.
REQUIRED_TOOLS = (
    "get_tool_guide",
    "get_column_statistics",
    "get_failed_executions",
    "get_memory_pressure",
    "get_elastic_pool_pressure",
    "get_columnstore_health",
    "get_database_baseline",
    "assess_capacity",
    "analyze_application_patterns",
    "get_diagnostic_history",
)
REQUIRED_PARAMETERS = {
    "benchmark_index_candidate": (
        "indexes",
        "index_name_prefix",
        "data_compression",
        "replaces",
        "slow_baseline_cases",
        "detail",
        "idempotency_key",
    ),
    "benchmark_tuning_candidate": ("cross_case", "slow_baseline_cases", "detail", "phase"),
    "collect_performance_evidence": ("detail",),
    "get_tuning_session": ("view",),
    "finalize_tuning_session": ("logical_preconditions", "selection_scope", "stopping_reason"),
    "explain_query": ("analyze", "parameter_case", "parameter_values", "parameter_types"),
    "compare_query_results": ("parameter_case", "parameter_values", "parameter_types"),
    "review_workload_indexes": ("query_ids", "include_change_plan", "soak_days", "objective"),
    "check_runtime_status": ("include_tool_names",),
    "get_tool_guide": ("name",),
    "diagnose_database": ("window_minutes", "sample_seconds"),
    "get_diagnostic_history": ("category", "as_of_utc", "window_minutes"),
    "get_deadlock_history": ("source",),
    "get_database_baseline": ("scope", "query_ids"),
    "apply_prepared_plan_action": ("intent_id", "authorization_reference", "confirmation_token"),
    "rollback_plan_action": ("intent_id", "authorization_reference", "confirmation_token"),
    "report_stuck": ("skill", "skill_version", "last_tool", "blocker_kind", "summary", "attempts"),
}

# The profiles each skill tells the agent to run under.
SKILL_PROFILES = {
    "sql_optimizer": ("optimizer", "sandbox"),
    "sql_health_triage": ("triage",),
    "sql_plan_enforcer": ("enforcer-review", "enforcer-apply"),
    # The index manager names the optimizer's proof tools when it routes proof.
    "sql_index_manager": ("index-review", "triage", "optimizer", "sandbox"),
}
# Tools a skill names only to forbid them. They must never appear as a call.
NAMED_ONLY_TO_FORBID = {
    "sql_optimizer": frozenset(),
    "sql_health_triage": frozenset(),
    "sql_plan_enforcer": frozenset({"force_query_plan", "apply_plan_action"}),
    "sql_index_manager": frozenset(
        {
            "execute_tsql_unrestricted",
            "create_test_index",
            "drop_test_index",
            "rebuild_index",
            "record_decision",
            "review_decision",
            "propose_lesson",
            "list_learning_candidates",
            "create_handoff",
            "get_handoff",
            "resolve_handoff",
        }
    ),
}


def bundle_text(bundle: str) -> str:
    core, references = BUNDLES[bundle]
    return "\n".join((core, *references.values()))


def _named_tools(text: str) -> set[str]:
    return {name for name in re.findall(r"[a-z][a-z0-9_]+", text) if name in ALL_TOOLS}


def read_contract(config_path: pathlib.Path) -> dict[str, object]:
    """Read tool names and profile allowlists from the MCP config without importing it."""

    tree = ast.parse(config_path.read_text(encoding="utf-8"))
    values: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            values[node.target.id] = node.value
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            values[node.targets[0].id] = node.value

    def strings(expression: ast.expr) -> set[str]:
        found: set[str] = set()
        for child in ast.walk(expression):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                found.add(child.value)
            elif isinstance(child, ast.Name) and child.id in values and child.id.endswith("_NAMES"):
                found |= strings(values[child.id])
        return found

    allowlists = values["PROFILE_TOOL_ALLOWLISTS"]
    assert isinstance(allowlists, ast.Dict)
    profiles: dict[str, list[str]] = {}
    for key, value in zip(allowlists.keys, allowlists.values, strict=True):
        assert isinstance(key, ast.Attribute)
        profiles[key.attr.lower().replace("_", "-")] = sorted(strings(value))
    groups = values["TOOL_GROUPS"]
    assert isinstance(groups, ast.Dict)
    grouped = {key.value for key in groups.keys if isinstance(key, ast.Constant)}
    incident = strings(values["INCIDENT_TOOL_NAMES"])
    learning = strings(values["LEARNING_TOOL_NAMES"])
    tools = grouped | incident | learning | {"check_runtime_status"}
    return {
        "tools": sorted(tools),
        "always_available": sorted(incident | {"check_runtime_status"}),
        "profiles": profiles,
        "parameters": read_parameters(config_path.with_name("server.py"), tools),
    }


def read_parameters(server_path: pathlib.Path, tools: set[str]) -> dict[str, list[str]]:
    """Read each tool's parameter names from the tool registry without importing it."""

    parameters: dict[str, list[str]] = {}
    for node in ast.walk(ast.parse(server_path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in tools:
            names = [argument.arg for argument in (*node.args.args, *node.args.kwonlyargs)]
            parameters[node.name] = sorted(name for name in names if name != "self")
    return dict(sorted(parameters.items()))


def _call_examples(text: str) -> list[tuple[str, str]]:
    """Every `tool(argument, name=value)` example in a skill, as (tool, argument name)."""

    found: list[tuple[str, str]] = []
    for match in re.finditer(r"\b([a-z][a-z0-9_]+)\(([^()]*)\)", text):
        tool, arguments = match.group(1), match.group(2)
        if tool not in ALL_TOOLS:
            continue
        for argument in arguments.split(","):
            name = argument.split("=", 1)[0].strip().strip("`")
            if re.fullmatch(r"[a-z][a-z0-9_]*", name):
                found.append((tool, name))
    return found


@pytest.mark.parametrize("bundle", sorted(SKILL_PROFILES))
def test_skill_names_only_tools_its_profiles_expose(bundle: str) -> None:
    # A tool the active profile does not expose sends the agent into a dead
    # end: it plans a step it cannot run, then improvises around the gap.
    exposed = set(ALWAYS_AVAILABLE)
    for profile in SKILL_PROFILES[bundle]:
        exposed |= set(CONTRACT["profiles"][profile])
    text = bundle_text(bundle)
    outside = _named_tools(text) - exposed - NAMED_ONLY_TO_FORBID[bundle]
    assert outside == set(), sorted(outside)
    for tool in NAMED_ONLY_TO_FORBID[bundle]:
        assert re.search(rf"\b{tool}\s*\(", text) is None, tool


def test_pin_holds_the_3_0_tools_and_parameters_the_skills_rely_on() -> None:
    # The skills route to these tools and arguments. The pin is regenerated
    # from the server source, so a rename there shows up here first.
    assert set(REQUIRED_TOOLS) <= ALL_TOOLS, sorted(set(REQUIRED_TOOLS) - ALL_TOOLS)
    assert set(PARAMETERS) == set(ALL_TOOLS)
    for tool, names in REQUIRED_PARAMETERS.items():
        missing = set(names) - set(PARAMETERS[tool])
        assert missing == set(), (tool, sorted(missing))
    for profile in ("optimizer", "sandbox", "triage", "index-review", "enforcer-review"):
        assert "get_tool_guide" in CONTRACT["profiles"][profile], profile
    assert "get_columnstore_health" in CONTRACT["profiles"]["index-review"]


@pytest.mark.parametrize("bundle", sorted(SKILL_PROFILES))
def test_skill_call_examples_use_only_parameters_the_tool_takes(bundle: str) -> None:
    # An argument the tool does not take is refused by the strict schema: the
    # agent loses a call and then guesses.
    wrong = [
        (tool, name)
        for tool, name in _call_examples(bundle_text(bundle))
        if name not in PARAMETERS[tool]
    ]
    assert wrong == [], wrong


def test_pinned_contract_matches_the_mcp_source_when_one_is_supplied() -> None:
    # Optional cross-repository check: AZURE_SQL_MCP_SRC=<azure-sql-mcp checkout>.
    source = os.environ.get("AZURE_SQL_MCP_SRC")
    if not source:
        pytest.skip("AZURE_SQL_MCP_SRC is not set")
    live = read_contract(pathlib.Path(source) / "src" / "azure_sql_mcp" / "config.py")
    for key, value in live.items():
        assert CONTRACT[key] == value, key


if __name__ == "__main__":
    # Regenerate the pin from an azure-sql-mcp checkout, from the repository root:
    #   python -m skills.tests.test_mcp_tool_contract <azure-sql-mcp checkout> "<source note>"
    import sys

    checkout = pathlib.Path(sys.argv[1])
    regenerated = read_contract(checkout / "src" / "azure_sql_mcp" / "config.py")
    ordered = {
        "always_available": regenerated["always_available"],
        "parameters": regenerated["parameters"],
        "profiles": regenerated["profiles"],
        "source": sys.argv[2] if len(sys.argv) > 2 else CONTRACT.get("source", ""),
        "tools": regenerated["tools"],
    }
    PIN.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")
