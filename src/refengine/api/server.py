from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn


def run_server(*, port: int = 8000, open_browser: bool = False) -> None:
    """Start the local RefEngine server on the loopback interface."""
    url = f"http://127.0.0.1:{port}"
    if open_browser:
        threading.Timer(1.2, webbrowser.open, args=(url,)).start()
    uvicorn.run(
        "refengine.api.app:app",
        host="127.0.0.1",
        port=port,
        reload=False,
        access_log=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the local RefEngine application.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    run_server(port=args.port, open_browser=args.open_browser)


if __name__ == "__main__":
    main()
