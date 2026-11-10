#!/usr/bin/env python3
"""Verify exact installed SQL skill parity and retired-surface absence."""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import os
import pathlib
import runpy
import sys
from collections.abc import Sequence

ROOT = pathlib.Path(__file__).resolve().parent
ACTIVE_BUNDLES = (
    "sql_optimizer",
    "sql_plan_enforcer",
    "sql_health_triage",
    "sql_index_manager",
)
OS_METADATA_FILES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
LEARNING_PACK = pathlib.Path("knowledge") / "azure-sql-mcp-learning-pack.json"
# The retired bundle is matched by the SHA-256 of its name. The name itself
# is not stored in this repository.
RETIRED_BUNDLE_SHA256 = "82df0207b0073cfbfb2e584f8955f5a8ba8ba25e5499aa240fa5fd14969dd0f8"
HOST_SKILL_DIRS = (
    pathlib.Path(".copilot/skills"),
    pathlib.Path(".claude/skills"),
    pathlib.Path(".agents/skills"),
    pathlib.Path(".codex/skills"),
)


def resolve_dest(explicit: str | None = None) -> pathlib.Path:
    if explicit:
        return pathlib.Path(explicit).expanduser()
    configured = os.environ.get("SQL_SKILLS_DEST")
    if configured:
        return pathlib.Path(configured).expanduser()
    for host in (".copilot", ".claude"):
        candidate = pathlib.Path.home() / host / "skills"
        if all((candidate / bundle).is_dir() for bundle in ACTIVE_BUNDLES):
            return candidate
    return pathlib.Path.home() / ".copilot" / "skills"


def is_retired_bundle_name(name: str) -> bool:
    return hashlib.sha256(name.encode("utf-8")).hexdigest() == RETIRED_BUNDLE_SHA256


def default_retired_wrapper() -> pathlib.Path | None:
    """The retired PATH wrapper in ~/.local/bin, when one is there."""
    bin_dir = pathlib.Path.home() / ".local" / "bin"
    if not bin_dir.is_dir():
        return None
    for entry in sorted(bin_dir.iterdir()):
        if is_retired_bundle_name(entry.name):
            return entry
    return None


def discoverable_skill_roots(skills_root: pathlib.Path) -> tuple[pathlib.Path, ...]:
    candidates = [skills_root.expanduser()]
    candidates.extend(pathlib.Path.home() / relative for relative in HOST_SKILL_DIRS)
    return tuple(dict.fromkeys(candidates))


def find_retired_skill_paths(skills_root: pathlib.Path) -> tuple[pathlib.Path, ...]:
    if not skills_root.exists():
        return ()
    found: list[pathlib.Path] = []
    for current, directories, _files in os.walk(skills_root, followlinks=False):
        current_path = pathlib.Path(current)
        kept: list[str] = []
        for name in directories:
            child = current_path / name
            if is_retired_bundle_name(name):
                found.append(child)
            elif child.is_symlink():
                continue
            else:
                kept.append(name)
        directories[:] = kept
    return tuple(sorted(set(found)))


def _declared_directories(bundle: str) -> tuple[str, ...]:
    """Read the directories a bundle publishes from its own installer."""
    installer = ROOT / bundle / "install.py"
    namespace = runpy.run_path(str(installer), run_name=f"_{bundle}_installer")
    return tuple(namespace.get("SKILL_DIRS", ()))


def _compare_directory(bundle: str, name: str, installed: pathlib.Path) -> list[str]:
    """Compare one installed reference directory with its source, file by file."""
    if installed.is_symlink() or not installed.is_dir():
        return [f"{bundle}: {name} is not a regular directory"]
    source = ROOT / bundle / name
    source_names = (
        {entry.name for entry in source.iterdir() if entry.name not in OS_METADATA_FILES}
        if source.is_dir()
        else set()
    )
    installed_names = {entry.name for entry in installed.iterdir()}
    problems = [
        f"{bundle}: {name}/{missing} missing"
        for missing in sorted(source_names - installed_names)
    ]
    problems.extend(
        f"{bundle}: unexpected {name}/{extra}"
        for extra in sorted(installed_names - source_names)
    )
    for common in sorted(source_names & installed_names):
        installed_file = installed / common
        if installed_file.is_symlink() or not installed_file.is_file():
            problems.append(f"{bundle}: {name}/{common} is not a regular file")
        elif not filecmp.cmp(source / common, installed_file, shallow=False):
            problems.append(f"{bundle}: {name}/{common} differs from source")
    return problems


def compare_install(
    skills_root: pathlib.Path,
    *,
    retired_wrapper: pathlib.Path | None = None,
    discovery_roots: Sequence[pathlib.Path] | None = None,
) -> list[str]:
    problems: list[str] = []
    for bundle in ACTIVE_BUNDLES:
        source = ROOT / bundle / "SKILL.md"
        destination = skills_root / bundle
        if destination.is_symlink():
            problems.append(f"{bundle}: installed directory is a symbolic link")
            continue
        if not destination.is_dir():
            problems.append(f"{bundle}: installed directory missing")
            continue
        directories = _declared_directories(bundle)
        expected = sorted(("SKILL.md", *directories))
        entries = sorted(entry.name for entry in destination.iterdir())
        if entries != expected:
            problems.append(
                f"{bundle}: runtime must contain only {', '.join(expected)}; "
                f"found {', '.join(entries) or 'nothing'}"
            )
            continue
        installed_skill = destination / "SKILL.md"
        if installed_skill.is_symlink():
            problems.append(f"{bundle}: SKILL.md is a symbolic link")
        elif not filecmp.cmp(source, installed_skill, shallow=False):
            problems.append(f"{bundle}: SKILL.md differs from source")
        for name in directories:
            problems.extend(_compare_directory(bundle, name, destination / name))

    installed_pack = skills_root / LEARNING_PACK
    if installed_pack.exists() or installed_pack.is_symlink():
        problems.append(
            "learning pack must remain a reviewed Git artifact; it must not be installed"
        )

    roots = discovery_roots or discoverable_skill_roots(skills_root)
    for discovery_root in roots:
        for retired in find_retired_skill_paths(
            pathlib.Path(discovery_root).expanduser()
        ):
            problems.append(f"retired skill remains discoverable: {retired}")

    wrapper = retired_wrapper or default_retired_wrapper()
    if wrapper is not None:
        wrapper = wrapper.expanduser()
    if wrapper is not None and (wrapper.exists() or wrapper.is_symlink()):
        problems.append(f"retired PATH wrapper remains discoverable: {wrapper}")

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check exact installed SQL skill parity.")
    parser.add_argument("--dest", help="Destination skills root.")
    parser.add_argument("--retired-wrapper", help="Obsolete PATH wrapper path to verify absent.")
    args = parser.parse_args(argv)

    skills_root = resolve_dest(args.dest)
    wrapper = (
        pathlib.Path(args.retired_wrapper).expanduser()
        if args.retired_wrapper
        else default_retired_wrapper()
    )
    problems = compare_install(skills_root, retired_wrapper=wrapper)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1

    print(f"Installed skill parity OK ({skills_root}): {', '.join(ACTIVE_BUNDLES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
