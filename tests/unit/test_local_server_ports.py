from __future__ import annotations

import socket

import pytest

from app.packaging import local_server


def test_is_port_bindable_treats_permission_error_as_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    class DeniedSocket:
        def __enter__(self) -> "DeniedSocket":
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

        def settimeout(self, timeout: float) -> None:
            return None

        def bind(self, address: tuple[str, int]) -> None:
            raise PermissionError(13, "denied")

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: DeniedSocket())

    assert not local_server.is_port_bindable(8051)


def test_find_free_port_skips_unbindable_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    checked_ports: list[int] = []

    def fake_is_port_bindable(port: int, *, host: str = "127.0.0.1") -> bool:
        checked_ports.append(port)
        return port == 8085

    monkeypatch.setattr(local_server, "is_port_bindable", fake_is_port_bindable)

    assert local_server.find_free_port(8051, search_size=40) == 8085
    assert checked_ports[0] == 8051
    assert 8085 in checked_ports


def test_find_free_port_raises_when_scan_window_has_no_bindable_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_server, "is_port_bindable", lambda port, *, host="127.0.0.1": False)

    with pytest.raises(RuntimeError, match="No bindable TCP port"):
        local_server.find_free_port(8051, search_size=3)
