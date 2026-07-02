from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser

import uvicorn
from fastapi import FastAPI


DEFAULT_PORT_SEARCH_SIZE = 300


def configure_console_encoding() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleCP(65001)
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def is_port_bindable(port: int, *, host: str = "127.0.0.1") -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            sock.bind((host, port))
    except OSError:
        return False
    return True


def find_free_port(
    start: int = 8010,
    *,
    host: str = "127.0.0.1",
    search_size: int = DEFAULT_PORT_SEARCH_SIZE,
) -> int:
    if search_size < 1:
        raise ValueError("search_size must be at least 1")

    for port in range(start, start + search_size):
        if is_port_bindable(port, host=host):
            return port

    end = start + search_size - 1
    raise RuntimeError(f"No bindable TCP port found on {host} from {start} to {end}.")


def open_browser_later(url: str, *, delay_seconds: float = 1.5) -> None:
    time.sleep(delay_seconds)
    webbrowser.open(url)


def run_local_app(
    app: FastAPI,
    *,
    display_name: str,
    start_port: int = 8010,
    landing_path: str = "/",
) -> None:
    configure_console_encoding()
    host = "127.0.0.1"
    port = find_free_port(start_port, host=host)
    normalized_path = landing_path if landing_path.startswith("/") else f"/{landing_path}"
    url = f"http://{host}:{port}{normalized_path}"
    print(f"{display_name} 正在启动：{url}")
    print("请不要关闭这个窗口；关闭窗口后工具会停止运行。")
    threading.Thread(target=open_browser_later, args=(url,), daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="info")
