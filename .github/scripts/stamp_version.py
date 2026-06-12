"""Stamp a CI build version into project metadata files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def normalize_version(raw: str) -> str:
    version = raw.strip().removeprefix("v")
    if not VERSION_RE.fullmatch(version):
        raise SystemExit(f"版本号必须类似 1.2.3 或 v1.2.3，当前为：{raw!r}")
    return version


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def stamp_pyproject(version: str) -> None:
    path = ROOT / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(?m)^version = "[^"]+"$', f'version = "{version}"', text, count=1)
    write_text(path, text)


def stamp_backend_fallback(version: str) -> None:
    write_text(
        ROOT / "app" / "_version.py",
        '"""Build-time version fallback for packaged binaries."""\n\n'
        f'__version__ = "{version}"\n',
    )


def stamp_json_version(path: Path, version: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = version
    packages = data.get("packages")
    if isinstance(packages, dict) and isinstance(packages.get(""), dict):
        packages[""]["version"] = version
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def stamp_cargo_toml(version: str) -> None:
    path = ROOT / "gui" / "src-tauri" / "Cargo.toml"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(?m)^version = "[^"]+"$', f'version = "{version}"', text, count=1)
    write_text(path, text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, help="Build version, with or without a leading v")
    args = parser.parse_args()
    version = normalize_version(args.version)

    stamp_pyproject(version)
    stamp_backend_fallback(version)
    stamp_json_version(ROOT / "gui" / "package.json", version)
    stamp_json_version(ROOT / "gui" / "package-lock.json", version)
    stamp_json_version(ROOT / "gui" / "src-tauri" / "tauri.conf.json", version)
    stamp_cargo_toml(version)
    print(f"已写入构建版本：{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
