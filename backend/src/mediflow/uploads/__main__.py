"""Trusted bounded retention and orphan cleanup; no client-accessible deletion route."""

import argparse

from mediflow.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100, choices=range(1, 101))
    args = parser.parse_args()
    try:
        from mediflow.worker import platform

        module = platform(Settings.from_environment()).uploads
        removed = module.cleanup(limit=args.limit)
    except Exception:
        parser.exit(2, "Cleanup is unavailable or not configured; retry after its lease expires.\n")
    print("Expired records removed:", removed)
    print("Cleanup failures:", module.cleanup_failures)
    if module.cleanup_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
