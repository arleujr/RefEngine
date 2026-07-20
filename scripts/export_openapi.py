from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from refengine.api.app import create_app  # noqa: E402


def main() -> None:
    destination = PROJECT_ROOT / "openapi" / "refengine.openapi.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = create_app(project_root=PROJECT_ROOT).openapi()
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(destination)


if __name__ == "__main__":
    main()
