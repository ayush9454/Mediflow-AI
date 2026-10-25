"""Trusted bounded retention and orphan cleanup; no client-accessible deletion route."""

import argparse

from mediflow.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100, choices=range(1, 101))
    args = parser.parse_args()
    module = app.state.uploads
    if module is None:
        raise SystemExit("Configure trusted Firestore and private Azure storage before cleanup.")
    try:
        removed = module.cleanup(limit=args.limit)
    except Exception:
        raise SystemExit("Cleanup was interrupted; retry after its lease expires.") from None
    print("Expired records removed:", removed)


if __name__ == "__main__":
    main()
