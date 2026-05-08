import errno
import socket

import pytest

from app.main import _describe_port_unavailable, _find_available_port


def test_describe_port_unavailable_distinguishes_in_use():
    error = OSError(errno.EADDRINUSE, "address already in use")

    assert _describe_port_unavailable(error) == "已被其他进程监听"


def test_describe_port_unavailable_distinguishes_permission_or_reserved():
    error = OSError(errno.EACCES, "permission denied")

    assert _describe_port_unavailable(error) == "被系统保留或当前用户无权限监听"


def test_strict_port_refuses_random_fallback(monkeypatch):
    monkeypatch.setenv("KOKOROMEMO_STRICT_PORT", "1")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

        with pytest.raises(RuntimeError, match=str(port)):
            _find_available_port("127.0.0.1", port)
