from __future__ import annotations

import argparse

import uvicorn

from app.packaging.local_server import configure_console_encoding, find_free_port


def run_dev_server(
    app_import: str,
    *,
    host: str = "127.0.0.1",
    preferred_port: int = 8051,
    log_level: str = "info",
    search_size: int = 300,
) -> None:
    configure_console_encoding()
    port = find_free_port(preferred_port, host=host, search_size=search_size)
    if port != preferred_port:
        print(f"Preferred port {preferred_port} is not bindable; using {port} instead.")
    print(f"Local server: http://{host}:{port}")
    uvicorn.run(app_import, host=host, port=port, log_level=log_level)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local uvicorn app on a bindable port.")
    parser.add_argument("app_import", help="Uvicorn import string, for example reconcile_web_app:app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--preferred-port", type=int, default=8051)
    parser.add_argument("--log-level", default="info")
    parser.add_argument("--search-size", type=int, default=300)
    args = parser.parse_args()

    run_dev_server(
        args.app_import,
        host=args.host,
        preferred_port=args.preferred_port,
        log_level=args.log_level,
        search_size=args.search_size,
    )


if __name__ == "__main__":
    main()
