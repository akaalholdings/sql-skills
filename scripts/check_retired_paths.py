#!/usr/bin/env python3
"""Ensure retired execution paths and references stay absent."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}
_TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".ps1",
    ".sh",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
    ".json",
}


def _join(parts: tuple[str, ...]) -> str:
    return "".join(parts)


_RETIRED_NAMES = {
    _join(("connect", "or")),
    _join(("legacy",)),
}
# The retired bundle name, in its underscore and hyphen forms, is matched by
# SHA-256 so the name itself is not stored in this repository.
_RETIRED_NAME_SHA256 = {
    "82df0207b0073cfbfb2e584f8955f5a8ba8ba25e5499aa240fa5fd14969dd0f8",
    "a4b70db4f5f07cfecdcce1d53702053788ea8283e55976db2ed907f7604608fb",
}
_NAME_TOKEN = re.compile(r"[a-z0-9_-]+")


def _is_retired_name(token: str) -> bool:
    return hashlib.sha256(token.encode("utf-8")).hexdigest() in _RETIRED_NAME_SHA256


def _has_retired_name(text: str) -> bool:
    return any(_is_retired_name(token) for token in _NAME_TOKEN.findall(text.casefold()))
_RETIRED_INDEX_TOOL_NAMES = {
    _join(("get_index_portfolio_", "snapshot")),
    _join(("capture_index_portfolio_", "snapshot")),
    _join(("classify_index_", "portfolio")),
    _join(("recheck_index_", "portfolio")),
}
_RETIRED_TEXT = {
    _join(("connect", "or")),
}
_RETIRED_TEXT.update(_RETIRED_INDEX_TOOL_NAMES)


@dataclass(frozen=True)
class RetiredPathIssue:
    path: Path
    line: int | None
    reason: str


def _skip(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return any(part in _SKIP_DIRS for part in relative.parts)


def _is_scannable(path: Path) -> bool:
    return path.suffix.lower() in _TEXT_SUFFIXES


def _is_integrity_checker(path: Path) -> bool:
    return path.name in {"check_retired_paths.py", "test_integrity_checks.py"}


def _candidate_paths(root: Path) -> list[Path]:
    """Use tracked and non-ignored files so private ignored leftovers are not scanned."""
    try:
        output = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return sorted(root.rglob("*"))
    return sorted(
        root / item.decode("utf-8")
        for item in output.split(b"\0")
        if item and (root / item.decode("utf-8")).exists()
    )


def check_retired_paths(root: Path = REPO_ROOT) -> list[RetiredPathIssue]:
    issues: list[RetiredPathIssue] = []
    for path in _candidate_paths(root):
        if _skip(path, root):
            continue
        relative = path.relative_to(root)
        if any(
            part.casefold() in _RETIRED_NAMES or _is_retired_name(part.casefold())
            for part in relative.parts
        ):
            issues.append(RetiredPathIssue(path, None, "retired path exists"))
            continue
        if not path.is_file() or not _is_scannable(path) or _is_integrity_checker(path):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, start=1):
            lowered = line.casefold()
            if any(text.casefold() in lowered for text in _RETIRED_TEXT) or _has_retired_name(
                lowered
            ):
                issues.append(RetiredPathIssue(path, number, "retired reference found"))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    issues = check_retired_paths(root)
    if issues:
        for issue in issues:
            location = str(issue.path.relative_to(root))
            if issue.line is not None:
                location += f":{issue.line}"
            print(f"{location}: {issue.reason}", file=sys.stderr)
        return 1
    print("retired paths absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
