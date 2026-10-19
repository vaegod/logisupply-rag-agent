"""Run the V2-only demo API with locally generated service/operator keys."""
from __future__ import annotations

import argparse
import json
import os
import secrets
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from .main import create_app

ROOT = Path(__file__).resolve().parents[1]


def main():
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8018, type=int)
    args = parser.parse_args()
    local = ROOT / "dify/local"
    local.mkdir(exist_ok=True)
    config_file = local / "runtime.json"
    if config_file.exists():
        config = json.loads(config_file.read_text(encoding="utf-8"))
    else:
        config = {"tool_key": secrets.token_urlsafe(32), "admin_key": secrets.token_urlsafe(32)}
        config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
    # This is a local tools-only helper. Never inherit a historical Railway
    # URL from the old runtime file; the complete local UI uses start-local.ps1.
    os.environ.setdefault("LOGISUPPLY_PUBLIC_URL", f"http://127.0.0.1:{args.port}")
    application = create_app(ROOT / "order_api/data/logisupply.db",
                             tool_key=config["tool_key"], admin_key=config["admin_key"])
    print(f"Local keys: {config_file} (not displayed, gitignored)")
    uvicorn.run(application, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
