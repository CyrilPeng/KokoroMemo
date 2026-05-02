import errno

from app.main import _describe_port_unavailable


def test_describe_port_unavailable_distinguishes_in_use():
    error = OSError(errno.EADDRINUSE, "address already in use")

    assert _describe_port_unavailable(error) == "已被其他进程监听"


def test_describe_port_unavailable_distinguishes_permission_or_reserved():
    error = OSError(errno.EACCES, "permission denied")

    assert _describe_port_unavailable(error) == "被系统保留或当前用户无权限监听"
