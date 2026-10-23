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


def test_android_start_script_supports_wake_lock_and_log_rotation():
    script = (ROOT / "packaging" / "android" / "common" / "start.sh").read_text(encoding="utf-8")

    assert "termux-wake-lock" in script
    assert "LOG_FILE.previous" in script
    assert "seq 1 180" in script
    assert 'server["port"] = 14514' not in script
    assert 'server.setdefault("port", 14514)' in script
