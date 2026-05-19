from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from booking_web_app import app


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


def find_free_port(start: int = 8020) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


def open_browser_later(url: str) -> None:
    time.sleep(1.5)
    webbrowser.open(url)


def main() -> None:
    configure_console_encoding()
    port = find_free_port()
    url = f"http://127.0.0.1:{port}/modules/booking"
    print(f"Booking 生成器正在启动：{url}")
    print("请不要关闭这个窗口；关闭窗口后工具会停止运行。")
    threading.Thread(target=open_browser_later, args=(url,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
