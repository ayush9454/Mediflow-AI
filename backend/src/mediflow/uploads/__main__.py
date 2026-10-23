"""Trusted bounded orphan cleanup; no client-accessible administrative route."""

import argparse

from mediflow.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100, choices=range(1, 101))
    args = parser.parse_args()
    module = app.state.uploads
    if module is None:
        raise SystemExit("Configure trusted Firestore and private Azure storage before cleanup.")
    print("Expired upload reservations removed:", module.cleanup(limit=args.limit))


if __name__ == "__main__":
    main()
