import shutil
import uuid
from pathlib import Path

from app import main


def test_write_port_file_is_atomic_replace(monkeypatch):
    work_dir = Path(".test_port_file") / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        config_path = work_dir / "config.yaml"
        monkeypatch.setattr(main, "resolve_config_path", lambda for_write=False: config_path)

        main._write_port_file(23456)
        main._write_port_file(23457)

        assert (work_dir / ".port").read_text(encoding="utf-8") == "23457"
        assert not (work_dir / ".port.tmp").exists()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
