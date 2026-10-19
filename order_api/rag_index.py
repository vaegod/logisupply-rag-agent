"""Build/check the Milvus SOP index. Stop the API before indexing a local Lite database."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from .rag import load_retriever


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Only check this corpus/model index; never call Embedding")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    engine = load_retriever()
    try:
        report = engine.index_info("ready" if engine.ready() else "not_ready") if args.check else engine.index()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report["status"] == "not_ready":
            raise SystemExit(1)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
