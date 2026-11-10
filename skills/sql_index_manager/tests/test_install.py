from __future__ import annotations

import importlib.util
import pathlib

SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]


def _load_installer():
    # Every bundle ships a module named install.py. Load this bundle's file by
    # path so a combined test run cannot test another bundle's installer.
    spec = importlib.util.spec_from_file_location(
        f"{SKILL_DIR.name}_install", SKILL_DIR / "install.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


install = _load_installer()


def _source_payload() -> dict[str, bytes]:
    files = {"SKILL.md": (SKILL_DIR / "SKILL.md").read_bytes()}
    for path in sorted((SKILL_DIR / "references").glob("*.md")):
        files[f"references/{path.name}"] = path.read_bytes()
    return files


def _installed(destination: pathlib.Path) -> dict[str, bytes]:
    return {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    }


def test_runtime_payload_is_the_core_file_and_its_references() -> None:
    assert install.SKILL_NAME == SKILL_DIR.name
    assert install.SKILL_FILES == ("SKILL.md",)
    assert install.SKILL_DIRS == ("references",)
    assert install.SKILL_NAME in install.KNOWN_BUNDLES


def test_install_is_exact_and_removes_stale_runtime(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "skills"
    destination = install.install(root)
    assert destination == root / install.SKILL_NAME
    assert _installed(destination) == _source_payload()
    assert len(_source_payload()) > 1

    (destination / "stale.txt").write_text("old", encoding="utf-8")
    (destination / "old-helper.py").write_text("old", encoding="utf-8")
    (destination / "state").mkdir()
    (destination / "state" / "old.json").write_text("{}", encoding="utf-8")
    (destination / "references" / "retired-topic.md").write_text("old", encoding="utf-8")

    destination = install.install(root)
    assert _installed(destination) == _source_payload()
    assert not any(destination.rglob("*.py"))
