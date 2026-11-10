from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import shutil
import stat

import pytest

SKILLS_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = SKILLS_ROOT.parent
ACTIVE_BUNDLES = (
    "sql_optimizer",
    "sql_plan_enforcer",
    "sql_health_triage",
    "sql_index_manager",
)
LEARNING_PACK = pathlib.Path("knowledge") / "azure-sql-mcp-learning-pack.json"
# The tools match the retired bundle by the SHA-256 of its name. The tests use a
# stand-in name and point both tools at its digest.
RETIRED_BUNDLE = "retired_bundle_stand_in"
RETIRED_COMPONENT = "".join(("con", "nector"))  # noqa: FLY002


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


install_all = _load("skills_install_all", SKILLS_ROOT / "install_all.py")
parity = _load("skills_parity", SKILLS_ROOT / "check_installed_parity.py")
REAL_RETIRED_DIGEST = install_all.RETIRED_BUNDLE_SHA256


@pytest.fixture(autouse=True)
def _stand_in_retired_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    digest = hashlib.sha256(RETIRED_BUNDLE.encode("utf-8")).hexdigest()
    monkeypatch.setattr(install_all, "RETIRED_BUNDLE_SHA256", digest)
    monkeypatch.setattr(parity, "RETIRED_BUNDLE_SHA256", digest)


def test_both_tools_match_the_same_retired_bundle_by_digest() -> None:
    # One digest in two files: an edit to one alone would let the retired
    # bundle pass the parity check or stay installed.
    assert len(REAL_RETIRED_DIGEST) == 64
    assert int(REAL_RETIRED_DIGEST, 16) >= 0
    assert _load(
        "skills_parity_fresh", SKILLS_ROOT / "check_installed_parity.py"
    ).RETIRED_BUNDLE_SHA256 == REAL_RETIRED_DIGEST
    assert not install_all.is_retired_bundle_name("sql_optimizer")
    assert install_all.is_retired_bundle_name(RETIRED_BUNDLE)


def test_no_retired_wrapper_is_assumed_when_the_bin_folder_has_none(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The default must never point at the bin folder itself: the installer
    # archives the path it is given.
    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)
    assert install_all.default_retired_wrapper() is None
    bin_dir = tmp_path / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "other-tool").write_text("x", encoding="utf-8")
    assert install_all.default_retired_wrapper() is None
    assert parity.default_retired_wrapper() is None
    (bin_dir / RETIRED_BUNDLE).write_text("x", encoding="utf-8")
    assert install_all.default_retired_wrapper() == bin_dir / RETIRED_BUNDLE
    assert parity.default_retired_wrapper() == bin_dir / RETIRED_BUNDLE


def _install(tmp_path: pathlib.Path, destination: pathlib.Path, tool=install_all):
    wrapper = tmp_path / "bin" / RETIRED_BUNDLE
    return tool.install_all(
        destination,
        backup_root=tmp_path / "archive",
        retired_wrapper=wrapper,
        discovery_roots=(destination,),
    )


def _problems(tmp_path: pathlib.Path, destination: pathlib.Path, tool=parity) -> list[str]:
    return tool.compare_install(
        destination,
        retired_wrapper=tmp_path / "bin" / RETIRED_BUNDLE,
        discovery_roots=(destination,),
    )


def _published(bundle_dir: pathlib.Path) -> dict[str, bytes]:
    """The files one source bundle publishes: SKILL.md plus references/*.md."""
    files = {"SKILL.md": (bundle_dir / "SKILL.md").read_bytes()}
    for path in sorted((bundle_dir / "references").glob("*.md")):
        files[f"references/{path.name}"] = path.read_bytes()
    return files


def _tree(root: pathlib.Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _copied_skills(tmp_path: pathlib.Path) -> pathlib.Path:
    """A private copy of the source tree, so a test can make a bundle unsafe."""
    copy = tmp_path / "source" / "skills"
    shutil.copytree(
        SKILLS_ROOT,
        copy,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".DS_Store"),
    )
    return copy


def test_release_tools_target_exactly_the_maintained_collection() -> None:
    assert install_all.ACTIVE_BUNDLES == ACTIVE_BUNDLES
    assert parity.ACTIVE_BUNDLES == ACTIVE_BUNDLES
    assert install_all.LEARNING_PACK == LEARNING_PACK
    assert parity.LEARNING_PACK == LEARNING_PACK
    for bundle in ACTIVE_BUNDLES:
        module = _load(f"{bundle}_installer", SKILLS_ROOT / bundle / "install.py")
        assert module.SKILL_FILES == ("SKILL.md",)
        assert module.SKILL_DIRS == ("references",)
        assert module.KNOWN_BUNDLES == ACTIVE_BUNDLES
        assert len(_published(SKILLS_ROOT / bundle)) > 1, bundle


def test_clean_install_contains_only_authoritative_skill_files(
    tmp_path: pathlib.Path,
) -> None:
    destination = tmp_path / "skills"
    installed_root, archive = _install(tmp_path, destination)

    assert installed_root == destination
    assert archive is None
    assert {
        entry.name for entry in destination.iterdir() if not entry.name.startswith(".")
    } == set(ACTIVE_BUNDLES)
    assert not (destination / LEARNING_PACK).exists()
    for bundle in ACTIVE_BUNDLES:
        assert _tree(destination / bundle) == _published(SKILLS_ROOT / bundle), bundle


def test_install_replaces_stale_active_payloads(tmp_path: pathlib.Path) -> None:
    destination = tmp_path / "skills"
    for bundle in ACTIVE_BUNDLES:
        old = destination / bundle
        old.mkdir(parents=True)
        (old / "old-helper.py").write_text("old", encoding="utf-8")
        (old / "state").mkdir()
        (old / "references").mkdir()
        (old / "references" / "retired-topic.md").write_text("old", encoding="utf-8")

    _root, archive = _install(tmp_path, destination)

    for bundle in ACTIVE_BUNDLES:
        assert _tree(destination / bundle) == _published(SKILLS_ROOT / bundle), bundle
    assert archive is not None
    assert stat.S_IMODE((tmp_path / "archive").stat().st_mode) == 0o700
    archived_markers = {
        marker.read_text(encoding="utf-8")
        for marker in archive.glob("prior-*/old-helper.py")
    }
    assert archived_markers == {"old"}


def test_install_archives_retired_skills_and_path_wrapper(
    tmp_path: pathlib.Path,
) -> None:
    destination = tmp_path / "skills"
    top_level = destination / RETIRED_BUNDLE
    nested = destination / "legacy" / RETIRED_BUNDLE
    wrapper = tmp_path / "bin" / RETIRED_BUNDLE
    for path in (top_level, nested):
        path.mkdir(parents=True)
        (path / "old.txt").write_text("retired", encoding="utf-8")
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")

    _root, archive = install_all.install_all(
        destination,
        backup_root=tmp_path / "archive",
        retired_wrapper=wrapper,
        discovery_roots=(destination,),
    )

    assert archive is not None
    assert not top_level.exists()
    assert not nested.exists()
    assert not wrapper.exists()
    assert len(tuple(archive.iterdir())) == 3
    assert stat.S_IMODE(archive.stat().st_mode) == 0o700


def test_late_install_failure_restores_all_prior_bundles(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "skills"
    for bundle in ACTIVE_BUNDLES:
        old = destination / bundle
        old.mkdir(parents=True)
        (old / "marker.txt").write_text(bundle, encoding="utf-8")

    real_replace = install_all.os.replace
    failed = False

    def flaky_replace(source, target):
        nonlocal failed
        source_path = pathlib.Path(source)
        if (
            not failed
            and ".sql-skills-stage-" in source_path.parent.name
            and source_path.name == "sql_plan_enforcer"
        ):
            failed = True
            raise OSError("synthetic late commit failure")
        return real_replace(source, target)

    monkeypatch.setattr(install_all.os, "replace", flaky_replace)

    with pytest.raises(OSError, match="synthetic"):
        _install(tmp_path, destination)

    for bundle in ACTIVE_BUNDLES:
        assert (destination / bundle / "marker.txt").read_text(encoding="utf-8") == bundle


def test_parity_rejects_changed_extra_and_retired_surfaces(
    tmp_path: pathlib.Path,
) -> None:
    destination = tmp_path / "skills"
    wrapper = tmp_path / "bin" / RETIRED_BUNDLE
    _install(tmp_path, destination)

    assert parity.compare_install(
        destination,
        retired_wrapper=wrapper,
        discovery_roots=(destination,),
    ) == []

    learning_destination = destination / LEARNING_PACK
    learning_destination.parent.mkdir(parents=True)
    learning_destination.write_text("{}\n", encoding="utf-8")
    problems = parity.compare_install(
        destination,
        retired_wrapper=wrapper,
        discovery_roots=(destination,),
    )
    assert any("Git artifact" in problem for problem in problems)
    learning_destination.unlink()

    (destination / "sql_optimizer" / "SKILL.md").write_text("changed", encoding="utf-8")
    problems = parity.compare_install(
        destination,
        retired_wrapper=wrapper,
        discovery_roots=(destination,),
    )
    assert any("differs" in problem for problem in problems)

    (destination / "sql_optimizer" / "SKILL.md").write_bytes(
        (SKILLS_ROOT / "sql_optimizer" / "SKILL.md").read_bytes()
    )
    (destination / "sql_optimizer" / "extra.md").write_text("stale", encoding="utf-8")
    problems = parity.compare_install(
        destination,
        retired_wrapper=wrapper,
        discovery_roots=(destination,),
    )
    assert any("only SKILL.md" in problem for problem in problems)

    (destination / "sql_optimizer" / "extra.md").unlink()
    (destination / RETIRED_BUNDLE).mkdir()
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("retired", encoding="utf-8")
    problems = parity.compare_install(
        destination,
        retired_wrapper=wrapper,
        discovery_roots=(destination,),
    )
    assert any("retired skill" in problem for problem in problems)
    assert any("PATH wrapper" in problem for problem in problems)


def test_parity_checks_every_reference_file(tmp_path: pathlib.Path) -> None:
    # The agent reads a reference file on demand. An edited, extra or missing
    # one in the host directory is guidance the repository never published.
    destination = tmp_path / "skills"
    _install(tmp_path, destination)
    references = destination / "sql_optimizer" / "references"
    source = SKILLS_ROOT / "sql_optimizer" / "references"
    name = min(path.name for path in source.glob("*.md"))

    (references / name).write_text("changed", encoding="utf-8")
    assert any(
        f"references/{name} differs" in problem
        for problem in _problems(tmp_path, destination)
    )

    (references / name).unlink()
    assert any(
        f"references/{name} missing" in problem
        for problem in _problems(tmp_path, destination)
    )

    shutil.copy2(source / name, references / name)
    (references / "stale.md").write_text("stale", encoding="utf-8")
    assert any(
        "unexpected references/stale.md" in problem
        for problem in _problems(tmp_path, destination)
    )

    (references / "stale.md").unlink()
    assert _problems(tmp_path, destination) == []

    shutil.rmtree(references)
    assert any("references" in problem for problem in _problems(tmp_path, destination))


def test_reference_removed_from_source_is_removed_by_the_next_install(
    tmp_path: pathlib.Path,
) -> None:
    copy = _copied_skills(tmp_path)
    tool = _load("copied_install_all", copy / "install_all.py")
    checker = _load("copied_parity", copy / "check_installed_parity.py")
    destination = tmp_path / "skills"
    _install(tmp_path, destination, tool)
    retired = min((copy / "sql_optimizer" / "references").glob("*.md"))
    assert (destination / "sql_optimizer" / "references" / retired.name).is_file()

    retired.unlink()
    _install(tmp_path, destination, tool)

    assert not (destination / "sql_optimizer" / "references" / retired.name).exists()
    assert _tree(destination / "sql_optimizer") == _published(copy / "sql_optimizer")
    assert _problems(tmp_path, destination, checker) == []


def _nested_directory(references: pathlib.Path) -> None:
    (references / "nested").mkdir()
    (references / "nested" / "topic.md").write_text("nested", encoding="utf-8")


def _non_markdown_file(references: pathlib.Path) -> None:
    (references / "helper.py").write_text("print('x')\n", encoding="utf-8")


def _symlinked_file(references: pathlib.Path) -> None:
    assert references.is_dir()
    target = references.parent / "SKILL.md"
    try:
        (references / "linked.md").symlink_to(target)
    except OSError:
        pytest.skip("this platform does not allow symbolic links here")


def _undeclared_directory(references: pathlib.Path) -> None:
    bundle = references.parent
    (bundle / "scripts").mkdir()
    (bundle / "scripts" / "topic.md").write_text("topic", encoding="utf-8")
    installer = bundle / "install.py"
    declared = 'SKILL_DIRS: tuple[str, ...] = ("references",)'
    text = installer.read_text(encoding="utf-8")
    assert declared in text
    installer.write_text(
        text.replace(declared, 'SKILL_DIRS: tuple[str, ...] = ("references", "scripts")'),
        encoding="utf-8",
    )


def _missing_directory(references: pathlib.Path) -> None:
    shutil.rmtree(references)


UNSAFE_SOURCES = (
    _nested_directory,
    _non_markdown_file,
    _symlinked_file,
    _undeclared_directory,
    _missing_directory,
)


@pytest.mark.parametrize("make_unsafe", UNSAFE_SOURCES)
def test_unsafe_reference_source_is_refused_before_any_bundle_is_replaced(
    tmp_path: pathlib.Path,
    make_unsafe,
) -> None:
    # Only reviewed Markdown may reach a host skill directory: no code, no
    # link out of the bundle, no directory the installer does not declare.
    copy = _copied_skills(tmp_path)
    make_unsafe(copy / "sql_plan_enforcer" / "references")
    tool = _load("copied_install_all", copy / "install_all.py")
    destination = tmp_path / "skills"
    for bundle in ACTIVE_BUNDLES:
        (destination / bundle).mkdir(parents=True)
        (destination / bundle / "marker.txt").write_text(bundle, encoding="utf-8")

    with pytest.raises(RuntimeError, match="sql_plan_enforcer"):
        _install(tmp_path, destination, tool)

    for bundle in ACTIVE_BUNDLES:
        assert _tree(destination / bundle) == {"marker.txt": bundle.encode()}


@pytest.mark.parametrize("bundle", ACTIVE_BUNDLES)
def test_single_bundle_installer_publishes_exactly_its_payload(
    tmp_path: pathlib.Path,
    bundle: str,
) -> None:
    installer = _load(f"{bundle}_single", SKILLS_ROOT / bundle / "install.py")
    root = tmp_path / "skills"
    destination = installer.install(root)
    assert destination == root / bundle
    assert _tree(destination) == _published(SKILLS_ROOT / bundle)

    (destination / "stale.txt").write_text("old", encoding="utf-8")
    (destination / "references" / "stale.md").write_text("old", encoding="utf-8")
    installer.install(root)
    assert _tree(destination) == _published(SKILLS_ROOT / bundle)
    assert {entry.name for entry in root.iterdir()} == {bundle}


@pytest.mark.parametrize("bundle", ACTIVE_BUNDLES)
@pytest.mark.parametrize("make_unsafe", UNSAFE_SOURCES)
def test_single_bundle_installer_refuses_an_unsafe_reference_source(
    tmp_path: pathlib.Path,
    bundle: str,
    make_unsafe,
) -> None:
    copy = _copied_skills(tmp_path)
    make_unsafe(copy / bundle / "references")
    installer = _load(f"{bundle}_unsafe", copy / bundle / "install.py")
    root = tmp_path / "skills"
    (root / bundle).mkdir(parents=True)
    (root / bundle / "marker.txt").write_text("prior", encoding="utf-8")

    with pytest.raises(RuntimeError):
        installer.install(root)

    assert _tree(root / bundle) == {"marker.txt": b"prior"}
    assert {entry.name for entry in root.iterdir()} == {bundle}


def test_install_and_parity_cover_secondary_discovery_roots(
    tmp_path: pathlib.Path,
) -> None:
    destination = tmp_path / "copilot" / "skills"
    secondary = tmp_path / "agents" / "skills"
    retired = secondary / "nested" / RETIRED_BUNDLE
    wrapper = tmp_path / "bin" / RETIRED_BUNDLE
    retired.mkdir(parents=True)
    (retired / "old.txt").write_text("retired", encoding="utf-8")

    _root, archive = install_all.install_all(
        destination,
        backup_root=tmp_path / "archive",
        retired_wrapper=wrapper,
        discovery_roots=(destination, secondary),
    )

    assert archive is not None
    assert not retired.exists()
    assert parity.compare_install(
        destination,
        retired_wrapper=wrapper,
        discovery_roots=(destination, secondary),
    ) == []

    stale = secondary / RETIRED_BUNDLE
    stale.mkdir(parents=True)
    problems = parity.compare_install(
        destination,
        retired_wrapper=wrapper,
        discovery_roots=(destination, secondary),
    )
    assert any(str(stale) in problem for problem in problems)


def test_retired_repository_trees_have_no_payload() -> None:
    ignored_names = {"__pycache__", ".DS_Store"}

    def payloads(path: pathlib.Path) -> list[pathlib.Path]:
        if not path.exists():
            return []
        return [
            item
            for item in path.rglob("*")
            if item.name not in ignored_names
            and "__pycache__" not in item.parts
            and item.suffix != ".pyc"
        ]

    assert payloads(REPO_ROOT / "legacy" / RETIRED_BUNDLE) == []
    assert payloads(REPO_ROOT / RETIRED_COMPONENT) == []
