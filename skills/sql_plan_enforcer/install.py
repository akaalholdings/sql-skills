#!/usr/bin/env python3
"""Install the sql_plan_enforcer Copilot skill."""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import sys
import tempfile
import uuid

SKILL_NAME = "sql_plan_enforcer"
SKILL_FILES = ("SKILL.md",)
SKILL_DIRS: tuple[str, ...] = ("references",)
ALLOWED_SKILL_DIRS = ("references",)
OS_METADATA_FILES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
KNOWN_BUNDLES = (
    "sql_optimizer",
    "sql_plan_enforcer",
    "sql_health_triage",
    "sql_index_manager",
)


def resolve_dest(explicit: str | None = None) -> pathlib.Path:
    if explicit:
        return pathlib.Path(explicit).expanduser()
    configured = os.environ.get("SQL_SKILLS_DEST")
    if configured:
        return pathlib.Path(configured).expanduser()
    for host in (".copilot", ".claude"):
        candidate = pathlib.Path.home() / host / "skills"
        if (candidate / SKILL_NAME).is_dir():
            return candidate
    for host in (".copilot", ".claude"):
        candidate = pathlib.Path.home() / host / "skills"
        if candidate.is_dir() or candidate.parent.is_dir():
            return candidate
    return pathlib.Path.home() / ".copilot" / "skills"


def _remove(path: pathlib.Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _payload(bundle_dir: pathlib.Path) -> list[pathlib.Path]:
    """Return every published file, relative to the bundle directory.

    The agent reads these files as instructions, so only SKILL.md and plain
    Markdown files directly inside a declared directory are published.
    """
    payload = [pathlib.Path(name) for name in SKILL_FILES]
    for relative in payload:
        source = bundle_dir / relative
        if source.is_symlink() or not source.is_file():
            raise RuntimeError(f"Missing or unsafe source file: {source}")
    for name in SKILL_DIRS:
        directory = bundle_dir / name
        if name not in ALLOWED_SKILL_DIRS:
            raise RuntimeError(f"Directory is not allowed in a skill bundle: {directory}")
        if directory.is_symlink() or not directory.is_dir():
            raise RuntimeError(f"Missing or unsafe source directory: {directory}")
        entries = sorted(
            entry for entry in directory.iterdir() if entry.name not in OS_METADATA_FILES
        )
        if not entries:
            raise RuntimeError(f"Empty source directory: {directory}")
        for entry in entries:
            if entry.is_symlink() or not entry.is_file() or entry.suffix != ".md":
                raise RuntimeError(f"Unsafe reference file: {entry}")
            payload.append(pathlib.Path(name) / entry.name)
    return payload


def install(skills_root: pathlib.Path) -> pathlib.Path:
    bundle_dir = pathlib.Path(__file__).resolve().parent
    payload = _payload(bundle_dir)
    skills_root.mkdir(parents=True, exist_ok=True)
    if skills_root.is_symlink() or not skills_root.is_dir():
        raise RuntimeError(f"Refusing unsafe skills root: {skills_root}")
    destination = skills_root / SKILL_NAME
    if destination.is_symlink():
        raise RuntimeError(f"Refusing symbolic-link destination: {destination}")

    stage_root = pathlib.Path(tempfile.mkdtemp(prefix=f".{SKILL_NAME}.stage-", dir=skills_root))
    staged = stage_root / SKILL_NAME
    staged.mkdir(mode=0o700)
    for relative in payload:
        (staged / relative).parent.mkdir(mode=0o700, exist_ok=True)
        shutil.copy2(bundle_dir / relative, staged / relative)
    backup = skills_root / f".{SKILL_NAME}.backup-{uuid.uuid4().hex}"
    moved_existing = False
    try:
        if destination.exists():
            os.replace(destination, backup)
            moved_existing = True
        os.replace(staged, destination)
    except Exception:
        if destination.exists() or destination.is_symlink():
            _remove(destination)
        if moved_existing and backup.exists():
            os.replace(backup, destination)
        raise
    else:
        if backup.exists():
            _remove(backup)
    finally:
        if stage_root.exists():
            shutil.rmtree(stage_root)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"Install {SKILL_NAME}.")
    parser.add_argument("--dest", help="Destination skills root.")
    args = parser.parse_args(argv)
    try:
        destination = install(resolve_dest(args.dest))
    except Exception as exc:  # noqa: BLE001 - CLI boundary reports install failure
        print(f"Install failed: {exc}", file=sys.stderr)
        return 1
    print(f"Installed {SKILL_NAME} to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
