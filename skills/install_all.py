#!/usr/bin/env python3
"""Install the four maintained SQL skills and retire obsolete discovery surfaces."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import runpy
import shutil
import sys
import tempfile
import uuid
from collections.abc import Sequence

ROOT = pathlib.Path(__file__).resolve().parent
ACTIVE_BUNDLES = (
    "sql_optimizer",
    "sql_plan_enforcer",
    "sql_health_triage",
    "sql_index_manager",
)
ALLOWED_SKILL_DIRS = ("references",)
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
    for host in (".copilot", ".claude"):
        candidate = pathlib.Path.home() / host / "skills"
        if candidate.is_dir() or candidate.parent.is_dir():
            return candidate
    return pathlib.Path.home() / ".copilot" / "skills"


def default_backup_root() -> pathlib.Path:
    return pathlib.Path.home() / ".azure-sql-mcp" / "backups" / "retired-skills"


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
    """Return the selected destination plus known user-level skill roots."""

    candidates = [skills_root.expanduser()]
    candidates.extend(pathlib.Path.home() / relative for relative in HOST_SKILL_DIRS)
    return tuple(dict.fromkeys(candidates))


def _remove(path: pathlib.Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _reference_files(bundle: str, directories: tuple[str, ...]) -> list[pathlib.Path]:
    """Return a bundle's reference files, relative to the bundle directory.

    The agent reads these files as instructions, so a bundle may publish only
    plain Markdown files directly inside an allowed, declared directory.
    """
    files: list[pathlib.Path] = []
    for name in directories:
        directory = ROOT / bundle / name
        if name not in ALLOWED_SKILL_DIRS:
            raise RuntimeError(f"{bundle} installer must not publish directory {name!r}.")
        if directory.is_symlink() or not directory.is_dir():
            raise RuntimeError(f"Missing or unsafe source directory for {bundle}: {name}")
        entries = sorted(
            entry for entry in directory.iterdir() if entry.name not in OS_METADATA_FILES
        )
        if not entries:
            raise RuntimeError(f"Empty source directory for {bundle}: {name}")
        for entry in entries:
            if entry.is_symlink() or not entry.is_file() or entry.suffix != ".md":
                raise RuntimeError(
                    f"Unsafe reference file for {bundle}: {name}/{entry.name}"
                )
            files.append(pathlib.Path(name) / entry.name)
    return files


def _validate_sources() -> dict[str, list[pathlib.Path]]:
    """Validate every source bundle and return the files each one publishes."""
    payloads: dict[str, list[pathlib.Path]] = {}
    for bundle in ACTIVE_BUNDLES:
        bundle_dir = ROOT / bundle
        skill = bundle_dir / "SKILL.md"
        installer = bundle_dir / "install.py"
        if bundle_dir.is_symlink() or skill.is_symlink() or installer.is_symlink():
            raise RuntimeError(f"Refusing symbolic-link source for {bundle}.")
        if not skill.is_file() or not installer.is_file():
            raise RuntimeError(f"Missing source files for {bundle}.")
        namespace = runpy.run_path(str(installer), run_name=f"_{bundle}_installer")
        if tuple(namespace.get("SKILL_FILES", ())) != ("SKILL.md",):
            raise RuntimeError(f"{bundle} installer must publish SKILL.md as its only file.")
        directories = tuple(namespace.get("SKILL_DIRS", ()))
        payloads[bundle] = [pathlib.Path("SKILL.md"), *_reference_files(bundle, directories)]

    pack = ROOT / LEARNING_PACK
    if pack.is_symlink() or not pack.is_file():
        raise RuntimeError(f"Missing or unsafe Git-only learning pack: {pack}")
    try:
        payload = json.loads(pack.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Learning pack is not valid JSON: {pack}") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "content_hash",
        "lessons",
        "pack_type",
        "provenance",
        "schema_version",
    }:
        raise RuntimeError("Learning pack has an unsupported shape.")
    if payload.get("pack_type") != "azure-sql-mcp-learning-pack":
        raise RuntimeError("Learning pack has an unsupported pack type.")
    if payload.get("schema_version") != 1 or not isinstance(payload.get("lessons"), list):
        raise RuntimeError("Learning pack has an unsupported schema version.")
    if payload.get("provenance") != {
        "contract_version": 1,
        "producer": "azure-sql-mcp-learning",
        "source": "local-owner-only-learning-store",
    }:
        raise RuntimeError("Learning pack provenance is invalid.")
    lesson_ids: list[str] = []
    for lesson in payload["lessons"]:
        if not isinstance(lesson, dict) or lesson.get("status") != "active":
            raise RuntimeError("Learning pack may contain active lessons only.")
        lesson_id = lesson.get("lesson_id")
        if not isinstance(lesson_id, str) or not lesson_id:
            raise RuntimeError("Learning pack lesson_id is invalid.")
        lesson_ids.append(lesson_id)
    if lesson_ids != sorted(lesson_ids) or len(set(lesson_ids)) != len(lesson_ids):
        raise RuntimeError("Learning pack lessons must have unique sorted identifiers.")
    content = dict(payload)
    content_hash = content.pop("content_hash")
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if content_hash != expected_hash:
        raise RuntimeError("Learning pack content hash does not validate.")
    return payloads


def find_retired_skill_paths(skills_root: pathlib.Path) -> tuple[pathlib.Path, ...]:
    """Return obsolete skill directories without following directory symlinks."""
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


def _new_archive(backup_root: pathlib.Path) -> pathlib.Path:
    backup_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(backup_root, 0o700)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    archive = backup_root / f"{stamp}-{uuid.uuid4().hex[:12]}"
    archive.mkdir(parents=True, mode=0o700)
    os.chmod(archive, 0o700)
    return archive


def install_all(
    skills_root: pathlib.Path,
    *,
    backup_root: pathlib.Path | None = None,
    retired_wrapper: pathlib.Path | None = None,
    discovery_roots: Sequence[pathlib.Path] | None = None,
) -> tuple[pathlib.Path, pathlib.Path | None]:
    """Transactionally replace active bundles and archive obsolete installations."""
    payloads = _validate_sources()
    skills_root = skills_root.expanduser()
    skills_root.mkdir(parents=True, exist_ok=True)
    if skills_root.is_symlink() or not skills_root.is_dir():
        raise RuntimeError(f"Refusing unsafe skills root: {skills_root}")

    stage_root = pathlib.Path(
        tempfile.mkdtemp(prefix=".sql-skills-stage-", dir=skills_root)
    )
    transaction_backup = pathlib.Path(
        tempfile.mkdtemp(prefix=".sql-skills-rollback-", dir=skills_root)
    )
    for bundle in ACTIVE_BUNDLES:
        staged = stage_root / bundle
        staged.mkdir(mode=0o700)
        for relative in payloads[bundle]:
            (staged / relative).parent.mkdir(mode=0o700, exist_ok=True)
            shutil.copy2(ROOT / bundle / relative, staged / relative)
    # The learning pack is a reviewed Git artifact for MCP import/review only.
    # It is deliberately not staged or copied into any host skill directory.

    installed: set[str] = set()
    old_moved: set[str] = set()
    archived_moves: list[tuple[pathlib.Path, pathlib.Path]] = []
    archive: pathlib.Path | None = None
    backup_root = (backup_root or default_backup_root()).expanduser()
    wrapper = retired_wrapper or default_retired_wrapper()
    if wrapper is not None:
        wrapper = wrapper.expanduser()

    try:
        for bundle in ACTIVE_BUNDLES:
            destination = skills_root / bundle
            if destination.is_symlink():
                raise RuntimeError(f"Refusing symbolic-link destination: {destination}")
            old = transaction_backup / bundle
            if destination.exists():
                os.replace(destination, old)
                old_moved.add(bundle)
            os.replace(stage_root / bundle, destination)
            installed.add(bundle)

        retired_paths: list[pathlib.Path] = []
        roots = discovery_roots or discoverable_skill_roots(skills_root)
        for discovery_root in roots:
            retired_paths.extend(
                find_retired_skill_paths(pathlib.Path(discovery_root).expanduser())
            )
        if wrapper is not None and (wrapper.exists() or wrapper.is_symlink()):
            retired_paths.append(wrapper)
        retired_paths = list(dict.fromkeys(retired_paths))

        if retired_paths or old_moved:
            archive = _new_archive(backup_root)
            for ordinal, source in enumerate(retired_paths, start=1):
                label = f"retired-{ordinal:02d}-{source.name}"
                target = archive / label
                shutil.move(str(source), str(target))
                archived_moves.append((source, target))
            for ordinal, bundle in enumerate(sorted(old_moved), start=1):
                source = transaction_backup / bundle
                target = archive / f"prior-{ordinal:02d}-{bundle}"
                shutil.move(str(source), str(target))
                archived_moves.append((source, target))
    except Exception:
        for source, target in reversed(archived_moves):
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(source))
        for bundle in reversed(ACTIVE_BUNDLES):
            destination = skills_root / bundle
            old = transaction_backup / bundle
            if bundle in installed and (destination.exists() or destination.is_symlink()):
                _remove(destination)
            if bundle in old_moved and old.exists():
                os.replace(old, destination)
        if archive is not None and archive.exists() and not any(archive.iterdir()):
            archive.rmdir()
        raise
    finally:
        if stage_root.exists():
            shutil.rmtree(stage_root)
        if transaction_backup.exists():
            shutil.rmtree(transaction_backup)

    return skills_root, archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install the maintained Azure SQL skills.")
    parser.add_argument("--dest", help="Destination skills root.")
    parser.add_argument("--backup-root", help="Protected archive root for retired payloads.")
    parser.add_argument(
        "--retired-wrapper",
        help="Obsolete PATH wrapper to archive; defaults to the historical user path.",
    )
    args = parser.parse_args(argv)

    destination = resolve_dest(args.dest)
    backup_root = pathlib.Path(args.backup_root).expanduser() if args.backup_root else None
    wrapper = (
        pathlib.Path(args.retired_wrapper).expanduser()
        if args.retired_wrapper
        else default_retired_wrapper()
    )
    try:
        installed_root, archive = install_all(
            destination,
            backup_root=backup_root,
            retired_wrapper=wrapper,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary restores prior bundles
        print(f"Installation failed; prior bundles restored: {exc}", file=sys.stderr)
        return 1

    print(f"Installed {', '.join(ACTIVE_BUNDLES)} to {installed_root}")
    if archive is not None:
        print(f"Archived prior and retired payloads under protected backup: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
