"""Write or check the offline knowledge-gap queue.

Examples::

    poetry run python audit.py --queue ../../data/learning/gaps.json
    poetry run python audit.py --queue ../../data/learning/gaps.json --check

The production indexer image does not run this command.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gaps import GapError, audit_knowledge, validate_queue

_DEFAULT_DATA = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge"


def load_queue_file(path: Path, data_dir: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise GapError("queue must be a JSON object")
    validate_queue(document, data_dir)
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit knowledge gaps into a JSON queue.")
    parser.add_argument("--data-dir", type=Path, default=_DEFAULT_DATA)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="Validate the queue and do not write it.")
    args = parser.parse_args(argv)

    data_dir = args.data_dir.resolve()
    queue = args.queue
    if args.check:
        if not queue.is_file():
            raise SystemExit(f"queue not found: {queue}")
        document = load_queue_file(queue, data_dir)
        print(f"valid {len(document['gaps'])} gaps")
        return 0

    existing = load_queue_file(queue, data_dir) if queue.is_file() else None
    document = audit_knowledge(data_dir, existing)
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for gap in document["gaps"]:
        print(
            f"{gap['priority']['score']:2d}  {gap['status']:8s}  {gap['kind']:12s}  {gap['dedupe_key']}"
        )
    print(f"wrote {len(document['gaps'])} gaps to {queue}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GapError as exc:
        raise SystemExit(str(exc)) from exc
