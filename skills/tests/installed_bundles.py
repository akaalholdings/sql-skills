"""Install the maintained bundles and read them back as a host would see them."""

from __future__ import annotations

import importlib.util
import pathlib
import tempfile

SKILLS_ROOT = pathlib.Path(__file__).resolve().parents[1]


def read_installed_bundles() -> dict[str, tuple[str, dict[str, str]]]:
    """Return {bundle: (SKILL.md text, {reference file name: text})}.

    Guidance that moved to a reference file still has to reach the host, so
    contract tests read the installed payload, not the source tree.
    """
    spec = importlib.util.spec_from_file_location(
        "skills_install_all_for_contracts", SKILLS_ROOT / "install_all.py"
    )
    assert spec is not None and spec.loader is not None
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    with tempfile.TemporaryDirectory() as root:
        base = pathlib.Path(root)
        destination = base / "skills"
        installer.install_all(
            destination,
            backup_root=base / "archive",
            retired_wrapper=base / "bin" / "absent-wrapper",
            discovery_roots=(destination,),
        )
        return {
            bundle: (
                (destination / bundle / "SKILL.md").read_text(encoding="utf-8"),
                {
                    path.name: path.read_text(encoding="utf-8")
                    for path in sorted((destination / bundle / "references").glob("*.md"))
                },
            )
            for bundle in installer.ACTIVE_BUNDLES
        }
