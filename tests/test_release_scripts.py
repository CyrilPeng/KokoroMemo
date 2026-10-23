from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def test_termux_setup_fallback_version_matches_project_version():
    script = (ROOT / "scripts" / "termux-setup.sh").read_text(encoding="utf-8")
    match = re.search(r'FALLBACK_VERSION="\$\{KOKOROMEMO_FALLBACK_VERSION:-([^}]+)\}"', script)

    assert match is not None
    assert match.group(1) == _project_version()
